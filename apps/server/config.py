"""Validated configuration; credentials are read from private files, never serialized."""
import json
import os
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Limits(BaseModel):
    model_config = ConfigDict(extra="forbid")
    capacity_bytes: int = Field(200_000_000_000, gt=0)
    target_bytes: int = Field(140_000_000_000, gt=0)
    archive_trigger_bytes: int = Field(160_000_000_000, gt=0)
    admission_stop_bytes: int = Field(180_000_000_000, gt=0)
    upload_bytes: int = Field(20_000_000, gt=0)
    archive_shard_bytes: int = Field(256_000_000, gt=0)
    restore_bytes: int = Field(1_000_000_000, gt=0)
    scan_reservation_bytes: int = Field(1_000_000_000, gt=0)
    import_reservation_bytes: int = Field(200_000_000, gt=0)
    agent_reservation_bytes: int = Field(100_000_000, gt=0)
    hot_sessions: int = Field(300, ge=260)
    restore_ttl_days: int = Field(7, ge=1)
    log_retention_days: int = Field(90, ge=1)
    max_range_sessions: int = Field(260, ge=1)
    pdf_pages: int = Field(30, ge=1)
    image_pixels: int = Field(30_000_000, gt=0)
    task_timeout_seconds: int = Field(900, ge=10)
    task_output_bytes: int = Field(5_000_000, gt=0)

    @model_validator(mode="after")
    def ordered(self):
        if not self.target_bytes < self.archive_trigger_bytes < self.admission_stop_bytes < self.capacity_bytes:
            raise ValueError("Storage watermarks must be strictly increasing below capacity")
        if self.upload_bytes >= self.admission_stop_bytes:
            raise ValueError("Upload limit exceeds admission capacity")
        return self


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    data_dir: Path = Path("/var/lib/stock-scanner")
    timezone: str = "UTC"
    storage_usage_mode: Literal["tree", "filesystem"] = "tree"
    owner_id: str = "owner"
    database_host: str = "postgres"
    database_port: int = 5432
    database_name: str = "scanner"
    database_user: str = "scanner_api"
    database_password_file: Path = Path("/run/secrets/database_password")
    api_token_file: Path = Path("/run/secrets/api_token")
    browser_origin: str | None = None
    browser_secure_cookie: bool = True
    browser_session_hours: int = Field(12, ge=1, le=168)
    poll_seconds: float = Field(5, gt=0)
    lease_seconds: int = Field(120, ge=10)
    max_job_attempts: int = Field(3, ge=1, le=10)
    settlement_minutes: int = Field(30, ge=0)
    archive_cron: str = "0 2 1 * *"
    backup_cron: str = "0 3 * * *"
    archive_after_days: int = Field(31, ge=1)
    unique_upload_backup_days: int = Field(1, ge=0)
    archive_evict: bool = False
    automatic_archives: bool = False
    maintenance_interval_seconds: int = Field(3600, ge=60)
    r2_endpoint: str | None = None
    r2_bucket: str | None = None
    r2_prefix: str = "stock-scanner"
    r2_access_key_file: Path = Path("/run/secrets/r2_access_key")
    r2_secret_key_file: Path = Path("/run/secrets/r2_secret_key")
    archive_key_file: Path = Path("/run/secrets/archive_key")
    codex_enabled: bool = False
    codex_binary: str = "codex"
    codex_model: str | None = None
    codex_profile_dir: Path = Path("/var/lib/codex-profile")
    # Set only after an operator verifies the deployed CLI sandbox on the host.
    codex_sandbox_verified: bool = False
    limits: Limits = Field(default_factory=Limits)

    @model_validator(mode="after")
    def valid(self):
        ZoneInfo(self.timezone)
        root = self.data_dir.resolve()
        repo = Path(__file__).resolve().parents[2]
        if root in {Path("/"), Path("/tmp"), Path("/workspace")} or root.is_relative_to(repo):
            raise ValueError("Server data must be outside the source checkout")
        import re
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", self.owner_id):
            raise ValueError("Invalid owner ID")
        if self.browser_origin:
            from urllib.parse import urlsplit
            origin = urlsplit(self.browser_origin)
            if origin.username or origin.password or origin.path or origin.query or origin.fragment or not origin.hostname:
                raise ValueError("Browser origin must contain only scheme, host and optional port")
            if self.browser_secure_cookie:
                if origin.scheme != "https":
                    raise ValueError("Browser sessions require an HTTPS origin")
            elif origin.scheme != "http" or origin.hostname not in {"localhost", "127.0.0.1", "::1"}:
                raise ValueError("Insecure development sessions are limited to an explicit loopback HTTP origin")
        if self.r2_endpoint:
            from urllib.parse import urlsplit
            u = urlsplit(self.r2_endpoint)
            if u.scheme != "https" or not u.hostname or not u.hostname.endswith(".r2.cloudflarestorage.com") or u.username or u.password or u.path not in {"", "/"} or u.query:
                raise ValueError("R2 endpoint must be the private HTTPS account endpoint")
        if "/" in self.r2_prefix.strip("/") or ".." in self.r2_prefix:
            raise ValueError("Archive prefix must be a single safe component")
        return self

    @classmethod
    def load(cls):
        path = os.environ.get("SCANNER_SERVER_CONFIG")
        values = json.loads(Path(path).read_text()) if path else {}
        overrides = {"SCANNER_SERVER_DATA_DIR": "data_dir", "SCANNER_SERVER_TIMEZONE": "timezone",
                     "SCANNER_DATABASE_USER": "database_user", "SCANNER_DATABASE_PASSWORD_FILE": "database_password_file"}
        for name, field in overrides.items():
            if name in os.environ:
                values[field] = os.environ[name]
        return cls(**values)


def secret_file(path: Path, binary=False):
    data = Path(path).read_bytes()
    if binary:
        return data
    value = data.decode().strip()
    if not value:
        raise ValueError("Required private credential file is empty")
    return value
