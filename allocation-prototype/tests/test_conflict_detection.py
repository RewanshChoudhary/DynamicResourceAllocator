from __future__ import annotations

from allocation.rules.conflict import RuleConflictDetector


def test_conflict_detector_blocks_logical_contradictions(base_config):
    config = dict(base_config)
    config["hard_rules"] = list(base_config["hard_rules"]) + [
        {"name": "max_rating", "enabled": True, "params": {"max_rating": 3.0}}
    ]

    detector = RuleConflictDetector()
    report = detector.detect(config)

    assert report.blocking is True
    assert any(c.conflict_type.value == "logical" for c in report.conflicts)


def test_conflict_detector_normalizes_weights(base_config):
    config = dict(base_config)
    config["weights"] = {
        "proximity_score": 0.5,
        "rating_score": 0.3,
        "fairness_score": 0.3,
    }

    detector = RuleConflictDetector()
    report = detector.detect(config)

    assert report.blocking is False
    assert abs(sum(report.weights_after_resolution.values()) - 1.0) < 1e-6
    assert any(c.conflict_type.value == "weight" for c in report.conflicts)


def test_conflict_detector_blocks_unknown_rule(base_config):
    config = dict(base_config)
    config["hard_rules"] = list(base_config["hard_rules"]) + [{"name": "unknown_rule", "enabled": True}]

    detector = RuleConflictDetector()
    report = detector.detect(config)

    assert report.blocking is True
    assert any("not registered" in c.description for c in report.conflicts)
