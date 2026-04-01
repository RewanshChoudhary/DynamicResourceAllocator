from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone

from common import make_partners

from allocation.domain.enums import VehicleType
from allocation.domain.order import Order
from allocation.engine.pipeline import DeterministicAllocationPipeline
from allocation.fairness.gini import FairnessEnforcer, GiniCalculator
from allocation.fairness.tracker import PartnerLoadTracker
from allocation.rules.registry import build_rule_set


def build_orders(batch_prefix: str, count: int) -> list[Order]:
    base_ts = datetime(2026, 2, 22, 9, 0, tzinfo=timezone.utc)
    orders: list[Order] = []
    for idx in range(count):
        orders.append(
            Order(
                order_id=f"{batch_prefix}-{idx:02d}",
                latitude=12.9716,
                longitude=77.5946,
                amount_paise=20000,
                requested_vehicle_type=VehicleType.BIKE,
                created_at=base_ts + timedelta(minutes=idx),
            )
        )
    return orders


if __name__ == "__main__":
    config = {
        "hard_rules": [
            {"name": "availability", "enabled": True},
            {"name": "vehicle_type", "enabled": True},
            {"name": "max_distance", "enabled": True, "params": {"max_distance_km": 5.0}},
            {"name": "min_rating", "enabled": True, "params": {"min_rating": 3.0}},
        ],
        "scoring_rules": [
            {"name": "proximity_score", "enabled": True, "params": {"scale_km": 5.0}},
            {"name": "rating_score", "enabled": True},
            {"name": "fairness_score", "enabled": True},
        ],
        "weights": {
            "proximity_score": 0.45,
            "rating_score": 0.25,
            "fairness_score": 0.30,
        },
    }

    hard_rules, scoring_rules = build_rule_set(config)
    pipeline = DeterministicAllocationPipeline(hard_rules=hard_rules, scoring_rules=scoring_rules)
    partners = make_partners()

    tracker = PartnerLoadTracker(window=timedelta(hours=1))

    print("Batch 1: forcing concentration on one partner (P-1).")
    batch1_orders = build_orders("B1", 15)
    batch1_weights = {
        "proximity_score": 0.75,
        "rating_score": 0.25,
        "fairness_score": 0.0,
    }
    batch1_result = pipeline.evaluate(
        orders=batch1_orders,
        partners=partners,
        scoring_weights=batch1_weights,
        partner_loads={partner.partner_id: 0 for partner in partners},
        fairness_escalation_event=None,
        conflict_resolution_report_hash="demo",
    )

    batch1_assignments = Counter([a.partner_id for a in batch1_result.allocations if a.partner_id])
    print("Batch 1 assignment counts:", dict(batch1_assignments))

    for allocation in batch1_result.allocations:
        if allocation.partner_id:
            tracker.record_assignment(allocation.partner_id)

    partner_loads = tracker.get_load_counts([partner.partner_id for partner in partners])
    gini_before = GiniCalculator.compute(list(partner_loads.values()))
    print("Rolling loads after batch 1:", partner_loads)
    print(f"Computed Gini before batch 2: {gini_before:.4f}")

    enforcer = FairnessEnforcer(
        base_weights=config["weights"],
        fairness_threshold=0.35,
        escalation_factor=1.5,
    )
    batch2_weights, event = enforcer.adjust_weights(partner_loads)
    print("Escalation event:", event.to_dict() if event else None)

    batch2_orders = build_orders("B2", 6)
    batch2_result = pipeline.evaluate(
        orders=batch2_orders,
        partners=partners,
        scoring_weights=batch2_weights,
        partner_loads=partner_loads,
        fairness_escalation_event=event.to_dict() if event else None,
        conflict_resolution_report_hash="demo",
    )
    batch2_assignments = Counter([a.partner_id for a in batch2_result.allocations if a.partner_id])

    print("Batch 2 assignment counts (after fairness escalation):", dict(batch2_assignments))
