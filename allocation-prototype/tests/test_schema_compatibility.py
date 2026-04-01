from __future__ import annotations

import sqlite3

import pytest

from allocation.persistence.models import assert_schema_compatible, create_all_tables, create_sqlite_engine


def test_assert_schema_compatible_accepts_current_schema(tmp_path):
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'current.db'}")
    create_all_tables(engine)

    assert_schema_compatible(engine)


def test_assert_schema_compatible_rejects_outdated_allocation_events_schema(tmp_path):
    db_path = tmp_path / "outdated.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE allocation_events (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                order_id VARCHAR(64) NOT NULL,
                manifest_id VARCHAR(64) NOT NULL,
                partner_id VARCHAR(64),
                status VARCHAR(32) NOT NULL,
                created_at DATETIME NOT NULL
            );

            CREATE TABLE sealed_manifests (
                manifest_id VARCHAR(64) NOT NULL PRIMARY KEY,
                manifest_json TEXT NOT NULL,
                trace_hash VARCHAR(64) NOT NULL,
                config_version_hash VARCHAR(64) NOT NULL,
                decided_at DATETIME NOT NULL
            );

            CREATE TABLE input_snapshots (
                input_hash VARCHAR(64) NOT NULL PRIMARY KEY,
                snapshot_json TEXT NOT NULL
            );

            CREATE TABLE config_versions (
                config_version_hash VARCHAR(64) NOT NULL PRIMARY KEY,
                config_yaml TEXT NOT NULL,
                config_json TEXT NOT NULL,
                inserted_at DATETIME NOT NULL
            );

            CREATE TABLE idempotency_records (
                "key" VARCHAR(128) NOT NULL PRIMARY KEY,
                status VARCHAR(32) NOT NULL,
                response_json TEXT NOT NULL,
                created_at DATETIME NOT NULL
            );
            """
        )
        conn.commit()
    finally:
        conn.close()

    engine = create_sqlite_engine(f"sqlite:///{db_path}")

    with pytest.raises(RuntimeError, match="allocation_events missing columns: config_version_hash, trace_hash"):
        assert_schema_compatible(engine)
