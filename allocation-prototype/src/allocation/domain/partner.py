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
