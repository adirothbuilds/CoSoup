import gzip
import json
import os
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def state_directory(value=None):
    path = Path(value or os.environ.get("SCANNER_STATE_DIR", "/workspace/stock-scanner-state")).expanduser().resolve()
    if path in {Path("/"), Path("/workspace"), Path("/tmp")} or path == ROOT or path.is_relative_to(ROOT):
        raise ValueError("SCANNER_STATE_DIR must be outside the repository (private raw data and reports)")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.stat().st_mode & 0o077:
        raise ValueError("Private state directory grants group/other access; use an owned directory with mode 0700")
    return path


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".write-")
    try:
        with os.fdopen(fd, "wb") as f:
            body = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()
            f.write(gzip.compress(body) if path.suffix == ".gz" else body)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def read_json(path):
    path = Path(path)
    body = path.read_bytes()
    return json.loads(gzip.decompress(body) if path.suffix == ".gz" else body)
