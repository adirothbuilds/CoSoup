from contextlib import contextmanager

from sqlalchemy import create_engine, select, event, inspect
from sqlalchemy.engine import URL
from sqlalchemy.orm import sessionmaker

from ..config import secret_file
from .models import Base, Version

SCHEMA_VERSION = 1


class Database:
    def __init__(self, settings=None, url=None):
        if url is None:
            url = URL.create("postgresql+psycopg", username=settings.database_user,
                             password=secret_file(settings.database_password_file), host=settings.database_host,
                             port=settings.database_port, database=settings.database_name)
        kwargs = {"connect_args": {"check_same_thread": False}} if str(url).startswith("sqlite") else {}
        self.engine = create_engine(url, pool_pre_ping=True, **kwargs)
        if self.engine.dialect.name == "sqlite":
            # Python sqlite's legacy transaction mode can commit a released first
            # SAVEPOINT even when the surrounding SQLAlchemy transaction fails.
            # Explicit BEGIN makes the development adapter match PostgreSQL atomicity.
            @event.listens_for(self.engine, "connect")
            def sqlite_connect(connection, _):
                connection.isolation_level = None
            @event.listens_for(self.engine, "begin")
            def sqlite_begin(connection):
                connection.exec_driver_sql("BEGIN")
        self.factory = sessionmaker(self.engine, expire_on_commit=False)

    @contextmanager
    def session(self):
        with self.factory() as db:
            with db.begin():
                yield db

    def migrate(self):
        # Versioned, explicit bootstrap. Future changes require a new migration.
        if inspect(self.engine).has_table("schema_version"):
            with self.session() as db:
                versions = list(db.scalars(select(Version.id)))
                if versions and versions != [SCHEMA_VERSION]:
                    raise RuntimeError("Unsupported database schema; run the documented migration")
        Base.metadata.create_all(self.engine)
        with self.session() as db:
            versions = list(db.scalars(select(Version.id)))
            if versions and versions != [SCHEMA_VERSION]:
                raise RuntimeError("Unsupported database schema; run the documented migration")
            if not versions:
                db.add(Version(id=SCHEMA_VERSION))

    def ready(self):
        with self.session() as db:
            return db.scalar(select(Version.id)) == SCHEMA_VERSION
