from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, model_validator

from allocation.domain.enums import VehicleType


RAW_TO_CORE_VEHICLE = {
    "MOTORCYCLE": VehicleType.BIKE,
    "SCOOTER": VehicleType.SCOOTER,
    "ELECTRIC_SCOOTER": VehicleType.SCOOTER,
}


def _coerce_vehicle_type(value: Any) -> VehicleType | None:
    if value is None:
        return None
    if isinstance(value, VehicleType):
        return value

    raw_value = str(value).strip()
    if not raw_value:
        return None

    try:
        return VehicleType(raw_value)
    except ValueError:
        return RAW_TO_CORE_VEHICLE.get(raw_value.upper())


def _coerce_raw_vehicle_type(value: Any) -> str | None:
    if value is None:
        return None
    raw_value = str(value).strip()
    if not raw_value:
        return None

    upper_value = raw_value.upper()
    if upper_value in RAW_TO_CORE_VEHICLE:
        return upper_value
    return None


class LocationIn(BaseModel):
    lat: float
    lon: float


class OrderIn(BaseModel):
    order_id: str
    latitude: float | None = None
    longitude: float | None = None
    amount_paise: int = 22000
    requested_vehicle_type: VehicleType | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    restaurant_location: LocationIn | None = None
    delivery_location: LocationIn | None = None
    restaurant_latitude: float | None = None
    restaurant_longitude: float | None = None
    delivery_latitude: float | None = None
    delivery_longitude: float | None = None
    weather_condition: str = "Sunny"
    traffic_density: str = "Low"
    order_type: str = "Meal"
    priority: str = "NORMAL"
    vehicle_required: str | None = None
    vehicle_required_raw: str | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_payload(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        payload = dict(data)
        restaurant_location = payload.get("restaurant_location")
        delivery_location = payload.get("delivery_location")

        if payload.get("latitude") is None and isinstance(restaurant_location, dict):
            payload["latitude"] = restaurant_location.get("lat")
        if payload.get("longitude") is None and isinstance(restaurant_location, dict):
            payload["longitude"] = restaurant_location.get("lon")

        if payload.get("restaurant_latitude") is None:
            payload["restaurant_latitude"] = payload.get("latitude")
        if payload.get("restaurant_longitude") is None:
            payload["restaurant_longitude"] = payload.get("longitude")

        if payload.get("delivery_latitude") is None and isinstance(delivery_location, dict):
            payload["delivery_latitude"] = delivery_location.get("lat")
        if payload.get("delivery_longitude") is None and isinstance(delivery_location, dict):
            payload["delivery_longitude"] = delivery_location.get("lon")

        requested_vehicle = (
            payload.get("requested_vehicle_type")
            or payload.get("vehicle_required")
            or payload.get("vehicle_required_raw")
        )
        coerced_vehicle = _coerce_vehicle_type(requested_vehicle)
        if coerced_vehicle is not None:
            payload["requested_vehicle_type"] = coerced_vehicle
        if payload.get("vehicle_required") is None and coerced_vehicle is not None:
            payload["vehicle_required"] = coerced_vehicle.value

        raw_vehicle = _coerce_raw_vehicle_type(payload.get("vehicle_required_raw"))
        if raw_vehicle is not None:
            payload["vehicle_required_raw"] = raw_vehicle

        if payload.get("latitude") is None or payload.get("longitude") is None:
            raise ValueError("Order payload requires latitude/longitude or restaurant_location")
        if payload.get("requested_vehicle_type") is None:
            raise ValueError(
                "Order payload requires requested_vehicle_type or vehicle_required/vehicle_required_raw"
            )

        return payload


class PartnerIn(BaseModel):
    partner_id: str
    latitude: float | None = None
    longitude: float | None = None
    is_available: bool
    rating: float
    vehicle_types: list[VehicleType] = Field(default_factory=list)
    active: bool = True
    name: str | None = None
    current_load: int = 0
    vehicle_condition: int = 1
    avg_time_taken_min: int = 30
    city: str | None = None
    raw_vehicle_type: str | None = None
    current_location: LocationIn | None = None
    vehicle_type: str | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_payload(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        payload = dict(data)
        current_location = payload.get("current_location")
        if payload.get("latitude") is None and isinstance(current_location, dict):
            payload["latitude"] = current_location.get("lat")
        if payload.get("longitude") is None and isinstance(current_location, dict):
            payload["longitude"] = current_location.get("lon")

        if not payload.get("vehicle_types"):
            singular_vehicle = payload.get("vehicle_type") or payload.get("raw_vehicle_type")
            coerced_vehicle = _coerce_vehicle_type(singular_vehicle)
            if coerced_vehicle is not None:
                payload["vehicle_types"] = [coerced_vehicle]

        raw_vehicle_type = _coerce_raw_vehicle_type(payload.get("raw_vehicle_type") or payload.get("vehicle_type"))
        if raw_vehicle_type is not None:
            payload["raw_vehicle_type"] = raw_vehicle_type

        payload.setdefault("name", payload.get("partner_id"))

        if payload.get("latitude") is None or payload.get("longitude") is None:
            raise ValueError("Partner payload requires latitude/longitude or current_location")
        if not payload.get("vehicle_types"):
            raise ValueError("Partner payload requires vehicle_types or vehicle_type/raw_vehicle_type")

        return payload


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
