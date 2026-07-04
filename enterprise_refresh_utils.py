import hashlib
import os
from datetime import datetime, timedelta, timezone


UTC = timezone.utc


def get_env_int(name, default):
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def utc_now():
    return datetime.now(UTC)


def get_month_key(dt):
    return dt.strftime("%Y-%m")


def get_day_key(dt):
    return dt.strftime("%Y-%m-%d")


def get_budget_limits():
    return {
        "monthly": get_env_int("MONTHLY_ENTERPRISE_CALL_BUDGET", 1000),
        "daily": get_env_int("DAILY_ENTERPRISE_CALL_BUDGET", 80),
        "per_run": get_env_int("PER_RUN_MAX_CALLS", 50),
    }


def get_bucket_count():
    return max(get_env_int("REFRESH_BUCKET_COUNT", 30), 1)


def bucket_for_place_id(place_id, bucket_count):
    source = (place_id or "").encode("utf-8")
    digest = hashlib.md5(source).hexdigest()
    return int(digest[:8], 16) % bucket_count


def ensure_refresh_meta_base(collection, record, now):
    refresh_meta = record.get("refreshMeta", {}) if isinstance(record, dict) else {}
    place_id = record.get("id") if isinstance(record, dict) else None
    updates = {}
    if "refreshBucket" not in refresh_meta:
        updates["refreshMeta.refreshBucket"] = bucket_for_place_id(place_id, get_bucket_count())
    if "nextEligibleAt" not in refresh_meta:
        updates["refreshMeta.nextEligibleAt"] = now
    if updates:
        collection.update_one({"_id": record["_id"]}, {"$set": updates})


def get_next_bucket(state_collection, job_name, bucket_count):
    state = state_collection.find_one({"jobName": job_name})
    previous = state.get("lastBucket", -1) if state else -1
    next_bucket = (previous + 1) % bucket_count
    state_collection.update_one(
        {"jobName": job_name},
        {
            "$set": {
                "jobName": job_name,
                "lastBucket": next_bucket,
                "updatedAt": utc_now(),
            }
        },
        upsert=True,
    )
    return next_bucket


def get_usage_count(usage_collection, scope, key):
    doc = usage_collection.find_one({"scope": scope, "key": key})
    if not doc:
        return 0
    return int(doc.get("calls", 0))


def increment_usage(usage_collection, scope, key, amount=1):
    usage_collection.update_one(
        {"scope": scope, "key": key},
        {
            "$inc": {"calls": amount},
            "$set": {"updatedAt": utc_now()},
            "$setOnInsert": {"createdAt": utc_now()},
        },
        upsert=True,
    )


def compute_remaining_budget(usage_collection, now):
    limits = get_budget_limits()
    monthly_used = get_usage_count(usage_collection, "month", get_month_key(now))
    daily_used = get_usage_count(usage_collection, "day", get_day_key(now))
    monthly_remaining = max(limits["monthly"] - monthly_used, 0)
    daily_remaining = max(limits["daily"] - daily_used, 0)
    allowed = min(monthly_remaining, daily_remaining, limits["per_run"])
    return {
        "limits": limits,
        "monthly_used": monthly_used,
        "daily_used": daily_used,
        "monthly_remaining": monthly_remaining,
        "daily_remaining": daily_remaining,
        "allowed_calls_this_run": allowed,
    }


def mark_refresh_result(collection, record_id, result_fields):
    collection.update_one({"_id": record_id}, {"$set": result_fields})


def next_eligible_at(now, cooldown_hours):
    return now + timedelta(hours=max(cooldown_hours, 1))
