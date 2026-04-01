from __future__ import annotations

from datetime import datetime, timezone

import pytest

from allocation.domain.enums import VehicleType
from allocation.domain.order import Order
from allocation.domain.partner import DeliveryPartner
from allocation.persistence.models import create_all_tables, create_session_factory, create_sqlite_engine


@pytest.fixture()
def session():
    engine = create_sqlite_engine("sqlite:///:memory:")
    create_all_tables(engine)
    session_factory = create_session_factory(engine)
    db_session = session_factory()
    try:
        yield db_session
    finally:
        db_session.close()
        engine.dispose()


@pytest.fixture()
def sample_orders() -> list[Order]:
    ts = datetime(2026, 2, 22, 12, 0, tzinfo=timezone.utc)
    return [
        Order(
            order_id="ORD-1",
            latitude=12.9716,
            longitude=77.5946,
            amount_paise=30000,
            requested_vehicle_type=VehicleType.BIKE,
            created_at=ts,
        ),
        Order(
            order_id="ORD-2",
            latitude=12.9720,
            longitude=77.5950,
            amount_paise=24000,
            requested_vehicle_type=VehicleType.BIKE,
            created_at=ts,
        ),
    ]


@pytest.fixture()
def sample_partners() -> list[DeliveryPartner]:
    return [
        DeliveryPartner(
            partner_id="PT-1",
            latitude=12.9720,
            longitude=77.5940,
            is_available=True,
            rating=4.7,
            vehicle_types=(VehicleType.BIKE,),
            active=True,
        ),
        DeliveryPartner(
            partner_id="PT-2",
            latitude=12.9780,
            longitude=77.6020,
            is_available=True,
            rating=4.4,
            vehicle_types=(VehicleType.BIKE,),
            active=True,
        ),
    ]


@pytest.fixture()
def base_config() -> dict:
    return {
        "hard_rules": [
            {"name": "availability", "enabled": True},
            {"name": "vehicle_type", "enabled": True},
            {"name": "max_distance", "enabled": True, "params": {"max_distance_km": 5.0}},
            {"name": "min_rating", "enabled": True, "params": {"min_rating": 3.5}},
        ],
        "scoring_rules": [
            {"name": "proximity_score", "enabled": True, "params": {"scale_km": 10.0}},
            {"name": "rating_score", "enabled": True},
            {"name": "fairness_score", "enabled": True},
        ],
        "weights": {
            "proximity_score": 0.45,
            "rating_score": 0.25,
            "fairness_score": 0.30,
        },
        "fairness": {
            "threshold": 0.35,
            "escalation_factor": 1.5,
            "window_minutes": 60,
        },
    }
