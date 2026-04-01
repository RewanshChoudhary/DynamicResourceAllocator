from __future__ import annotations

import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from allocation.api.schemas import AllocationRequest
from allocation.domain.enums import VehicleType


DATASET_DIR = PROJECT_ROOT / "demo" / "sample_datasets"
EXPECTED_DATASETS = {
    "realistic_clear_weather.json",
    "realistic_severe_weather.json",
    "realistic_traffic_jam.json",
}


def _validate_dataset(path: Path) -> list[str]:
    errors: list[str] = []
    payload = json.loads(path.read_text(encoding="utf-8"))

    try:
        AllocationRequest.model_validate(payload)
    except Exception as exc:
        errors.append(f"schema validation failed: {exc}")

    orders = payload.get("orders", [])
    partners = payload.get("partners", [])

    if not orders:
        errors.append("orders list is empty")
    if len(partners) < 5:
        errors.append(f"partners list too small: {len(partners)}")

    valid_vehicle_values = {vehicle.value for vehicle in VehicleType}
    for partner in partners:
        partner_id = partner.get("partner_id", "<unknown>")
        for vehicle_type in partner.get("vehicle_types", []):
            if vehicle_type not in valid_vehicle_values:
                errors.append(f"{partner_id} has invalid vehicle_type={vehicle_type}")

        rating = float(partner.get("rating", 0.0))
        if not (3.0 <= rating <= 5.0):
            errors.append(f"{partner_id} has rating out of range: {rating}")

    return errors


def main() -> int:
    dataset_paths = sorted(DATASET_DIR.glob("*.json"))
    if not dataset_paths:
        print("FAIL no dataset files found")
        return 1

    actual_dataset_names = {path.name for path in dataset_paths}
    if actual_dataset_names != EXPECTED_DATASETS:
        print("FAIL dataset directory does not match the expected three-file catalog")
        print(f"  - expected: {sorted(EXPECTED_DATASETS)}")
        print(f"  - actual: {sorted(actual_dataset_names)}")
        return 1

    failures = 0
    for path in dataset_paths:
        errors = _validate_dataset(path)
        if errors:
            failures += 1
            print(f"FAIL {path.name}")
            for error in errors:
                print(f"  - {error}")
            continue
        print(f"PASS {path.name}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
