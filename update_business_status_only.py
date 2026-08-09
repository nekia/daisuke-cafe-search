"""
businessStatus のみを Place Details (Pro) で更新する。

Field mask は businessStatus のみ → Place Details Pro SKU。
Enterprise 更新ジョブとは別の利用カウンタ・予算で、無料枠超過を防ぐ。

環境変数（任意）:
  MONTHLY_PRO_CALL_BUDGET   既定 4500（無料枠 ~5000 未満）
  PRO_PER_RUN_MAX_CALLS     既定 50（CLI --per-run で上書き可）
  PRO_HARD_MONTHLY_CAP      既定 5000（これ以上は設定しても呼ばない）
  BUSINESS_STATUS_STALE_DAYS 既定 30
  PRO_COOLDOWN_HOURS        既定 72
  PRO_FAILURE_COOLDOWN_HOURS 既定 24
  PRO_DRY_RUN=1             API を呼ばず候補だけ表示

例:
  python update_business_status_only.py --per-run 200
  python update_business_status_only.py -n 100 --dry-run
"""

import argparse
import json
import os
import time
from datetime import timedelta

import requests
from dotenv import load_dotenv
from pymongo import MongoClient

from enterprise_refresh_utils import (
    compute_remaining_pro_budget,
    ensure_refresh_meta_base,
    get_bucket_count,
    get_next_bucket,
    get_env_int,
    increment_pro_usage,
    next_eligible_at,
    utc_now,
)

load_dotenv()

# Pro SKU。他フィールドを混ぜないこと（Enterprise 課金になる）
FIELD_MASK = "businessStatus"
JOB_NAME = "business_status_only_refresh"
CLOSED_STATUSES = frozenset({"CLOSED_PERMANENTLY", "CLOSED_TEMPORARILY"})


def is_obsolete_place_id_error(error_response):
    """Place ID が無効・廃止されたときの 404 / NOT_FOUND。"""
    if error_response is None:
        return False
    if error_response.status_code != 404:
        return False
    body = (error_response.text or "").lower()
    return (
        "no longer valid" in body
        or "not found" in body
        or "not_found" in body
        or "place id" in body
    )


def get_business_status(place_id, api_key):
    url = f"https://places.googleapis.com/v1/places/{place_id}?languageCode=ja"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-FieldMask": FIELD_MASK,
        "X-Goog-Api-Key": api_key,
    }
    max_retries = max(get_env_int("PRO_RETRY_COUNT", 3), 1)
    backoff_sec = max(get_env_int("PRO_BACKOFF_SECONDS", 2), 1)
    last_response = None
    for attempt in range(max_retries):
        response = requests.get(url, headers=headers, timeout=30)
        last_response = response
        if response.status_code == 200:
            return response.json(), None
        if response.status_code in (429, 500, 502, 503, 504):
            sleep_seconds = backoff_sec * (2**attempt)
            print(f"retrying {place_id} status={response.status_code} sleep={sleep_seconds}s")
            time.sleep(sleep_seconds)
            continue
        return None, response
    return None, last_response


def pick_candidates(collection, run_bucket, allowed_calls, stale_days):
    now = utc_now()
    stale_threshold = now - timedelta(days=stale_days)
    common_eligibility = {
        "$or": [
            {"refreshMeta.nextEligibleAt": {"$lte": now}},
            {"refreshMeta.nextEligibleAt": {"$exists": False}},
        ]
    }
    bucket_filter = {
        "$or": [
            {"refreshMeta.refreshBucket": run_bucket},
            {"refreshMeta.refreshBucket": {"$exists": False}},
        ]
    }

    query_missing = {
        "$and": [
            common_eligibility,
            bucket_filter,
            {
                "$or": [
                    {"businessStatus": {"$exists": False}},
                    {"businessStatus": None},
                    {"businessStatus": ""},
                ]
            },
        ]
    }
    query_stale = {
        "$and": [
            common_eligibility,
            bucket_filter,
            {"businessStatus": {"$ne": "CLOSED_PERMANENTLY"}},
            {"refreshMeta.placeIdInvalid": {"$ne": True}},
            {
                "$or": [
                    {"refreshMeta.businessStatusSyncedAt": {"$exists": False}},
                    {"refreshMeta.businessStatusSyncedAt": {"$lt": stale_threshold}},
                ]
            },
        ]
    }

    picked = []
    seen = set()
    for query in (query_missing, query_stale):
        for record in collection.find(query).limit(max(allowed_calls * 5, 20)):
            record_id = str(record.get("_id"))
            if record_id in seen:
                continue
            seen.add(record_id)
            picked.append(record)
            if len(picked) >= allowed_calls:
                return picked
    return picked


