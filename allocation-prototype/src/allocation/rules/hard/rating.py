from __future__ import annotations

from allocation.domain.order import Order
from allocation.domain.partner import DeliveryPartner
from allocation.rules.base import FilterResult, HardRule
from allocation.rules.registry import rule_registry


@rule_registry.register
class MinRatingRule(HardRule):
    rule_name = "min_rating"

    def evaluate(self, order: Order, partner: DeliveryPartner) -> FilterResult:
        del order
        if not self.enabled:
            return FilterResult(True, None, "rule_disabled")

        min_rating = float(self.params.get("min_rating", 0.0))
        if partner.rating >= min_rating:
            return FilterResult(True, None, f"rating={partner.rating:.2f}")
        return FilterResult(False, "RATING_TOO_LOW", f"rating={partner.rating:.2f} < min={min_rating:.2f}")


@rule_registry.register
class MaxRatingRule(HardRule):
    rule_name = "max_rating"

    def evaluate(self, order: Order, partner: DeliveryPartner) -> FilterResult:
        del order
        if not self.enabled:
            return FilterResult(True, None, "rule_disabled")

        max_rating = float(self.params.get("max_rating", 5.0))
        if partner.rating <= max_rating:
            return FilterResult(True, None, f"rating={partner.rating:.2f}")
        return FilterResult(False, "RATING_TOO_HIGH", f"rating={partner.rating:.2f} > max={max_rating:.2f}")
