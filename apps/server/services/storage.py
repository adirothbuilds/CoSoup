import hashlib
import os
import shutil
import fcntl
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path

from sqlalchemy import delete, func, select, text

from ..errors import ServiceError
from ..persistence.models import Artifact, Reservation, now
from .jobs import utc


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


class Storage:
    def __init__(self, settings):
        self.settings, self.root = settings, settings.data_dir.resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.root.stat().st_mode & 0o077:
            raise ValueError("Server data root must have private 0700 permissions")

    def path(self, relative):
        p = Path(relative)
        if p.is_absolute() or ".." in p.parts:
            raise ServiceError("unsafe_path", "Artifact path is outside managed storage")
        target = (self.root / p).resolve()
        if not target.is_relative_to(self.root) or target == self.root:
            raise ServiceError("unsafe_path", "Artifact path is outside managed storage")
        return target

    def usage(self):
        if self.settings.storage_usage_mode == "filesystem":
            stat = os.statvfs(self.root)
            return (stat.f_blocks-stat.f_bfree)*stat.f_frsize
        total = 0
        for base, dirs, files in os.walk(self.root, followlinks=False):
            dirs[:] = [d for d in dirs if not (Path(base)/d).is_symlink()]
            for name in files:
                p = Path(base)/name
                if not p.is_symlink():
                    try:
                        total += p.stat().st_blocks * 512
                    except FileNotFoundError:
                        pass
        return total

    @contextmanager
    def reader(self):
        path = self.root/"readers.lock"
        if not path.exists():
            path.touch(mode=0o600)
        with path.open("rb") as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            yield

    @contextmanager
    def evictor(self):
        with (self.root/"readers.lock").open("a+") as f:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                yield False
                return
            yield True

    def status(self, db):
        used = self.usage()
        reserved = db.scalar(select(func.coalesce(func.sum(Reservation.bytes), 0)).where(Reservation.expires_at > now()))
        limits = self.settings.limits
        free = shutil.disk_usage(self.root).free
        return {"used_bytes": used, "reserved_bytes": reserved, "filesystem_free_bytes": free,
                "capacity_bytes": limits.capacity_bytes, "admission_stop_bytes": limits.admission_stop_bytes,
                "pressure": used+reserved >= limits.archive_trigger_bytes,
                "admission_blocked": used+reserved >= limits.admission_stop_bytes,
                "quota_enforcement": "Application admission only; configure a host filesystem quota for a hard ceiling"}

    def reserve(self, db, identity, owner, size, maintenance=False):
        if size <= 0:
            raise ValueError("Reservation must be positive")
        if db.bind.dialect.name == "postgresql":
            db.execute(text("SELECT pg_advisory_xact_lock(194021)"))
        db.execute(delete(Reservation).where(Reservation.expires_at <= now()))
        old = db.get(Reservation, identity)
        if old:
            db.delete(old)
            db.flush()
        current = self.status(db)
        ceiling = self.settings.limits.capacity_bytes if maintenance else self.settings.limits.admission_stop_bytes
        if current["used_bytes"]+current["reserved_bytes"]+size > ceiling or current["filesystem_free_bytes"] < size:
            raise ServiceError("storage_pressure", "Storage reservation cannot fit; archive or free verified data before resuming", 503)
        db.add(Reservation(id=identity, owner_id=owner, bytes=size,
                           expires_at=now()+timedelta(seconds=max(600, self.settings.lease_seconds*2))))

    def register(self, db, owner, path, dataset, metadata=None):
        path = Path(path).resolve()
        if not path.is_relative_to(self.root) or path.is_symlink():
            raise ServiceError("unsafe_path", "Cannot catalog external files")
        relative = str(path.relative_to(self.root))
        h, size = digest(path), path.stat().st_size
        old = db.scalar(select(Artifact).where(Artifact.owner_id == owner, Artifact.path == relative))
        if old:
            if old.sha256 != h:
                raise ServiceError("artifact_changed", "Immutable artifact contents changed")
            old.status = "hot"
            return old
        row = Artifact(owner_id=owner, dataset=dataset, path=relative, sha256=h, size=size, metadata_=metadata or {})
        db.add(row)
        db.flush()
        return row

    def read(self, artifact, max_bytes=None):
        p = self.path(artifact.path)
        if not p.is_file():
            raise ServiceError("restore_required", "Artifact is archived; submit a restore job", 409)
        if max_bytes and p.stat().st_size > max_bytes:
            raise ServiceError("artifact_too_large", "Artifact exceeds response limit", 413)
        if digest(p) != artifact.sha256:
            raise ServiceError("checksum_mismatch", "Artifact failed integrity validation")
        return p
