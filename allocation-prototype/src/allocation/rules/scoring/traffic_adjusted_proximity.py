from __future__ import annotations

from allocation.domain.order import Order
from allocation.domain.partner import DeliveryPartner
from allocation.rules.base import ScoreResult, ScoringRule
from allocation.rules.registry import rule_registry
from allocation.rules.utils import haversine_km


DEFAULT_TRAFFIC_MULTIPLIERS = {
    "Low": 1.0,
    "Medium": 1.3,
    "High": 1.6,
    "Jam": 2.2,
}


# Score scale: 0-1 (matching existing pipeline contract)
# Verified against: rules/scoring/proximity.py on 2026-04-02
@rule_registry.register
class TrafficAdjustedProximityRule(ScoringRule):
    rule_name = "traffic_adjusted_proximity"

    def score(self, order: Order, partner: DeliveryPartner, context: dict[str, object]) -> ScoreResult:
        del context
        if not self.enabled:
            return ScoreResult(0.0, {"traffic_adjusted_proximity": 0.0})

        max_distance_km = float(self.params.get("max_distance_km", 10.0))
        multipliers = {
            str(key): float(value)
            for key, value in self.params.get("traffic_multipliers", DEFAULT_TRAFFIC_MULTIPLIERS).items()
        }

        raw_distance = haversine_km(order.latitude, order.longitude, partner.latitude, partner.longitude)
        traffic_density = order.traffic_density or "Low"
        multiplier = multipliers.get(traffic_density, 1.0)
        effective_distance = raw_distance * multiplier

        if max_distance_km <= 0:
            raw_score = 0.0
        else:
            raw_score = max(0.0, min(1.0, 1.0 - (effective_distance / max_distance_km)))

        return ScoreResult(
            round(raw_score, 6),
            {
                "raw_distance_km": round(raw_distance, 3),
                "traffic_density": traffic_density,
                "traffic_multiplier": round(multiplier, 3),
                "effective_distance_km": round(effective_distance, 3),
                "max_distance_km": round(max_distance_km, 3),
                "traffic_adjusted_proximity": round(raw_score, 6),
            },
        )
