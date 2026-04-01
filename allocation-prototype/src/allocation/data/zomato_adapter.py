from __future__ import annotations

import csv
import json
import math
from collections import Counter, OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

MISSING_MARKERS = {"", "nan", "none", "null", "na"}
RAW_VEHICLE_TO_CORE = {
    "MOTORCYCLE": "bike",
    "SCOOTER": "scooter",
    "ELECTRIC_SCOOTER": "scooter",
}
DEFAULT_REALISTIC_CITY = "Metropolitian"
DEFAULT_REALISTIC_WEATHER = "Sunny"
DEFAULT_REALISTIC_TRAFFIC = "Low"
DEFAULT_REALISTIC_ORDER_TYPE = "Meal"
DEFAULT_REALISTIC_PRIORITY = "NORMAL"
DEFAULT_REALISTIC_CREATED_AT = datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc)


@dataclass(frozen=True)
class CsvAuditSummary:
    total_rows: int
    unique_delivery_partners: int
    duplicate_order_ids: int
    date_range_start: str | None
    date_range_end: str | None
    missing_counts: dict[str, int]
    anomaly_counts: dict[str, int]
    top_city_counts: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_rows": self.total_rows,
            "unique_delivery_partners": self.unique_delivery_partners,
            "duplicate_order_ids": self.duplicate_order_ids,
            "date_range_start": self.date_range_start,
            "date_range_end": self.date_range_end,
            "missing_counts": self.missing_counts,
            "anomaly_counts": self.anomaly_counts,
            "top_city_counts": self.top_city_counts,
        }


def _ensure_existing_csv(csv_path: str | Path) -> Path:
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV not found: {path}")
    return path


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    return str(value).strip().lower() in MISSING_MARKERS


def _parse_float(value: Any) -> float | None:
    if _is_missing(value):
        return None
    try:
        return float(str(value).strip())
    except ValueError:
        return None


def _parse_int(value: Any) -> int | None:
    if _is_missing(value):
        return None
    try:
        return int(float(str(value).strip()))
    except ValueError:
        return None


def _normalize_city(raw: str | None) -> str:
    if raw is None:
        return "Unknown"
    value = raw.strip()
    if value.lower() == "metropolitian":
        return "Metropolitan"
    if value.lower() == "nan" or not value:
        return "Unknown"
    return value


def _normalize_vehicle(raw: str | None) -> str:
    value = (raw or "").strip().lower()
    if value in {"motorcycle", "bicycle", "bike"}:
        return "bike"
    if value in {"scooter", "electric_scooter"}:
        return "scooter"
    if value in {"car", "auto", "van"}:
        return "car"
    return "bike"


def _row_matches_filters(
    row: dict[str, Any],
    source_filters: dict[str, str | list[str] | tuple[str, ...] | set[str]] | None,
) -> bool:
    if not source_filters:
        return True

    for field_name, expected in source_filters.items():
        actual = (row.get(field_name) or "").strip()
        if isinstance(expected, str):
            allowed = {expected.strip()}
        else:
            allowed = {str(value).strip() for value in expected}
        if actual not in allowed:
            return False

    return True


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    earth_radius_km = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.asin(math.sqrt(a))
    return earth_radius_km * c


def _parse_timestamp(order_date: str | None, time_ordered: str | None) -> datetime:
    if _is_missing(order_date):
        return datetime.now(timezone.utc)

    date_part = str(order_date).strip()
    if _is_missing(time_ordered):
        time_part = "12:00"
    else:
        time_part = str(time_ordered).strip()

    try:
        dt = datetime.strptime(f"{date_part} {time_part}", "%d-%m-%Y %H:%M")
    except ValueError:
        dt = datetime.strptime(date_part, "%d-%m-%Y")
    return dt.replace(tzinfo=timezone.utc)


def _estimate_amount_paise(type_of_order: str | None, multiple_deliveries: int | None) -> int:
    order_kind = (type_of_order or "").strip().lower()
    base = {
        "drinks": 12000,
        "snack": 18000,
        "meal": 26000,
        "buffet": 42000,
    }.get(order_kind, 22000)

    extra = max(0, min(multiple_deliveries or 0, 3)) * 2500
    return base + extra


