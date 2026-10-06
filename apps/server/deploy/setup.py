"""Render one private .env into the server's internal config and secret mounts.

Executed inside the server image, so setup needs no host Python dependencies.
The env file is data: never source it in a shell or log its credential values.
"""
import argparse
import base64
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import tempfile

from apps.server.__main__ import initialize
from apps.server.config import Settings


ROLES = ("admin", "api", "scanner", "scheduler", "storage", "imports", "codex")
SECRET_NAMES = {role.upper() + "_DATABASE_PASSWORD": role + "_database_password" for role in ROLES}
SECRET_NAMES.update(API_TOKEN="api_token", MASSIVE_API_KEY="massive_api_key",
                    R2_ACCESS_KEY="r2_access_key", R2_SECRET_KEY="r2_secret_key")
COMPOSE_KEYS = ("BIND_ADDRESS", "SERVER_PORT", "WEB_BIND_ADDRESS", "WEB_PORT", "API_WORKERS",
                "POSTGRES_MEMORY", "POSTGRES_CPUS", "API_MEMORY", "API_CPUS", "SCANNER_MEMORY", "SCANNER_CPUS",
                "SCHEDULER_MEMORY", "SCHEDULER_CPUS", "IMPORT_MEMORY", "IMPORT_CPUS", "STORAGE_MEMORY", "STORAGE_CPUS",
                "WEB_MEMORY", "WEB_CPUS", "CODEX_MEMORY", "CODEX_CPUS")
PROTECTED = ("data_dir", "database_password_file", "api_token_file", "archive_key_file",
             "r2_access_key_file", "r2_secret_key_file", "codex_profile_dir")


class SetupError(ValueError):
    pass


