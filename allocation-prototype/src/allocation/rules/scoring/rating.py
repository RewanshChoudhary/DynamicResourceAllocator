from __future__ import annotations

from allocation.domain.order import Order
from allocation.domain.partner import DeliveryPartner
from allocation.rules.base import ScoreResult, ScoringRule
from allocation.rules.registry import rule_registry


@rule_registry.register
class RatingScoreRule(ScoringRule):
    rule_name = "rating_score"

    def score(self, order: Order, partner: DeliveryPartner, context: dict[str, object]) -> ScoreResult:
        del order
        del context
        if not self.enabled:
            return ScoreResult(0.0, {"rating_score": 0.0})

        raw = max(0.0, min(partner.rating / 5.0, 1.0))
        return ScoreResult(raw, {"rating": round(partner.rating, 3), "rating_score": round(raw, 6)})
