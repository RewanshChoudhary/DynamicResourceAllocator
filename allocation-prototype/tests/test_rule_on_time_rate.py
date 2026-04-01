from __future__ import annotations

from allocation.domain.enums import VehicleType
from allocation.domain.order import Order
from allocation.domain.partner import DeliveryPartner
from allocation.rules.scoring.on_time_rate import OnTimeRateRule


def _order() -> Order:
    return Order(
        order_id="ORD-1",
        latitude=12.9716,
        longitude=77.5946,
        amount_paise=25000,
        requested_vehicle_type=VehicleType.BIKE,
    )


def _partner(avg_time_taken_min: int) -> DeliveryPartner:
    return DeliveryPartner(
        partner_id=f"PT-{avg_time_taken_min}",
        latitude=12.9717,
        longitude=77.5947,
        is_available=True,
        rating=4.8,
        vehicle_types=(VehicleType.BIKE,),
        avg_time_taken_min=avg_time_taken_min,
    )


def test_fast_partner_scores_high():
    result = OnTimeRateRule(baseline_minutes=30).score(_order(), _partner(15), {})

    assert result.raw_score == 1.0


def test_average_partner_scores_ten():
    result = OnTimeRateRule(baseline_minutes=30).score(_order(), _partner(30), {})

    assert result.raw_score == 1.0


def test_slow_partner_scores_lower():
    result = OnTimeRateRule(baseline_minutes=30).score(_order(), _partner(60), {})

    assert result.raw_score == 0.5


def test_very_slow_partner_floor_is_zero():
    result = OnTimeRateRule(baseline_minutes=30).score(_order(), _partner(999), {})

    assert 0.0 < result.raw_score < 0.1


def test_score_breakdown_contains_required_keys():
    result = OnTimeRateRule(baseline_minutes=30).score(_order(), _partner(45), {})

    assert {
        "partner_avg_time_min",
        "baseline_minutes",
        "speed_ratio",
        "display_score_10",
        "on_time_rate",
    } <= result.score_breakdown.keys()


def test_evidence_contains_partner_id():
    result = OnTimeRateRule(baseline_minutes=30).score(_order(), _partner(45), {})

    assert result.score_breakdown["partner_avg_time_min"] == 45.0


def test_weight_in_config_is_correct_type(base_config):
    config = dict(base_config)
    config["scoring_rules"] = list(base_config["scoring_rules"]) + [
        {"name": "on_time_rate", "enabled": True, "params": {"baseline_minutes": 30}}
    ]
    config["weights"] = dict(base_config["weights"]) | {"on_time_rate": 0.15}

    assert isinstance(config["weights"]["on_time_rate"], float)
