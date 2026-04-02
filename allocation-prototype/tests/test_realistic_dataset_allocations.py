from __future__ import annotations

import json
from pathlib import Path

from allocation.api.routers.allocate import allocate
from allocation.api.routers.simulate import run_simulation
from allocation.api.schemas import AllocationRequest, SimulationRequest
from allocation.persistence.repository import ManifestRepository
from allocation.reservation import store as reservation_store_module
from api_test_utils import build_api_test_context


DATASET_DIR = Path(__file__).resolve().parents[1] / "demo" / "sample_datasets"
PRESET_PATH = Path(__file__).resolve().parents[1] / "data" / "simulation_presets.json"


def setup_function() -> None:
    reservation_store_module._store_instance = None


def _allocate_sample(tmp_path: Path, filename: str, *, idempotency_key: str):
    context = build_api_test_context(tmp_path)
    payload = json.loads((DATASET_DIR / filename).read_text())
    request_payload = AllocationRequest.model_validate(payload)
    response = allocate(
        request_payload,
        context.request("POST", "/allocations"),
        x_idempotency_key=idempotency_key,
    )
    return context, payload, response


def _trace_for_manifest(context, manifest_id: str) -> dict:
    with context.session_factory() as session:
        manifest = ManifestRepository(session).get(manifest_id)
        assert manifest is not None
        return manifest.evaluation_trace


def test_severe_weather_dataset_triggers_weather_safety_rejections(tmp_path):
    context, payload, response = _allocate_sample(
        tmp_path,
        "realistic_severe_weather.json",
        idempotency_key="realistic-severe-weather",
    )

    trace = _trace_for_manifest(context, response.manifest_id)

    assert response.summary["allocated_orders"] <= len(payload["partners"])
    assert response.summary["unallocated_orders"] > 0
    assert response.aggregate_diagnostics["hard_rule_elimination_counts"]["max_distance"] == 0
    assert response.aggregate_diagnostics["hard_rule_elimination_counts"]["weather_safety"] > 0
    assert any(
        hard_result.get("failure_code") == "VEHICLE_UNSAFE_IN_WEATHER"
        for order_trace in trace.get("orders", [])
        for candidate in order_trace.get("candidates", [])
        for hard_result in candidate.get("hard_results", [])
    )


def test_clear_weather_dataset_includes_on_time_rate_in_trace_scoring(tmp_path):
    context, payload, response = _allocate_sample(
        tmp_path,
        "realistic_clear_weather.json",
        idempotency_key="realistic-clear-weather",
    )

    trace = _trace_for_manifest(context, response.manifest_id)
    scored_candidates = 0

    assert response.summary["allocated_orders"] <= len(payload["partners"])
    assert response.summary["unallocated_orders"] > 0
    assert response.aggregate_diagnostics["hard_rule_elimination_counts"]["max_distance"] == 0
    for order_trace in trace.get("orders", []):
        hard_passed_candidates = [candidate for candidate in order_trace.get("candidates", []) if candidate["hard_passed"]]
        for candidate in hard_passed_candidates:
            scored_candidates += 1
            assert any(score["rule"] == "on_time_rate" for score in candidate.get("scoring_results", []))

    assert scored_candidates > 0


def test_traffic_jam_dataset_and_preset_change_allocations_when_verified(tmp_path):
    context, payload, response = _allocate_sample(
        tmp_path,
        "realistic_traffic_jam.json",
        idempotency_key="realistic-traffic-jam",
    )

    assert response.summary["allocated_orders"] <= len(payload["partners"])
    assert response.summary["unallocated_orders"] > 0
    assert response.aggregate_diagnostics["hard_rule_elimination_counts"]["max_distance"] < 1000

    metadata = payload["metadata"]
    if metadata.get("traffic_delta_verified") is not True:
        assert metadata["note"] == "equidistant partners; delta requires custom coords"
        return

    presets = json.loads(PRESET_PATH.read_text())
    traffic_preset = next(preset for preset in presets if preset["name"] == "Enable Traffic-Aware Proximity")
    simulation_payload = SimulationRequest.model_validate(
        {
            "manifest_id": response.manifest_id,
            "mutations": traffic_preset["mutations"],
        }
    )

    result = run_simulation(
        simulation_payload,
        context.request("POST", "/simulations"),
    )

    assert result["counterfactual_summary"]["total_changed_orders"] >= 1
