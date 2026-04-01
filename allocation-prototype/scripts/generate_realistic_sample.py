from __future__ import annotations

import argparse
import copy
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from allocation.api.schemas import AllocationRequest
from allocation.config.loader import ConfigLoader
from allocation.data.zomato_adapter import (
    build_order_set,
    build_partner_pool,
    generate_realistic_sample as generate_generic_realistic_sample,
    load_and_clean_csv,
    write_json,
)
from allocation.domain.order import Order
from allocation.domain.partner import DeliveryPartner
from allocation.engine.pipeline import DeterministicAllocationPipeline, PipelineResult
from allocation.rules.registry import build_rule_set
from allocation.rules.utils import haversine_km


OUTPUT_DIR = PROJECT_ROOT / "demo" / "sample_datasets"
RULE_CONFIG_PATH = PROJECT_ROOT / "src" / "allocation" / "config" / "rules.yaml"
TRAFFIC_PRESET_WEIGHTS = {
    "traffic_adjusted_proximity": 0.25,
    "proximity_score": 0.10,
}


@dataclass(frozen=True)
class CuratedDatasetSpec:
    slug: str
    name: str
    city: str
    scenario: str
    description: str
    recommended_for: str
    source_filters: dict[str, list[str]]
    max_orders: int
    require_weather_rejection: bool = False
    required_raw_vehicle_types: tuple[str, ...] = ()
    verify_traffic_delta: bool = False
    require_all_orders_allocated: bool = False


CURATED_SPECS = {
    "clear_weather": CuratedDatasetSpec(
        slug="realistic_clear_weather",
        name="Zomato Clear Weather Large (172 orders)",
        city="India",
        scenario="Large clear-weather allocation slice generated from Sunny, Cloudy, and Windy Zomato rows.",
        description="Large current-format payload sourced from the Zomato delivery dataset for baseline allocation runs without using the dataset's distance field.",
        recommended_for="High-volume baseline allocation demos, score inspection, and on_time_rate walkthroughs.",
        source_filters={"weather": ["Sunny", "Cloudy", "Windy"]},
        max_orders=172,
    ),
    "severe_weather": CuratedDatasetSpec(
        slug="realistic_severe_weather",
        name="Zomato Severe Weather Large (288 orders)",
        city="India",
        scenario="Large severe-weather slice generated from Stormy and Sandstorms Zomato rows.",
        description="Large current-format payload from the Zomato delivery dataset for showing weather-based safety filtering without relying on the dataset's distance field.",
        recommended_for="Weather safety rule demos, rejection diagnostics, and severe-condition allocation review at larger scale.",
        source_filters={"weather": ["Stormy", "Sandstorms"]},
        max_orders=288,
        require_weather_rejection=True,
        required_raw_vehicle_types=("MOTORCYCLE", "ELECTRIC_SCOOTER"),
    ),
    "traffic_jam": CuratedDatasetSpec(
        slug="realistic_traffic_jam",
        name="Zomato Traffic Jam Large (544 orders)",
        city="India",
        scenario="Large High and Jam traffic slice curated to demonstrate traffic-aware proximity counterfactuals.",
        description="Large current-format payload from the Zomato delivery dataset for showing traffic-aware partner ranking without using the dataset's distance field.",
        recommended_for="Counterfactual simulation demos and traffic-aware scoring comparison at larger scale.",
        source_filters={"traffic_density": ["Jam", "High"]},
        max_orders=544,
        verify_traffic_delta=True,
    ),
}


def _default_csv_path() -> Path:
    return (PROJECT_ROOT / ".." / "Zomato Dataset.csv").resolve()


def _default_output_path(mode: str) -> Path:
    if mode == "generic":
        return PROJECT_ROOT / "demo" / "zomato_allocation_payload.json"
    spec = CURATED_SPECS[mode]
    return OUTPUT_DIR / f"{spec.slug}.json"


def _rule_entry(config: dict[str, Any], rule_name: str) -> dict[str, Any]:
    for section in ("hard_rules", "scoring_rules"):
        for entry in config.get(section, []):
            if entry.get("name") == rule_name:
                return entry
    raise KeyError(f"Rule {rule_name} not found in config")


def _scoring_config(enable_traffic_adjusted: bool) -> dict[str, Any]:
    config = copy.deepcopy(ConfigLoader(RULE_CONFIG_PATH).load().config)
    if enable_traffic_adjusted:
        _rule_entry(config, "traffic_adjusted_proximity")["enabled"] = True
        config.setdefault("weights", {}).update(TRAFFIC_PRESET_WEIGHTS)
    return config


