from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from allocation.domain.enums import VehicleType


class OrderIn(BaseModel):
    order_id: str
    latitude: float
    longitude: float
    amount_paise: int
    requested_vehicle_type: VehicleType
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PartnerIn(BaseModel):
    partner_id: str
    latitude: float
    longitude: float
    is_available: bool
    rating: float
    vehicle_types: list[VehicleType]
    active: bool = True


class AllocationRequest(BaseModel):
    orders: list[OrderIn]
    partners: list[PartnerIn]


class AllocationResponse(BaseModel):
    manifest_id: str
    allocations: list[dict[str, Any]]
    summary: dict[str, Any]
    aggregate_diagnostics: dict[str, Any] | None = None


class SimulationRequest(BaseModel):
    manifest_id: str
    mutations: list[dict[str, Any]]
