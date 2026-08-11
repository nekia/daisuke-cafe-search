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
    """opening_hours 等向け（日次上限あり）。"""
    return {
        "monthly": get_env_int("MONTHLY_ENTERPRISE_CALL_BUDGET", 1000),
        "daily": get_env_int("DAILY_ENTERPRISE_CALL_BUDGET", 80),
        "per_run": get_env_int("PER_RUN_MAX_CALLS", 50),
    }


def get_enterprise_budget_limits():
    """Enterprise(+Atmosphere) 向け。無料枠(約1000/月)を超えないようハードキャップ付き。

    日次上限は設けない（月次・ハードキャップ・1実行上限のみ）。Pro 版と同仕様。
    """
    hard_cap = max(get_env_int("ENTERPRISE_HARD_MONTHLY_CAP", 1000), 0)
    monthly = get_env_int("MONTHLY_ENTERPRISE_CALL_BUDGET", 1000)
    if hard_cap > 0:
        monthly = min(monthly, hard_cap)
    return {
        "monthly": monthly,
        "per_run": get_env_int("PER_RUN_MAX_CALLS", 50),
        "hard_monthly_cap": hard_cap,
    }


def get_pro_budget_limits():
    """Place Details Pro 向け。無料枠(約5000/月)を超えないよう既定は余裕を持たせる。

    日次上限は設けない（月次・ハードキャップ・1実行上限のみ）。
    """
    hard_cap = max(get_env_int("PRO_HARD_MONTHLY_CAP", 5000), 0)
    monthly = get_env_int("MONTHLY_PRO_CALL_BUDGET", 4500)
    if hard_cap > 0:
        monthly = min(monthly, hard_cap)
    return {
        "monthly": monthly,
        "per_run": get_env_int("PRO_PER_RUN_MAX_CALLS", 50),
        "hard_monthly_cap": hard_cap,
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
    """日次上限あり（update_opening_hours.py 向け）。"""
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


def compute_remaining_enterprise_budget(usage_collection, now, per_run_override=None):
    """Enterprise(+Atmosphere) 無料枠超過防止。日次制限なし（Pro 版と同仕様）。

    月次カウンタ scope=month は opening_hours と共有。
    per_run_override: 1実行あたり上限を上書き（CLI --per-run 用）。
    """
    limits = get_enterprise_budget_limits()
    if per_run_override is not None:
        limits = {**limits, "per_run": max(int(per_run_override), 0)}
    monthly_used = get_usage_count(usage_collection, "month", get_month_key(now))
    hard_cap = limits.get("hard_monthly_cap") or 0
    effective_monthly_limit = limits["monthly"]
    if hard_cap > 0:
        effective_monthly_limit = min(effective_monthly_limit, hard_cap)
        monthly_remaining = max(effective_monthly_limit - monthly_used, 0)
    else:
        monthly_remaining = max(effective_monthly_limit - monthly_used, 0)
    allowed = min(monthly_remaining, limits["per_run"])
    return {
        "limits": {**limits, "monthly": effective_monthly_limit},
        "monthly_used": monthly_used,
        "monthly_remaining": monthly_remaining,
        "allowed_calls_this_run": allowed,
    }


def increment_enterprise_usage(usage_collection, now, amount=1):
    increment_usage(usage_collection, "month", get_month_key(now), amount)


def compute_remaining_pro_budget(usage_collection, now, per_run_override=None):
    """Enterprise と別カウンタで Pro SKU の無料枠超過を防ぐ。日次制限なし。

    per_run_override: 1実行あたり上限を上書き（CLI --per-run 用）。None なら環境変数既定。
    """
    limits = get_pro_budget_limits()
    if per_run_override is not None:
        limits = {**limits, "per_run": max(int(per_run_override), 0)}
    monthly_used = get_usage_count(usage_collection, "pro_month", get_month_key(now))
    hard_cap = limits.get("hard_monthly_cap") or 0
    effective_monthly_limit = limits["monthly"]
    if hard_cap > 0:
        # 設定ミスでも無料枠ハードキャップを超えない
        effective_monthly_limit = min(effective_monthly_limit, hard_cap)
        monthly_remaining = max(effective_monthly_limit - monthly_used, 0)
    else:
        monthly_remaining = max(effective_monthly_limit - monthly_used, 0)
    allowed = min(monthly_remaining, limits["per_run"])
    return {
        "limits": {**limits, "monthly": effective_monthly_limit},
        "monthly_used": monthly_used,
        "monthly_remaining": monthly_remaining,
        "allowed_calls_this_run": allowed,
    }


def increment_pro_usage(usage_collection, now, amount=1):
    increment_usage(usage_collection, "pro_month", get_month_key(now), amount)


def mark_refresh_result(collection, record_id, result_fields):
    collection.update_one({"_id": record_id}, {"$set": result_fields})


def next_eligible_at(now, cooldown_hours):
    return now + timedelta(hours=max(cooldown_hours, 1))
