"""Versioned AES-256-GCM file envelope; plaintext is published only after tag verification."""
import hashlib
import os
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from ..config import secret_file
from ..errors import ServiceError

MAGIC = b"SSR1"
HEADER_SIZE = 32  # Magic, 16-byte public key fingerprint, 12-byte random nonce.


class Encryption:
    def __init__(self, key_file):
        self.key = secret_file(key_file, binary=True)
        if len(self.key) != 32:
            raise ServiceError("archive_key_invalid", "Archive encryption key must contain exactly 32 private random bytes")
        self.key_id = hashlib.sha256(self.key).digest()[:16]

    def encrypt(self, source, destination):
        header = MAGIC+self.key_id+os.urandom(12)
        encryptor = Cipher(algorithms.AES(self.key), modes.GCM(header[-12:])).encryptor()
        encryptor.authenticate_additional_data(header)
        with Path(source).open("rb") as src, Path(destination).open("wb") as dst:
            dst.write(header)
            for b in iter(lambda: src.read(1024*1024), b""):
                dst.write(encryptor.update(b))
            dst.write(encryptor.finalize())
            dst.write(encryptor.tag)
        Path(destination).chmod(0o600)

    def decrypt(self, source, destination):
        try:
            with Path(source).open("rb") as src, Path(destination).open("wb") as dst:
                header = src.read(HEADER_SIZE)
                if len(header) != HEADER_SIZE or header[:4] != MAGIC or header[4:20] != self.key_id:
                    raise ServiceError("archive_key_mismatch", "Archive format or encryption key does not match")
                remaining = Path(source).stat().st_size-HEADER_SIZE-16
                if remaining < 0:
                    raise ServiceError("archive_integrity", "Truncated encrypted archive")
                src.seek(-16, 2)
                tag = src.read(16)
                src.seek(HEADER_SIZE)
                dec = Cipher(algorithms.AES(self.key), modes.GCM(header[-12:], tag)).decryptor()
                dec.authenticate_additional_data(header)
                while remaining:
                    chunk = src.read(min(remaining, 1024*1024))
                    if not chunk:
                        raise ServiceError("archive_integrity", "Truncated encrypted archive")
                    dst.write(dec.update(chunk))
                    remaining -= len(chunk)
                dst.write(dec.finalize())
            Path(destination).chmod(0o600)
        except (InvalidTag, ServiceError):
            Path(destination).unlink(missing_ok=True)
            raise ServiceError("archive_integrity", "Archive authentication failed; no contents published") from None
