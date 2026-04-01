from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class GiniCalculator:
    @staticmethod
    def compute(load_counts: list[int]) -> float:
        if not load_counts:
            raise ValueError("Gini calculation requires at least one partner load")

        total = sum(load_counts)
        if total == 0:
            return 0.0

        sorted_counts = sorted(load_counts)
        n = len(sorted_counts)

        weighted_sum = 0
        for idx, value in enumerate(sorted_counts, start=1):
            weighted_sum += idx * value

        numerator = 2 * weighted_sum
        denominator = n * total
        gini = (numerator / denominator) - ((n + 1) / n)
        return max(0.0, min(gini, 1.0))


@dataclass(frozen=True)
class FairnessEscalationEvent:
    pre_gini: float
    post_gini_projection: float
    old_weights: dict[str, float]
    new_weights: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "pre_gini": round(self.pre_gini, 8),
            "post_gini_projection": round(self.post_gini_projection, 8),
            "old_weights": self.old_weights,
            "new_weights": self.new_weights,
        }


class FairnessEnforcer:
    def __init__(
        self,
        base_weights: dict[str, float],
        fairness_rule_name: str = "fairness_score",
        fairness_threshold: float = 0.35,
        escalation_factor: float = 1.5,
    ) -> None:
        self.base_weights = dict(base_weights)
        self.fairness_rule_name = fairness_rule_name
        self.fairness_threshold = fairness_threshold
        self.escalation_factor = escalation_factor

    def baseline_weights(self) -> dict[str, float]:
        return dict(self.base_weights)

    def adjust_weights(self, partner_loads: dict[str, int]) -> tuple[dict[str, float], FairnessEscalationEvent | None]:
        gini = GiniCalculator.compute(list(partner_loads.values()))
        old = dict(self.base_weights)

        if gini <= self.fairness_threshold:
            return old, None

        if self.fairness_rule_name not in old:
            return old, None

        new_weights = dict(old)
        new_weights[self.fairness_rule_name] = new_weights[self.fairness_rule_name] * self.escalation_factor
        total = sum(new_weights.values())
        if total <= 0:
            return old, None

        normalized = {k: round(v / total, 8) for k, v in new_weights.items()}

        event = FairnessEscalationEvent(
            pre_gini=gini,
            post_gini_projection=gini,
            old_weights=old,
            new_weights=normalized,
        )
        return normalized, event
