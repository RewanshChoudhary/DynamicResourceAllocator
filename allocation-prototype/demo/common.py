from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from allocation.config.loader import ConfigLoader
from allocation.domain.enums import VehicleType
from allocation.domain.order import Order
from allocation.domain.partner import DeliveryPartner


def make_orders() -> list[Order]:
    base_time = datetime(2026, 2, 22, 10, 0, tzinfo=timezone.utc)
    return [
        Order(
            order_id="O-100",
            latitude=12.9716,
            longitude=77.5946,
            amount_paise=35000,
            requested_vehicle_type=VehicleType.BIKE,
            created_at=base_time,
        ),
        Order(
            order_id="O-101",
            latitude=12.9720,
            longitude=77.5952,
            amount_paise=27000,
            requested_vehicle_type=VehicleType.BIKE,
            created_at=base_time,
        ),
        Order(
            order_id="O-102",
            latitude=12.9724,
            longitude=77.5960,
            amount_paise=19000,
            requested_vehicle_type=VehicleType.BIKE,
            created_at=base_time,
        ),
    ]


def make_partners() -> list[DeliveryPartner]:
    return [
        DeliveryPartner(
            partner_id="P-1",
            latitude=12.9720,
            longitude=77.5940,
            is_available=True,
            rating=4.8,
            vehicle_types=(VehicleType.BIKE,),
            active=True,
        ),
        DeliveryPartner(
            partner_id="P-2",
            latitude=12.9780,
            longitude=77.6030,
            is_available=True,
            rating=4.4,
            vehicle_types=(VehicleType.BIKE,),
            active=True,
        ),
        DeliveryPartner(
            partner_id="P-3",
            latitude=12.9800,
            longitude=77.6070,
            is_available=True,
            rating=4.2,
            vehicle_types=(VehicleType.BIKE,),
            active=True,
        ),
    ]


def get_default_config_path() -> Path:
    return PROJECT_ROOT / "src" / "allocation" / "config" / "rules.yaml"


def get_broken_config_path() -> Path:
    return PROJECT_ROOT / "src" / "allocation" / "config" / "rules_broken.yaml"


def load_default_config() -> tuple[dict, str]:
    loader = ConfigLoader(get_default_config_path())
    loaded = loader.load()
    return loaded.config, loaded.conflict_report.sha256()


def new_session(db_name: str):
    from allocation.persistence.models import create_all_tables, create_session_factory, create_sqlite_engine

    db_path = PROJECT_ROOT / f"{db_name}.db"
    if db_path.exists():
        db_path.unlink()
    engine = create_sqlite_engine(f"sqlite:///{db_path}")
    create_all_tables(engine)
    session_factory = create_session_factory(engine)
    return session_factory(), db_path


def store_config(session, config: dict):
    from allocation.persistence.config_versions import ConfigVersionStore

    store = ConfigVersionStore(session)
    return store.put_if_absent(config)
