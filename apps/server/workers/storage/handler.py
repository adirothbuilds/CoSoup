import json
import os
import shutil
import subprocess
import tarfile
from datetime import date, timedelta
from pathlib import Path

import zstandard
from sqlalchemy import delete, select

from stock_scanner.calendar import expected_session, sessions_ending
from stock_scanner.storage import atomic_json

from ...adapters.encryption import Encryption
from ...adapters.objects import R2ObjectStore
from ...config import secret_file
from ...errors import ServiceError
from ...persistence.models import Archive, Artifact, Event, now
from ...services.jobs import owned, utc
from ...services.storage import digest


def export_old_events(context):
    cutoff = now()-timedelta(days=context.settings.limits.log_retention_days)
    with context.database.session() as db:
        rows = list(db.scalars(select(Event).where(Event.owner_id == context.job.owner_id, Event.at < cutoff).order_by(Event.id).limit(10000)))
    if not rows:
        return
    path = context.storage.path(f"logs/events-{rows[0].id}-{rows[-1].id}.json.gz")
    if not path.exists():
        atomic_json(path, [{"id": r.id, "at": r.at.isoformat(), "code": r.code, "level": r.level,
                            "job_id": r.job_id, "schedule_id": r.schedule_id, "data": r.data} for r in rows])
    with context.database.session() as db:
        context.storage.register(db, context.job.owner_id, path, "logs", {"event_ids": [r.id for r in rows]})


def evict_verified(context, durable):
    if not context.settings.archive_evict or not durable:
        return
    storage, owner = context.storage, context.job.owner_id
    earliest = sessions_ending(expected_session(), context.settings.limits.hot_sessions)[0]
    with storage.evictor() as allowed:
        if not allowed:
            return
        with context.database.session() as db:
            rows = list(db.scalars(select(Artifact).join(Archive, Archive.id == Artifact.archive_id).where(
                Artifact.owner_id == owner, Artifact.status == "hot", Archive.status == "verified")))
            for row in rows:
                session = row.metadata_.get("session")
                if row.dataset in {"grouped", "reference"} and (not session or session >= earliest):
                    continue
                if row.restored_at and utc(row.restored_at) > now()-timedelta(days=context.settings.limits.restore_ttl_days):
                    continue
                path = storage.path(row.path)
                if path.exists():
                    if digest(path) != row.sha256:
                        raise ServiceError("artifact_changed", "Verified artifact changed; refusing eviction")
                    path.unlink()
                row.status = "cold"
                if row.dataset == "logs":
                    db.execute(delete(Event).where(Event.owner_id == owner, Event.id.in_(row.metadata_.get("event_ids", []))))


