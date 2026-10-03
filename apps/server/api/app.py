import base64
import hashlib
import hmac
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from decimal import Decimal
from datetime import date

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import JSONResponse, Response, StreamingResponse
from sqlalchemy import delete, select
from pydantic import ValidationError

from stock_scanner.rules import Rules

from ..config import Settings, secret_file
from ..errors import ServiceError
from ..persistence.database import Database
from ..persistence.models import Artifact, Event, Import, Job, Occurrence, Policy, Portfolio, Report, Reservation, Rule, Schedule, Signal, Transaction, now, uid
from ..services.jobs import enqueue, event, job_view, owned
from ..services.policy import effective
from ..services.portfolios import ledger, transaction
from ..services.scans import plan
from ..services.storage import Storage
from ..workers.scheduler.service import TASKS
from ..workers.scheduler.triggers import next_occurrence, validate
from .schemas import AgentRequest, AnalysisRequest, ConfirmImport, ImportRequest, PortfolioRequest, RestoreRequest, ScanRequest, ScheduleRequest, TransactionRequest, WeeklyRequest
from .limits import BodyLimit
from .sessions import BrowserSessions
from .schemas import MovementRequest
from ..services.market import bars as cached_bars, movement
from ..services.agent_context import context_packet


def view(row, fields):
    return {name: str(value) if isinstance(value := getattr(row, name), Decimal) else value for name in fields.split()}