def parse_env(text):
    result = {}
    for number, line in enumerate(text.splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = re.fullmatch(r"\s*([A-Z][A-Z0-9_]*)\s*=(.*)", line)
        if not match:
            raise SetupError(f"Invalid env assignment at line {number}")
        key, raw = match.groups()
        if key in result:
            raise SetupError(f"Duplicate env key {key}")
        try:
            pieces = shlex.split(raw, comments=True)
        except ValueError:
            raise SetupError(f"Invalid quoting for {key}") from None
        if len(pieces) > 1:
            raise SetupError(f"Quote values containing spaces for {key}")
        result[key] = pieces[0] if pieces else ""
    return result


def write_private(path, content):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    data = content.encode() if isinstance(content, str) else content
    if path.exists() and path.read_bytes() == data:
        path.chmod(0o600)
        return
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(data)
    temporary.chmod(0o600)
    temporary.replace(path)


def env_text(values):
    return "# CoSoup setup: edit this file, then rerun setup.sh. Values are never executed.\n" + "".join(
        f"{key}={shlex.quote(str(value))}\n" for key, value in values.items())


def prepare(root, mode, host_root, uid, gid, architecture, origin=None):
    root = Path(root).resolve()
    if root.stat().st_mode & 0o077:
        raise SetupError("The deployment directory must have private 0700 permissions")
    env_path, config_path = root / ".env", root / "config/server.json"
    if not env_path.exists() and config_path.exists():
        raise SetupError("This is an existing manual deployment. Select a new setup root to preserve it")
    fresh = not config_path.exists()
    values = parse_env(env_path.read_text()) if env_path.exists() else {}
    defaults = {"MODE": mode, "COMPOSE_PROJECT_NAME": f"cosoup-{mode}", "TIMEZONE": "Asia/Jerusalem",
                "BIND_ADDRESS": "127.0.0.1", "SERVER_PORT": "8080", "WEB_BIND_ADDRESS": "127.0.0.1", "WEB_PORT": "8081",
                "BROWSER_ORIGIN": origin or "", "BROWSER_SECURE_COOKIE": str(mode == "prod").lower(),
                "MASSIVE_API_KEY": "", "R2_ENDPOINT": "", "R2_BUCKET": "", "R2_ACCESS_KEY": "", "R2_SECRET_KEY": "",
                "CODEX_ENABLED": "false", "CODEX_SANDBOX_VERIFIED": "false", "AUTOMATIC_ARCHIVES": "false", "ARCHIVE_EVICT": "false"}
    for key, default in defaults.items():
        values.setdefault(key, default)
    if values["MODE"] != mode:
        raise SetupError("The env MODE differs from this setup mode; use separate roots for dev and prod")
    project = values["COMPOSE_PROJECT_NAME"]
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", project):
        raise SetupError("Invalid COMPOSE_PROJECT_NAME")
    metadata_path = root / ".deployment.json"
    metadata = {"mode": mode, "project": project, "host_root": host_root}
    if metadata_path.exists() and json.loads(metadata_path.read_text()) != metadata:
        raise SetupError("Deployment identity changed; do not reuse one database root across projects")
    for key in ["API_TOKEN", *(role.upper() + "_DATABASE_PASSWORD" for role in ROLES), "ARCHIVE_KEY_BASE64"]:
        if not values.get(key):
            if not fresh:
                raise SetupError(f"Missing existing credential {key}; restore it instead of regenerating it")
            values[key] = base64.b64encode(secrets.token_bytes(32)).decode() if key == "ARCHIVE_KEY_BASE64" else secrets.token_urlsafe(48)

    # Persist the canonical file even when prod still needs its private HTTPS origin.
    write_private(env_path, env_text(values))
    if mode == "prod" and not values["BROWSER_ORIGIN"]:
        raise SetupError("Set BROWSER_ORIGIN to your private HTTPS origin in .env, then rerun setup")
    try:
        ports = {key: int(values[key]) for key in ["SERVER_PORT", "WEB_PORT"]}
    except ValueError:
        raise SetupError("SERVER_PORT and WEB_PORT must be integer ports") from None
    if any(not 1024 <= port <= 65535 for port in ports.values()) or len(set(ports.values())) != 2:
        raise SetupError("Use distinct unprivileged SERVER_PORT and WEB_PORT values")
    if mode == "dev":
        expected_origin = f"http://127.0.0.1:{ports['WEB_PORT']}"
        if values["BROWSER_ORIGIN"] not in {"", expected_origin} or values["BROWSER_SECURE_COOKIE"] != "false":
            raise SetupError("Dev setup requires the exact loopback HTTP origin and BROWSER_SECURE_COOKIE=false")
        if any(values[key] != "127.0.0.1" for key in ["BIND_ADDRESS", "WEB_BIND_ADDRESS"]):
            raise SetupError("Dev setup binds only to 127.0.0.1")
        values["BROWSER_ORIGIN"] = expected_origin
    elif values["BROWSER_SECURE_COOKIE"] != "true":
        raise SetupError("Prod setup requires BROWSER_SECURE_COOKIE=true")

    model = Settings().model_dump(mode="json")
    settings_keys = {key.upper(): key for key in model if key not in PROTECTED and key != "limits"}
    limit_keys = {"LIMIT_" + key.upper(): key for key in model["limits"]}
    allowed = set(settings_keys) | set(limit_keys) | set(COMPOSE_KEYS) | set(SECRET_NAMES) | {"MODE", "COMPOSE_PROJECT_NAME", "ARCHIVE_KEY_BASE64"}
    if set(values) - allowed:
        raise SetupError("Unknown env keys: " + ", ".join(sorted(set(values) - allowed)))
    for key, field in settings_keys.items():
        if key in values:
            model[field] = values[key] if values[key] else None
    for key, field in limit_keys.items():
        if key in values:
            model["limits"][field] = values[key]
    try:
        settings = Settings(**model)
        archive_key = base64.b64decode(values["ARCHIVE_KEY_BASE64"], validate=True)
    except ValueError:
        raise SetupError("Invalid server settings or ARCHIVE_KEY_BASE64; check the private env file") from None
    if len(archive_key) != 32:
        raise SetupError("ARCHIVE_KEY_BASE64 must encode exactly 32 bytes")
    if len(values["API_TOKEN"]) < 32:
        raise SetupError("API_TOKEN must contain at least 32 characters")
    for key, secret_name in SECRET_NAMES.items():
        existing = root / "secrets" / secret_name
        if key == "ADMIN_DATABASE_PASSWORD" and existing.exists() and existing.read_text().strip() != values[key]:
            raise SetupError("Do not rotate the PostgreSQL admin password by editing .env; existing database authentication would fail")
    existing_key = root / "secrets/archive_key"
    if existing_key.exists() and not fresh and existing_key.read_bytes() != archive_key:
        raise SetupError("Preserve ARCHIVE_KEY_BASE64 to keep existing archives recoverable")

    initialize(root, settings.timezone, host_root)
    for key, name in SECRET_NAMES.items():
        write_private(root / "secrets" / name, values[key])
    write_private(root / "secrets/archive_key", archive_key)
    write_private(config_path, settings.model_dump_json(indent=2) + "\n")
    native_platform = "linux/arm64" if architecture in {"arm64", "aarch64"} else "linux/amd64"
    compose = {"SERVER_ROOT": host_root, "SCANNER_UID": uid, "SCANNER_GID": gid, "MODE": mode,
               "COMPOSE_PROJECT_NAME": project, "COSOUP_WEB_PLATFORM": native_platform,
               "COSOUP_CODEX_PLATFORM": native_platform}
    compose.update({key: values[key] for key in COMPOSE_KEYS if key in values})
    write_private(root / "compose.env", env_text(compose))
    write_private(env_path, env_text(values))
    write_private(metadata_path, json.dumps(metadata) + "\n")
    write_private(root / ".browser-origin", settings.browser_origin + "\n")
    return {"mode": mode, "project": project, "origin": settings.browser_origin}


def main():
    parser = argparse.ArgumentParser(description="Prepare private CoSoup files from one env source")
    parser.add_argument("--root", default="/private")
    parser.add_argument("--host-root", required=True)
    parser.add_argument("--mode", choices=["dev", "prod"], required=True)
    parser.add_argument("--uid", type=int, required=True)
    parser.add_argument("--gid", type=int, required=True)
    parser.add_argument("--architecture", required=True)
    parser.add_argument("--origin")
    args = parser.parse_args()
    try:
        result = prepare(args.root, args.mode, args.host_root, args.uid, args.gid, args.architecture, args.origin)
    except (SetupError, OSError, json.JSONDecodeError) as error:
        parser.exit(1, f"CoSoup setup: {error}\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