def _fix_restaurant_coordinates(
    restaurant_lat: float,
    restaurant_lon: float,
    delivery_lat: float,
    delivery_lon: float,
) -> tuple[float, float, bool]:
    corrected = False
    rest_lat = restaurant_lat
    rest_lon = restaurant_lon

    if restaurant_lat < 0 and delivery_lat > 0:
        rest_lat = abs(restaurant_lat)
        corrected = True
    if restaurant_lon < 0 and delivery_lon > 0:
        rest_lon = abs(restaurant_lon)
        corrected = True

    return rest_lat, rest_lon, corrected


def audit_zomato_csv(csv_path: str | Path) -> CsvAuditSummary:
    path = _ensure_existing_csv(csv_path)

    missing_counts: dict[str, int] = {}
    anomaly_counts = {
        "invalid_age_rows": 0,
        "invalid_rating_rows": 0,
        "negative_restaurant_coordinate_rows": 0,
        "distance_over_30km_rows": 0,
        "distance_over_80km_rows": 0,
        "speed_over_80kmh_rows": 0,
    }

    unique_partners: set[str] = set()
    order_ids: set[str] = set()
    duplicate_order_ids = 0
    city_counts: dict[str, int] = {}
    dates: list[datetime] = []
    total_rows = 0

    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            total_rows += 1

            order_id = row.get("ID", "")
            if order_id in order_ids:
                duplicate_order_ids += 1
            order_ids.add(order_id)

            partner_id = row.get("Delivery_person_ID", "")
            if not _is_missing(partner_id):
                unique_partners.add(partner_id.strip())

            normalized_city = _normalize_city(row.get("City"))
            city_counts[normalized_city] = city_counts.get(normalized_city, 0) + 1

            for key, value in row.items():
                if _is_missing(value):
                    missing_counts[key] = missing_counts.get(key, 0) + 1

            age = _parse_int(row.get("Delivery_person_Age"))
            if age is not None and not (16 <= age <= 80):
                anomaly_counts["invalid_age_rows"] += 1

            rating = _parse_float(row.get("Delivery_person_Ratings"))
            if rating is not None and not (1.0 <= rating <= 5.0):
                anomaly_counts["invalid_rating_rows"] += 1

            restaurant_lat = _parse_float(row.get("Restaurant_latitude"))
            restaurant_lon = _parse_float(row.get("Restaurant_longitude"))
            delivery_lat = _parse_float(row.get("Delivery_location_latitude"))
            delivery_lon = _parse_float(row.get("Delivery_location_longitude"))
            time_taken = _parse_int(row.get("Time_taken (min)"))

            if None not in (restaurant_lat, restaurant_lon, delivery_lat, delivery_lon):
                if restaurant_lat < 0 or restaurant_lon < 0:
                    anomaly_counts["negative_restaurant_coordinate_rows"] += 1

                fixed_lat, fixed_lon, _ = _fix_restaurant_coordinates(
                    restaurant_lat,
                    restaurant_lon,
                    delivery_lat,
                    delivery_lon,
                )

                distance_km = _haversine_km(fixed_lat, fixed_lon, delivery_lat, delivery_lon)
                if distance_km > 30:
                    anomaly_counts["distance_over_30km_rows"] += 1
                if distance_km > 80:
                    anomaly_counts["distance_over_80km_rows"] += 1

                if time_taken is not None and time_taken > 0:
                    speed_kmh = distance_km / (time_taken / 60)
                    if speed_kmh > 80:
                        anomaly_counts["speed_over_80kmh_rows"] += 1

            if not _is_missing(row.get("Order_Date")):
                try:
                    dates.append(datetime.strptime(str(row["Order_Date"]).strip(), "%d-%m-%Y"))
                except ValueError:
                    pass

    top_city_counts = dict(sorted(city_counts.items(), key=lambda item: item[1], reverse=True)[:10])
    return CsvAuditSummary(
        total_rows=total_rows,
        unique_delivery_partners=len(unique_partners),
        duplicate_order_ids=duplicate_order_ids,
        date_range_start=min(dates).date().isoformat() if dates else None,
        date_range_end=max(dates).date().isoformat() if dates else None,
        missing_counts=dict(sorted(missing_counts.items(), key=lambda item: item[1], reverse=True)),
        anomaly_counts=anomaly_counts,
        top_city_counts=top_city_counts,
    )


