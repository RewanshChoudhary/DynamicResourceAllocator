from __future__ import annotations

from allocation.domain.order import Order
from allocation.domain.partner import DeliveryPartner
from allocation.rules.base import ScoreResult, ScoringRule
from allocation.rules.registry import rule_registry


@rule_registry.register
class FairnessScoreRule(ScoringRule):
    rule_name = "fairness_score"

    def score(self, order: Order, partner: DeliveryPartner, context: dict[str, object]) -> ScoreResult:
        del order
        if not self.enabled:
            return ScoreResult(0.0, {"fairness_score": 0.0})

        partner_loads = context.get("partner_loads", {})
        if not isinstance(partner_loads, dict):
            partner_loads = {}

        load = max(0, int(partner.current_load))
        max_load = max([max(0, int(v)) for v in partner_loads.values()] + [load, 0])

        if max_load <= 0:
            raw = 1.0
        else:
            raw = max(0.0, 1.0 - (load / max_load))

        return ScoreResult(
            raw,
            {
                "partner_current_load": float(load),
                "max_partner_load": float(max_load),
                "fairness_score": round(raw, 6),
            },
        )
