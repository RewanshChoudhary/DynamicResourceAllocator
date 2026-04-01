from __future__ import annotations

from allocation.domain.order import Order
from allocation.domain.partner import DeliveryPartner
from allocation.rules.base import FilterResult, HardRule
from allocation.rules.registry import rule_registry
from allocation.rules.utils import haversine_km


@rule_registry.register
class MaxDistanceRule(HardRule):
    rule_name = "max_distance"

    def evaluate(self, order: Order, partner: DeliveryPartner) -> FilterResult:
        if not self.enabled:
            return FilterResult(True, None, "rule_disabled")

        max_distance_km = float(self.params.get("max_distance_km", 5.0))
        distance_km = haversine_km(
            order.latitude,
            order.longitude,
            partner.latitude,
            partner.longitude,
        )

        if distance_km <= max_distance_km:
            return FilterResult(True, None, f"distance={distance_km:.3f}km")
        return FilterResult(
            False,
            "DISTANCE_LIMIT_EXCEEDED",
            f"distance={distance_km:.3f}km exceeds max={max_distance_km:.3f}km",
        )