def archive(context, store=None, force_ids=None):
    store = store or R2ObjectStore(context.settings)
    encryption = Encryption(context.settings.archive_key_file)
    owner, storage, settings = context.job.owner_id, context.storage, context.settings
    cutoff = now()-timedelta(days=settings.archive_after_days)
    export_old_events(context)
    with context.database.session() as db:
        rows = list(db.scalars(select(Artifact).where(Artifact.owner_id == owner,
                              Artifact.status == "hot", Artifact.archive_id.is_(None)).order_by(Artifact.created_at)))
        eligible = []
        for r in rows:
            session = r.metadata_.get("session")
            if force_ids:
                if r.id not in force_ids:
                    continue
            elif r.dataset in {"grouped", "reference"}:
                if not session or session > cutoff.date().isoformat():
                    continue
            elif r.dataset == "uploads":
                if utc(r.created_at) > now()-timedelta(days=settings.unique_upload_backup_days):
                    continue
            elif utc(r.created_at) > cutoff and r.dataset != "logs":
                continue
            if r.restored_at and utc(r.restored_at) > now()-timedelta(days=settings.limits.restore_ttl_days):
                continue
            eligible.append(r)
    archive_ids = []
    while eligible:
        batch, size = [], 0
        # Bound each archive, and process one dataset at a time for provenance.
        dataset = eligible[0].dataset
        for row in eligible[:]:
            if row.dataset != dataset:
                continue
            if row.size > settings.limits.archive_shard_bytes:
                raise ServiceError("artifact_too_large", "Artifact exceeds archive shard size; raise configured limit before archiving")
            if batch and size+row.size > settings.limits.archive_shard_bytes:
                continue
            batch.append(row)
            eligible.remove(row)
            size += row.size
        context.checkpoint(stage="archiving", archived_ids=archive_ids, artifacts=len(batch))
        with context.database.session() as db:
            storage.reserve(db, context.job.id, owner, max(size*3+1_000_000, 10_000_000), maintenance=True)
        import hashlib
        identity = hashlib.sha256(json.dumps(sorted((r.id, r.sha256) for r in batch)).encode()).hexdigest()[:32]
        staging = storage.path(f"archive-staging/{identity}")
        staging.mkdir(parents=True, mode=0o700)
        members = [{"id": r.id, "path": r.path, "sha256": r.sha256, "size": r.size,
                    "dataset": r.dataset, "metadata": r.metadata_} for r in batch]
        manifest = {"version": 1, "owner_id": owner, "archive_id": identity, "dataset": dataset, "members": members}
        object_key = f"{settings.r2_prefix}/{owner}/{now():%Y-%m}/{identity}.tar.zst.aesgcm"
        with context.database.session() as db:
            old = db.get(Archive, identity)
            if old:
                object_key = old.object_key
            else:
                db.add(Archive(id=identity, owner_id=owner, object_key=object_key, manifest=manifest))
        try:
            plain = staging/"payload.tar.zst"
            with plain.open("wb") as f, zstandard.ZstdCompressor(level=3).stream_writer(f) as z, tarfile.open(fileobj=z, mode="w|") as tar:
                for row in batch:
                    path = storage.read(row)
                    tar.add(path, arcname=row.id, recursive=False)
                import io
                b = json.dumps(manifest, sort_keys=True).encode()
                info = tarfile.TarInfo("manifest.json")
                info.size, info.mode = len(b), 0o600
                tar.addfile(info, io.BytesIO(b))
            encrypted = staging/"payload.aesgcm"
            encryption.encrypt(plain, encrypted)
            h, length = digest(encrypted), encrypted.stat().st_size
            store.put(object_key, encrypted)
            store.verify(object_key, h, length)
            with context.database.session() as db:
                record = owned(db, Archive, identity, owner, lock=True)
                record.status, record.sha256, record.size = "verified", h, length
                for r in batch:
                    row = owned(db, Artifact, r.id, owner, lock=True)
                    row.archive_id = identity
            # A durable remote object and committed manifest are prerequisites.
            # Never evict when any reader job may use the artifact.
            archive_ids.append(identity)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
    # Logs must be cataloged/archived before deleting their database equivalents.
    evict_verified(context, store.durable)
    return {"archive_ids": archive_ids, "eviction_enabled": settings.archive_evict,
            "note": "Verified full remote hash; recent/active data remains local"}


