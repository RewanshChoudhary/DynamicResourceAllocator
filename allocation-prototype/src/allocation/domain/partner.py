from __future__ import annotations

from dataclasses import dataclass

from allocation.domain.enums import VehicleType


@dataclass(frozen=True)
class DeliveryPartner:
    partner_id: str
    latitude: float
    longitude: float
    is_available: bool
    rating: float
    vehicle_types: tuple[VehicleType, ...]
    active: bool = True
    name: str | None = None
    current_load: int = 0
    vehicle_condition: int = 1
    avg_time_taken_min: int = 30
    city: str | None = None
    raw_vehicle_type: str | None = None
