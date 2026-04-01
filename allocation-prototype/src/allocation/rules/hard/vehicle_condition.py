from __future__ import annotations

from allocation.domain.order import Order
from allocation.domain.partner import DeliveryPartner
from allocation.rules.base import FilterResult, HardRule
from allocation.rules.registry import rule_registry


@rule_registry.register
class VehicleConditionRule(HardRule):
    rule_name = "vehicle_condition"

    def evaluate(self, order: Order, partner: DeliveryPartner) -> FilterResult:
        del order
        if not self.enabled:
            return FilterResult(True, None, "rule_disabled")

        min_condition = int(self.params.get("min_condition", 1))
        if partner.vehicle_condition >= min_condition:
            return FilterResult(True, None, "")
        return FilterResult(
            False,
            "VEHICLE_CONDITION_BELOW_MINIMUM",
            (
                f"Partner vehicle condition {partner.vehicle_condition} "
                f"is below minimum required {min_condition}"
            ),
        )
