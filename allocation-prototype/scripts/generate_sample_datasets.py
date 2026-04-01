from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from random import Random
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "demo" / "sample_datasets"
IST = timezone(timedelta(hours=5, minutes=30))


@dataclass(frozen=True)
class ScenarioSpec:
    slug: str
    code: str
    name: str
    city: str
    scenario: str
    description: str
    recommended_for: str
    seed: int
    order_count: int
    partner_count: int
    base_time: datetime
    order_anchors: tuple[tuple[float, float], ...]
    order_anchor_weights: tuple[float, ...]
    partner_anchors: tuple[tuple[float, float], ...]
    partner_anchor_weights: tuple[float, ...]
    vehicle_weights: tuple[tuple[str, float], ...]
    partner_profile_weights: tuple[tuple[str, float], ...]
    order_spread_lat: float
    order_spread_lon: float
    partner_spread_lat: float
    partner_spread_lon: float
    unavailable_ratio: float
    inactive_ratio: float
    low_rating_ratio: float


PARTNER_PROFILES: dict[str, dict[str, Any]] = {
    "bike": {"vehicle_types": ["bike"], "base_rating": 4.45},
    "scooter_dual": {"vehicle_types": ["scooter", "bike"], "base_rating": 4.35},
    "scooter": {"vehicle_types": ["scooter"], "base_rating": 4.2},
    "car": {"vehicle_types": ["car"], "base_rating": 4.55},
}


SCENARIOS = (
    ScenarioSpec(
        slug="bengaluru_lunch_rush",
        code="BLR",
        name="Bengaluru Lunch Rush",
        city="Bengaluru",
        scenario="Dense weekday lunch demand across Indiranagar, Domlur, and Koramangala",
        description="A larger lunch-rush scenario with dense central demand, mixed two-wheeler supply, and a smaller car fleet for bulky orders.",
        recommended_for="Frontend demos, realistic local testing, and reading allocation explanations at medium scale.",
        seed=1107,
        order_count=42,
        partner_count=28,
        base_time=datetime(2026, 4, 2, 11, 45, tzinfo=IST),
        order_anchors=((12.9784, 77.6408), (12.9699, 77.6387), (12.9352, 77.6245), (12.9602, 77.6461)),
        order_anchor_weights=(0.34, 0.26, 0.22, 0.18),
        partner_anchors=((12.9775, 77.6417), (12.9708, 77.6382), (12.9558, 77.6389), (12.9442, 77.6268)),
        partner_anchor_weights=(0.34, 0.28, 0.22, 0.16),
        vehicle_weights=(("bike", 0.58), ("scooter", 0.28), ("car", 0.14)),
        partner_profile_weights=(("bike", 0.43), ("scooter_dual", 0.27), ("scooter", 0.12), ("car", 0.18)),
        order_spread_lat=0.0065,
        order_spread_lon=0.0065,
        partner_spread_lat=0.0045,
        partner_spread_lon=0.0045,
        unavailable_ratio=0.14,
        inactive_ratio=0.07,
        low_rating_ratio=0.11,
    ),
    ScenarioSpec(
        slug="hyderabad_monsoon_mixed_fleet",
        code="HYD",
        name="Hyderabad Monsoon Mixed Fleet",
        city="Hyderabad",
        scenario="Rain-shift demand across HITEC City, Madhapur, Kondapur, and Gachibowli",
        description="A larger mixed-fleet scenario with rain-hour demand, stronger car usage, and visible availability pressure.",
        recommended_for="Vehicle-compatibility demos, mixed-fleet regression checks, and larger manual API runs.",
        seed=2213,
        order_count=48,
        partner_count=30,
        base_time=datetime(2026, 7, 18, 18, 40, tzinfo=IST),
        order_anchors=((17.4427, 78.3791), (17.4504, 78.3885), (17.4587, 78.3647), (17.4361, 78.3716)),
        order_anchor_weights=(0.29, 0.27, 0.23, 0.21),
        partner_anchors=((17.4442, 78.3806), (17.4526, 78.3812), (17.4461, 78.3704), (17.4394, 78.3759)),
        partner_anchor_weights=(0.31, 0.27, 0.23, 0.19),
        vehicle_weights=(("bike", 0.38), ("scooter", 0.34), ("car", 0.28)),
        partner_profile_weights=(("bike", 0.31), ("scooter_dual", 0.24), ("scooter", 0.17), ("car", 0.28)),
        order_spread_lat=0.008,
        order_spread_lon=0.008,
        partner_spread_lat=0.0055,
        partner_spread_lon=0.0055,
        unavailable_ratio=0.18,
        inactive_ratio=0.06,
        low_rating_ratio=0.13,
    ),
    ScenarioSpec(
        slug="gurugram_distance_pressure",
        code="GGN",
        name="Gurugram Distance Pressure",
        city="Gurugram",
        scenario="Evening demand spread from Cyber City to the edge of the service radius",
        description="A larger suburban scenario where supply stays clustered but many orders drift outward, making the distance rule a major factor.",
        recommended_for="Diagnostics demos, distance-limit investigations, and larger unallocated-order explainability checks.",
        seed=3319,
        order_count=56,
        partner_count=24,
        base_time=datetime(2026, 4, 2, 19, 10, tzinfo=IST),
        order_anchors=((28.4305, 77.0984), (28.4591, 77.0969), (28.4036, 77.0729), (28.4462, 77.1368), (28.3857, 77.0521)),
        order_anchor_weights=(0.22, 0.17, 0.17, 0.24, 0.20),
        partner_anchors=((28.4341, 77.1045), (28.4324, 77.0971), (28.4389, 77.1098)),
        partner_anchor_weights=(0.38, 0.34, 0.28),
        vehicle_weights=(("bike", 0.47), ("scooter", 0.24), ("car", 0.29)),
        partner_profile_weights=(("bike", 0.39), ("scooter_dual", 0.18), ("scooter", 0.11), ("car", 0.32)),
        order_spread_lat=0.0105,
        order_spread_lon=0.0105,
        partner_spread_lat=0.0048,
        partner_spread_lon=0.0048,
        unavailable_ratio=0.16,
        inactive_ratio=0.08,
        low_rating_ratio=0.14,
    ),
)


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def weighted_choice(rng: Random, weighted_values: tuple[tuple[Any, float], ...]) -> Any:
    total = sum(weight for _, weight in weighted_values)
    threshold = rng.random() * total
    running = 0.0
    for value, weight in weighted_values:
        running += weight
        if running >= threshold:
            return value
    return weighted_values[-1][0]


