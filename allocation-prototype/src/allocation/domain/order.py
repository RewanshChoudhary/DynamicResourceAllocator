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
