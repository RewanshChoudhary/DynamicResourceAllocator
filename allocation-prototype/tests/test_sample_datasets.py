from __future__ import annotations

import json
from pathlib import Path

from allocation.api.schemas import AllocationRequest

DATASET_DIR = Path(__file__).resolve().parents[1] / "demo" / "sample_datasets"


def test_curated_sample_datasets_validate_against_request_schema():
    dataset_paths = sorted(DATASET_DIR.glob("*.json"))

    assert dataset_paths

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

    assert {"bike", "scooter", "car"} <= requested_vehicle_types
    assert {"bike", "scooter", "car"} <= partner_vehicle_types


def test_curated_sample_datasets_are_substantially_larger_than_smoke_samples():
    for path in DATASET_DIR.glob("*.json"):
        payload = json.loads(path.read_text())
        assert len(payload["orders"]) >= 40, path.name
        assert len(payload["partners"]) >= 24, path.name


def test_zomato_high_volume_sample_is_available_for_large_demo_runs():
    path = DATASET_DIR / "zomato_national_high_volume.json"
    payload = json.loads(path.read_text())

    assert payload["metadata"]["name"] == "Zomato National High Volume"
    assert len(payload["orders"]) >= 400
    assert len(payload["partners"]) >= 200


def test_csv_derived_zomato_sample_slices_are_available():
    expected = {
        "zomato_metro_jam_core.json": "Zomato Metro Jam Core",
        "zomato_urban_low_traffic.json": "Zomato Urban Low Traffic",
        "zomato_festival_jam_surge.json": "Zomato Festival Jam Surge",
        "zomato_metro_high_traffic.json": "Zomato Metro High Traffic",
    }

    for filename, expected_name in expected.items():
        payload = json.loads((DATASET_DIR / filename).read_text())
        assert payload["metadata"]["name"] == expected_name
        assert payload["metadata"]["generator"] == "scripts/generate_zomato_sample_datasets.py"
        assert payload["metadata"]["source_filters"]
        assert len(payload["orders"]) >= 60
        assert len(payload["partners"]) >= 50