def build_allocation_payload_from_zomato(
    csv_path: str | Path,
    max_orders: int = 250,
    max_partners: int = 150,
    max_delivery_radius_km: float = 30.0,
    source_filters: dict[str, str | list[str] | tuple[str, ...] | set[str]] | None = None,
) -> dict[str, Any]:
    path = _ensure_existing_csv(csv_path)

    orders: list[dict[str, Any]] = []
    partner_state: "OrderedDict[str, dict[str, Any]]" = OrderedDict()

    dropped_counts = {
        "missing_core_fields": 0,
        "invalid_age": 0,
        "invalid_rating": 0,
        "invalid_coordinates": 0,
        "distance_outlier": 0,
        "duplicate_order_id": 0,
    }
    corrected_coordinate_rows = 0

    seen_order_ids: set[str] = set()
    source_filter_match_count = 0
    source_valid_match_count = 0
    source_unique_partners: set[str] = set()

    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if not _row_matches_filters(row, source_filters):
                continue

            source_filter_match_count += 1
            order_id = (row.get("ID") or "").strip()
            partner_id = (row.get("Delivery_person_ID") or "").strip()
            if not order_id or not partner_id:
                dropped_counts["missing_core_fields"] += 1
                continue
            if order_id in seen_order_ids:
                dropped_counts["duplicate_order_id"] += 1
                continue

            restaurant_lat = _parse_float(row.get("Restaurant_latitude"))
            restaurant_lon = _parse_float(row.get("Restaurant_longitude"))
            delivery_lat = _parse_float(row.get("Delivery_location_latitude"))
            delivery_lon = _parse_float(row.get("Delivery_location_longitude"))
            age = _parse_int(row.get("Delivery_person_Age"))
            rating = _parse_float(row.get("Delivery_person_Ratings"))

            if None in (restaurant_lat, restaurant_lon, delivery_lat, delivery_lon):
                dropped_counts["invalid_coordinates"] += 1
                continue
            if age is None or not (16 <= age <= 80):
                dropped_counts["invalid_age"] += 1
                continue
            if rating is None or not (1.0 <= rating <= 5.0):
                dropped_counts["invalid_rating"] += 1
                continue

            fixed_lat, fixed_lon, corrected = _fix_restaurant_coordinates(
                restaurant_lat,
                restaurant_lon,
                delivery_lat,
                delivery_lon,
            )
            if corrected:
                corrected_coordinate_rows += 1

            distance_km = _haversine_km(fixed_lat, fixed_lon, delivery_lat, delivery_lon)
            if distance_km > max_delivery_radius_km:
                dropped_counts["distance_outlier"] += 1
                continue

            created_at = _parse_timestamp(row.get("Order_Date"), row.get("Time_Orderd"))
            multiple_deliveries = _parse_int(row.get("multiple_deliveries"))
            requested_vehicle = _normalize_vehicle(row.get("Type_of_vehicle"))
            source_valid_match_count += 1
            source_unique_partners.add(partner_id)
            seen_order_ids.add(order_id)

            if len(orders) < max_orders:
                orders.append(
                    {
                        "order_id": order_id,
                        "latitude": round(fixed_lat, 6),
                        "longitude": round(fixed_lon, 6),
                        "amount_paise": _estimate_amount_paise(row.get("Type_of_order"), multiple_deliveries),
                        "requested_vehicle_type": requested_vehicle,
                        "created_at": created_at.isoformat(),
                    }
                )
            else:
                continue

            if partner_id not in partner_state and len(partner_state) >= max_partners:
                continue

            partner = partner_state.setdefault(
                partner_id,
                {
                    "partner_id": partner_id,
                    "latitude": round(delivery_lat, 6),
                    "longitude": round(delivery_lon, 6),
                    "is_available": True,
                    "rating_sum": 0.0,
                    "rating_count": 0,
                    "vehicle_types": set(),
                    "active": True,
                },
            )
            partner["latitude"] = round(delivery_lat, 6)
            partner["longitude"] = round(delivery_lon, 6)
            partner["rating_sum"] += float(rating)
            partner["rating_count"] += 1
            partner["vehicle_types"].add(requested_vehicle)

    partners: list[dict[str, Any]] = []
    for payload in partner_state.values():
        count = max(1, int(payload["rating_count"]))
        partners.append(
            {
                "partner_id": payload["partner_id"],
                "latitude": payload["latitude"],
                "longitude": payload["longitude"],
                "is_available": payload["is_available"],
                "rating": round(payload["rating_sum"] / count, 2),
                "vehicle_types": sorted(payload["vehicle_types"]),
                "active": payload["active"],
            }
        )

    metadata = {
        "source_file": str(path),
        "source_filters": dict(source_filters) if source_filters else None,
        "source_filter_match_count": source_filter_match_count,
        "source_valid_match_count": source_valid_match_count,
        "source_unique_delivery_partners": len(source_unique_partners),
        "max_orders": max_orders,
        "max_partners": max_partners,
        "max_delivery_radius_km": max_delivery_radius_km,
        "orders_generated": len(orders),
        "partners_generated": len(partners),
        "corrected_coordinate_rows": corrected_coordinate_rows,
        "dropped_counts": dropped_counts,
    }

    return {
        "orders": orders,
        "partners": partners,
        "metadata": metadata,
    }


