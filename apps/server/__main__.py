"""Operational entrypoints; no credentials are accepted as command arguments."""
import argparse
import json
import os
import secrets
from pathlib import Path

from .config import Settings, secret_file
from .persistence.database import Database


def initialize(root, timezone, host_root=None):
    root = Path(root).resolve()
    checkout = Path(__file__).resolve().parents[2]
    if root in {Path("/"), Path("/tmp"), Path("/workspace")} or root == checkout or root.is_relative_to(checkout):
        raise ValueError("Private deployment root must be outside the repository")
    for d in [root, root/"config", root/"secrets", root/"data"]:
        d.mkdir(parents=True, exist_ok=True, mode=0o700)
    for name in ["postgres", "market", "reports", "uploads", "job-workspaces", "archive-staging", "restore-cache", "backup-staging", "backups", "logs", "codex-profile"]:
        (root/"data"/name).mkdir(exist_ok=True, mode=0o700)
    lock = root/"data/readers.lock"
    if not lock.exists():
        lock.touch(mode=0o600)
    for name in ["admin", "api", "scanner", "scheduler", "storage", "imports", "codex"]:
        path = root/"secrets"/(name+"_database_password")
        if not path.exists():
            path.write_text(secrets.token_urlsafe(40))
            path.chmod(0o600)
    for name in ["api_token", "archive_key", "massive_api_key", "r2_access_key", "r2_secret_key"]:
        path = root/"secrets"/name
        if not path.exists():
            path.write_bytes(secrets.token_bytes(32) if name == "archive_key" else
                             secrets.token_urlsafe(48).encode() if name == "api_token" else b"")
            path.chmod(0o600)
    config = root/"config/server.json"
    if not config.exists():
        config.write_text(Settings(timezone=timezone).model_dump_json(indent=2))
        config.chmod(0o600)
    env = root/"compose.env"
    if not env.exists():
        env.write_text(f"SERVER_ROOT={host_root or root}\nSCANNER_UID={os.getuid()}\nSCANNER_GID={os.getgid()}\nBIND_ADDRESS=127.0.0.1\nSERVER_PORT=8080\n")
        env.chmod(0o600)
    return {"root": str(root), "config_created": True, "credentials": "Private files created; existing values preserved",
            "quota": "Provision a dedicated filesystem/quota before relying on a hard storage ceiling"}


def roles(database, directory):
    """Fixed role names and grants. Called only by the admin migration service."""
    from psycopg import sql
    common = {"jobs", "events", "reservations", "policies", "schema_version"}
    readable = {
        "api": None,
        "scanner": common | {"rules", "reports", "signals", "artifacts", "portfolios", "transactions"},
        "scheduler": common | {"schedules", "occurrences"},
        "storage": None,  # Consistent encrypted pg_dump requires reading all tables.
        "imports": common | {"imports", "artifacts"},
        "codex": common | {"reports", "artifacts", "portfolios", "transactions"},
    }
    writable = {
        "api": {"jobs", "events", "reservations", "policies", "schedules", "rules", "portfolios", "transactions", "imports", "artifacts"},
        "scanner": common | {"reports", "signals", "artifacts"},
        "scheduler": {"jobs", "events", "schedules", "occurrences"},
        "storage": common | {"artifacts", "archives"},
        "imports": common | {"imports"},
        "codex": common | {"reports", "artifacts"},
    }
    with database.engine.begin() as connection:
        raw = connection.connection.driver_connection
        for role, tables in writable.items():
            name = "scanner_"+role
            password = secret_file(Path(directory)/(role+"_database_password"))
            with raw.cursor() as cursor:
                cursor.execute("SELECT 1 FROM pg_roles WHERE rolname=%s", (name,))
                exists = cursor.fetchone()
                statement = sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}" if exists else "CREATE ROLE {} WITH LOGIN PASSWORD {}")
                cursor.execute(statement.format(sql.Identifier(name), sql.Literal(password)))
                cursor.execute(sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(name)))
                # Wrapper reads are owner-scoped. Model/parse child processes receive
                # no database role or credential. Storage needs SELECT for pg_dump.
                cursor.execute(sql.SQL("REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM {}").format(sql.Identifier(name)))
                if readable[role] is None:
                    cursor.execute(sql.SQL("GRANT SELECT ON ALL TABLES IN SCHEMA public TO {}").format(sql.Identifier(name)))
                else:
                    for table in sorted(readable[role] | tables):
                        cursor.execute(sql.SQL("GRANT SELECT ON TABLE {} TO {}").format(sql.Identifier(table), sql.Identifier(name)))
                cursor.execute(sql.SQL("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {}").format(sql.Identifier(name)))
                for table in sorted(tables):
                    cursor.execute(sql.SQL("GRANT INSERT, UPDATE, DELETE ON TABLE {} TO {}").format(sql.Identifier(table), sql.Identifier(name)))


