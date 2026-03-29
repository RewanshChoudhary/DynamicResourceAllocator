from __future__ import annotations

from datetime import datetime, timezone

from allocation.domain.enums import VehicleType
from allocation.domain.order import Order
from allocation.domain.partner import DeliveryPartner
from allocation.engine.pipeline import DeterministicAllocationPipeline, build_aggregate_diagnostics
from allocation.rules.registry import build_rule_set


def _order(order_id: str, vehicle_type: VehicleType, latitude: float = 12.9716, longitude: float = 77.5946) -> Order:
    return Order(
        order_id=order_id,
        latitude=latitude,
        longitude=longitude,
        amount_paise=25000,
        requested_vehicle_type=vehicle_type,
        created_at=datetime(2026, 2, 22, 12, 0, tzinfo=timezone.utc),
    )


def _partner(
    partner_id: str,
    vehicle_types: tuple[VehicleType, ...],
    *,
    latitude: float = 12.9717,
    longitude: float = 77.5947,
    is_available: bool = True,
    active: bool = True,
    rating: float = 4.8,
) -> DeliveryPartner:
    return DeliveryPartner(
        partner_id=partner_id,
        latitude=latitude,
        longitude=longitude,
        is_available=is_available,
        rating=rating,
        vehicle_types=vehicle_types,
        active=active,
    )


def test_pipeline_aggregate_diagnostics_reports_expected_unallocated_count(base_config):
    hard_rules, scoring_rules = build_rule_set(base_config)
    pipeline = DeterministicAllocationPipeline(hard_rules, scoring_rules)

    orders = [
        _order("ORD-ALLOCATED", VehicleType.BIKE),
        _order("ORD-UNALLOCATED", VehicleType.CAR),
    ]
    partners = [_partner("PT-BIKE", (VehicleType.BIKE,))]

    result = pipeline.evaluate(
        orders=orders,
        partners=partners,
        scoring_weights=base_config["weights"],
        partner_loads={"PT-BIKE": 0},
        fairness_escalation_event=None,
        conflict_resolution_report_hash="conflict-hash",
    )

    assert result.aggregate_diagnostics["total_orders"] == 2
    assert result.aggregate_diagnostics["allocated"] == 1
    assert result.aggregate_diagnostics["unallocated"] == 1


def test_pipeline_aggregate_diagnostics_counts_first_failed_rule_across_all_candidate_pairs(base_config):
    hard_rules, scoring_rules = build_rule_set(base_config)
    pipeline = DeterministicAllocationPipeline(hard_rules, scoring_rules)

    orders = [
        _order("ORD-CAR-1", VehicleType.CAR),
        _order("ORD-CAR-2", VehicleType.CAR),
    ]
    partners = [
        _partner("PT-BIKE-1", (VehicleType.BIKE,)),
        _partner("PT-BIKE-2", (VehicleType.BIKE,)),
        _partner("PT-BIKE-3", (VehicleType.BIKE,)),
    ]

    result = pipeline.evaluate(
        orders=orders,
        partners=partners,
        scoring_weights=base_config["weights"],
        partner_loads={partner.partner_id: 0 for partner in partners},
        fairness_escalation_event=None,
        conflict_resolution_report_hash="conflict-hash",
    )

    assert result.aggregate_diagnostics["unallocated"] == 2
    assert result.aggregate_diagnostics["hard_rule_elimination_counts"]["vehicle_type"] == 6
    assert result.aggregate_diagnostics["hard_rule_elimination_counts"]["availability"] == 0
    assert result.aggregate_diagnostics["hard_rule_elimination_counts"]["max_distance"] == 0
    assert result.aggregate_diagnostics["hard_rule_elimination_counts"]["min_rating"] == 0


def test_aggregate_diagnostics_groups_unallocated_orders_by_failure_combination():
    diagnostics = build_aggregate_diagnostics(
        order_traces=[
            {
                "order_id": "ORD-A",
                "selected_partner_id": None,
                "candidates": [
                    {
                        "partner_id": "PT-1",
                        "hard_results": [
                            {
                                "rule": "vehicle_type",
                                "passed": False,
                                "failure_code": "VEHICLE_TYPE_MISMATCH",
                            }
                        ],
                    },
                    {
                        "partner_id": "PT-2",
                        "hard_results": [
                            {
                                "rule": "max_distance",
                                "passed": False,
                                "failure_code": "DISTANCE_LIMIT_EXCEEDED",
                            }
                        ],
                    },
                ],
            },
            {
                "order_id": "ORD-B",
                "selected_partner_id": None,
                "candidates": [
                    {
                        "partner_id": "PT-3",
                        "hard_results": [
                            {
                                "rule": "availability",
                                "passed": False,
                                "failure_code": "PARTNER_UNAVAILABLE",
                            }
                        ],
                    },
                    {
                        "partner_id": "PT-4",
                        "hard_results": [
                            {
                                "rule": "vehicle_type",
                                "passed": False,
                                "failure_code": "VEHICLE_TYPE_MISMATCH",
                            }
                        ],
                    },
                ],
            },
        ],
        hard_rule_names=["availability", "vehicle_type", "max_distance", "min_rating"],
    )

    assert diagnostics["unallocated"] == 2
    assert diagnostics["unallocated_orders_by_failure_combination"] == {
        "DISTANCE_LIMIT_EXCEEDED+VEHICLE_TYPE_MISMATCH": 1,
        "PARTNER_UNAVAILABLE+VEHICLE_TYPE_MISMATCH": 1,
    }