def _orders_from_request(payload: AllocationRequest) -> list[Order]:
    return [
        Order(
            order_id=order.order_id,
            latitude=float(order.latitude),
            longitude=float(order.longitude),
            amount_paise=order.amount_paise,
            requested_vehicle_type=order.requested_vehicle_type,
            created_at=order.created_at,
            restaurant_latitude=order.restaurant_latitude if order.restaurant_latitude is not None else order.latitude,
            restaurant_longitude=(
                order.restaurant_longitude if order.restaurant_longitude is not None else order.longitude
            ),
            delivery_latitude=order.delivery_latitude,
            delivery_longitude=order.delivery_longitude,
            weather_condition=order.weather_condition,
            traffic_density=order.traffic_density,
            order_type=order.order_type,
            priority=order.priority,
            vehicle_required_raw=order.vehicle_required_raw,
        )
        for order in payload.orders
    ]


def _partners_from_request(payload: AllocationRequest) -> list[DeliveryPartner]:
    return [
        DeliveryPartner(
            partner_id=partner.partner_id,
            latitude=float(partner.latitude),
            longitude=float(partner.longitude),
            is_available=partner.is_available,
            rating=partner.rating,
            vehicle_types=tuple(partner.vehicle_types),
            active=partner.active,
            name=partner.name,
            current_load=partner.current_load,
            vehicle_condition=partner.vehicle_condition,
            avg_time_taken_min=partner.avg_time_taken_min,
            city=partner.city,
            raw_vehicle_type=partner.raw_vehicle_type,
        )
        for partner in payload.partners
    ]


def _evaluate_payload(payload: dict[str, Any], *, enable_traffic_adjusted: bool = False) -> PipelineResult:
    config = _scoring_config(enable_traffic_adjusted=enable_traffic_adjusted)
    hard_rules, scoring_rules = build_rule_set(config)
    pipeline = DeterministicAllocationPipeline(hard_rules=hard_rules, scoring_rules=scoring_rules)

    request_payload = AllocationRequest.model_validate(payload)
    orders = _orders_from_request(request_payload)
    partners = _partners_from_request(request_payload)

    return pipeline.evaluate(
        orders=orders,
        partners=partners,
        scoring_weights=config.get("weights", {}),
        partner_loads={partner.partner_id: 0 for partner in partners},
        fairness_escalation_event=None,
        conflict_resolution_report_hash="generate-realistic-sample",
    )