def restore(context, store=None):
    store = store or R2ObjectStore(context.settings)
    encryption = Encryption(context.settings.archive_key_file)
    owner, storage = context.job.owner_id, context.storage
    with context.database.session() as db:
        rows = [owned(db, Artifact, identity, owner) for identity in context.job.payload["artifact_ids"]]
        archives = {r.archive_id: owned(db, Archive, r.archive_id, owner) for r in rows if r.archive_id}
        if any(not r.archive_id and not storage.path(r.path).is_file() for r in rows):
            raise ServiceError("not_archived", "Artifact has no verified remote copy")
        needed = sum(a.size or 0 for a in archives.values())*3+sum(r.size for r in rows)
        if needed > context.settings.limits.restore_bytes:
            raise ServiceError("restore_size_limit", "Restore exceeds configured limit; submit smaller groups")
        storage.reserve(db, context.job.id, owner, max(needed, 1_000_000))
    restored = []
    for identity, record in archives.items():
        if record.status != "verified":
            raise ServiceError("archive_unverified", "Archive is not verified")
        context.checkpoint(stage="restoring", archive_id=identity, restored_ids=restored)
        staging = storage.path(f"restore-cache/{context.job.id}/{identity}")
        staging.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            encrypted, plain = staging/"object.aesgcm", staging/"payload.tar.zst"
            store.download(record.object_key, encrypted, record.size)
            if encrypted.stat().st_size != record.size or digest(encrypted) != record.sha256:
                raise ServiceError("archive_integrity", "Downloaded object failed checksum verification")
            encryption.decrypt(encrypted, plain)
            catalog = {m["id"]: m for m in record.manifest["members"]}
            wanted = {r.id: r for r in rows if r.archive_id == identity}
            seen, extracted = set(), 0
            with plain.open("rb") as f, zstandard.ZstdDecompressor().stream_reader(f) as z, tarfile.open(fileobj=z, mode="r|") as tar:
                for entry in tar:
                    if not entry.isfile() or "/" in entry.name or entry.name in seen:
                        raise ServiceError("unsafe_archive", "Archive has duplicate, nonregular or unsafe members")
                    seen.add(entry.name)
                    if entry.name == "manifest.json":
                        if entry.size > 1_000_000:
                            raise ServiceError("unsafe_archive", "Archive manifest exceeds size limit")
                        manifest = json.loads(tar.extractfile(entry).read())
                        if manifest != record.manifest:
                            raise ServiceError("archive_integrity", "Archive manifest does not match catalog")
                        continue
                    m = catalog.get(entry.name)
                    if m is None or entry.size != m["size"]:
                        raise ServiceError("unsafe_archive", "Archive member does not match manifest")
                    extracted += entry.size
                    if extracted > sum(x["size"] for x in catalog.values()):
                        raise ServiceError("unsafe_archive", "Decompression exceeds declared size")
                    if entry.name in wanted:
                        temp = staging/entry.name
                        with tar.extractfile(entry) as src, temp.open("wb") as dst:
                            shutil.copyfileobj(src, dst, 1024*1024)
                        if digest(temp) != m["sha256"]:
                            raise ServiceError("archive_integrity", "Restored member failed checksum")
            if seen != set(catalog)|{"manifest.json"}:
                raise ServiceError("archive_integrity", "Archive is incomplete")
            for identity_, row in wanted.items():
                target = storage.path(row.path)
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                temp = staging/identity_
                temp.chmod(0o600)
                os.replace(temp, target)
                with context.database.session() as db:
                    current = owned(db, Artifact, identity_, owner)
                    current.status, current.restored_at = "hot", now()
                restored.append(identity_)
        finally:
            shutil.rmtree(staging, ignore_errors=True)
    return {"restored_artifact_ids": restored}


def backup(context):
    # pg_dump is consistent and does not copy a live PostgreSQL data directory.
    import time
    settings, storage = context.settings, context.storage
    with context.database.session() as db:
        storage.reserve(db, context.job.id, context.job.owner_id, settings.limits.restore_bytes, maintenance=True)
    destination = storage.path(f"backups/{context.job.id}-{context.job.attempts}.dump")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PGPASSWORD": secret_file(settings.database_password_file)}
    process, completed, started = None, False, time.monotonic()
    try:
        with destination.open("xb") as output:
            process = subprocess.Popen(["pg_dump", "-h", settings.database_host, "-p", str(settings.database_port),
                                      "-U", settings.database_user, "-d", settings.database_name, "-Fc"],
                                      stdout=output, stderr=subprocess.DEVNULL, env=env)
            while process.poll() is None:
                if destination.stat().st_size > settings.limits.restore_bytes:
                    raise ServiceError("backup_size_limit", "Database backup exceeded configured maximum")
                if time.monotonic()-started > settings.limits.task_timeout_seconds:
                    raise ServiceError("backup_timeout", "Database backup exceeded configured wall time")
                context.checkpoint(stage="database_backup")
                time.sleep(1)
        if process.returncode:
            raise ServiceError("backup_failed", "Consistent database backup failed; check private database connectivity")
        if destination.stat().st_size > settings.limits.restore_bytes:
            raise ServiceError("backup_size_limit", "Database backup exceeded configured maximum")
        destination.chmod(0o600)
        completed = True
        with context.database.session() as db:
            artifact = storage.register(db, context.job.owner_id, destination, "backup")
            identity = artifact.id
        # A failed cloud upload retains the consistent dump for explicit recovery.
        return archive(context, force_ids=[identity])
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        if not completed:
            destination.unlink(missing_ok=True)


def handle(context):
    if context.job.kind == "archive":
        return archive(context)
    if context.job.kind == "restore":
        return restore(context)
    if context.job.kind == "backup":
        return backup(context)
    raise ServiceError("invalid_task", "Unsupported storage task")
