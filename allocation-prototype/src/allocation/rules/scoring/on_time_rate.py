from __future__ import annotations

from allocation.domain.order import Order
from allocation.domain.partner import DeliveryPartner
from allocation.rules.base import ScoreResult, ScoringRule
from allocation.rules.registry import rule_registry


# Score scale: 0-1 (matching existing pipeline contract)
# Verified against: rules/scoring/proximity.py on 2026-04-02
@rule_registry.register
class OnTimeRateRule(ScoringRule):
    rule_name = "on_time_rate"

    def score(self, order: Order, partner: DeliveryPartner, context: dict[str, object]) -> ScoreResult:
        del order
        del context
        if not self.enabled:
            return ScoreResult(0.0, {"on_time_rate": 0.0})

        baseline_minutes = int(self.params.get("baseline_minutes", 30))
        partner_avg_time_min = max(1, int(partner.avg_time_taken_min))
        speed_ratio = baseline_minutes / partner_avg_time_min
        raw_score = max(0.0, min(speed_ratio, 1.0))
        display_score_10 = max(0.0, min(10.0, 10.0 * speed_ratio))

        return ScoreResult(
            round(raw_score, 6),
            {
                "partner_avg_time_min": float(partner_avg_time_min),
                "baseline_minutes": float(baseline_minutes),
                "speed_ratio": round(speed_ratio, 3),
                "display_score_10": round(display_score_10, 3),
                "on_time_rate": round(raw_score, 6),
            },
        )
