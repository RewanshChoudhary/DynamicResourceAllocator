from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Type

from allocation.rules.base import HardRule, ScoringRule


@dataclass(frozen=True)
class RuleDefinition:
    name: str
    cls: type[HardRule] | type[ScoringRule]
    kind: str


class RuleRegistry:
    def __init__(self) -> None:
        self._definitions: dict[str, RuleDefinition] = {}

    def register(self, cls: Type[HardRule] | Type[ScoringRule]) -> Type[HardRule] | Type[ScoringRule]:
        name = getattr(cls, "rule_name", "")
        if not name:
            raise ValueError(f"Rule {cls.__name__} must define rule_name")

        if issubclass(cls, HardRule):
            kind = "hard"
        elif issubclass(cls, ScoringRule):
            kind = "scoring"
        else:
            raise TypeError(f"Unsupported rule type: {cls.__name__}")

        if name in self._definitions:
            raise ValueError(f"Rule already registered: {name}")

        self._definitions[name] = RuleDefinition(name=name, cls=cls, kind=kind)
        return cls

    def get(self, rule_name: str) -> RuleDefinition:
        if rule_name not in self._definitions:
            raise KeyError(f"Unknown rule: {rule_name}")
        return self._definitions[rule_name]

    def names(self) -> set[str]:
        return set(self._definitions)


rule_registry = RuleRegistry()


def import_all_rules() -> None:
    import allocation.rules.hard.availability
    import allocation.rules.hard.distance
    import allocation.rules.hard.load_capacity
    import allocation.rules.hard.rating
    import allocation.rules.hard.vehicle_condition
    import allocation.rules.hard.weather_safety
    import allocation.rules.hard.vehicle_type
    import allocation.rules.scoring.fairness
    import allocation.rules.scoring.on_time_rate
    import allocation.rules.scoring.proximity
    import allocation.rules.scoring.rating
    import allocation.rules.scoring.traffic_adjusted_proximity


def build_rule_set(config: dict[str, Any]) -> tuple[list[HardRule], list[ScoringRule]]:
    import_all_rules()

    hard_rules: list[HardRule] = []
    scoring_rules: list[ScoringRule] = []

    for entry in config.get("hard_rules", []):
        name = entry["name"]
        definition = rule_registry.get(name)
        if definition.kind != "hard":
            raise ValueError(f"Rule {name} configured as hard but is {definition.kind}")
        params = dict(entry.get("params", {}))
        if name == "vehicle_type" and "vehicle_compatibility" in config:
            params["vehicle_compatibility"] = config["vehicle_compatibility"]
        enabled = entry.get("enabled", True)
        hard_rules.append(definition.cls(enabled=enabled, **params))

    for entry in config.get("scoring_rules", []):
        name = entry["name"]
        definition = rule_registry.get(name)
        if definition.kind != "scoring":
            raise ValueError(f"Rule {name} configured as scoring but is {definition.kind}")
        params = entry.get("params", {})
        enabled = entry.get("enabled", True)
        scoring_rules.append(definition.cls(enabled=enabled, **params))

    return hard_rules, scoring_rules
