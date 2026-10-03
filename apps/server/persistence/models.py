from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now():
    return datetime.now(timezone.utc)


def uid():
    return uuid4().hex


class Base(DeclarativeBase):
    pass


class Version(Base):
    __tablename__ = "schema_version"
    id: Mapped[int] = mapped_column(primary_key=True)


class Policy(Base):
    __tablename__ = "policies"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64))
    values: Mapped[dict] = mapped_column(JSON)


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("owner_id", "idempotency_key"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    queue: Mapped[str] = mapped_column(String(20), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSON)
    payload_hash: Mapped[str] = mapped_column(String(64))
    idempotency_key: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[str | None] = mapped_column(String(32))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    progress: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[dict | None] = mapped_column(JSON)


class Event(Base):
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    job_id: Mapped[str | None] = mapped_column(String(32), index=True)
    schedule_id: Mapped[str | None] = mapped_column(String(32), index=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    level: Mapped[str] = mapped_column(String(10), default="info")
    code: Mapped[str] = mapped_column(String(80))
    data: Mapped[dict] = mapped_column(JSON, default=dict)


class Schedule(Base):
    __tablename__ = "schedules"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(120))
    trigger: Mapped[dict] = mapped_column(JSON)
    task: Mapped[dict] = mapped_column(JSON)
    missed_policy: Mapped[str] = mapped_column(String(20), default="run_once")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    next_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)


class Occurrence(Base):
    __tablename__ = "occurrences"
    __table_args__ = (UniqueConstraint("schedule_id", "scheduled_at"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    schedule_id: Mapped[str] = mapped_column(ForeignKey("schedules.id"))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    enqueued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    job_id: Mapped[str | None] = mapped_column(String(32))
    state: Mapped[str] = mapped_column(String(30))


class Rule(Base):
    __tablename__ = "rules"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    values: Mapped[dict] = mapped_column(JSON)
    fingerprint: Mapped[str] = mapped_column(String(64))


class Artifact(Base):
    __tablename__ = "artifacts"
    __table_args__ = (UniqueConstraint("owner_id", "path"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    dataset: Mapped[str] = mapped_column(String(30), index=True)
    path: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    status: Mapped[str] = mapped_column(String(20), default="hot")
    archive_id: Mapped[str | None] = mapped_column(String(32))
    restored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, default=dict)


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (UniqueConstraint("job_id", "data_date", "mode"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    job_id: Mapped[str] = mapped_column(String(32))
    data_date: Mapped[str] = mapped_column(String(10), index=True)
    mode: Mapped[str] = mapped_column(String(30), index=True)
    quality: Mapped[str] = mapped_column(String(40))
    artifact_id: Mapped[str] = mapped_column(ForeignKey("artifacts.id"))
    markdown_id: Mapped[str] = mapped_column(ForeignKey("artifacts.id"))
    summary: Mapped[dict] = mapped_column(JSON)


class Signal(Base):
    __tablename__ = "signals"
    __table_args__ = (UniqueConstraint("owner_id", "data_date", "symbol", "rules_hash", "mode"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    data_date: Mapped[str] = mapped_column(String(10), index=True)
    symbol: Mapped[str] = mapped_column(String(30))
    rules_hash: Mapped[str] = mapped_column(String(64))
    mode: Mapped[str] = mapped_column(String(30))
    report_id: Mapped[str] = mapped_column(String(32))
    payload: Mapped[dict] = mapped_column(JSON)


class Archive(Base):
    __tablename__ = "archives"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(20), default="building")
    object_key: Mapped[str] = mapped_column(Text)
    sha256: Mapped[str | None] = mapped_column(String(64))
    size: Mapped[int | None] = mapped_column(BigInteger)
    manifest: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Reservation(Base):
    __tablename__ = "reservations"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(64))
    bytes: Mapped[int] = mapped_column(BigInteger)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Portfolio(Base):
    __tablename__ = "portfolios"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(120))
    currency: Mapped[str] = mapped_column(String(3), default="USD")


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (UniqueConstraint("portfolio_id", "external_ref"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    portfolio_id: Mapped[str] = mapped_column(ForeignKey("portfolios.id"), index=True)
    type: Mapped[str] = mapped_column(String(20))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    symbol: Mapped[str | None] = mapped_column(String(30))
    quantity: Mapped[object | None] = mapped_column(Numeric(28, 10))
    price: Mapped[object | None] = mapped_column(Numeric(28, 10))
    amount: Mapped[object | None] = mapped_column(Numeric(28, 10))
    fees: Mapped[object] = mapped_column(Numeric(28, 10), default=0)
    currency: Mapped[str] = mapped_column(String(3))
    external_ref: Mapped[str | None] = mapped_column(String(160))
    correction_of: Mapped[str | None] = mapped_column(String(32))
    superseded: Mapped[bool] = mapped_column(Boolean, default=False)
    provenance: Mapped[dict] = mapped_column(JSON, default=dict)


class Import(Base):
    __tablename__ = "imports"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=uid)
    owner_id: Mapped[str] = mapped_column(String(64), index=True)
    portfolio_id: Mapped[str] = mapped_column(ForeignKey("portfolios.id"))
    upload_id: Mapped[str] = mapped_column(ForeignKey("artifacts.id"))
    job_id: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(30), default="queued")
    proposal: Mapped[dict] = mapped_column(JSON, default=dict)
    confirmed_ids: Mapped[list] = mapped_column(JSON, default=list)
