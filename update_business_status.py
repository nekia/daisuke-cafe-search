"""
Enterprise(+Atmosphere) で businessStatus ほかを更新する。

日次上限なし・月次ハードキャップ・1実行上限は update_business_status_only.py と同仕様。
月次カウンタ (scope=month) は update_opening_hours.py と共有。

環境変数（任意）:
  MONTHLY_ENTERPRISE_CALL_BUDGET  既定 1000
  ENTERPRISE_HARD_MONTHLY_CAP     既定 1000（これ以上は設定しても呼ばない）
  PER_RUN_MAX_CALLS               既定 50（CLI --per-run で上書き可）
  BUSINESS_STATUS_STALE_DAYS      既定 30
  ENTERPRISE_COOLDOWN_HOURS       既定 72
  ENTERPRISE_FAILURE_COOLDOWN_HOURS 既定 24
  ENTERPRISE_DRY_RUN=1            API を呼ばず候補だけ表示

例:
  python update_business_status.py --per-run 200
  python update_business_status.py -n 100 --dry-run
  python update_business_status.py --count-remaining
  python update_business_status.py --all-buckets --per-run 500
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
    compute_remaining_enterprise_budget,
    ensure_refresh_meta_base,
    get_bucket_count,
    get_next_bucket,
    get_env_int,
    increment_enterprise_usage,
    next_eligible_at,
    utc_now,
)

load_dotenv()

JOB_NAME = "business_status_refresh"

BASE_FIELD_MASK = ",".join(
    [
        "businessStatus",
        "currentOpeningHours",
        "displayName",
        "formattedAddress",
        "primaryType",
        "primaryTypeDisplayName",
        "generativeSummary",
        "reviewSummary",
    ]
)


def _localized_text(value):
    """Places API の文字列 or LocalizedText / 入れ子 text をフラットな str にする。"""
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        inner = value.get("text")
        if isinstance(inner, str):
            return inner.strip() or None
        if isinstance(inner, dict):
            nested = inner.get("text")
            if isinstance(nested, str):
                return nested.strip() or None
    return None


def build_searchable_texts(payload, record):
    values = [
        (record.get("location_name") or {}).get("text"),
        record.get("alias"),
        _localized_text(payload.get("displayName")),
        _localized_text(payload.get("primaryTypeDisplayName")),
        _localized_text(
            (payload.get("generativeSummary") or {}).get("description")
        ),
        _localized_text((payload.get("reviewSummary") or {}).get("text")),
        _localized_text(payload.get("reviewSummary")),
    ]
    unique = []
    for value in values:
        text = value.strip() if isinstance(value, str) else None
        if text and text not in unique:
            unique.append(text)
    return unique


def get_place_payload(place_id, api_key):
    extra_mask = os.getenv("PLACES_ENTERPRISE_EXTRA_FIELDS", "").strip()
    full_mask = BASE_FIELD_MASK if not extra_mask else f"{BASE_FIELD_MASK},{extra_mask}"
    url = f"https://places.googleapis.com/v1/places/{place_id}?languageCode=ja"

    def fetch(field_mask):
        headers = {
            "Content-Type": "application/json",
            "X-Goog-FieldMask": field_mask,
            "X-Goog-Api-Key": api_key,
        }
        max_retries = max(get_env_int("ENTERPRISE_RETRY_COUNT", 3), 1)
        backoff_sec = max(get_env_int("ENTERPRISE_BACKOFF_SECONDS", 2), 1)
        for attempt in range(max_retries):
            response = requests.get(url, headers=headers, timeout=30)
            if response.status_code == 200:
                return response.json(), None
            if response.status_code in (429, 500, 502, 503, 504):
                sleep_seconds = backoff_sec * (2**attempt)
                print(f"retrying {place_id} status={response.status_code} sleep={sleep_seconds}s")
                time.sleep(sleep_seconds)
                continue
            return None, response
        return None, response

    payload, error_response = fetch(full_mask)
    if payload:
        return payload

    if extra_mask and error_response is not None and error_response.status_code == 400:
        print(f"fallback field mask for {place_id} because extra fields failed")
        payload, _ = fetch(BASE_FIELD_MASK)
        return payload

    if error_response is not None:
        print(f"API error for {place_id}: status={error_response.status_code} body={error_response.text}")
    return None


def _eligibility_filters(now):
    return {
        "$or": [
            {"refreshMeta.nextEligibleAt": {"$lte": now}},
            {"refreshMeta.nextEligibleAt": {"$exists": False}},
        ]
    }


def _bucket_filter(run_bucket):
    if run_bucket is None:
        return None
    return {
        "$or": [
            {"refreshMeta.refreshBucket": run_bucket},
            {"refreshMeta.refreshBucket": {"$exists": False}},
        ]
    }


def _candidate_queries(now, stale_days, run_bucket=None):
    """更新候補クエリ。run_bucket=None なら全バケット対象。"""
    stale_threshold = now - timedelta(days=stale_days)
    parts = [_eligibility_filters(now)]
    bucket = _bucket_filter(run_bucket)
    if bucket is not None:
        parts.append(bucket)

    query_missing = {
        "$and": [
            *parts,
            {
                "$or": [
                    {"businessStatus": {"$exists": False}},
                    {"businessStatus": None},
                ]
            },
            {"id": {"$not": {"$regex": "^import-"}}},
        ]
    }
    query_stale = {
        "$and": [
            *parts,
            {"businessStatus": {"$ne": "CLOSED_PERMANENTLY"}},
            {
                "$or": [
                    {"refreshMeta.businessStatusSyncedAt": {"$exists": False}},
                    {"refreshMeta.businessStatusSyncedAt": {"$lt": stale_threshold}},
                ]
            },
            {"id": {"$not": {"$regex": "^import-"}}},
        ]
    }
    return query_missing, query_stale


def pick_candidates(collection, run_bucket, allowed_calls, stale_days):
    now = utc_now()
    query_missing, query_stale = _candidate_queries(now, stale_days, run_bucket=run_bucket)

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


def count_remaining_entries(stale_days=None):
    """更新すべき残件数を集計（API は呼ばない）。バケット進行も進めない。"""
    client = MongoClient(os.environ["MONGODB_ADDRESS"])
    db = client.places
    collection = db.place_info
    state_collection = db.refresh_state

    try:
        now = utc_now()
        stale_days = (
            stale_days
            if stale_days is not None
            else get_env_int("BUSINESS_STATUS_STALE_DAYS", 30)
        )
        bucket_count = get_bucket_count()
        state = state_collection.find_one({"jobName": JOB_NAME})
        last_bucket = state.get("lastBucket") if state else None
        next_bucket = 0 if last_bucket is None else (int(last_bucket) + 1) % bucket_count

        query_missing_all, query_stale_all = _candidate_queries(
            now, stale_days, run_bucket=None
        )
        missing_ids = set(collection.distinct("_id", query_missing_all))
        stale_ids = set(collection.distinct("_id", query_stale_all))
        remaining_ids = missing_ids | stale_ids

        query_missing_next, query_stale_next = _candidate_queries(
            now, stale_days, run_bucket=next_bucket
        )
        missing_next = set(collection.distinct("_id", query_missing_next))
        stale_next = set(collection.distinct("_id", query_stale_next))
        remaining_next = missing_next | stale_next

        stale_threshold = now - timedelta(days=stale_days)
        cooldown_blocked = collection.count_documents(
            {
                "$and": [
                    {"refreshMeta.nextEligibleAt": {"$gt": now}},
                    {"id": {"$not": {"$regex": "^import-"}}},
                    {
                        "$or": [
                            {"businessStatus": {"$exists": False}},
                            {"businessStatus": None},
                            {
                                "$and": [
                                    {"businessStatus": {"$ne": "CLOSED_PERMANENTLY"}},
                                    {
                                        "$or": [
                                            {
                                                "refreshMeta.businessStatusSyncedAt": {
                                                    "$exists": False
                                                }
                                            },
                                            {
                                                "refreshMeta.businessStatusSyncedAt": {
                                                    "$lt": stale_threshold
                                                }
                                            },
                                        ]
                                    },
                                ]
                            },
                        ]
                    },
                ]
            }
        )

        total_places = collection.count_documents(
            {"id": {"$not": {"$regex": "^import-"}}}
        )
        permanently_closed = collection.count_documents(
            {"businessStatus": "CLOSED_PERMANENTLY"}
        )
        with_snapshot = collection.count_documents(
            {"enterpriseData.latestSnapshot": {"$exists": True}}
        )

        print("=== Remaining update candidates (Enterprise+Atmosphere) ===")
        print(f"stale_days={stale_days}")
        print(
            f"bucket_count={bucket_count} last_bucket={last_bucket} "
            f"next_bucket={next_bucket}"
        )
        print(f"total places (excl. import stubs): {total_places}")
        print(f"CLOSED_PERMANENTLY: {permanently_closed}")
        print(f"enterpriseData.latestSnapshot exists: {with_snapshot}")
        print("---")
        print(f"remaining (all buckets, eligible now): {len(remaining_ids)}")
        print(f"  - missing businessStatus: {len(missing_ids)}")
        print(f"  - stale (incl. overlap with missing): {len(stale_ids)}")
        print(f"  - unique remaining: {len(remaining_ids)}")
        print(f"remaining in next bucket ({next_bucket}): {len(remaining_next)}")
        print(
            f"cooldown-blocked (would be candidates after cooldown): {cooldown_blocked}"
        )
        print("---")
        print(
            "残件数の定義: クールダウン明けかつ "
            "(businessStatus 欠落) または "
            "(永久閉業以外で businessStatusSyncedAt が無い／stale_days 超)"
        )
        return {
            "remaining_all": len(remaining_ids),
            "remaining_next_bucket": len(remaining_next),
            "missing": len(missing_ids),
            "stale": len(stale_ids),
            "cooldown_blocked": cooldown_blocked,
            "next_bucket": next_bucket,
        }
    finally:
        client.close()


def update_closed_business_status(per_run=None, dry_run=None, all_buckets=False):
    client = MongoClient(os.environ["MONGODB_ADDRESS"])
    db = client.places
    collection = db.place_info
    usage_collection = db.api_usage_counters
    state_collection = db.refresh_state
    api_key = os.environ["GOOGLE_MAPS_API_KEY"]
    if dry_run is None:
        dry_run = os.getenv("ENTERPRISE_DRY_RUN", "").strip() in ("1", "true", "True", "yes")

    closed_businesses = []

    try:
        now = utc_now()
        budget = compute_remaining_enterprise_budget(
            usage_collection, now, per_run_override=per_run
        )
        bucket_count = get_bucket_count()
        # 通常は1バケットだけ進める。--all-buckets では全候補を対象にし、回転状態は進めない。
        run_bucket = (
            None
            if all_buckets
            else get_next_bucket(state_collection, "business_status_refresh", bucket_count)
        )
        stale_days = get_env_int("BUSINESS_STATUS_STALE_DAYS", 30)
        cooldown_hours_ok = get_env_int("ENTERPRISE_COOLDOWN_HOURS", 72)
        cooldown_hours_fail = get_env_int("ENTERPRISE_FAILURE_COOLDOWN_HOURS", 24)

        print("=== Enterprise(+Atmosphere) budget ===")
        print(f"dry_run={dry_run}")
        print(
            f"month used={budget['monthly_used']} remaining={budget['monthly_remaining']} "
            f"(limit={budget['limits']['monthly']}, hard_cap={budget['limits'].get('hard_monthly_cap')})"
        )
        print("day limit=disabled")
        print(
            f"run allowance={budget['allowed_calls_this_run']} "
            f"(per_run={budget['limits']['per_run']})"
        )
        if all_buckets:
            print(f"run bucket=ALL (0-{bucket_count - 1})")
        else:
            print(f"run bucket={run_bucket}/{bucket_count - 1}")

        if budget["allowed_calls_this_run"] <= 0:
            print("No available Enterprise budget (free-tier safety). Exit without API calls.")
            return

        records_to_check = pick_candidates(
            collection, run_bucket, budget["allowed_calls_this_run"], stale_days
        )
        if not records_to_check:
            if all_buckets:
                print("No eligible records across all buckets.")
            else:
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
        failed_count = 0
        api_calls = 0
        max_calls = budget["allowed_calls_this_run"]

        for i, record in enumerate(records_to_check, 1):
            live_budget = compute_remaining_enterprise_budget(
                usage_collection, utc_now(), per_run_override=per_run
            )
            if live_budget["monthly_remaining"] <= 0 or api_calls >= max_calls:
                print("Enterprise budget exhausted mid-run. Stopping.")
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
            payload = get_place_payload(place_id, api_key)
            increment_enterprise_usage(usage_collection, now, 1)
            api_calls += 1

            if not payload:
                failed_count += 1
                collection.update_one(
                    {"_id": record["_id"]},
                    {
                        "$set": {
                            "refreshMeta.lastEnterpriseSyncAt": now,
                            "refreshMeta.lastEnterpriseStatus": "error",
                            "refreshMeta.nextEligibleAt": next_eligible_at(now, cooldown_hours_fail),
                        }
                    },
                )
                continue

            business_status = payload.get("businessStatus")
            searchable_texts = build_searchable_texts(payload, record)
            update_data = {
                "refreshMeta.lastEnterpriseSyncAt": now,
                "refreshMeta.businessStatusSyncedAt": now,
                "refreshMeta.lastEnterpriseStatus": "ok",
                "refreshMeta.nextEligibleAt": next_eligible_at(now, cooldown_hours_ok),
                "enterpriseData.latestSnapshot": payload,
                "enterpriseData.searchableTexts": searchable_texts,
            }
            if business_status:
                update_data["businessStatus"] = business_status

            result = collection.update_one({"_id": record["_id"]}, {"$set": update_data})
            if result.acknowledged:
                updated_count += 1
                print(f"[{i}/{len(records_to_check)}] updated: {location_name} ({business_status})")
            else:
                failed_count += 1

            if business_status == "CLOSED_PERMANENTLY":
                closed_count += 1
                closed_businesses.append(
                    {
                        "name": location_name,
                        "address": record.get("address", "住所情報なし"),
                        "alias": alias,
                        "place_id": place_id,
                    }
                )

            time.sleep(0.1)

        print("=" * 60)
        print("処理結果:")
        print(f"  対象件数: {len(records_to_check)}")
        print(f"  API呼び出し数: {api_calls}")
        print(f"  更新成功: {updated_count}")
        print(f"  閉業店舗: {closed_count}")
        print(f"  失敗: {failed_count}")
        print("=" * 60)

        if closed_businesses:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"closed_businesses_{timestamp}.json"
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
        description="Enterprise(+Atmosphere) で businessStatus 等を更新（無料枠安全装置付き）"
    )
    parser.add_argument(
        "--per-run",
        "-n",
        type=int,
        default=None,
        metavar="N",
        help="1実行あたりの最大 API 呼び出し数（既定: 環境変数 PER_RUN_MAX_CALLS または 50）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="API を呼ばず候補だけ表示",
    )
    parser.add_argument(
        "--count-remaining",
        action="store_true",
        help="更新すべき残件数を集計して終了（API・バケット進行なし）",
    )
    parser.add_argument(
        "--all-buckets",
        action="store_true",
        help="バケット分割を無視し、全バケットの更新候補を1実行で処理（月次枠・--per-run は有効）",
    )
    args = parser.parse_args()
    if args.per_run is not None and args.per_run < 0:
        parser.error("--per-run must be >= 0")

    if args.count_remaining:
        count_remaining_entries()
    else:
        print("business_status情報の更新を開始します...")
        update_closed_business_status(
            per_run=args.per_run,
            dry_run=True if args.dry_run else None,
            all_buckets=args.all_buckets,
        )
        print("処理が完了しました")
