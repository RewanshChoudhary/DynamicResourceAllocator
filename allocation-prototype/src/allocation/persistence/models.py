from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text, create_engine
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
