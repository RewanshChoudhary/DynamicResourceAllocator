from __future__ import annotations

from allocation.domain.order import Order
from allocation.domain.partner import DeliveryPartner
from allocation.rules.base import ScoreResult, ScoringRule
from allocation.rules.registry import rule_registry
from allocation.rules.utils import haversine_km


@rule_registry.register
class ProximityScoreRule(ScoringRule):
    rule_name = "proximity_score"

    def score(self, order: Order, partner: DeliveryPartner, context: dict[str, object]) -> ScoreResult:
        del context
        if not self.enabled:
            return ScoreResult(0.0, {"proximity": 0.0})

        scale_km = float(self.params.get("scale_km", 10.0))
        distance_km = haversine_km(order.latitude, order.longitude, partner.latitude, partner.longitude)
        bounded = min(distance_km, scale_km)
        raw = max(0.0, 1.0 - (bounded / scale_km))
        return ScoreResult(raw, {"distance_km": round(distance_km, 6), "proximity": round(raw, 6)})
