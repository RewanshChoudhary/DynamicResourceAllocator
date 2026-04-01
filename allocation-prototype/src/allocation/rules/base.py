from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from allocation.domain.order import Order
from allocation.domain.partner import DeliveryPartner


@dataclass(frozen=True)
class FilterResult:
    passed: bool
    failure_code: str | None
    rationale: str


@dataclass(frozen=True)
class ScoreResult:
    raw_score: float
    score_breakdown: dict[str, float]


class Rule(ABC):
    rule_name: str = ""
    depends_on: tuple[str, ...] = ()

    def __init__(self, enabled: bool = True, **params: Any) -> None:
        self.enabled = enabled
        self.params = params

    def serialize(self) -> dict[str, Any]:
        return {
            "rule_name": self.rule_name,
            "enabled": self.enabled,
            "params": self.params,
            "depends_on": list(self.depends_on),
        }


class HardRule(Rule, ABC):
    @abstractmethod
    def evaluate(self, order: Order, partner: DeliveryPartner) -> FilterResult:
        raise NotImplementedError


class ScoringRule(Rule, ABC):
    @abstractmethod
    def score(self, order: Order, partner: DeliveryPartner, context: dict[str, Any]) -> ScoreResult:
        raise NotImplementedError
