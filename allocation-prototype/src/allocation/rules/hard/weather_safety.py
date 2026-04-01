from __future__ import annotations

from allocation.domain.order import Order
from allocation.domain.partner import DeliveryPartner
from allocation.rules.base import FilterResult, HardRule
from allocation.rules.registry import rule_registry


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
            return FilterResult(passed=True, failure_code=None, rationale="")

        if weather in severe_conditions and raw_vehicle in restricted_vehicles:
            return FilterResult(
                passed=False,
                failure_code="VEHICLE_UNSAFE_IN_WEATHER",
                rationale=f"{raw_vehicle} restricted during {weather} conditions",
            )
        return FilterResult(passed=True, failure_code=None, rationale="")
