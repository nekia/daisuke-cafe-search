import os
import time
from datetime import timedelta

import requests
from dotenv import load_dotenv
from pymongo import MongoClient

from enterprise_refresh_utils import (
    compute_remaining_budget,
    ensure_refresh_meta_base,
    get_bucket_count,
    get_day_key,
    get_month_key,
    get_next_bucket,
    get_env_int,
    increment_usage,
    next_eligible_at,
    utc_now,
)

load_dotenv()

BASE_FIELD_MASK = ",".join(
    [
        "currentOpeningHours",
        "businessStatus",
        "displayName",
        "formattedAddress",
        "primaryType",
        "primaryTypeDisplayName",
        "generativeSummary",
        "reviewSummary",
    ]
)


def build_searchable_texts(payload, record):
    values = [
        (record.get("location_name") or {}).get("text"),
        record.get("alias"),
        record.get("address"),
        record.get("formattedAddress"),
        (record.get("primary_type") or {}).get("text"),
        record.get("primary_type_api"),
        payload.get("displayName", {}).get("text"),
        payload.get("formattedAddress"),
        payload.get("primaryTypeDisplayName", {}).get("text"),
        payload.get("primaryType"),
        payload.get("generativeSummary", {}).get("description", {}).get("text"),
        payload.get("reviewSummary", {}).get("text"),
    ]
    unique = []
    for value in values:
        if isinstance(value, str):
            text = value.strip()
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
                    {"openingHours": {"$exists": False}},
                    {"openingHours": None},
                ]
            },
            {
                "$or": [
                    {"openingHoursStatus": {"$exists": False}},
                    {"openingHoursStatus": {"$ne": "営業時間不明店舗"}},
                ]
            },
        ]
    }
    query_stale = {
        "$and": [
            common_eligibility,
            bucket_filter,
            {"businessStatus": {"$ne": "CLOSED_PERMANENTLY"}},
            {
                "$or": [
                    {"refreshMeta.openingHoursSyncedAt": {"$exists": False}},
                    {"refreshMeta.openingHoursSyncedAt": {"$lt": stale_threshold}},
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


def update_opening_hours_for_missing_records():
    client = MongoClient(os.environ["MONGODB_ADDRESS"])
    db = client.places
    collection = db.place_info
    usage_collection = db.api_usage_counters
    state_collection = db.refresh_state
    api_key = os.environ["GOOGLE_MAPS_API_KEY"]

    try:
        now = utc_now()
        budget = compute_remaining_budget(usage_collection, now)
        bucket_count = get_bucket_count()
        run_bucket = get_next_bucket(state_collection, "opening_hours_refresh", bucket_count)
        stale_days = get_env_int("OPENING_HOURS_STALE_DAYS", 14)
        cooldown_hours_ok = get_env_int("ENTERPRISE_COOLDOWN_HOURS", 72)
        cooldown_hours_fail = get_env_int("ENTERPRISE_FAILURE_COOLDOWN_HOURS", 24)

        print("=== Budget status ===")
        print(
            f"month used={budget['monthly_used']} remaining={budget['monthly_remaining']} "
            f"(limit={budget['limits']['monthly']})"
        )
        print(
            f"day used={budget['daily_used']} remaining={budget['daily_remaining']} "
            f"(limit={budget['limits']['daily']})"
        )
        print(f"run allowance={budget['allowed_calls_this_run']}")
        print(f"run bucket={run_bucket}/{bucket_count - 1}")

        if budget["allowed_calls_this_run"] <= 0:
            print("No available budget. Exit without API calls.")
            return

        records_to_check = pick_candidates(collection, run_bucket, budget["allowed_calls_this_run"], stale_days)
        if not records_to_check:
            print("No eligible records for this bucket.")
            return

        updated_count = 0
        failed_count = 0
        api_calls = 0

        for i, record in enumerate(records_to_check, 1):
            place_id = record.get("id")
            location_name = record.get("location_name", {}).get("text", "N/A")
            alias = record.get("alias", "N/A")
            print(f"[{i}/{len(records_to_check)}] processing: {location_name} (alias: {alias})")

            if not place_id:
                failed_count += 1
                print(f"missing place_id: {location_name}")
                continue

            if str(place_id).startswith("import-"):
                print(f"skip import stub: {location_name}")
                continue

            ensure_refresh_meta_base(collection, record, now)
            payload = get_place_payload(place_id, api_key)
            increment_usage(usage_collection, "month", get_month_key(now), 1)
            increment_usage(usage_collection, "day", get_day_key(now), 1)
            api_calls += 1

            if not payload:
                failed_count += 1
                collection.update_one(
                    {"_id": record["_id"]},
                    {
                        "$set": {
                            "openingHoursStatus": "api_error",
                            "refreshMeta.lastEnterpriseSyncAt": now,
                            "refreshMeta.lastEnterpriseStatus": "error",
                            "refreshMeta.nextEligibleAt": next_eligible_at(now, cooldown_hours_fail),
                        }
                    },
                )
                continue

            opening_hours = payload.get("currentOpeningHours")
            searchable_texts = build_searchable_texts(payload, record)

            update_data = {
                "refreshMeta.lastEnterpriseSyncAt": now,
                "refreshMeta.openingHoursSyncedAt": now,
                "refreshMeta.lastEnterpriseStatus": "ok",
                "refreshMeta.nextEligibleAt": next_eligible_at(now, cooldown_hours_ok),
                "enterpriseData.latestSnapshot": payload,
                "enterpriseData.searchableTexts": searchable_texts,
            }
            if opening_hours:
                update_data["openingHours"] = opening_hours
                update_data["openingHoursStatus"] = "available"
            else:
                update_data["openingHours"] = None
                update_data["openingHoursStatus"] = "営業時間不明店舗"

            if payload.get("businessStatus"):
                update_data["businessStatus"] = payload.get("businessStatus")

            result = collection.update_one({"_id": record["_id"]}, {"$set": update_data})
            if result.acknowledged:
                updated_count += 1
            else:
                failed_count += 1

            time.sleep(0.1)

        print("=" * 60)
        print("処理結果:")
        print(f"  対象件数: {len(records_to_check)}")
        print(f"  API呼び出し数: {api_calls}")
        print(f"  更新成功: {updated_count}")
        print(f"  更新失敗: {failed_count}")
        print("=" * 60)

    except Exception as e:
        print(f"processing failed: {str(e)}")
    finally:
        client.close()


if __name__ == "__main__":
    print("営業時間情報の更新を開始します...")
    update_opening_hours_for_missing_records()
    print("処理が完了しました")