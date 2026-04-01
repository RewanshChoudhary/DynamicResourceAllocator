from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text, create_engine, inspect as sa_inspect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class AllocationEventModel(Base):
    __tablename__ = "allocation_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(String(64), index=True)
    manifest_id: Mapped[str] = mapped_column(String(64), index=True)
    partner_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    trace_hash: Mapped[str] = mapped_column(String(64), index=True)
    config_version_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class SealedManifestModel(Base):
    __tablename__ = "sealed_manifests"

    manifest_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    manifest_json: Mapped[str] = mapped_column(Text, nullable=False)
    trace_hash: Mapped[str] = mapped_column(String(64), index=True)
    config_version_hash: Mapped[str] = mapped_column(String(64), index=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class InputSnapshotModel(Base):
    __tablename__ = "input_snapshots"

    input_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)


class ConfigVersionModel(Base):
    __tablename__ = "config_versions"

    config_version_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    config_yaml: Mapped[str] = mapped_column(Text, nullable=False)
    config_json: Mapped[str] = mapped_column(Text, nullable=False)
    inserted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class IdempotencyRecordModel(Base):
    __tablename__ = "idempotency_records"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    response_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


def create_sqlite_engine(db_url: str = "sqlite:///allocation_prototype.db"):
    return create_engine(db_url, future=True)


def create_session_factory(engine):
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def create_all_tables(engine) -> None:
    Base.metadata.create_all(engine)


REQUIRED_SCHEMA_COLUMNS = {
    "allocation_events": {
        "id",
        "order_id",
        "manifest_id",
        "partner_id",
        "status",
        "trace_hash",
        "config_version_hash",
        "created_at",
    },
    "sealed_manifests": {
        "manifest_id",
        "manifest_json",
        "trace_hash",
        "config_version_hash",
        "decided_at",
    },
    "input_snapshots": {
        "input_hash",
        "snapshot_json",
    },
    "config_versions": {
        "config_version_hash",
        "config_yaml",
        "config_json",
        "inserted_at",
    },
    "idempotency_records": {
        "key",
        "status",
        "response_json",
        "created_at",
    },
}


def find_missing_schema_columns(engine) -> dict[str, list[str]]:
    inspector = sa_inspect(engine)
    existing_tables = set(inspector.get_table_names())
    missing: dict[str, list[str]] = {}
    for table_name, required_columns in REQUIRED_SCHEMA_COLUMNS.items():
        if table_name not in existing_tables:
            missing[table_name] = sorted(required_columns)
            continue

        existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
        missing_columns = sorted(required_columns - existing_columns)
        if missing_columns:
            missing[table_name] = missing_columns
    return missing


def assert_schema_compatible(engine) -> None:
    missing = find_missing_schema_columns(engine)
    if not missing:
        return

    details = "; ".join(
        f"{table_name} missing columns: {', '.join(columns)}"
        for table_name, columns in sorted(missing.items())
    )
    raise RuntimeError(
        "Database schema is outdated or incomplete. "
        f"{details}. If this database predates Alembic versioning, run "
        "`.venv/bin/alembic stamp 13cab1c6d55d` and then `.venv/bin/alembic upgrade head`, "
        "or recreate the database."
    )