def choose_anchor(
    rng: Random,
    anchors: tuple[tuple[float, float], ...],
    weights: tuple[float, ...],
) -> tuple[float, float]:
    weighted_anchors = tuple(zip(anchors, weights, strict=True))
    return weighted_choice(rng, weighted_anchors)


def jittered_point(
    rng: Random,
    anchor: tuple[float, float],
    lat_delta: float,
    lon_delta: float,
) -> tuple[float, float]:
    lat = anchor[0] + rng.uniform(-lat_delta, lat_delta)
    lon = anchor[1] + rng.uniform(-lon_delta, lon_delta)
    return round(lat, 6), round(lon, 6)


def rounded_amount(rng: Random, vehicle_type: str) -> int:
    ranges = {
        "bike": (16000, 38000),
        "scooter": (18000, 43000),
        "car": (42000, 98000),
    }
    low, high = ranges[vehicle_type]
    steps = list(range(low, high + 500, 500))
    return rng.choice(steps)


def generated_order(spec: ScenarioSpec, rng: Random, index: int) -> dict[str, Any]:
    anchor = choose_anchor(rng, spec.order_anchors, spec.order_anchor_weights)
    latitude, longitude = jittered_point(rng, anchor, spec.order_spread_lat, spec.order_spread_lon)
    requested_vehicle_type = weighted_choice(rng, spec.vehicle_weights)
    created_at = spec.base_time + timedelta(minutes=index * 2 + rng.randint(0, 2))
    return {
        "order_id": f"{spec.code}-{index + 1:03d}",
        "latitude": latitude,
        "longitude": longitude,
        "amount_paise": rounded_amount(rng, requested_vehicle_type),
        "requested_vehicle_type": requested_vehicle_type,
        "created_at": created_at.isoformat(),
    }


def generated_partner(spec: ScenarioSpec, rng: Random, index: int) -> dict[str, Any]:
    anchor = choose_anchor(rng, spec.partner_anchors, spec.partner_anchor_weights)
    latitude, longitude = jittered_point(rng, anchor, spec.partner_spread_lat, spec.partner_spread_lon)
    profile_name = weighted_choice(rng, spec.partner_profile_weights)
    profile = PARTNER_PROFILES[profile_name]

    low_rated = rng.random() < spec.low_rating_ratio
    if low_rated:
        rating = round(rng.uniform(3.05, 3.45), 1)
    else:
        rating = round(clamp(rng.gauss(profile["base_rating"], 0.22), 3.5, 4.9), 1)

    active = rng.random() >= spec.inactive_ratio
    is_available = active and rng.random() >= spec.unavailable_ratio

    return {
        "partner_id": f"P-{spec.code}-{index + 1:03d}",
        "latitude": latitude,
        "longitude": longitude,
        "is_available": is_available,
        "rating": rating,
        "vehicle_types": profile["vehicle_types"],
        "active": active,
    }


def build_dataset(spec: ScenarioSpec) -> dict[str, Any]:
    rng = Random(spec.seed)
    orders = [generated_order(spec, rng, index) for index in range(spec.order_count)]
    partners = [generated_partner(spec, rng, index) for index in range(spec.partner_count)]

    return {
        "metadata": {
            "name": spec.name,
            "city": spec.city,
            "scenario": spec.scenario,
            "description": spec.description,
            "recommended_for": spec.recommended_for,
            "orders_generated": len(orders),
            "partners_generated": len(partners),
            "generator": "scripts/generate_sample_datasets.py",
        },
        "orders": orders,
        "partners": partners,
    }


def write_dataset(spec: ScenarioSpec) -> Path:
    payload = build_dataset(spec)
    output_path = OUTPUT_DIR / f"{spec.slug}.json"
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return output_path


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for spec in SCENARIOS:
        path = write_dataset(spec)
        payload = json.loads(path.read_text(encoding="utf-8"))
        print(
            f"Wrote {path.name}: "
            f"{len(payload['orders'])} orders, {len(payload['partners'])} partners"
        )


if __name__ == "__main__":
    main()
