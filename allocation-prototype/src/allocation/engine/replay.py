from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from allocation.domain.enums import VehicleType
from allocation.domain.order import Order
from allocation.domain.partner import DeliveryPartner
from allocation.engine.loads import initial_partner_loads_for_replay
from allocation.engine.manifest import SealedDecisionManifest, canonical_json_bytes, sha256_hex
from allocation.engine.pipeline import DeterministicAllocationPipeline
from allocation.rules.registry import build_rule_set


@dataclass(frozen=True)
class ReplayResult:
    matched: bool
    trace_hash_identical: bool
    original_trace: dict[str, Any]
    replayed_trace: dict[str, Any]
    divergence_point_if_any: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "matched": self.matched,
            "trace_hash_identical": self.trace_hash_identical,
            "original_trace": self.original_trace,
            "replayed_trace": self.replayed_trace,
            "divergence_point_if_any": self.divergence_point_if_any,
        }


class ReplayError(ValueError):
    pass


def snapshot_to_orders(snapshot: dict[str, Any]) -> list[Order]:
    orders: list[Order] = []
    for payload in snapshot.get("orders", []):
        orders.append(
            Order(
                order_id=payload["order_id"],
                latitude=float(payload["latitude"]),
                longitude=float(payload["longitude"]),
                amount_paise=int(payload["amount_paise"]),
                requested_vehicle_type=VehicleType(payload["requested_vehicle_type"]),
                created_at=datetime.fromisoformat(payload["created_at"]),
                restaurant_latitude=(
                    float(payload["restaurant_latitude"])
                    if payload.get("restaurant_latitude") is not None
                    else None
                ),
                restaurant_longitude=(
                    float(payload["restaurant_longitude"])
                    if payload.get("restaurant_longitude") is not None
                    else None
                ),
                delivery_latitude=(
                    float(payload["delivery_latitude"])
                    if payload.get("delivery_latitude") is not None
                    else None
                ),
                delivery_longitude=(
                    float(payload["delivery_longitude"])
                    if payload.get("delivery_longitude") is not None
                    else None
                ),
                weather_condition=str(payload.get("weather_condition", "Sunny")),
                traffic_density=str(payload.get("traffic_density", "Low")),
                order_type=str(payload.get("order_type", "Meal")),
                priority=str(payload.get("priority", "NORMAL")),
                vehicle_required_raw=payload.get("vehicle_required_raw"),
            )
        )
    return orders


def snapshot_to_partners(snapshot: dict[str, Any]) -> list[DeliveryPartner]:
    partners: list[DeliveryPartner] = []
    for payload in snapshot.get("partners", []):
        partners.append(
            DeliveryPartner(
                partner_id=payload["partner_id"],
                latitude=float(payload["latitude"]),
                longitude=float(payload["longitude"]),
                is_available=bool(payload["is_available"]),
                rating=float(payload["rating"]),
                vehicle_types=tuple(VehicleType(v) for v in payload.get("vehicle_types", [])),
                active=bool(payload.get("active", True)),
                name=payload.get("name"),
                current_load=int(payload.get("current_load", 0)),
                vehicle_condition=int(payload.get("vehicle_condition", 1)),
                avg_time_taken_min=int(payload.get("avg_time_taken_min", 30)),
                city=payload.get("city"),
                raw_vehicle_type=payload.get("raw_vehicle_type"),
            )
        )
    return partners


class DeterministicReplayer:
    def __init__(self, manifest_repo: Any, input_snapshot_repo: Any, config_store: Any) -> None:
        self.manifest_repo = manifest_repo
        self.input_snapshot_repo = input_snapshot_repo
        self.config_store = config_store

    def replay(self, manifest_id: str) -> ReplayResult:
        manifest = self.manifest_repo.get(manifest_id)
        if manifest is None:
            raise ReplayError(f"Manifest {manifest_id} not found")

        snapshot = self.input_snapshot_repo.get(manifest.input_hash)
        if snapshot is None:
            raise ReplayError(f"Input snapshot {manifest.input_hash} not found")

        historical_config = self.config_store.get_by_hash(manifest.config_version_hash)
        if historical_config is None:
            raise ReplayError(f"Config {manifest.config_version_hash} not found")

        hard_rules, scoring_rules = build_rule_set(historical_config["config"])
        pipeline = DeterministicAllocationPipeline(hard_rules=hard_rules, scoring_rules=scoring_rules)

        orders = snapshot_to_orders(snapshot)
        partners = snapshot_to_partners(snapshot)

        replayed = pipeline.evaluate(
            orders=orders,
            partners=partners,
            scoring_weights=manifest.evaluation_trace.get("scoring_weights", {}),
            partner_loads=initial_partner_loads_for_replay(manifest.evaluation_trace, partners),
            fairness_escalation_event=manifest.fairness_escalation_event,
            conflict_resolution_report_hash=manifest.conflict_resolution_report_hash,
        )

        replayed_trace = replayed.trace.to_dict()
        replayed_trace_hash = sha256_hex(canonical_json_bytes(replayed_trace))
        trace_hash_identical = replayed_trace_hash == manifest.trace_hash

        divergence = self._find_divergence(manifest.evaluation_trace, replayed_trace)

        return ReplayResult(
            matched=trace_hash_identical and divergence is None,
            trace_hash_identical=trace_hash_identical,
            original_trace=manifest.evaluation_trace,
            replayed_trace=replayed_trace,
            divergence_point_if_any=divergence,
        )

    @staticmethod
    def _find_divergence(original_trace: dict[str, Any], replayed_trace: dict[str, Any]) -> str | None:
        original_orders = {o["order_id"]: o for o in original_trace.get("orders", [])}
        replayed_orders = {o["order_id"]: o for o in replayed_trace.get("orders", [])}

        for order_id in sorted(set(original_orders) | set(replayed_orders)):
            if order_id not in original_orders:
                return f"order {order_id} missing from original trace"
            if order_id not in replayed_orders:
                return f"order {order_id} missing from replayed trace"

            original_partner = original_orders[order_id].get("selected_partner_id")
            replayed_partner = replayed_orders[order_id].get("selected_partner_id")
            if original_partner != replayed_partner:
                return (
                    f"order {order_id} selected partner diverged: "
                    f"original={original_partner} replayed={replayed_partner}"
                )

        return None