def update_business_status_only(per_run=None, dry_run=None):
    client = MongoClient(os.environ["MONGODB_ADDRESS"])
    db = client.places
    collection = db.place_info
    usage_collection = db.api_usage_counters
    state_collection = db.refresh_state
    api_key = os.environ["GOOGLE_MAPS_API_KEY"]
    if dry_run is None:
        dry_run = os.getenv("PRO_DRY_RUN", "").strip() in ("1", "true", "True", "yes")

    closed_businesses = []

    try:
        now = utc_now()
        budget = compute_remaining_pro_budget(usage_collection, now, per_run_override=per_run)
        bucket_count = get_bucket_count()
        run_bucket = get_next_bucket(state_collection, JOB_NAME, bucket_count)
        stale_days = get_env_int("BUSINESS_STATUS_STALE_DAYS", 30)
        cooldown_hours_ok = get_env_int("PRO_COOLDOWN_HOURS", 72)
        cooldown_hours_fail = get_env_int("PRO_FAILURE_COOLDOWN_HOURS", 24)

        print("=== Pro budget (businessStatus only) ===")
        print(f"field_mask={FIELD_MASK} dry_run={dry_run}")
        print(
            f"month used={budget['monthly_used']} remaining={budget['monthly_remaining']} "
            f"(limit={budget['limits']['monthly']}, hard_cap={budget['limits'].get('hard_monthly_cap')})"
        )
        print("day limit=disabled")
        print(f"run allowance={budget['allowed_calls_this_run']} (per_run={budget['limits']['per_run']})")
        print(f"run bucket={run_bucket}/{bucket_count - 1}")

        if budget["allowed_calls_this_run"] <= 0:
            print("No available Pro budget (free-tier safety). Exit without API calls.")
            return

        records_to_check = pick_candidates(
            collection, run_bucket, budget["allowed_calls_this_run"], stale_days
        )
        if not records_to_check:
            print("No eligible records for this bucket.")
            return

        if dry_run:
            print(f"DRY RUN: would check {len(records_to_check)} places")
            for record in records_to_check[:20]:
                name = (record.get("location_name") or {}).get("text", "N/A")
                print(f"  - {name} ({record.get('id')}) status={record.get('businessStatus')}")
            if len(records_to_check) > 20:
                print(f"  ... and {len(records_to_check) - 20} more")
            return

        updated_count = 0
        closed_count = 0
        obsolete_count = 0
        failed_count = 0
        api_calls = 0
        max_calls = budget["allowed_calls_this_run"]
        # 無効 Place ID は再問い合わせ不要（事実上スキップ）
        obsolete_cooldown_hours = get_env_int("PRO_OBSOLETE_COOLDOWN_HOURS", 24 * 365 * 10)

        for i, record in enumerate(records_to_check, 1):
            # 実行中に予算を再評価（並行実行や設定ミス対策）
            live_budget = compute_remaining_pro_budget(
                usage_collection, utc_now(), per_run_override=per_run
            )
            if live_budget["monthly_remaining"] <= 0 or api_calls >= max_calls:
                print("Pro budget exhausted mid-run. Stopping.")
                break

            place_id = record.get("id")
            location_name = record.get("location_name", {}).get("text", "N/A")
            alias = record.get("alias", "N/A")

            if not place_id:
                print(f"missing place_id: {location_name}")
                failed_count += 1
                continue

            if str(place_id).startswith("import-"):
                print(f"skip import stub: {location_name}")
                continue

            ensure_refresh_meta_base(collection, record, now)
            payload, error_response = get_business_status(place_id, api_key)
            increment_pro_usage(usage_collection, now, 1)
            api_calls += 1

            if not payload:
                if is_obsolete_place_id_error(error_response):
                    # 無効 ID は閉業扱いにし、通常表示から除外（閉業のみでは表示）
                    business_status = "CLOSED_PERMANENTLY"
                    update_data = {
                        "businessStatus": business_status,
                        "refreshMeta.lastProStatusSyncAt": now,
                        "refreshMeta.businessStatusSyncedAt": now,
                        "refreshMeta.lastProStatus": "not_found",
                        "refreshMeta.placeIdInvalid": True,
                        "refreshMeta.placeIdInvalidAt": now,
                        "refreshMeta.nextEligibleAt": next_eligible_at(now, obsolete_cooldown_hours),
                    }
                    result = collection.update_one({"_id": record["_id"]}, {"$set": update_data})
                    if result.acknowledged:
                        updated_count += 1
                        obsolete_count += 1
                        closed_count += 1
                        print(
                            f"[{i}/{len(records_to_check)}] obsolete Place ID → "
                            f"CLOSED_PERMANENTLY: {location_name}"
                        )
                        closed_businesses.append(
                            {
                                "name": location_name,
                                "address": record.get("address")
                                or record.get("formattedAddress", "住所情報なし"),
                                "alias": alias,
                                "place_id": place_id,
                                "businessStatus": business_status,
                                "reason": "place_id_invalid",
                            }
                        )
                    else:
                        failed_count += 1
                    time.sleep(0.1)
                    continue

                failed_count += 1
                if error_response is not None:
                    print(
                        f"API error for {place_id}: "
                        f"status={error_response.status_code} body={error_response.text[:200]}"
                    )
                collection.update_one(
                    {"_id": record["_id"]},
                    {
                        "$set": {
                            "refreshMeta.lastProStatusSyncAt": now,
                            "refreshMeta.lastProStatus": "error",
                            "refreshMeta.nextEligibleAt": next_eligible_at(now, cooldown_hours_fail),
                        }
                    },
                )
                continue

            business_status = payload.get("businessStatus")
            update_data = {
                "refreshMeta.lastProStatusSyncAt": now,
                "refreshMeta.businessStatusSyncedAt": now,
                "refreshMeta.lastProStatus": "ok",
                "refreshMeta.placeIdInvalid": False,
                "refreshMeta.nextEligibleAt": next_eligible_at(now, cooldown_hours_ok),
            }
            if business_status:
                update_data["businessStatus"] = business_status

            result = collection.update_one({"_id": record["_id"]}, {"$set": update_data})
            if result.acknowledged:
                updated_count += 1
                print(f"[{i}/{len(records_to_check)}] updated: {location_name} ({business_status})")
            else:
                failed_count += 1

            if business_status in CLOSED_STATUSES:
                closed_count += 1
                closed_businesses.append(
                    {
                        "name": location_name,
                        "address": record.get("address") or record.get("formattedAddress", "住所情報なし"),
                        "alias": alias,
                        "place_id": place_id,
                        "businessStatus": business_status,
                    }
                )

            time.sleep(0.1)

        print("=" * 60)
        print("処理結果:")
        print(f"  対象件数: {len(records_to_check)}")
        print(f"  API呼び出し数: {api_calls}")
        print(f"  更新成功: {updated_count}")
        print(f"  閉業/臨時休業: {closed_count} (うち Place ID 無効: {obsolete_count})")
        print(f"  失敗: {failed_count}")
        print("=" * 60)

        if closed_businesses:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"closed_businesses_pro_{timestamp}.json"
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(closed_businesses, f, ensure_ascii=False, indent=2)
            print(f"closed list saved: {filename}")

    except Exception as e:
        print(f"processing failed: {str(e)}")
        raise
    finally:
        client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="businessStatus のみを Place Details Pro で更新（無料枠安全装置付き）"
    )
    parser.add_argument(
        "--per-run",
        "-n",
        type=int,
        default=None,
        metavar="N",
        help="1実行あたりの最大 API 呼び出し数（既定: 環境変数 PRO_PER_RUN_MAX_CALLS または 50）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="API を呼ばず候補だけ表示",
    )
    args = parser.parse_args()
    if args.per_run is not None and args.per_run < 0:
        parser.error("--per-run must be >= 0")

    print("businessStatus のみの更新を開始します...")
    update_business_status_only(per_run=args.per_run, dry_run=True if args.dry_run else None)
    print("処理が完了しました")
