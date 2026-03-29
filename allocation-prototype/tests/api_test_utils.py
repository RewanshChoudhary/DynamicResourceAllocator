from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from starlette.requests import Request

from allocation.fairness.tracker import PartnerLoadTracker
from allocation.persistence.models import create_all_tables, create_session_factory, create_sqlite_engine


@dataclass
class ApiTestContext:
    app: FastAPI
    engine: Any
    session_factory: Any

    def request(self, method: str, path: str) -> Request:
        return Request(
            {
                "type": "http",
                "method": method,
                "path": path,
                "headers": [],
                "app": self.app,
            }
        )


def build_api_test_context(tmp_path: Path) -> ApiTestContext:
    engine = create_sqlite_engine(f"sqlite:///{tmp_path / 'api_test.db'}")
    create_all_tables(engine)
    session_factory = create_session_factory(engine)

    app = FastAPI()
    app.state.session_factory = session_factory
    app.state.partner_load_tracker = PartnerLoadTracker(window=timedelta(hours=1))

    return ApiTestContext(app=app, engine=engine, session_factory=session_factory)


def minimal_allocation_payload() -> dict[str, Any]:
    created_at = datetime(2026, 2, 22, 12, 0, tzinfo=timezone.utc).isoformat()
    return {
        "orders": [
            {
                "order_id": "ORD-1",
                "latitude": 12.9716,
                "longitude": 77.5946,
                "amount_paise": 30000,
                "requested_vehicle_type": "bike",
                "created_at": created_at,
            },
            {
                "order_id": "ORD-2",
                "latitude": 12.9720,
                "longitude": 77.5950,
                "amount_paise": 24000,
                "requested_vehicle_type": "bike",
                "created_at": created_at,
            },
        ],
        "partners": [
            {
                "partner_id": "PT-1",
                "latitude": 12.9717,
                "longitude": 77.5947,
                "is_available": True,
                "rating": 4.8,
                "vehicle_types": ["bike"],
                "active": True,
            },
            {
                "partner_id": "PT-2",
                "latitude": 12.9721,
                "longitude": 77.5951,
                "is_available": True,
                "rating": 4.6,
                "vehicle_types": ["bike"],
                "active": True,
            },
            {
                "partner_id": "PT-3",
                "latitude": 12.9725,
                "longitude": 77.5955,
                "is_available": True,
                "rating": 4.4,
                "vehicle_types": ["scooter"],
                "active": True,
            },
        ],
    }
