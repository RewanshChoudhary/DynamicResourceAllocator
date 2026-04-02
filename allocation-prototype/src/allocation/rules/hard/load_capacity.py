from __future__ import annotations

from allocation.domain.order import Order
from allocation.domain.partner import DeliveryPartner
from allocation.rules.base import FilterResult, HardRule
from allocation.rules.registry import rule_registry


@rule_registry.register
class LoadCapacityRule(HardRule):
    rule_name = "load_capacity"

    def evaluate(self, order: Order, partner: DeliveryPartner) -> FilterResult:
        del order
        if not self.enabled:
            return FilterResult(True, None, "rule_disabled")

        max_active_orders = max(1, int(self.params.get("max_active_orders", 3)))
        current_load = max(0, int(partner.current_load))

        if current_load < max_active_orders:
            return FilterResult(
                True,
                None,
                f"current_load={current_load} below max_active_orders={max_active_orders}",
            )

        return FilterResult(
            False,
            "PARTNER_AT_CAPACITY",
            f"current_load={current_load} reached max_active_orders={max_active_orders}",
        )
