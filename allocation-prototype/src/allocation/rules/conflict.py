from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from allocation.domain.enums import ConflictResolution, ConflictType
from allocation.rules.registry import import_all_rules, rule_registry


@dataclass(frozen=True)
class ConflictRecord:
    conflict_type: ConflictType
    rule_names_involved: tuple[str, ...]
    description: str
    resolution: ConflictResolution

    def to_dict(self) -> dict[str, Any]:
        return {
            "conflict_type": self.conflict_type.value,
            "rule_names_involved": list(self.rule_names_involved),
            "description": self.description,
            "resolution": self.resolution.value,
        }


@dataclass(frozen=True)
class ConflictResolutionReport:
    conflicts: tuple[ConflictRecord, ...]
    blocking: bool
    weights_after_resolution: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {
            "conflicts": [c.to_dict() for c in self.conflicts],
            "blocking": self.blocking,
            "weights_after_resolution": self.weights_after_resolution,
        }

    def canonical_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, ensure_ascii=True, separators=(",", ":"))

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


class RuleConflictError(ValueError):
    def __init__(self, report: ConflictResolutionReport) -> None:
        super().__init__(f"Configuration conflict detected: {report.to_dict()}")
        self.report = report


class RuleConflictDetector:
    WEIGHT_TOLERANCE = 0.001

    def detect(self, config: dict[str, Any]) -> ConflictResolutionReport:
        import_all_rules()
        registered_rule_names = rule_registry.names()

        conflicts: list[ConflictRecord] = []
        blocking = False

        hard_rules = [
            r
            for r in config.get("hard_rules", [])
            if isinstance(r, dict) and r.get("enabled", True)
        ]
        scoring_rules = [
            r
            for r in config.get("scoring_rules", [])
            if isinstance(r, dict) and r.get("enabled", True)
        ]
        enabled_rule_names: set[str] = set()
        for entry in hard_rules + scoring_rules:
            name = entry.get("name")
            if isinstance(name, str) and name:
                enabled_rule_names.add(name)

        min_rating = None
        max_rating = None
        for entry in hard_rules:
            name = entry.get("name")
            if not isinstance(name, str):
                continue
            params = entry.get("params", {})
            if name == "min_rating":
                min_rating = float(params.get("min_rating", 0.0))
            if name == "max_rating":
                max_rating = float(params.get("max_rating", 5.0))

        if min_rating is not None and max_rating is not None and min_rating > max_rating:
            blocking = True
            conflicts.append(
                ConflictRecord(
                    conflict_type=ConflictType.LOGICAL,
                    rule_names_involved=("min_rating", "max_rating"),
                    description=(
                        f"Contradictory rating bounds: min_rating={min_rating:.3f} "
                        f"is greater than max_rating={max_rating:.3f}."
                    ),
                    resolution=ConflictResolution.REQUIRES_OPERATOR_ACTION,
                )
            )

        weights = {k: float(v) for k, v in config.get("weights", {}).items()}
        enabled_scoring_names = [
            name
            for entry in scoring_rules
            for name in [entry.get("name")]
            if isinstance(name, str) and name
        ]
        filtered_weights = {k: weights.get(k, 0.0) for k in enabled_scoring_names}

        weight_sum = sum(filtered_weights.values())
        normalized_weights = dict(filtered_weights)

        if enabled_scoring_names:
            if abs(weight_sum - 1.0) > self.WEIGHT_TOLERANCE:
                if weight_sum <= 0:
                    equal_weight = round(1.0 / len(enabled_scoring_names), 8)
                    normalized_weights = {name: equal_weight for name in enabled_scoring_names}
                else:
                    normalized_weights = {
                        name: round(value / weight_sum, 8)
                        for name, value in filtered_weights.items()
                    }
                conflicts.append(
                    ConflictRecord(
                        conflict_type=ConflictType.WEIGHT,
                        rule_names_involved=tuple(sorted(enabled_scoring_names)),
                        description=(
                            f"Scoring weights sum to {weight_sum:.6f}; expected 1.0. "
                            f"Auto-normalized by delta {1.0 - weight_sum:.6f}."
                        ),
                        resolution=ConflictResolution.AUTO_RESOLVED,
                    )
                )

        configured_rules = hard_rules + scoring_rules
        for entry in configured_rules:
            rule_name = entry.get("name")
            if not isinstance(rule_name, str) or not rule_name:
                blocking = True
                conflicts.append(
                    ConflictRecord(
                        conflict_type=ConflictType.DEPENDENCY,
                        rule_names_involved=("<missing_name>",),
                        description="Configured rule entry is missing a valid string 'name'.",
                        resolution=ConflictResolution.REQUIRES_OPERATOR_ACTION,
                    )
                )
                continue

            if rule_name not in registered_rule_names:
                blocking = True
                conflicts.append(
                    ConflictRecord(
                        conflict_type=ConflictType.DEPENDENCY,
                        rule_names_involved=(rule_name,),
                        description=f"Configured rule {rule_name} is not registered.",
                        resolution=ConflictResolution.REQUIRES_OPERATOR_ACTION,
                    )
                )
                continue

            definition = rule_registry.get(rule_name)
            depends_on = tuple(entry.get("depends_on", definition.cls.depends_on))
            for dep_name in depends_on:
                if dep_name not in registered_rule_names:
                    blocking = True
                    conflicts.append(
                        ConflictRecord(
                            conflict_type=ConflictType.DEPENDENCY,
                            rule_names_involved=(rule_name, dep_name),
                            description=f"Dependency {dep_name} for rule {rule_name} is not registered.",
                            resolution=ConflictResolution.REQUIRES_OPERATOR_ACTION,
                        )
                    )
                elif dep_name not in enabled_rule_names:
                    blocking = True
                    conflicts.append(
                        ConflictRecord(
                            conflict_type=ConflictType.DEPENDENCY,
                            rule_names_involved=(rule_name, dep_name),
                            description=f"Dependency {dep_name} for rule {rule_name} is disabled in config.",
                            resolution=ConflictResolution.REQUIRES_OPERATOR_ACTION,
                        )
                    )

        return ConflictResolutionReport(
            conflicts=tuple(conflicts),
            blocking=blocking,
            weights_after_resolution=normalized_weights,
        )

    def validate_or_raise(self, config: dict[str, Any]) -> ConflictResolutionReport:
        report = self.detect(config)
        if report.blocking:
            raise RuleConflictError(report)
        return report
