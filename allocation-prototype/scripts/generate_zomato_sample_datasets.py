from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from allocation.data.zomato_adapter import build_allocation_payload_from_zomato, write_json  # noqa: E402


OUTPUT_DIR = PROJECT_ROOT / "demo" / "sample_datasets"


@dataclass(frozen=True)
class ZomatoSampleSpec:
    slug: str
    name: str
    city: str
    scenario: str
    description: str
    recommended_for: str
    max_orders: int
    max_partners: int
    source_filters: dict[str, str]


SPECS = (
    ZomatoSampleSpec(
        slug="zomato_national_high_volume",
        name="Zomato National High Volume",
        city="Multi-city India",
        scenario="Large cross-city allocation sample adapted from the Zomato delivery dataset",
        description="High-volume payload derived from the Zomato source CSV for validating allocation throughput, audit endpoints, replay, and counterfactual execution at larger scale.",
        recommended_for="Large payload allocation runs, audit and replay verification, and frontend or manual API validation.",
        max_orders=400,
        max_partners=220,
        source_filters={},
    ),
    ZomatoSampleSpec(
        slug="zomato_metro_jam_core",
        name="Zomato Metro Jam Core",
        city="Metropolitan",
        scenario="CSV slice with City=Metropolitian, Road_traffic_density=Jam, Festival=No",
        description="Metropolitan jam-traffic payload derived directly from the Zomato CSV for validating deterministic assignment and rejection behavior under dense delivery pressure.",
        recommended_for="Allocation baseline checks, manifest replay, and hard-rule diagnostics under jam traffic.",
        max_orders=96,
        max_partners=72,
        source_filters={"City": "Metropolitian", "Road_traffic_density": "Jam", "Festival": "No"},
    ),
    ZomatoSampleSpec(
        slug="zomato_urban_low_traffic",
        name="Zomato Urban Low Traffic",
        city="Urban",
        scenario="CSV slice with City=Urban, Road_traffic_density=Low, Festival=No",
        description="Urban low-traffic payload from the Zomato CSV for validating baseline allocation quality when hard-rule pressure is lighter and partner supply is broader.",
        recommended_for="Low-friction allocation checks, replay validation, and frontend walkthroughs with faster assignment conditions.",
        max_orders=84,
        max_partners=60,
        source_filters={"City": "Urban", "Road_traffic_density": "Low", "Festival": "No"},
    ),
    ZomatoSampleSpec(
        slug="zomato_festival_jam_surge",
        name="Zomato Festival Jam Surge",
        city="Metropolitan",
        scenario="CSV slice with City=Metropolitian, Road_traffic_density=Jam, Festival=Yes",
        description="Festival-period metropolitan jam payload sourced from the Zomato CSV for validating allocation behavior when demand spikes and partner selection pressure increases.",
        recommended_for="Counterfactual checks, rejection-summary review, and festival surge allocation validation.",
        max_orders=72,
        max_partners=54,
        source_filters={"City": "Metropolitian", "Road_traffic_density": "Jam", "Festival": "Yes"},
    ),
    ZomatoSampleSpec(
        slug="zomato_metro_high_traffic",
        name="Zomato Metro High Traffic",
        city="Metropolitan",
        scenario="CSV slice with City=Metropolitian, Road_traffic_density=High, Festival=No",
        description="Metropolitan high-traffic payload from the Zomato CSV for validating allocation output when distance and availability pressure remain high but demand is smaller than the jam slice.",
        recommended_for="Distance-rule inspection, allocation regression checks, and medium-sized replay or audit runs.",
        max_orders=80,
        max_partners=56,
        source_filters={"City": "Metropolitian", "Road_traffic_density": "High", "Festival": "No"},
    ),
)


def _build_payload(csv_path: Path, spec: ZomatoSampleSpec) -> dict[str, Any]:
    payload = build_allocation_payload_from_zomato(
        csv_path,
        max_orders=spec.max_orders,
        max_partners=spec.max_partners,
        max_delivery_radius_km=30.0,
        source_filters=spec.source_filters,
    )
    payload["metadata"].update(
        {
            "name": spec.name,
            "city": spec.city,
            "scenario": spec.scenario,
            "description": spec.description,
            "recommended_for": spec.recommended_for,
            "generator": "scripts/generate_zomato_sample_datasets.py",
        }
    )
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate CSV-derived sample datasets from the Zomato source data")
    parser.add_argument(
        "--input",
        default=str((PROJECT_ROOT / ".." / "Zomato Dataset.csv").resolve()),
        help="Path to Zomato CSV",
    )
    args = parser.parse_args()

    csv_path = Path(args.input).resolve()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    for spec in SPECS:
        output_path = OUTPUT_DIR / f"{spec.slug}.json"
        payload = _build_payload(csv_path, spec)
        write_json(output_path, payload)
        print(
            f"Wrote {output_path.name}: "
            f"{payload['metadata']['orders_generated']} orders, "
            f"{payload['metadata']['partners_generated']} partners"
        )


if __name__ == "__main__":
    main()
