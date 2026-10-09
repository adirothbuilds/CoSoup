from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import select

from stock_scanner.calendar import calendar, expected_session, sessions_ending
from stock_scanner.market import load_market
from stock_scanner.signals import observations
from stock_scanner.storage import atomic_json, read_json

from ..errors import ServiceError
from ..persistence.models import Job, Report, Signal
from .jobs import owned


def published(context, mode):
    with context.database.session() as db:
        row = db.scalar(select(Report).where(Report.owner_id == context.job.owner_id,
                       Report.job_id == context.job.id, Report.mode == mode))
        return {"report_id": row.id, "quality": row.quality} if row else None


def publish(context, data_date, mode, result, markdown):
    existing = published(context, mode)
    if existing:
        return existing
    storage, job = context.storage, context.job
    directory = storage.path(f"reports/{job.owner_id}/{job.id}-{job.lease_token}")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    atomic_json(directory/"report.json", result)
    (directory/"report.md").write_text(markdown)
    (directory/"report.md").chmod(0o600)
    with context.database.session() as db:
        artifact = storage.register(db, job.owner_id, directory/"report.json", "reports", {"session": data_date})
        md = storage.register(db, job.owner_id, directory/"report.md", "reports", {"session": data_date})
        row = Report(owner_id=job.owner_id, job_id=job.id, data_date=data_date, mode=mode,
                     quality=result["status"], artifact_id=artifact.id, markdown_id=md.id,
                     summary={k: v for k, v in result.items() if k not in {"signals", "positions", "companies", "managers", "charts", "portfolio_proposals", "markdown"}})
        db.add(row)
        db.flush()
        return {"report_id": row.id, "quality": row.quality}


def weekly(context):
    mode = context.job.payload.get("mode", "live")
    existing = published(context, "weekly_"+mode)
    if existing:
        return existing
    end = context.job.payload.get("end_date") or expected_session(settlement_minutes=context.settings.settlement_minutes)
    latest = expected_session(settlement_minutes=context.settings.settlement_minutes)
    if end > latest or not calendar().is_session(end):
        raise ServiceError("invalid_date", "Weekly summary needs an eligible completed market session", 422)
    monday = (date.fromisoformat(end)-timedelta(days=date.fromisoformat(end).weekday())).isoformat()
    expected = [x.date().isoformat() for x in calendar().sessions_in_range(monday, end)]
    with context.database.session() as db:
        rows = list(db.scalars(select(Report).join(Job, Job.id == Report.job_id).where(
            Report.owner_id == context.job.owner_id, Report.mode == mode, Report.data_date >= monday,
            Report.data_date <= end).order_by(Job.created_at.desc())))
        by_date = {}
        for row in rows:
            by_date.setdefault(row.data_date, row)
        if end not in by_date or by_date[end].quality.startswith("blocked"):
            raise ServiceError("missing_daily", "No usable daily report exists for the requested final session")
        signals = list(db.scalars(select(Signal).where(Signal.owner_id == context.job.owner_id,
                           Signal.mode == mode, Signal.data_date <= end,
                           Signal.data_date >= (date.fromisoformat(end)-timedelta(days=90)).isoformat())))
    context.checkpoint(stage="following_signals", count=len(signals))
    sessions = sessions_ending(end)
    symbols = sorted({s.symbol for s in signals})
    try:
        if symbols:
            snapshots = read_json(context.storage.path(f"market/raw/splits/{sessions[0]}_{end}.json.gz"))
            matrix, errors, _, events = load_market(context.storage.path("market"), sessions, symbols, snapshots)
            followed = observations([{"symbol": s.symbol, "signal_date": s.data_date, "rules_id": s.rules_hash,
                                      "original": s.payload} for s in signals], matrix, symbols, sessions, events, errors)
        else:
            followed = []
    except (OSError, ValueError) as e:
        raise ServiceError("restore_required", "Weekly input snapshots are missing or archived; restore before resuming") from None
    missing = sorted(set(expected)-set(by_date))
    partial = missing or any(r.quality != "complete" for r in by_date.values()) or any(s["monitor_status"] == "unavailable" for s in followed)
    result = {"status": "partial_coverage" if partial else "complete", "data_date": end, "week_start": monday,
              "mode": mode, "daily_report_ids": [r.id for r in by_date.values()], "missing_daily_sessions": missing,
              "signals": followed, "observation_note": "Observed split-adjusted price changes, not trading returns"}
    markdown = f"# Weekly research: {monday} to {end}\n\nMode: {mode}. Quality: {result['status']}.\n\nMissing daily sessions: {', '.join(missing) or 'none'}.\n\nObserved price changes are not trading returns.\n\n"
    for s in followed:
        markdown += f"- {s['symbol']} ({s['signal_date']}): {s['monitor_status']}; price change: {s['price_change']}.\n"
    return publish(context, end, "weekly_"+mode, result, markdown)
