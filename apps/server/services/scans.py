from datetime import date, datetime, timezone

import pandas as pd
from sqlalchemy import select

from stock_scanner.calendar import calendar, expected_session, sessions_ending
from stock_scanner.rules import Rules

from ..errors import ServiceError
from ..persistence.models import Artifact, Rule
from .jobs import owned


def plan(db, storage, settings, owner, request):
    rule = owned(db, Rule, request["rules_id"], owner) if request.get("rules_id") else None
    rules = Rules(**rule.values) if rule else Rules(settlement_minutes=settings.settlement_minutes)
    latest = expected_session(settlement_minutes=rules.settlement_minutes)
    start, end = request.get("start_date") or latest, request.get("end_date") or latest
    if start > end or end > latest:
        raise ServiceError("invalid_date_range", "Range must end on or before the latest eligible completed session", 422)
    cal = calendar()
    try:
        requested = [x.date().isoformat() for x in cal.sessions_in_range(start, end)]
    except (ValueError, KeyError):
        raise ServiceError("calendar_range", "Requested dates are outside the supported exchange calendar", 422) from None
    if not requested or len(requested) > settings.limits.max_range_sessions:
        raise ServiceError("range_limit", "No sessions or range exceeds configured maximum", 422)
    mode = request.get("mode", "live")
    if mode == "live" and requested != [latest]:
        raise ServiceError("live_date", "Live scans must target only the latest eligible session", 422)
    required = set()
    for session in requested:
        required.update(sessions_ending(session, rules.history_sessions))
    archived = {r.metadata_.get("session"): r.id for r in db.scalars(select(Artifact).where(Artifact.owner_id == owner, Artifact.dataset == "grouped", Artifact.archive_id.is_not(None)))}
    hot, cold, missing = [], [], []
    for d in sorted(required):
        if storage.path("market/raw/grouped/"+d+".json.gz").is_file():
            hot.append(d)
        elif d in archived:
            cold.append({"session": d, "artifact_id": archived[d]})
        else:
            missing.append(d)
    dates = [x.date().isoformat() for x in pd.date_range(start, end)]
    return {"sessions": requested, "skipped_nontrading_dates": sorted(set(dates)-set(requested)),
            "warmup_start": min(required), "required_sessions": sorted(required), "hot_sessions": hot,
            "cold_sessions": cold, "missing_sessions": missing, "rules": rules.__dict__, "mode": mode,
            "estimated_minimum_grouped_requests": len(missing),
            "estimate_note": "Dated listing/split pagination and research add requests; older history entitlement is not guaranteed"}
