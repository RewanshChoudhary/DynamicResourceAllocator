from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from allocation.domain.enums import VehicleType


@dataclass(frozen=True)
class Order:
    order_id: str
    latitude: float
    longitude: float
    amount_paise: int
    requested_vehicle_type: VehicleType
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    restaurant_latitude: float | None = None
    restaurant_longitude: float | None = None
    delivery_latitude: float | None = None
    delivery_longitude: float | None = None
    weather_condition: str = "Sunny"
    traffic_density: str = "Low"
    order_type: str = "Meal"
    priority: str = "NORMAL"
    vehicle_required_raw: str | None = None
