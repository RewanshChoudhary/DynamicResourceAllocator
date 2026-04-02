from __future__ import annotations

from allocation.domain.order import Order
from allocation.domain.partner import DeliveryPartner
from allocation.rules.base import FilterResult, HardRule
from allocation.rules.registry import rule_registry


# This rule reads raw_vehicle_type, not vehicle_type (core enum).
# MOTORCYCLE and SCOOTER are restricted by default.
# ELECTRIC_SCOOTER is intentionally excluded from defaults.
# These are distinct at the raw field level even though SCOOTER and
# ELECTRIC_SCOOTER share the same core enum value.
@rule_registry.register
class WeatherSafetyRule(HardRule):
    rule_name = "weather_safety"

    def evaluate(self, order: Order, partner: DeliveryPartner) -> FilterResult:
        if not self.enabled:
            return FilterResult(True, None, "rule_disabled")

        weather = order.weather_condition
        severe_conditions = tuple(self.params.get("severe_conditions", ["Stormy", "Sandstorms"]))
        restricted_vehicles = tuple(self.params.get("restricted_vehicles", ["MOTORCYCLE", "SCOOTER"]))

        raw_vehicle = getattr(partner, "raw_vehicle_type", None)
        if not raw_vehicle:
            # raw_vehicle_type not populated - cannot apply restriction safely.
            # Fail open to avoid incorrectly blocking legitimate partners.
            return FilterResult(passed=True, failure_code=None, rationale="")

        if weather in severe_conditions and raw_vehicle in restricted_vehicles:
            return FilterResult(
                passed=False,
                failure_code="VEHICLE_UNSAFE_IN_WEATHER",
                rationale=f"{raw_vehicle} restricted during {weather} conditions",
            )
        return FilterResult(passed=True, failure_code=None, rationale="")