def create_app(settings=None, database=None, token=None):
    settings = settings or Settings.load()
    database = database or Database(settings)
    storage = Storage(settings)
    token = token or secret_file(settings.api_token_file)
    if len(token) < 32:
        raise ValueError("API token must have at least 32 random characters")
    verifier = hashlib.sha256(token.encode()).digest()
    del token
    app = FastAPI(title="Private Stock Research Server", version="0.1.0", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(BodyLimit, upload_bytes=settings.limits.upload_bytes)
    sessions = BrowserSessions(settings, database, verifier)

    @app.middleware("http")
    async def private_responses(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.exception_handler(ServiceError)
    async def service_error(request, error):
        return JSONResponse(status_code=error.status, content={"error": {"code": error.code, "message": error.message}})

    @app.exception_handler(ValidationError)
    async def schema_error(request, error):
        return JSONResponse(status_code=422, content={"error": {"code": "invalid_input", "message": "Input failed schema validation"}})

    def owner(request: Request):
        raw = request.headers.get("authorization", "")
        if not raw:
            sessions.read(request)
            return settings.owner_id
        scheme, _, credential = raw.partition(" ")
        if scheme.lower() == "basic":
            try:
                username, credential = base64.b64decode(credential, validate=True).decode().split(":", 1)
                if username != "owner":
                    credential = ""
            except (ValueError, UnicodeDecodeError):
                credential = ""
        elif scheme.lower() != "bearer":
            credential = ""
        if not hmac.compare_digest(hashlib.sha256(credential.encode()).digest(), verifier):
            challenge = "Basic realm=research" if request.url.path.endswith("/docs") else "Bearer"
            raise HTTPException(401, "Authentication required", headers={"WWW-Authenticate": challenge})
        return settings.owner_id

    def db_session():
        with database.session() as db:
            yield db

    def current(db):
        return effective(settings, db)

    def key_header(value):
        if value and (len(value) > 200 or not value.isascii()):
            raise ServiceError("invalid_idempotency_key", "Use an ASCII idempotency key of at most 200 characters", 422)
        return value

    def submitted(db, principal, kind, payload, key):
        row = enqueue(db, principal, kind, payload, key_header(key))
        return {"job_id": row.id, "status": row.status, "status_url": f"/api/v1/jobs/{row.id}",
                "events_url": f"/api/v1/jobs/{row.id}/events/stream"}

    @app.post("/api/v1/auth/session")
    def connect(request: Request, response: Response, principal=Depends(owner)):
        return sessions.create(request, response)

    @app.get("/api/v1/auth/session")
    def session_info(request: Request):
        data = sessions.read(request, mutation=False)
        return {"owner_id":settings.owner_id,"expires_at":data["expires_at"],"csrf_token":data["csrf_token"]}

    @app.delete("/api/v1/auth/session")
    def disconnect(request: Request, response: Response):
        return sessions.revoke(request,response)

    @app.get("/api/v1/market/context")
    def market_context(principal=Depends(owner)):
        from stock_scanner.calendar import expected_session, next_run
        return {"latest_session":expected_session(settlement_minutes=settings.settlement_minutes),
                "next_run":next_run(settlement_minutes=settings.settlement_minutes),"market_timezone":"America/New_York"}

    @app.get("/api/v1/market/tickers/{symbol}/bars")
    def market_bars(symbol: str, start_date: date | None = None, end_date: date | None = None,
                    principal=Depends(owner), db=Depends(db_session)):
        return cached_bars(db,storage,current(db),principal,symbol,start_date.isoformat() if start_date else None,end_date.isoformat() if end_date else None)

    @app.post("/api/v1/market/movement-snapshots")
    def market_movement(request: MovementRequest, principal=Depends(owner), db=Depends(db_session)):
        return movement(db,storage,current(db),principal,request)

    @app.get("/api/v1/health/live")
    def live():
        return {"status": "alive"}

    @app.get("/api/v1/health/ready")
    def ready():
        try:
            good = database.ready()
        except Exception:
            good = False
        return JSONResponse({"status": "ready" if good else "unavailable"}, status_code=200 if good else 503)

    @app.get("/api/v1/docs", include_in_schema=False)
    def docs(principal=Depends(owner)):
        return get_swagger_ui_html(openapi_url="/api/v1/openapi.json", title="Research API")

    @app.get("/api/v1/openapi.json", include_in_schema=False)
    def schema(principal=Depends(owner)):
        return app.openapi()

    @app.get("/api/v1/system/status")
    def status(principal=Depends(owner), db=Depends(db_session)):
        cfg = current(db)
        return {"version": "0.1.0", "server_timezone": cfg.timezone, "market_timezone": "America/New_York",
                "storage": Storage(cfg).status(db), "codex_enabled": cfg.codex_enabled,
                "archive_configured": bool(cfg.r2_endpoint and cfg.r2_bucket),
                "capabilities": {"codex": "operator_verified" if cfg.codex_enabled and cfg.codex_sandbox_verified else "unverified" if cfg.codex_enabled else "disabled",
                                 "archive": "configured_unverified" if cfg.r2_endpoint and cfg.r2_bucket else "disabled",
                                 "mail": "unavailable", "browser_sessions": bool(cfg.browser_origin)}}

    @app.get("/api/v1/me")
    def me(principal=Depends(owner), db=Depends(db_session)):
        row = db.get(Policy, "preferences:"+principal)
        return {"id": principal, "preferences": row.values if row else {}}

    @app.patch("/api/v1/me")
    def preferences(values: dict, principal=Depends(owner), db=Depends(db_session)):
        if set(values)-{"display_timezone", "default_portfolio_id"}:
            raise ServiceError("invalid_preferences", "Unsupported preference", 422)
        if values.get("display_timezone"):
            from zoneinfo import ZoneInfo
            try:
                ZoneInfo(values["display_timezone"])
            except (KeyError, TypeError):
                raise ServiceError("invalid_timezone", "Use an IANA timezone", 422) from None
        if values.get("default_portfolio_id"):
            owned(db, Portfolio, values["default_portfolio_id"], principal)
        row = db.get(Policy, "preferences:"+principal)
        if row:
            row.values = {**row.values, **values}
        else:
            db.add(Policy(id="preferences:"+principal, owner_id=principal, values=values))
        return {"updated": True}

    @app.get("/api/v1/rules")
    def rules(principal=Depends(owner), db=Depends(db_session)):
        return [view(r, "id values fingerprint") for r in db.scalars(select(Rule).where(Rule.owner_id == principal))]

    @app.post("/api/v1/rules", status_code=201)
    def new_rules(values: dict, principal=Depends(owner), db=Depends(db_session)):
        try:
            validated = Rules(**values).__dict__
        except (TypeError, ValueError):
            raise ServiceError("invalid_rules", "Rules must be valid scanner thresholds", 422) from None
        row = Rule(owner_id=principal, values=validated, fingerprint=hashlib.sha256(json.dumps(validated, sort_keys=True).encode()).hexdigest())
        db.add(row)
        db.flush()
        return view(row, "id values fingerprint")

    @app.get("/api/v1/market/coverage")
    def coverage(start_date: str, end_date: str, principal=Depends(owner), db=Depends(db_session)):
        request = ScanRequest(mode="historical_snapshot", start_date=start_date, end_date=end_date)
        return plan(db, storage, current(db), principal, request.model_dump(mode="json"))

    @app.post("/api/v1/scan-plans")
    def scan_plan(request: ScanRequest, principal=Depends(owner), db=Depends(db_session)):
        return plan(db, storage, current(db), principal, request.model_dump(mode="json"))

    @app.post("/api/v1/scans", status_code=202)
    def scans(request: ScanRequest, principal=Depends(owner), db=Depends(db_session), key: str | None = Header(None, alias="Idempotency-Key")):
        payload = request.model_dump(mode="json")
        plan(db, storage, current(db), principal, payload)
        return submitted(db, principal, "scan", payload, key)

    @app.post("/api/v1/weekly-summaries", status_code=202)
    def summary(request: WeeklyRequest, principal=Depends(owner), db=Depends(db_session), key: str | None = Header(None, alias="Idempotency-Key")):
        return submitted(db, principal, "weekly", request.model_dump(mode="json"), key)

    @app.get("/api/v1/signals")
    def signals(mode: str = "live", limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0), principal=Depends(owner), db=Depends(db_session)):
        rows = db.scalars(select(Signal).where(Signal.owner_id == principal, Signal.mode == mode).order_by(Signal.data_date.desc()).limit(limit).offset(offset))
        return [view(r, "id data_date symbol mode report_id payload") for r in rows]

    @app.get("/api/v1/jobs")
    def jobs(limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0), principal=Depends(owner), db=Depends(db_session)):
        return [job_view(r) for r in db.scalars(select(Job).where(Job.owner_id == principal).order_by(Job.created_at.desc()).limit(limit).offset(offset))]

    @app.get("/api/v1/jobs/{identity}")
    def job(identity: str, principal=Depends(owner), db=Depends(db_session)):
        return job_view(owned(db, Job, identity, principal))

    @app.post("/api/v1/jobs/{identity}/cancel")
    def cancel(identity: str, principal=Depends(owner), db=Depends(db_session)):
        row = owned(db, Job, identity, principal, lock=True)
        row.cancel_requested = True
        if row.status in {"queued", "waiting_for_archive"}:
            row.status = "cancelled"
            db.execute(delete(Reservation).where(Reservation.id == identity))
        event(db, principal, "cancel_requested", identity)
        return job_view(row)

    @app.post("/api/v1/jobs/{identity}/resume")
    def resume(identity: str, principal=Depends(owner), db=Depends(db_session)):
        row = owned(db, Job, identity, principal, lock=True)
        if row.status not in {"failed", "cancelled", "waiting_for_archive"}:
            raise ServiceError("invalid_job_state", "Only stopped jobs can resume")
        row.status, row.cancel_requested, row.error = "queued", False, None
        row.updated_at = now()
        event(db, principal, "job_resumed", identity)
        return job_view(row)

    @app.get("/api/v1/jobs/{identity}/events")
    def events(identity: str, after: int = Query(0, ge=0), principal=Depends(owner), db=Depends(db_session)):
        owned(db, Job, identity, principal)
        return [view(r, "id at level code data") for r in db.scalars(select(Event).where(Event.owner_id == principal, Event.job_id == identity, Event.id > after).order_by(Event.id).limit(500))]

    @app.get("/api/v1/jobs/{identity}/events/stream")
    def stream(identity: str, request: Request, after: int = Query(0, ge=0), principal=Depends(owner), db=Depends(db_session)):
        owned(db, Job, identity, principal)
        try:
            cursor = max(after, int(request.headers.get("last-event-id", "0")))
        except ValueError:
            raise ServiceError("invalid_event_id", "Event cursor must be an integer", 422) from None
        async def generate():
            import asyncio
            position = cursor
            while not await request.is_disconnected():
                with database.session() as session:
                    row = owned(session, Job, identity, principal)
                    batch = list(session.scalars(select(Event).where(Event.owner_id == principal, Event.job_id == identity, Event.id > position).order_by(Event.id).limit(100)))
                    terminal = row.status in {"succeeded", "failed", "cancelled", "waiting_for_archive"}
                for e in batch:
                    position = e.id
                    yield f"id: {e.id}\ndata: {json.dumps(view(e, 'id level code data'))}\n\n"
                if terminal and not batch:
                    return
                yield ": heartbeat\n\n"
                await asyncio.sleep(settings.poll_seconds)
        return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-store"})

    @app.get("/api/v1/reports")
    def reports(mode: str | None = None, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0), principal=Depends(owner), db=Depends(db_session)):
        q = select(Report).where(Report.owner_id == principal)
        if mode:
            q = q.where(Report.mode == mode)
        return [view(r, "id job_id data_date mode quality artifact_id markdown_id summary") for r in db.scalars(q.order_by(Report.data_date.desc()).limit(limit).offset(offset))]

    @app.get("/api/v1/reports/{identity}")
    def report(identity: str, principal=Depends(owner), db=Depends(db_session)):
        return view(owned(db, Report, identity, principal), "id job_id data_date mode quality artifact_id markdown_id summary")

    @app.get("/api/v1/reports/{identity}/content")
    def report_content(identity: str, format: str = "json", principal=Depends(owner), db=Depends(db_session)):
        if format not in {"json", "markdown"}:
            raise ServiceError("invalid_format", "Use json or markdown", 422)
        row = owned(db, Report, identity, principal)
        artifact = owned(db, Artifact, row.artifact_id if format == "json" else row.markdown_id, principal)
        with storage.reader():
            path = storage.read(artifact, current(db).limits.task_output_bytes)
            body = path.read_bytes()
        return Response(body, media_type="application/json" if format == "json" else "text/markdown", headers={"Cache-Control": "no-store"})

    def schedule_payload(request, cfg):
        validate(request.trigger, cfg)
        if request.task.get("type") not in TASKS:
            raise ServiceError("invalid_task", "Unsupported schedule task", 422)
        task = request.task.copy()
        type_ = task.pop("type")
        if type_ == "daily_scan":
            ScanRequest(**task)
        elif type_ == "weekly_summary":
            WeeklyRequest(**task)
        elif type_ == "agent_task":
            AgentRequest(**task)
        elif task:
            raise ServiceError("invalid_task", "Storage schedule accepts no arbitrary task arguments", 422)
        if request.missed_run_policy == "catch_up" and type_ != "daily_scan":
            raise ServiceError("invalid_catchup", "catch_up applies to market scans; use run_once for other tasks", 422)

    @app.get("/api/v1/schedules")
    def schedules(principal=Depends(owner), db=Depends(db_session)):
        return [view(r, "id name trigger task missed_policy enabled next_at revision") for r in db.scalars(select(Schedule).where(Schedule.owner_id == principal))]

    @app.post("/api/v1/schedules", status_code=201)
    def add_schedule(request: ScheduleRequest, principal=Depends(owner), db=Depends(db_session)):
        cfg = current(db)
        schedule_payload(request, cfg)
        next_at, skipped = next_occurrence(request.trigger, now(), cfg)
        if request.enabled and next_at is None:
            raise ServiceError("schedule_in_past", "One-shot schedule must be in the future", 422)
        row = Schedule(owner_id=principal, name=request.name, trigger=request.trigger, task=request.task,
                       missed_policy=request.missed_run_policy, enabled=request.enabled, next_at=next_at)
        db.add(row)
        db.flush()
        for wall in skipped:
            event(db, principal, "dst_nonexistent_time_skipped", schedule_id=row.id, data={"wall_time": wall})
        return view(row, "id name next_at enabled")

    @app.patch("/api/v1/schedules/{identity}")
    def edit_schedule(identity: str, values: dict, principal=Depends(owner), db=Depends(db_session)):
        row = owned(db, Schedule, identity, principal, lock=True)
        merged = {"name": row.name, "trigger": row.trigger, "task": row.task, "missed_run_policy": row.missed_policy, "enabled": row.enabled, **values}
        request = ScheduleRequest(**merged)
        cfg = current(db)
        schedule_payload(request, cfg)
        row.name, row.trigger, row.task, row.enabled, row.missed_policy = request.name, request.trigger, request.task, request.enabled, request.missed_run_policy
        row.next_at, _ = next_occurrence(request.trigger, now(), cfg)
        row.revision += 1
        return view(row, "id name next_at enabled revision")

    @app.post("/api/v1/schedules/{identity}/run-now", status_code=202)
    def run_now(identity: str, principal=Depends(owner), db=Depends(db_session), key: str | None = Header(None, alias="Idempotency-Key")):
        row = owned(db, Schedule, identity, principal)
        payload = row.task.copy()
        kind = {"daily_scan": "scan", "weekly_summary": "weekly", "archive_completed_months": "archive", "database_backup": "backup", "agent_task": "agent"}[payload.pop("type")]
        return submitted(db, principal, kind, payload, key)

    @app.get("/api/v1/schedules/{identity}/occurrences")
    def occurrences(identity: str, limit: int = Query(100, ge=1, le=500), principal=Depends(owner), db=Depends(db_session)):
        owned(db, Schedule, identity, principal)
        return [view(r, "id scheduled_at enqueued_at job_id state") for r in db.scalars(select(Occurrence).where(Occurrence.schedule_id == identity, Occurrence.owner_id == principal).order_by(Occurrence.scheduled_at.desc()).limit(limit))]

    @app.get("/api/v1/storage/status")
    def storage_status(principal=Depends(owner), db=Depends(db_session)):
        cfg = current(db)
        return {**Storage(cfg).status(db), "policy": cfg.limits.model_dump(), "archive_after_days": cfg.archive_after_days, "archive_evict": cfg.archive_evict}

    @app.patch("/api/v1/storage/policy")
    def update_policy(values: dict, principal=Depends(owner), db=Depends(db_session)):
        if set(values)-{"limits", "archive_after_days", "archive_evict"}:
            raise ServiceError("invalid_policy", "Only retention/limit policy fields can be changed", 422)
        current_ = current(db).model_dump()
        for key_, value in values.items():
            current_[key_] = {**current_[key_], **value} if key_ == "limits" else value
        try:
            validated = Settings(**current_)
        except (ValueError, TypeError):
            raise ServiceError("invalid_policy", "Policy limits are invalid", 422) from None
        if validated.limits.upload_bytes > settings.limits.upload_bytes:
            raise ServiceError("upload_restart_required", "Raise the upload ceiling in server.json and restart the API before raising the runtime policy", 422)
        persisted = {"limits": validated.limits.model_dump(), "archive_after_days": validated.archive_after_days, "archive_evict": validated.archive_evict}
        row = db.get(Policy, "storage")
        if row:
            row.values = persisted
        else:
            db.add(Policy(id="storage", owner_id=principal, values=persisted))
        event(db, principal, "storage_policy_updated")
        return persisted

    @app.get("/api/v1/storage/archives")
    def archives(principal=Depends(owner), db=Depends(db_session)):
        from ..persistence.models import Archive
        return [view(r, "id status size created_at") for r in db.scalars(select(Archive).where(Archive.owner_id == principal).order_by(Archive.created_at.desc()).limit(100))]

    @app.get("/api/v1/storage/artifacts")
    def artifacts(dataset: str | None = None, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0), principal=Depends(owner), db=Depends(db_session)):
        q = select(Artifact).where(Artifact.owner_id == principal)
        if dataset:
            q = q.where(Artifact.dataset == dataset)
        return [view(r, "id dataset sha256 size status archive_id metadata_") for r in db.scalars(q.order_by(Artifact.created_at.desc()).limit(limit).offset(offset))]

    @app.post("/api/v1/storage/archive-jobs", status_code=202)
    def archive_job(principal=Depends(owner), db=Depends(db_session), key: str | None = Header(None, alias="Idempotency-Key")):
        return submitted(db, principal, "archive", {}, key)

    @app.post("/api/v1/storage/restore-jobs", status_code=202)
    def restore_job(request: RestoreRequest, principal=Depends(owner), db=Depends(db_session), key: str | None = Header(None, alias="Idempotency-Key")):
        for identity in request.artifact_ids:
            owned(db, Artifact, identity, principal)
        return submitted(db, principal, "restore", request.model_dump(), key)

    @app.get("/api/v1/portfolios")
    def portfolios(principal=Depends(owner), db=Depends(db_session)):
        return [view(r, "id name currency") for r in db.scalars(select(Portfolio).where(Portfolio.owner_id == principal))]

    @app.post("/api/v1/portfolios", status_code=201)
    def add_portfolio(request: PortfolioRequest, principal=Depends(owner), db=Depends(db_session)):
        row = Portfolio(owner_id=principal, **request.model_dump())
        db.add(row)
        db.flush()
        return view(row, "id name currency")

    @app.get("/api/v1/portfolios/{identity}/transactions")
    def transactions(identity: str, limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0), principal=Depends(owner), db=Depends(db_session)):
        owned(db, Portfolio, identity, principal)
        return [view(r, "id type at symbol quantity price amount fees currency external_ref correction_of superseded provenance") for r in db.scalars(select(Transaction).where(Transaction.portfolio_id == identity, Transaction.owner_id == principal).order_by(Transaction.at).limit(limit).offset(offset))]

    @app.post("/api/v1/portfolios/{identity}/transactions", status_code=201)
    def add_transaction(identity: str, request: TransactionRequest, principal=Depends(owner), db=Depends(db_session)):
        row = transaction(db, principal, identity, request.model_dump())
        return {"id": row.id}

    @app.post("/api/v1/portfolios/{identity}/transactions/{transaction_id}/corrections", status_code=201)
    def correction(identity: str, transaction_id: str, request: TransactionRequest, principal=Depends(owner), db=Depends(db_session)):
        owned(db, Portfolio, identity, principal, lock=True)
        original = owned(db, Transaction, transaction_id, principal, lock=True)
        if original.portfolio_id != identity or original.superseded:
            raise ServiceError("invalid_correction", "Transaction is not an active record in this portfolio")
        original.superseded = True
        db.flush()
        row = transaction(db, principal, identity, request.model_dump(), correction_of=original.id)
        return {"id": row.id, "correction_of": original.id}

    @app.get("/api/v1/portfolios/{identity}/positions")
    def positions(identity: str, as_of: datetime | None = None, principal=Depends(owner), db=Depends(db_session)):
        if as_of and as_of.tzinfo is None:
            raise ServiceError("invalid_timestamp", "as_of must include timezone", 422)
        return ledger(db, principal, identity, as_of)

    @app.post("/api/v1/portfolios/{identity}/analysis-jobs", status_code=202)
    def portfolio_analysis(identity: str, request: AnalysisRequest, principal=Depends(owner), db=Depends(db_session), key: str | None = Header(None, alias="Idempotency-Key")):
        owned(db, Portfolio, identity, principal)
        return submitted(db, principal, "portfolio_analysis", {**request.model_dump(mode="json"), "portfolio_id": identity}, key)

    @app.post("/api/v1/uploads", status_code=201)
    async def upload(file: UploadFile = File(...), principal=Depends(owner), db=Depends(db_session)):
        types = {"image/jpeg": ".jpg", "image/png": ".png", "application/pdf": ".pdf", "text/csv": ".csv"}
        if file.content_type not in types:
            raise ServiceError("unsupported_upload", "Upload JPEG, PNG, PDF or transaction CSV", 415)
        cfg, identity = current(db), uid()
        storage.reserve(db, identity, principal, cfg.limits.upload_bytes)
        path = storage.path(f"uploads/{principal}/{identity}{types[file.content_type]}")
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            size = 0
            with path.open("xb") as target:
                while chunk := await file.read(1024*1024):
                    size += len(chunk)
                    if size > cfg.limits.upload_bytes:
                        raise ServiceError("upload_size_limit", "Upload exceeds configured maximum", 413)
                    target.write(chunk)
            path.chmod(0o600)
            with path.open("rb") as f:
                head = f.read(8)
            valid = {"image/jpeg": head.startswith(b"\xff\xd8\xff"), "image/png": head == b"\x89PNG\r\n\x1a\n",
                     "application/pdf": head.startswith(b"%PDF-"), "text/csv": size > 0}[file.content_type]
            if not valid:
                raise ServiceError("upload_signature", "Upload content does not match media type", 422)
            artifact = storage.register(db, principal, path, "uploads", {"media_type": file.content_type})
            return {"upload_id": artifact.id, "sha256": artifact.sha256, "size": size}
        except Exception:
            path.unlink(missing_ok=True)
            raise
        finally:
            db.execute(delete(Reservation).where(Reservation.id == identity))
            await file.close()

    @app.post("/api/v1/imports", status_code=202)
    def import_job(request: ImportRequest, principal=Depends(owner), db=Depends(db_session), key: str | None = Header(None, alias="Idempotency-Key")):
        owned(db, Portfolio, request.portfolio_id, principal)
        artifact = owned(db, Artifact, request.upload_id, principal)
        if artifact.dataset != "uploads":
            raise ServiceError("invalid_upload", "Import must refer to an uploaded document", 422)
        if key:
            previous = db.scalar(select(Job).where(Job.owner_id == principal, Job.idempotency_key == key_header(key)))
            if previous:
                if previous.kind != "import":
                    raise ServiceError("idempotency_conflict", "Idempotency key belongs to another task")
                old = owned(db, Import, previous.payload["import_id"], principal)
                if old.upload_id != request.upload_id or old.portfolio_id != request.portfolio_id:
                    raise ServiceError("idempotency_conflict", "Idempotency key belongs to different import inputs")
                return {"job_id": previous.id, "status": previous.status, "import_id": old.id}
        row = Import(owner_id=principal, portfolio_id=request.portfolio_id, upload_id=request.upload_id)
        db.add(row)
        db.flush()
        result = submitted(db, principal, "import", {"import_id": row.id}, key)
        row.job_id = result["job_id"]
        return {**result, "import_id": row.id}

    @app.get("/api/v1/imports/{identity}")
    def imported(identity: str, principal=Depends(owner), db=Depends(db_session)):
        return view(owned(db, Import, identity, principal), "id portfolio_id upload_id job_id status proposal confirmed_ids")

    @app.post("/api/v1/imports/{identity}/confirm")
    def confirm(identity: str, request: ConfirmImport, principal=Depends(owner), db=Depends(db_session)):
        row = owned(db, Import, identity, principal, lock=True)
        fingerprint = hashlib.sha256(request.model_dump_json().encode()).hexdigest()
        if row.status == "confirmed":
            if row.proposal.get("confirmation_hash") != fingerprint:
                raise ServiceError("confirmation_conflict", "Import was confirmed with different rows")
            return {"transaction_ids": row.confirmed_ids}
        if row.status != "awaiting_review":
            raise ServiceError("invalid_import_state", "Import must be awaiting user review")
        ids = []
        upload = owned(db, Artifact, row.upload_id, principal)
        for i, record in enumerate(request.rows):
            values = record.model_dump()
            values["external_ref"] = values.get("external_ref") or f"import:{upload.sha256}:{i}"
            tx = transaction(db, principal, row.portfolio_id, values, {"import_id": row.id, "upload_id": row.upload_id})
            ids.append(tx.id)
        row.status, row.confirmed_ids = "confirmed", ids
        row.proposal = {**row.proposal, "confirmation_hash": fingerprint}
        return {"transaction_ids": ids}

    @app.post("/api/v1/imports/{identity}/reject")
    def reject(identity: str, principal=Depends(owner), db=Depends(db_session)):
        row = owned(db, Import, identity, principal, lock=True)
        if row.status == "confirmed":
            raise ServiceError("invalid_import_state", "Confirmed records require auditable transaction corrections")
        row.status = "rejected"
        return {"status": row.status}

    @app.get("/api/v1/agent/profiles")
    def profiles(principal=Depends(owner)):
        return [{"id": "research-analyst", "enabled": settings.codex_enabled,
                 "ready": settings.codex_enabled and settings.codex_sandbox_verified,
                 "capabilities": ["daily_review", "weekly_review", "portfolio_review", "document_review"], "writes_portfolio": False,
                 "vision_media_types": ["image/png","image/jpeg"], "context_schema_version":1}]

    @app.post("/api/v1/agent/context")
    def agent_context(request: AgentRequest, principal=Depends(owner), db=Depends(db_session)):
        return context_packet(db,storage,current(db),principal,request.model_dump(mode="json"))

    @app.post("/api/v1/agent/tasks", status_code=202)
    def agent(request: AgentRequest, principal=Depends(owner), db=Depends(db_session), key: str | None = Header(None, alias="Idempotency-Key")):
        if not settings.codex_enabled or not settings.codex_sandbox_verified:
            raise ServiceError("agent_disabled", "Codex is disabled until private authentication and sandbox verification are configured", 503)
        for identity in request.report_ids:
            owned(db, Report, identity, principal)
        if request.portfolio_id:
            owned(db, Portfolio, request.portfolio_id, principal)
        for identity in request.upload_ids:
            artifact = owned(db, Artifact, identity, principal)
            if artifact.dataset != "uploads" or artifact.metadata_.get("media_type") not in {"image/png","image/jpeg"}:
                raise ServiceError("unsupported_vision_media", "Vision accepts JPEG/PNG uploads", 422)
        return submitted(db, principal, "agent", request.model_dump(mode="json"), key)

    @app.get("/api/v1/agent/tasks/{identity}")
    def agent_status(identity: str, principal=Depends(owner), db=Depends(db_session)):
        row = owned(db, Job, identity, principal)
        if row.kind != "agent":
            raise ServiceError("not_found", "Agent task not found", 404)
        return job_view(row)

    @app.post("/api/v1/agent/tasks/{identity}/cancel")
    def agent_cancel(identity: str, principal=Depends(owner), db=Depends(db_session)):
        row = owned(db, Job, identity, principal, lock=True)
        if row.kind != "agent":
            raise ServiceError("not_found", "Agent task not found", 404)
        row.cancel_requested = True
        if row.status == "queued":
            row.status = "cancelled"
        return {"status": row.status, "cancel_requested": True}

    return app
