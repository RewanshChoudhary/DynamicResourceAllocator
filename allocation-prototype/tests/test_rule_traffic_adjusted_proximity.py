from __future__ import annotations

from allocation.domain.enums import VehicleType
from allocation.domain.order import Order
from allocation.domain.partner import DeliveryPartner
from allocation.rules.scoring.traffic_adjusted_proximity import TrafficAdjustedProximityRule


def _order(traffic_density: str) -> Order:
    return Order(
        order_id=f"ORD-{traffic_density}",
        latitude=12.9716,
        longitude=77.5946,
        amount_paise=25000,
        requested_vehicle_type=VehicleType.BIKE,
        traffic_density=traffic_density,
    )


def _partner(latitude: float = 12.9816, longitude: float = 77.6046) -> DeliveryPartner:
    return DeliveryPartner(
        partner_id="PT-1",
        latitude=latitude,
        longitude=longitude,
        is_available=True,
        rating=4.8,
        vehicle_types=(VehicleType.BIKE,),
    )


def test_low_traffic_matches_raw_distance_score():
    result = TrafficAdjustedProximityRule(max_distance_km=10.0).score(_order("Low"), _partner(), {})

    assert 0.0 <= result.raw_score <= 1.0
    assert result.score_breakdown["traffic_multiplier"] == 1.0


def test_jam_traffic_reduces_score_vs_low_traffic():
    rule = TrafficAdjustedProximityRule(max_distance_km=10.0)

    low = rule.score(_order("Low"), _partner(), {})
    jam = rule.score(_order("Jam"), _partner(), {})

    assert jam.raw_score < low.raw_score


def test_unknown_traffic_density_defaults_to_multiplier_one():
    result = TrafficAdjustedProximityRule(max_distance_km=10.0).score(_order("Holiday"), _partner(), {})

    assert result.score_breakdown["traffic_multiplier"] == 1.0


def test_score_is_never_negative():
    result = TrafficAdjustedProximityRule(max_distance_km=1.0).score(_order("Jam"), _partner(13.5, 78.5), {})

    assert result.raw_score >= 0.0


def test_score_is_never_above_ten():
    result = TrafficAdjustedProximityRule(max_distance_km=10.0).score(_order("Low"), _partner(12.9716, 77.5946), {})

    assert result.raw_score <= 1.0


def test_score_breakdown_has_all_required_keys():
    result = TrafficAdjustedProximityRule(max_distance_km=10.0).score(_order("High"), _partner(), {})

    assert {
        "raw_distance_km",
        "traffic_density",
        "traffic_multiplier",
        "effective_distance_km",
        "max_distance_km",
        "traffic_adjusted_proximity",
    } <= result.score_breakdown.keys()


def test_very_far_partner_scores_zero_not_negative():
    result = TrafficAdjustedProximityRule(max_distance_km=10.0).score(_order("Low"), _partner(28.7041, 77.1025), {})

    assert result.raw_score == 0.0
