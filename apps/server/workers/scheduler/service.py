from datetime import timedelta

from sqlalchemy import select

from stock_scanner.calendar import expected_session

from ...errors import ServiceError
from ...persistence.models import Occurrence, Schedule, now
from ...services.jobs import enqueue, event, utc
from .triggers import next_occurrence

TASKS = {"daily_scan", "weekly_summary", "archive_completed_months", "database_backup", "agent_task"}


def tick(database, settings, at=None):
    at = at or now()
    count = 0
    with database.session() as db:
        from ...services.policy import effective
        settings = effective(settings, db)
        schedules = list(db.scalars(select(Schedule).where(Schedule.enabled.is_(True), Schedule.next_at <= at).with_for_update(skip_locked=True)))
        for row in schedules:
            scheduled = utc(row.next_at)
            lateness = max(0, int((at-scheduled).total_seconds()))
            payload = row.task.copy()
            type_ = payload.pop("type")
            if type_ not in TASKS:
                raise ServiceError("invalid_task", "Schedule task is not supported")
            skip = row.missed_policy == "skip" and lateness > settings.poll_seconds*2
            if not skip:
                kind = {"daily_scan": "scan", "weekly_summary": "weekly", "archive_completed_months": "archive",
                        "database_backup": "backup", "agent_task": "agent"}[type_]
                if kind == "scan":
                    payload.setdefault("mode", "live")
                    payload.setdefault("research", "current")
                    if row.missed_policy == "catch_up" and lateness > 86400:
                        payload.update(mode="historical_snapshot", start_date=expected_session(scheduled, settings.settlement_minutes),
                                       end_date=expected_session(at, settings.settlement_minutes), research="as_of_only")
                job = enqueue(db, row.owner_id, kind, payload, key=f"schedule:{row.id}:{scheduled.isoformat()}")
                job_id = job.id
            else:
                job_id = None
            db.add(Occurrence(owner_id=row.owner_id, schedule_id=row.id, scheduled_at=scheduled,
                              enqueued_at=at, job_id=job_id, state="skipped" if skip else "enqueued"))
            event(db, row.owner_id, "schedule_skipped" if skip else "schedule_enqueued", job_id, row.id,
                  {"scheduled_for_utc": scheduled.isoformat(), "actual_at_utc": at.isoformat(), "lateness_seconds": lateness,
                   "timezone": row.trigger.get("timezone") or settings.timezone})
            row.next_at, skipped = next_occurrence(row.trigger, at, settings)
            if row.next_at is None:
                row.enabled = False
            for wall in skipped:
                event(db, row.owner_id, "dst_nonexistent_time_skipped", schedule_id=row.id, data={"wall_time": wall})
            count += 1
        if settings.automatic_archives and settings.r2_endpoint and settings.r2_bucket:
            from ...services.storage import Storage
            if Storage(settings).status(db)["pressure"]:
                bucket = int(at.timestamp())//settings.maintenance_interval_seconds
                enqueue(db, settings.owner_id, "archive", {}, key=f"pressure-archive:{bucket}")
    return count
