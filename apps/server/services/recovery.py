"""Offline recovery of a downloaded archive, without a surviving database catalog."""
import json
import os
import shutil
import tarfile
import tempfile
from pathlib import Path

import zstandard

from ..adapters.encryption import Encryption
from ..errors import ServiceError
from .storage import digest


def recover(source, key_file, destination, max_bytes=1_000_000_000, expected_hash=None):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    checkout = Path(__file__).resolve().parents[3]
    if destination.exists() or destination.is_relative_to(checkout):
        raise ServiceError("unsafe_destination", "Recovery requires a new private directory outside the repository")
    if source.stat().st_size > max_bytes:
        raise ServiceError("restore_size_limit", "Encrypted archive exceeds recovery limit")
    if expected_hash and digest(source) != expected_hash:
        raise ServiceError("archive_integrity", "Encrypted archive failed expected checksum")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    staging = Path(tempfile.mkdtemp(prefix=".recovery-", dir=destination.parent))
    try:
        plain, output = staging/"payload.tar.zst", staging/"members"
        output.mkdir(mode=0o700)
        Encryption(key_file).decrypt(source, plain)
        members, total, manifest = {}, 0, None
        with plain.open("rb") as f, zstandard.ZstdDecompressor().stream_reader(f) as z, tarfile.open(fileobj=z, mode="r|") as tar:
            for entry in tar:
                if not entry.isfile() or not entry.name.isalnum() and entry.name != "manifest.json" or entry.name in members:
                    raise ServiceError("unsafe_archive", "Archive contains unsafe or duplicate entries")
                if entry.name == "manifest.json":
                    if manifest is not None or entry.size > 1_000_000:
                        raise ServiceError("unsafe_archive", "Invalid archive manifest")
                    manifest = json.loads(tar.extractfile(entry).read())
                    continue
                total += entry.size
                if total > max_bytes:
                    raise ServiceError("restore_size_limit", "Expanded archive exceeds recovery limit")
                path = output/entry.name
                with tar.extractfile(entry) as src, path.open("wb") as dst:
                    shutil.copyfileobj(src, dst, 1024*1024)
                path.chmod(0o600)
                members[entry.name] = (entry.size, digest(path))
        if not isinstance(manifest, dict) or manifest.get("version") != 1:
            raise ServiceError("archive_integrity", "Unsupported archive manifest")
        expected = {m["id"]: (m["size"], m["sha256"]) for m in manifest["members"]}
        if members != expected or len(expected) != len(manifest["members"]):
            raise ServiceError("archive_integrity", "Archive members failed manifest validation")
        # Publish opaque member IDs only; untrusted manifest paths are never used.
        (output/"manifest.json").write_text(json.dumps(manifest, indent=2))
        (output/"manifest.json").chmod(0o600)
        os.replace(output, destination)
        return {"destination": str(destination), "archive_id": manifest["archive_id"], "members": len(members)}
    finally:
        shutil.rmtree(staging, ignore_errors=True)
