from __future__ import annotations

import pytest

from allocation.fairness.gini import FairnessEnforcer, GiniCalculator


def test_gini_calculator_basics():
    assert GiniCalculator.compute([0, 0, 0]) == 0.0
    assert GiniCalculator.compute([5, 5, 5]) == 0.0
    assert GiniCalculator.compute([10, 0, 0]) > 0.6


@pytest.mark.parametrize("loads", [[], None])
def test_gini_calculator_rejects_empty(loads):
    with pytest.raises(ValueError):
        GiniCalculator.compute(loads or [])


def test_fairness_enforcer_escalates_and_renormalizes(base_config):
    enforcer = FairnessEnforcer(
        base_weights=base_config["weights"],
        fairness_threshold=0.35,
        escalation_factor=1.5,
    )

    weights, event = enforcer.adjust_weights({"p1": 20, "p2": 0, "p3": 0})

    assert event is not None
    assert event.pre_gini > 0.35
    assert weights["fairness_score"] > base_config["weights"]["fairness_score"]
    assert abs(sum(weights.values()) - 1.0) < 1e-6
