from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from allocation.rules.conflict import RuleConflictDetector, RuleConflictError, ConflictResolutionReport


@dataclass(frozen=True)
class LoadedConfig:
    config: dict[str, Any]
    conflict_report: ConflictResolutionReport


class ConfigLoader:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.conflict_detector = RuleConflictDetector()

    def load(self) -> LoadedConfig:
        raw = yaml.safe_load(self.path.read_text())
        if not isinstance(raw, dict):
            raise ValueError("Rule config must be a YAML mapping")

        report = self.conflict_detector.detect(raw)
        if report.weights_after_resolution:
            raw = dict(raw)
            raw["weights"] = report.weights_after_resolution

        if report.blocking:
            raise RuleConflictError(report)

        return LoadedConfig(config=raw, conflict_report=report)
