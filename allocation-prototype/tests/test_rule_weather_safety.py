from __future__ import annotations

from allocation.domain.enums import VehicleType
from allocation.domain.order import Order
from allocation.domain.partner import DeliveryPartner
from allocation.rules.hard.weather_safety import WeatherSafetyRule


def _order(weather: str) -> Order:
    return Order(
        order_id=f"ORD-{weather}",
        latitude=12.9716,
        longitude=77.5946,
        amount_paise=25000,
        requested_vehicle_type=VehicleType.BIKE,
        weather_condition=weather,
    )


def _partner(raw_vehicle_type: str | None) -> DeliveryPartner:
    vehicle_type = VehicleType.BIKE if raw_vehicle_type == "MOTORCYCLE" else VehicleType.SCOOTER
    return DeliveryPartner(
        partner_id=f"PT-{raw_vehicle_type or 'UNKNOWN'}",
        latitude=12.9717,
        longitude=77.5947,
        is_available=True,
        rating=4.8,
        vehicle_types=(vehicle_type,),
        raw_vehicle_type=raw_vehicle_type,
    )


def test_motorcycle_rejected_in_stormy_weather():
    result = WeatherSafetyRule().evaluate(_order("Stormy"), _partner("MOTORCYCLE"))

    assert result.passed is False


def test_scooter_rejected_in_sandstorms():
    result = WeatherSafetyRule().evaluate(_order("Sandstorms"), _partner("SCOOTER"))

    assert result.passed is False


def test_electric_scooter_allowed_in_stormy_weather():
    result = WeatherSafetyRule().evaluate(_order("Stormy"), _partner("ELECTRIC_SCOOTER"))

    assert result.passed is True


def test_motorcycle_allowed_in_cloudy_weather():
    result = WeatherSafetyRule().evaluate(_order("Cloudy"), _partner("MOTORCYCLE"))

    assert result.passed is True


def test_motorcycle_allowed_in_sunny_weather():
    result = WeatherSafetyRule().evaluate(_order("Sunny"), _partner("MOTORCYCLE"))

    assert result.passed is True


def test_custom_config_can_restrict_all_vehicles():
    rule = WeatherSafetyRule(restricted_vehicles=["MOTORCYCLE", "SCOOTER", "ELECTRIC_SCOOTER"])

    assert rule.evaluate(_order("Stormy"), _partner("MOTORCYCLE")).passed is False
    assert rule.evaluate(_order("Stormy"), _partner("SCOOTER")).passed is False
    assert rule.evaluate(_order("Stormy"), _partner("ELECTRIC_SCOOTER")).passed is False


def test_failure_code_is_correct_string():
    result = WeatherSafetyRule().evaluate(_order("Stormy"), _partner("MOTORCYCLE"))

    assert result.failure_code == "VEHICLE_UNSAFE_IN_WEATHER"


def test_missing_raw_vehicle_type_fails_open():
    result = WeatherSafetyRule().evaluate(_order("Stormy"), _partner(None))

    assert result.passed is True
    assert result.failure_code is None