def main():
    parser = argparse.ArgumentParser(description="Private modular research server operations")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="Create private configuration/credential placeholders without overwriting values")
    init.add_argument("--root", required=True)
    init.add_argument("--timezone", default="UTC")
    init.add_argument("--host-root", help="Actual host path when init is run through a container bind mount")
    recovery = sub.add_parser("recover-archive", help="Authenticate and unpack a downloaded archive without PostgreSQL")
    recovery.add_argument("--file", required=True)
    recovery.add_argument("--key-file", required=True)
    recovery.add_argument("--destination", required=True)
    recovery.add_argument("--max-bytes", type=int, default=1_000_000_000)
    recovery.add_argument("--expected-sha256")
    migrate = sub.add_parser("migrate", help="Explicit versioned schema bootstrap and worker roles")
    migrate.add_argument("--role-secrets-dir")
    sub.add_parser("seed-schedules", help="Create disabled configurable daily/weekly/archive/backup schedules")
    api = sub.add_parser("api")
    api.add_argument("--host", default="0.0.0.0")
    api.add_argument("--port", type=int, default=8080)
    api.add_argument("--workers", type=int, default=1)
    arguments = parser.parse_args()
    if arguments.command == "init":
        print(json.dumps(initialize(arguments.root, arguments.timezone, arguments.host_root)))
    elif arguments.command == "recover-archive":
        from .services.recovery import recover
        print(json.dumps(recover(arguments.file, arguments.key_file, arguments.destination, arguments.max_bytes, arguments.expected_sha256)))
    elif arguments.command == "api":
        import uvicorn
        uvicorn.run("apps.server.api.main:app", host=arguments.host, port=arguments.port,
                    workers=arguments.workers, access_log=False)
    else:
        settings = Settings.load()
        database = Database(settings)
        if arguments.command == "migrate":
            database.migrate()
            if arguments.role_secrets_dir:
                roles(database, arguments.role_secrets_dir)
            print(json.dumps({"schema_version": 1, "roles_configured": bool(arguments.role_secrets_dir)}))
        else:
            from sqlalchemy import select
            from .persistence.models import Schedule, now
            from .workers.scheduler.triggers import next_occurrence
            examples = [
                ("Daily market scan", {"type": "market_close"}, {"type": "daily_scan", "research": "current"}, "catch_up"),
                ("Weekly market summary", {"type": "market_close", "frequency": "weekly"}, {"type": "weekly_summary"}, "run_once"),
                ("Monthly private archive", {"type": "local_cron", "expression": settings.archive_cron, "timezone": settings.timezone}, {"type": "archive_completed_months"}, "run_once"),
                ("Nightly metadata backup", {"type": "local_cron", "expression": settings.backup_cron, "timezone": settings.timezone}, {"type": "database_backup"}, "run_once"),
            ]
            with database.session() as db:
                for name, trigger, task, missed in examples:
                    if db.scalar(select(Schedule).where(Schedule.owner_id == settings.owner_id, Schedule.name == name)) is None:
                        next_at, _ = next_occurrence(trigger, now(), settings)
                        db.add(Schedule(owner_id=settings.owner_id, name=name, trigger=trigger, task=task,
                                        missed_policy=missed, next_at=next_at, enabled=False))
            print(json.dumps({"schedules": "Defaults prepared, disabled until explicitly enabled"}))


if __name__ == "__main__":
    main()
