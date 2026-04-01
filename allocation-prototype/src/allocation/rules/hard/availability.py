from __future__ import annotations

from allocation.domain.order import Order
from allocation.domain.partner import DeliveryPartner
from allocation.rules.base import FilterResult, HardRule
from allocation.rules.registry import rule_registry


@rule_registry.register
class AvailabilityRule(HardRule):
    rule_name = "availability"

    def evaluate(self, order: Order, partner: DeliveryPartner) -> FilterResult:
        del order
        if not self.enabled:
            return FilterResult(True, None, "rule_disabled")
        if partner.active and partner.is_available:
            return FilterResult(True, None, "partner_available")
        return FilterResult(False, "PARTNER_UNAVAILABLE", "partner is not currently available")
