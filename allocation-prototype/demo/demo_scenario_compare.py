from __future__ import annotations

import copy
from pathlib import Path

from common import PROJECT_ROOT

from allocation.api.schemas import AllocationRequest
from allocation.config.loader import ConfigLoader
from allocation.domain.order import Order
from allocation.domain.partner import DeliveryPartner
from allocation.engine.pipeline import DeterministicAllocationPipeline
from allocation.rules.registry import build_rule_set


PAYLOAD_PATH = PROJECT_ROOT / "demo" / "zomato_allocation_payload.json"
CONFIG_PATH = PROJECT_ROOT / "src" / "allocation" / "config" / "rules.yaml"


def load_payload() -> tuple[list[Order], list[DeliveryPartner]]:
    payload = AllocationRequest.model_validate_json(PAYLOAD_PATH.read_text())
    orders = [
        Order(
            order_id=order.order_id,
            latitude=order.latitude,
            longitude=order.longitude,
            amount_paise=order.amount_paise,
            requested_vehicle_type=order.requested_vehicle_type,
            created_at=order.created_at,
        )
        for order in payload.orders
    ]
    partners = [
        DeliveryPartner(
            partner_id=partner.partner_id,
            latitude=partner.latitude,
            longitude=partner.longitude,
            is_available=partner.is_available,
            rating=partner.rating,
            vehicle_types=tuple(partner.vehicle_types),
            active=partner.active,
        )
        for partner in payload.partners
    ]
    return orders, partners


def scenario_configurations() -> list[tuple[str, dict]]:
    loaded = ConfigLoader(CONFIG_PATH).load()
    compatibility = copy.deepcopy(loaded.config)

    baseline = copy.deepcopy(compatibility)
    baseline.pop("vehicle_compatibility", None)

    relaxed_distance = copy.deepcopy(baseline)
    for rule in relaxed_distance["hard_rules"]:
        if rule["name"] == "max_distance":
            rule.setdefault("params", {})["max_distance_km"] = 8.0
            break

    return [
        ("Baseline", baseline),
        ("Relaxed distance", relaxed_distance),
        ("Compatibility", compatibility),
    ]


def format_failure_combination(aggregate_diagnostics: dict) -> str:
    combinations = aggregate_diagnostics.get("unallocated_orders_by_failure_combination", {})
    if not combinations:
        return "NONE"

    top_combination, count = max(combinations.items(), key=lambda item: (item[1], item[0]))
    label = (
        top_combination.replace("DISTANCE_LIMIT_EXCEEDED", "DISTANCE")
        .replace("VEHICLE_TYPE_MISMATCH", "VEHICLE")
        .replace("PARTNER_UNAVAILABLE", "AVAILABILITY")
        .replace("RATING_TOO_LOW", "RATING_LOW")
        .replace("RATING_TOO_HIGH", "RATING_HIGH")
    )
    return f"{label} ({count})"


def run_scenario(name: str, config: dict, orders: list[Order], partners: list[DeliveryPartner]) -> dict[str, str | int]:
    hard_rules, scoring_rules = build_rule_set(config)
    pipeline = DeterministicAllocationPipeline(hard_rules, scoring_rules)
    result = pipeline.evaluate(
        orders=orders,
        partners=partners,
        scoring_weights=config["weights"],
        partner_loads={partner.partner_id: 0 for partner in partners},
        fairness_escalation_event=None,
        conflict_resolution_report_hash="scenario-compare",
    )

    diagnostics = result.aggregate_diagnostics
    return {
        "scenario": name,
        "allocated": diagnostics["allocated"],
        "unallocated": diagnostics["unallocated"],
        "top_failure": format_failure_combination(diagnostics),
    }


if __name__ == "__main__":
    if not PAYLOAD_PATH.exists():
        raise SystemExit(
            "Expected demo/zomato_allocation_payload.json. Run scripts/prepare_zomato_data.py first."
        )

    orders, partners = load_payload()
    rows = [run_scenario(name, config, orders, partners) for name, config in scenario_configurations()]

    print("Scenario              Allocated  Unallocated  Top hard-rule elimination")
    print("---------------------------------------------------------------------------")
    for row in rows:
        print(
            f"{row['scenario']:<21}"
            f"{row['allocated']:<11}"
            f"{row['unallocated']:<13}"
            f"{row['top_failure']}"
        )