def _payload_from_rows(
    rows: list[dict[str, Any]],
    *,
    csv_path: Path,
    spec: CuratedDatasetSpec,
    extra_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    orders = build_order_set(rows, max_orders=spec.max_orders)
    partners = build_partner_pool(rows)
    payload: dict[str, Any] = {
        "orders": orders,
        "partners": partners,
        "metadata": {
            "name": spec.name,
            "city": spec.city,
            "scenario": spec.scenario,
            "description": spec.description,
            "recommended_for": spec.recommended_for,
            "generator": "scripts/generate_realistic_sample.py",
            "source_file": str(csv_path),
            "source_filters": spec.source_filters,
            "orders_generated": len(orders),
            "partners_generated": len(partners),
        },
    }
    if extra_metadata:
        payload["metadata"].update(extra_metadata)
    return payload


def _window_iter(rows: list[dict[str, Any]], *, window_size: int, max_windows: int | None = None):
    total_windows = (len(rows) + window_size - 1) // window_size
    limit = min(total_windows, max_windows) if max_windows is not None else total_windows
    for window_index in range(limit):
        start = window_index * window_size
        window = rows[start : start + window_size]
        if window:
            yield window_index, window


def _minimum_partner_count(spec: CuratedDatasetSpec) -> int:
    if spec.max_orders >= 500:
        return 45
    if spec.max_orders >= 250:
        return 40
    if spec.max_orders >= 150:
        return 35
    return 5


def _cluster_signature(rows: list[dict[str, Any]]) -> tuple[tuple[str, float, float], ...]:
    return tuple(
        (
            str(row["partner_id"]),
            float(row["restaurant_lat"]),
            float(row["restaurant_lon"]),
        )
        for row in rows[:25]
    )


def _candidate_rows_from_anchor(
    rows: list[dict[str, Any]],
    anchor: dict[str, Any],
    *,
    max_orders: int,
    min_unique_partners: int,
) -> tuple[float, list[dict[str, Any]]] | None:
    distance_rows = sorted(
        (
            haversine_km(
                float(anchor["restaurant_lat"]),
                float(anchor["restaurant_lon"]),
                float(row["restaurant_lat"]),
                float(row["restaurant_lon"]),
            ),
            index,
            row,
        )
        for index, row in enumerate(rows)
    )
    if len(distance_rows) < max_orders:
        return None

    selected_pairs: list[tuple[float, int, dict[str, Any]]] = []
    selected_indexes: set[int] = set()
    seen_partners: set[str] = set()

    for distance_km, index, row in distance_rows:
        partner_id = str(row.get("partner_id", "")).strip()
        if not partner_id or partner_id in seen_partners:
            continue
        seen_partners.add(partner_id)
        selected_pairs.append((distance_km, index, row))
        selected_indexes.add(index)
        if len(seen_partners) >= min_unique_partners:
            break

    if len(seen_partners) < min_unique_partners:
        return None

    for distance_km, index, row in distance_rows:
        if index in selected_indexes:
            continue
        selected_pairs.append((distance_km, index, row))
        selected_indexes.add(index)
        if len(selected_pairs) >= max_orders:
            break

    if len(selected_pairs) < max_orders:
        return None

    selected = [row for _, _, row in selected_pairs]
    radius_km = max(distance_km for distance_km, _, _ in selected_pairs)
    return radius_km, selected


def _cluster_candidates(rows: list[dict[str, Any]], spec: CuratedDatasetSpec) -> list[list[dict[str, Any]]]:
    if len(rows) <= spec.max_orders:
        return [rows]

    minimum_partner_count = _minimum_partner_count(spec)
    bucketed_rows: dict[tuple[float, float], list[dict[str, Any]]] = {}
    for row in rows:
        bucket_key = (round(float(row["restaurant_lat"]), 1), round(float(row["restaurant_lon"]), 1))
        bucketed_rows.setdefault(bucket_key, []).append(row)

    candidate_entries: list[tuple[tuple[float, int, int, float], list[dict[str, Any]]]] = []
    seen_signatures: set[tuple[tuple[str, float, float], ...]] = set()

    for bucket_rows in sorted(bucketed_rows.values(), key=len, reverse=True):
        if len(bucket_rows) < spec.max_orders:
            continue

        anchor_step = max(1, len(bucket_rows) // 12)
        for anchor_index in range(0, len(bucket_rows), anchor_step):
            candidate = _candidate_rows_from_anchor(
                bucket_rows,
                bucket_rows[anchor_index],
                max_orders=spec.max_orders,
                min_unique_partners=minimum_partner_count,
            )
            if candidate is None:
                continue

            radius_km, selected_rows = candidate
            partner_count = len({str(row["partner_id"]) for row in selected_rows if str(row.get("partner_id", "")).strip()})
            if partner_count < minimum_partner_count:
                continue

            signature = _cluster_signature(selected_rows)
            if signature in seen_signatures:
                continue
            seen_signatures.add(signature)

            candidate_entries.append(
                (
                    (radius_km, -partner_count, -len(bucket_rows), float(bucket_rows[anchor_index]["restaurant_lat"])),
                    selected_rows,
                )
            )

        if len(candidate_entries) >= 18:
            break

    if not candidate_entries:
        candidate_entries.extend(
            (
                (float(window_index), -len({row["partner_id"] for row in window}), -len(window), 0.0),
                window,
            )
            for window_index, window in _window_iter(rows, window_size=spec.max_orders, max_windows=5 if spec.verify_traffic_delta else None)
        )

    candidate_entries.sort(key=lambda item: item[0])
    return [rows for _, rows in candidate_entries]


def _selected_partner_diff_exists(baseline: PipelineResult, traffic_adjusted: PipelineResult) -> bool:
    baseline_map = {allocation.order_id: allocation.partner_id for allocation in baseline.allocations}
    traffic_map = {allocation.order_id: allocation.partner_id for allocation in traffic_adjusted.allocations}
    return any(baseline_map.get(order_id) != traffic_map.get(order_id) for order_id in baseline_map)


def _has_failure_code(result: PipelineResult, failure_code: str) -> bool:
    for order_trace in result.trace.orders:
        for candidate in order_trace.get("candidates", []):
            for hard_result in candidate.get("hard_results", []):
                if hard_result.get("failure_code") == failure_code:
                    return True
    return False


def _window_has_required_raw_vehicle_types(rows: list[dict[str, Any]], required_types: tuple[str, ...]) -> bool:
    if not required_types:
        return True
    seen_types = {partner["raw_vehicle_type"] for partner in build_partner_pool(rows)}
    return set(required_types) <= seen_types


def _valid_demo_window(rows: list[dict[str, Any]], max_orders: int) -> bool:
    if not rows:
        return False

    orders = build_order_set(rows, max_orders=max_orders)
    partners = build_partner_pool(rows)
    if not orders or len(partners) < 5:
        return False

    return all(3.0 <= float(partner.get("rating", 0.0)) <= 5.0 for partner in partners)


def _payload_quality_key(payload: dict[str, Any], result: PipelineResult) -> tuple[int, int, float, int]:
    hard_failures = result.aggregate_diagnostics.get("hard_rule_elimination_counts", {})
    return (
        int(result.aggregate_diagnostics.get("unallocated", 0)),
        int(hard_failures.get("max_distance", 0)),
        -len(payload.get("partners", [])),
        -len(payload.get("orders", [])),
    )


def _select_curated_payload(csv_path: Path, spec: CuratedDatasetSpec) -> dict[str, Any]:
    clean_rows = load_and_clean_csv(str(csv_path))
    filtered_rows = [
        row
        for row in clean_rows
        if all(str(row.get(field, "")).strip() in set(values) for field, values in spec.source_filters.items())
    ]

    best_payload: dict[str, Any] | None = None
    best_quality_key: tuple[int, int, float, int] | None = None
    best_eligible_payload: dict[str, Any] | None = None
    best_eligible_quality_key: tuple[int, int, float, int] | None = None
    traffic_checks = 0

    for window in _cluster_candidates(filtered_rows, spec):
        if not _valid_demo_window(window, spec.max_orders):
            continue

        payload = _payload_from_rows(window, csv_path=csv_path, spec=spec)
        baseline_result = _evaluate_payload(payload)
        quality_key = _payload_quality_key(payload, baseline_result)
        if best_payload is None or quality_key < best_quality_key:
            best_payload = payload
            best_quality_key = quality_key

        if not _window_has_required_raw_vehicle_types(window, spec.required_raw_vehicle_types):
            continue
        if spec.require_all_orders_allocated and baseline_result.aggregate_diagnostics.get("unallocated", 0) > 0:
            continue
        if spec.require_weather_rejection and not _has_failure_code(
            baseline_result,
            "VEHICLE_UNSAFE_IN_WEATHER",
        ):
            continue

        if best_eligible_payload is None or quality_key < best_eligible_quality_key:
            best_eligible_payload = payload
            best_eligible_quality_key = quality_key

        if spec.verify_traffic_delta:
            if traffic_checks >= 5:
                continue
            traffic_checks += 1
            traffic_adjusted_result = _evaluate_payload(payload, enable_traffic_adjusted=True)
            if _selected_partner_diff_exists(baseline_result, traffic_adjusted_result):
                payload["metadata"]["traffic_delta_verified"] = True
                return payload
            continue

    if best_eligible_payload is not None and not spec.verify_traffic_delta:
        return best_eligible_payload

    if best_payload is None:
        fallback_rows = filtered_rows[: spec.max_orders]
        best_payload = _payload_from_rows(fallback_rows, csv_path=csv_path, spec=spec)

    if spec.verify_traffic_delta:
        best_payload["metadata"]["traffic_delta_verified"] = False
        best_payload["metadata"]["note"] = "equidistant partners; delta requires custom coords"

    return best_payload


def generate_curated_dataset(mode: str, *, csv_path: Path, output_path: Path) -> None:
    spec = CURATED_SPECS[mode]
    payload = _select_curated_payload(csv_path, spec)
    write_json(output_path, payload)
    print(
        f"Wrote {output_path.name}: "
        f"{len(payload['orders'])} orders, {len(payload['partners'])} partners"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate realistic sample payloads from the Zomato CSV")
    parser.add_argument(
        "--mode",
        choices=["generic", *CURATED_SPECS.keys()],
        default="generic",
        help="Generation mode for either the base realistic sample or curated demo datasets",
    )
    parser.add_argument(
        "--csv",
        default=str(_default_csv_path()),
        help="Path to the source Zomato CSV",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Destination JSON path. Defaults to the mode-specific sample dataset path.",
    )
    parser.add_argument(
        "--max-orders",
        type=int,
        default=None,
        help="Maximum number of orders to include in generic mode. Curated modes use built-in sizes.",
    )
    parser.add_argument(
        "--weather",
        action="append",
        default=[],
        help="Optional clean-row weather filter for generic mode. Repeat to allow multiple values.",
    )
    parser.add_argument(
        "--traffic",
        action="append",
        default=[],
        help="Optional clean-row traffic-density filter for generic mode. Repeat to allow multiple values.",
    )
    parser.add_argument(
        "--city",
        action="append",
        default=[],
        help="Optional clean-row city filter for generic mode. Repeat to allow multiple values.",
    )
    args = parser.parse_args()

    csv_path = Path(args.csv).resolve()
    output_path = Path(args.output).resolve() if args.output else _default_output_path(args.mode).resolve()

    if args.mode == "generic":
        source_filters: dict[str, list[str]] = {}
        if args.weather:
            source_filters["weather"] = args.weather
        if args.traffic:
            source_filters["traffic_density"] = args.traffic
        if args.city:
            source_filters["city"] = args.city

        generate_generic_realistic_sample(
            csv_path=str(csv_path),
            output_path=str(output_path),
            max_orders=args.max_orders or 15,
            source_filters=source_filters or None,
        )
        return

    generate_curated_dataset(args.mode, csv_path=csv_path, output_path=output_path)


if __name__ == "__main__":
    main()
