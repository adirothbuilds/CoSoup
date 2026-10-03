from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from croniter import croniter
import pandas as pd

from stock_scanner.calendar import calendar, next_run

from ...errors import ServiceError


def _validate(trigger, settings):
    kind = trigger.get("type")
    if kind == "local_cron":
        ZoneInfo(trigger.get("timezone") or settings.timezone)
        if not croniter.is_valid(trigger.get("expression", "")) or len(trigger["expression"].split()) != 5:
            raise ServiceError("invalid_schedule", "A valid five-field cron expression is required", 422)
    elif kind == "once":
        at = datetime.fromisoformat(trigger["at"])
        if at.tzinfo is None:
            raise ServiceError("invalid_schedule", "One-shot timestamp requires a timezone", 422)
    elif kind == "market_close":
        if trigger.get("frequency", "daily") not in {"daily", "weekly"}:
            raise ServiceError("invalid_schedule", "Market frequency must be daily or weekly", 422)
    else:
        raise ServiceError("invalid_schedule", "Unsupported trigger type", 422)


def validate(trigger, settings):
    try:
        _validate(trigger, settings)
    except ServiceError:
        raise
    except (ValueError, KeyError, TypeError, OverflowError):
        raise ServiceError("invalid_schedule", "Trigger fields, timezone or timestamp are invalid", 422) from None


def next_occurrence(trigger, after, settings):
    validate(trigger, settings)
    after = after.astimezone(timezone.utc)
    skipped = []
    if trigger["type"] == "once":
        at = datetime.fromisoformat(trigger["at"]).astimezone(timezone.utc)
        return (at if at > after else None), skipped
    if trigger["type"] == "market_close":
        candidate = after
        for _ in range(10):
            next_ = next_run(candidate, settings.settlement_minutes)
            at = datetime.fromisoformat(next_["run_at_utc"])
            session = pd.Timestamp(next_["session"])
            following = calendar().next_session(session)
            if trigger.get("frequency", "daily") == "daily" or following.date().isocalendar()[:2] != session.date().isocalendar()[:2]:
                return at, skipped
            candidate = at
        raise ServiceError("invalid_schedule", "No eligible market occurrence found")
    zone = ZoneInfo(trigger.get("timezone") or settings.timezone)
    naive = after.astimezone(zone).replace(tzinfo=None)
    it = croniter(trigger["expression"], naive)
    for _ in range(400):
        wall = it.get_next(datetime)
        local = wall.replace(tzinfo=zone, fold=0)
        at = local.astimezone(timezone.utc)
        if at.astimezone(zone).replace(tzinfo=None) != wall:
            skipped.append(wall.isoformat())
            continue
        # fold=0 deliberately selects only the first occurrence of repeated wall time.
        if at > after:
            return at, skipped
    raise ServiceError("invalid_schedule", "No valid occurrence found within search limit")