def write_json(path: str | Path, payload: dict[str, Any]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _normalize_dataset_vehicle_type(raw: str | None) -> str | None:
    value = (raw or "").strip().lower()
    if value == "motorcycle":
        return "MOTORCYCLE"
    if value == "scooter":
        return "SCOOTER"
    if value == "electric_scooter":
        return "ELECTRIC_SCOOTER"
    return None


def _normalize_dataset_city(raw: str | None) -> str:
    value = (raw or "").strip()
    if not value or value.lower() == "nan":
        return DEFAULT_REALISTIC_CITY
    return value


def _normalize_dataset_text(raw: str | None, *, default: str) -> str:
    value = (raw or "").strip()
    if not value or value.lower() == "nan":
        return default
    return value


def _clean_row_matches_filters(
    row: dict[str, Any],
    source_filters: dict[str, str | list[str] | tuple[str, ...] | set[str]] | None,
) -> bool:
    if not source_filters:
        return True

    for field_name, expected in source_filters.items():
        actual = str(row.get(field_name, "")).strip()
        if isinstance(expected, str):
            allowed = {expected.strip()}
        else:
            allowed = {str(value).strip() for value in expected}
        if actual not in allowed:
            return False

    return True


def _most_common_value(values: list[str], default: str) -> str:
    filtered = [value for value in values if value]
    if not filtered:
        return default

    counts = Counter(filtered)
    most_common_count = max(counts.values())
    for value in filtered:
        if counts[value] == most_common_count:
            return value
    return default


def _synthetic_created_at(row_index: int) -> str:
    return (DEFAULT_REALISTIC_CREATED_AT + timedelta(minutes=row_index - 1)).isoformat()


def load_and_clean_csv(csv_path: str) -> list[dict[str, Any]]:
    path = _ensure_existing_csv(csv_path)

    total_rows = 0
    dropped_rows = 0
    zero_coords = 0
    nan_ratings = 0
    negative_lat_rows = 0
    clean_rows: list[dict[str, Any]] = []

    with path.open(newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader(handle)
        for raw_row in reader:
            total_rows += 1
            row = {key: str(value).strip() if value is not None else "" for key, value in raw_row.items()}

            rating = _parse_float(row.get("Delivery_person_Ratings"))
            if rating is None:
                dropped_rows += 1
                nan_ratings += 1
                continue

            restaurant_lat = _parse_float(row.get("Restaurant_latitude"))
            restaurant_lon = _parse_float(row.get("Restaurant_longitude"))
            delivery_lat = _parse_float(row.get("Delivery_location_latitude"))
            delivery_lon = _parse_float(row.get("Delivery_location_longitude"))
            if None in (restaurant_lat, restaurant_lon, delivery_lat, delivery_lon):
                dropped_rows += 1
                zero_coords += 1
                continue

            if restaurant_lat == 0.0 or restaurant_lon == 0.0:
                dropped_rows += 1
                zero_coords += 1
                continue

            if math.isclose(restaurant_lat, -27.163303, rel_tol=0.0, abs_tol=1e-6):
                dropped_rows += 1
                negative_lat_rows += 1
                continue

            fixed_restaurant_lat, fixed_restaurant_lon, _ = _fix_restaurant_coordinates(
                restaurant_lat,
                restaurant_lon,
                delivery_lat,
                delivery_lon,
            )

            raw_vehicle_type = _normalize_dataset_vehicle_type(row.get("Type_of_vehicle"))
            if raw_vehicle_type is None:
                dropped_rows += 1
                continue

            current_load = _parse_int(row.get("multiple_deliveries"))
            vehicle_condition = _parse_int(row.get("Vehicle_condition"))
            time_taken_min = _parse_int(row.get("Time_taken (min)"))
            if time_taken_min is None:
                dropped_rows += 1
                continue

            clean_rows.append(
                {
                    "partner_id": row.get("Delivery_person_ID", ""),
                    "rating": round(float(rating), 1),
                    "restaurant_lat": round(float(fixed_restaurant_lat), 6),
                    "restaurant_lon": round(float(fixed_restaurant_lon), 6),
                    "delivery_lat": round(float(delivery_lat), 6),
                    "delivery_lon": round(float(delivery_lon), 6),
                    "vehicle_type_raw": raw_vehicle_type,
                    "vehicle_type_core": RAW_VEHICLE_TO_CORE[raw_vehicle_type],
                    "order_type": _normalize_dataset_text(
                        row.get("Type_of_order"),
                        default=DEFAULT_REALISTIC_ORDER_TYPE,
                    ),
                    "current_load": int(current_load or 0),
                    "vehicle_condition": int(vehicle_condition if vehicle_condition is not None else 1),
                    "weather": _normalize_dataset_text(
                        row.get("Weather_conditions"),
                        default=DEFAULT_REALISTIC_WEATHER,
                    ),
                    "traffic_density": _normalize_dataset_text(
                        row.get("Road_traffic_density"),
                        default=DEFAULT_REALISTIC_TRAFFIC,
                    ),
                    "city": _normalize_dataset_city(row.get("City")),
                    "time_taken_min": int(time_taken_min),
                }
            )

    print(
        "Loaded "
        f"{total_rows} rows, dropped {dropped_rows} rows "
        f"({zero_coords} zero-coords, {nan_ratings} NaN-ratings, {negative_lat_rows} negative-lat), "
        f"final clean count: {len(clean_rows)}"
    )
    return clean_rows


def build_partner_pool(clean_rows: list[dict]) -> list[dict]:
    grouped_rows: "OrderedDict[str, list[dict[str, Any]]]" = OrderedDict()
    for row in clean_rows:
        partner_id = str(row.get("partner_id", "")).strip()
        if not partner_id:
            continue
        grouped_rows.setdefault(partner_id, []).append(row)

    partners: list[dict[str, Any]] = []
    for partner_id, rows in grouped_rows.items():
        raw_vehicle_type = _most_common_value(
            [str(row.get("vehicle_type_raw", "")).strip() for row in rows],
            default="MOTORCYCLE",
        )
        core_vehicle_type = RAW_VEHICLE_TO_CORE.get(raw_vehicle_type, "bike")
        last_row = rows[-1]

        partners.append(
            {
                "partner_id": partner_id,
                "name": partner_id,
                "rating": round(sum(float(row["rating"]) for row in rows) / len(rows), 1),
                "vehicle_type": core_vehicle_type,
                "vehicle_types": [core_vehicle_type],
                "raw_vehicle_type": raw_vehicle_type,
                "current_location": {
                    "lat": float(last_row["restaurant_lat"]),
                    "lon": float(last_row["restaurant_lon"]),
                },
                "latitude": float(last_row["restaurant_lat"]),
                "longitude": float(last_row["restaurant_lon"]),
                "is_available": True,
                "current_load": int(round(sum(int(row["current_load"]) for row in rows) / len(rows))),
                "vehicle_condition": min(int(row["vehicle_condition"]) for row in rows),
                "avg_time_taken_min": int(round(sum(int(row["time_taken_min"]) for row in rows) / len(rows))),
                "city": _most_common_value(
                    [str(row.get("city", "")).strip() for row in rows],
                    default=DEFAULT_REALISTIC_CITY,
                ),
                "active": True,
            }
        )

    return partners


def build_order_set(clean_rows: list[dict], max_orders: int = 20) -> list[dict]:
    orders: list[dict[str, Any]] = []
    for row_index, row in enumerate(clean_rows[:max_orders], start=1):
        pickup_lat = float(row["restaurant_lat"])
        pickup_lon = float(row["restaurant_lon"])
        delivery_lat = float(row["delivery_lat"])
        delivery_lon = float(row["delivery_lon"])
        vehicle_required = str(row["vehicle_type_core"])

        orders.append(
            {
                "order_id": f"ORD_{row_index:04d}",
                "restaurant_location": {"lat": pickup_lat, "lon": pickup_lon},
                "delivery_location": {"lat": delivery_lat, "lon": delivery_lon},
                "restaurant_latitude": pickup_lat,
                "restaurant_longitude": pickup_lon,
                "delivery_latitude": delivery_lat,
                "delivery_longitude": delivery_lon,
                "latitude": pickup_lat,
                "longitude": pickup_lon,
                "amount_paise": _estimate_amount_paise(str(row.get("order_type")), int(row.get("current_load", 0))),
                "order_type": str(row["order_type"]),
                "vehicle_required": vehicle_required,
                "vehicle_required_raw": str(row["vehicle_type_raw"]),
                "requested_vehicle_type": vehicle_required,
                "priority": DEFAULT_REALISTIC_PRIORITY,
                "weather_condition": str(row["weather"]),
                "traffic_density": str(row["traffic_density"]),
                "created_at": _synthetic_created_at(row_index),
            }
        )

    return orders


def generate_realistic_sample(
    csv_path: str,
    output_path: str,
    max_orders: int = 15,
    *,
    source_filters: dict[str, str | list[str] | tuple[str, ...] | set[str]] | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    rows = load_and_clean_csv(csv_path)
    filtered_rows = [row for row in rows if _clean_row_matches_filters(row, source_filters)]
    partners = build_partner_pool(filtered_rows)
    orders = build_order_set(filtered_rows, max_orders=max_orders)

    payload: dict[str, Any] = {
        "orders": orders,
        "partners": partners,
        "metadata": {
            "name": "Realistic Zomato Dataset (15 orders)",
            "city": "India",
            "scenario": "CSV-backed Zomato allocation sample with realistic order and partner attributes.",
            "description": "Compact payload generated directly from the cleaned Zomato delivery dataset for realistic allocation runs.",
            "recommended_for": "Real-data allocation demos, rule validation, and replay checks.",
            "generator": "scripts/generate_realistic_sample.py",
            "source_file": str(Path(csv_path)),
            "source_filters": dict(source_filters) if source_filters else None,
            "orders_generated": len(orders),
            "partners_generated": len(partners),
        },
    }
    if metadata:
        payload["metadata"].update(metadata)

    write_json(output_path, payload)
    print(
        f"Generated realistic sample: {max_orders} orders, "
        f"{len(partners)} partners -> {output_path}"
    )
