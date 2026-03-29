from __future__ import annotations

from allocation.domain.order import Order
from allocation.domain.partner import DeliveryPartner
from allocation.rules.base import FilterResult, HardRule
from allocation.rules.registry import rule_registry


@rule_registry.register
class VehicleTypeRule(HardRule):
    rule_name = "vehicle_type"

    def evaluate(self, order: Order, partner: DeliveryPartner) -> FilterResult:
        if not self.enabled:
            return FilterResult(True, None, "rule_disabled")

        allowed_vehicle_types = self._allowed_vehicle_types(order.requested_vehicle_type.value)
        if any(vehicle_type.value in allowed_vehicle_types for vehicle_type in partner.vehicle_types):
            return FilterResult(True, None, "vehicle_type_match")
        return FilterResult(
            False,
            "VEHICLE_TYPE_MISMATCH",
            f"partner does not support vehicle={order.requested_vehicle_type.value}",
        )

    def _allowed_vehicle_types(self, requested_vehicle_type: str) -> set[str]:
        compatibility_map = self.params.get("vehicle_compatibility")
        if not compatibility_map:
            return {requested_vehicle_type}

        compatible = compatibility_map.get(requested_vehicle_type, [requested_vehicle_type])
        return {str(vehicle_type) for vehicle_type in compatible}
