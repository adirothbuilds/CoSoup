import hashlib
import json
from datetime import timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from ..errors import Cancelled, ServiceError
from ..persistence.models import Event, Job, Reservation, now, uid

QUEUES = {"scan": "scanner", "weekly": "scanner", "portfolio_analysis": "scanner",
          "archive": "storage", "restore": "storage", "backup": "storage",
          "import": "imports", "agent": "codex"}


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def owned(db, model, identity, owner, lock=False):
    q = select(model).where(model.id == identity, model.owner_id == owner)
    if lock:
        q = q.with_for_update()
    row = db.scalar(q)
    if row is None:
        raise ServiceError("not_found", "Record not found", 404)
    return row


def event(db, owner, code, job_id=None, schedule_id=None, data=None, level="info"):
    # Callers supply typed facts, not raw exceptions, prompts or document contents.
    db.add(Event(owner_id=owner, code=code, job_id=job_id, schedule_id=schedule_id,
                 data=data or {}, level=level))


def enqueue(db, owner, kind, payload, key=None):
    if kind not in QUEUES:
        raise ServiceError("invalid_task", "Unsupported task type", 422)
    digest = hashlib.sha256(json.dumps({"kind": kind, "payload": payload}, sort_keys=True).encode()).hexdigest()
    if key:
        old = db.scalar(select(Job).where(Job.owner_id == owner, Job.idempotency_key == key))
        if old:
            if old.payload_hash != digest:
                raise ServiceError("idempotency_conflict", "Idempotency key was used with different inputs")
            return old
    row = Job(id=uid(), owner_id=owner, kind=kind, queue=QUEUES[kind], payload=payload,
              payload_hash=digest, idempotency_key=key)
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        old = db.scalar(select(Job).where(Job.owner_id == owner, Job.idempotency_key == key))
        if old is None or old.payload_hash != digest:
            raise ServiceError("idempotency_conflict", "Concurrent submission conflict") from None
        return old
    event(db, owner, "job_queued", row.id, data={"kind": kind})
    return row


class Jobs:
    def __init__(self, database, settings):
        self.database, self.settings = database, settings

    def claim(self, queue):
        at = now()
        with self.database.session() as db:
            expired = list(db.scalars(select(Job).where(Job.queue == queue, Job.status == "running", Job.lease_until < at).with_for_update(skip_locked=True)))
            for row in expired:
                row.status = "failed" if row.attempts >= self.settings.max_job_attempts else "queued"
                row.error = {"code": "lease_expired", "message": "Worker lease expired; checkpoint retained"}
                row.lease_token = None
                event(db, row.owner_id, "lease_expired", row.id, level="warning")
            db.flush()
            row = db.scalar(select(Job).where(Job.queue == queue, Job.status == "queued").order_by(Job.created_at).with_for_update(skip_locked=True).limit(1))
            if row is None:
                return None
            if row.cancel_requested:
                row.status = "cancelled"
                event(db, row.owner_id, "job_cancelled", row.id)
                return None
            row.status, row.lease_token = "running", uid()
            row.attempts += 1
            row.lease_until = at + timedelta(seconds=self.settings.lease_seconds)
            row.updated_at = at
            event(db, row.owner_id, "job_started", row.id, data={"attempt": row.attempts})
            return row

    def heartbeat(self, identity, token):
        with self.database.session() as db:
            row = db.scalar(select(Job).where(Job.id == identity, Job.lease_token == token, Job.status == "running").with_for_update())
            if row is None:
                return False
            row.lease_until = now() + timedelta(seconds=self.settings.lease_seconds)
            row.updated_at = now()
            db.execute(update(Reservation).where(Reservation.id == identity).values(expires_at=now()+timedelta(seconds=self.settings.lease_seconds*2)))
            return not row.cancel_requested

    def checkpoint(self, identity, token, progress):
        with self.database.session() as db:
            row = db.scalar(select(Job).where(Job.id == identity, Job.lease_token == token, Job.status == "running").with_for_update())
            if row is None or row.cancel_requested:
                raise Cancelled()
            row.progress, row.updated_at = progress, now()
            event(db, row.owner_id, "job_progress", row.id, data=progress)

    def finish(self, identity, token, status, result=None, error=None):
        with self.database.session() as db:
            row = db.scalar(select(Job).where(Job.id == identity, Job.lease_token == token, Job.status == "running").with_for_update())
            if row is None:
                return
            row.status = "cancelled" if row.cancel_requested else status
            row.result, row.error = result or {}, error
            row.lease_token, row.lease_until, row.updated_at = None, None, now()
            db.execute(__import__('sqlalchemy').delete(Reservation).where(Reservation.id == identity))
            event(db, row.owner_id, "job_" + row.status, row.id, data={"error_code": error.get("code") if error else None})


def job_view(row):
    return {"id": row.id, "kind": row.kind, "status": row.status, "created_at": row.created_at,
            "updated_at": row.updated_at, "attempts": row.attempts, "cancel_requested": row.cancel_requested,
            "progress": row.progress, "result": row.result, "error": row.error}
