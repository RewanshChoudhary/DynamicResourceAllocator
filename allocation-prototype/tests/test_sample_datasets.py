from __future__ import annotations

import json
from pathlib import Path

from allocation.api.schemas import AllocationRequest

DATASET_DIR = Path(__file__).resolve().parents[1] / "demo" / "sample_datasets"
LARGE_REALISTIC_DATASET_MINIMUMS = {
    "realistic_clear_weather.json": (172, 35),
    "realistic_severe_weather.json": (288, 40),
    "realistic_traffic_jam.json": (544, 45),
}


def test_curated_sample_datasets_validate_against_request_schema():
    dataset_paths = sorted(DATASET_DIR.glob("*.json"))

    assert dataset_paths
    assert {path.name for path in dataset_paths} == {
        "realistic_clear_weather.json",
        "realistic_severe_weather.json",
        "realistic_traffic_jam.json",
    }

    for path in dataset_paths:
        payload = json.loads(path.read_text())
        AllocationRequest.model_validate(payload)
        assert payload["metadata"]["name"]
        assert payload["metadata"]["city"]
        assert payload["orders"]
        assert payload["partners"]


def test_curated_sample_datasets_cover_all_vehicle_types():
    requested_vehicle_types: set[str] = set()
    partner_vehicle_types: set[str] = set()

    for path in DATASET_DIR.glob("*.json"):
        payload = json.loads(path.read_text())
        requested_vehicle_types.update(order["requested_vehicle_type"] for order in payload["orders"])
        for partner in payload["partners"]:
            partner_vehicle_types.update(partner["vehicle_types"])

    assert {"bike", "scooter"} <= requested_vehicle_types
    assert {"bike", "scooter"} <= partner_vehicle_types


def test_curated_sample_datasets_are_substantially_larger_than_smoke_samples():
    for path in DATASET_DIR.glob("*.json"):
        payload = json.loads(path.read_text())
        min_orders, min_partners = LARGE_REALISTIC_DATASET_MINIMUMS[path.name]
        assert len(payload["orders"]) == min_orders, path.name
        assert len(payload["partners"]) >= min_partners, path.name


def test_only_three_large_zomato_samples_are_available():
    expected = {
        "realistic_clear_weather.json": "Zomato Clear Weather Large (172 orders)",
        "realistic_severe_weather.json": "Zomato Severe Weather Large (288 orders)",
        "realistic_traffic_jam.json": "Zomato Traffic Jam Large (544 orders)",
    }

    for filename, expected_name in expected.items():
        payload = json.loads((DATASET_DIR / filename).read_text())
        assert payload["metadata"]["name"] == expected_name
        assert payload["metadata"]["generator"] == "scripts/generate_realistic_sample.py"
        assert payload["metadata"]["source_filters"]
        assert len(payload["orders"]) >= LARGE_REALISTIC_DATASET_MINIMUMS[filename][0]
        assert len(payload["partners"]) >= LARGE_REALISTIC_DATASET_MINIMUMS[filename][1]


def test_realistic_traffic_jam_dataset_records_delta_verification_status():
    payload = json.loads((DATASET_DIR / "realistic_traffic_jam.json").read_text())

    assert "traffic_delta_verified" in payload["metadata"]
    assert isinstance(payload["metadata"]["traffic_delta_verified"], bool)
