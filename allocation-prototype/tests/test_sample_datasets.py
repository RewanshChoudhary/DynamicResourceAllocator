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
