from __future__ import annotations

import json
from pathlib import Path

from allocation.api.schemas import AllocationRequest
from allocation.data.zomato_adapter import (
    build_order_set,
    build_partner_pool,
    generate_realistic_sample,
    load_and_clean_csv,
)


CSV_HEADER = (
    "ID,Delivery_person_ID,Delivery_person_Age,Delivery_person_Ratings,"
    "Restaurant_latitude,Restaurant_longitude,Delivery_location_latitude,"
    "Delivery_location_longitude,Order_Date,Time_Orderd,Time_Order_picked,"
    "Weather_conditions,Road_traffic_density,Vehicle_condition,Type_of_order,"
    "Type_of_vehicle,multiple_deliveries,Festival,City,Time_taken (min)"
)


def _write_csv(tmp_path: Path, rows: list[str]) -> Path:
    path = tmp_path / "zomato_extended.csv"
    path.write_text("\n".join([CSV_HEADER, *rows]), encoding="utf-8")
    return path


def test_load_and_clean_drops_zero_coords(tmp_path: Path):
    csv_path = _write_csv(
        tmp_path,
        [
            "0x1,P1,25,4.5,0.0,77.5946,12.9816,77.6046,12-02-2022,10:15,10:25,Sunny,Low,1,Meal,motorcycle,1,No,Urban,20",
            "0x2,P2,25,4.6,12.9716,77.5946,12.9816,77.6046,12-02-2022,10:15,10:25,Sunny,Low,1,Meal,scooter,1,No,Urban,20",
        ],
    )

    clean_rows = load_and_clean_csv(str(csv_path))

    assert len(clean_rows) == 1
    assert clean_rows[0]["partner_id"] == "P2"


def test_load_and_clean_drops_nan_ratings(tmp_path: Path):
    csv_path = _write_csv(
        tmp_path,
        [
            "0x1,P1,25,,12.9716,77.5946,12.9816,77.6046,12-02-2022,10:15,10:25,Sunny,Low,1,Meal,motorcycle,1,No,Urban,20",
            "0x2,P2,25,4.6,12.9716,77.5946,12.9816,77.6046,12-02-2022,10:15,10:25,Sunny,Low,1,Meal,scooter,1,No,Urban,20",
        ],
    )

    clean_rows = load_and_clean_csv(str(csv_path))

    assert len(clean_rows) == 1
    assert clean_rows[0]["partner_id"] == "P2"


def test_load_and_clean_drops_negative_lat(tmp_path: Path):
    csv_path = _write_csv(
        tmp_path,
        [
            "0x1,P1,25,4.5,-27.163303,78.057044,27.233303,78.127044,12-02-2022,10:15,10:25,Sunny,Low,1,Meal,motorcycle,1,No,Urban,20",
            "0x2,P2,25,4.6,12.9716,77.5946,12.9816,77.6046,12-02-2022,10:15,10:25,Sunny,Low,1,Meal,scooter,1,No,Urban,20",
        ],
    )

    clean_rows = load_and_clean_csv(str(csv_path))

    assert len(clean_rows) == 1
    assert clean_rows[0]["partner_id"] == "P2"


def test_load_and_clean_fills_nan_load_with_zero(tmp_path: Path):
    csv_path = _write_csv(
        tmp_path,
        [
            "0x1,P1,25,4.5,12.9716,77.5946,12.9816,77.6046,12-02-2022,10:15,10:25,Sunny,Low,1,Meal,motorcycle,,No,,20",
        ],
    )

    clean_rows = load_and_clean_csv(str(csv_path))

    assert clean_rows[0]["current_load"] == 0
    assert clean_rows[0]["city"] == "Metropolitian"


def test_build_partner_pool_aggregates_correctly():
    partners = build_partner_pool(
        [
            {
                "partner_id": "P1",
                "rating": 4.0,
                "restaurant_lat": 12.9716,
                "restaurant_lon": 77.5946,
                "delivery_lat": 12.9816,
                "delivery_lon": 77.6046,
                "vehicle_type_raw": "MOTORCYCLE",
                "vehicle_type_core": "bike",
                "order_type": "Meal",
                "current_load": 0,
                "vehicle_condition": 2,
                "weather": "Sunny",
                "traffic_density": "Low",
                "city": "Urban",
                "time_taken_min": 20,
            },
            {
                "partner_id": "P1",
                "rating": 4.6,
                "restaurant_lat": 12.9726,
                "restaurant_lon": 77.5956,
                "delivery_lat": 12.9826,
                "delivery_lon": 77.6056,
                "vehicle_type_raw": "MOTORCYCLE",
                "vehicle_type_core": "bike",
                "order_type": "Meal",
                "current_load": 1,
                "vehicle_condition": 1,
                "weather": "Cloudy",
                "traffic_density": "Medium",
                "city": "Urban",
                "time_taken_min": 30,
            },
            {
                "partner_id": "P1",
                "rating": 4.8,
                "restaurant_lat": 12.9736,
                "restaurant_lon": 77.5966,
                "delivery_lat": 12.9836,
                "delivery_lon": 77.6066,
                "vehicle_type_raw": "SCOOTER",
                "vehicle_type_core": "scooter",
                "order_type": "Snack",
                "current_load": 2,
                "vehicle_condition": 2,
                "weather": "Windy",
                "traffic_density": "High",
                "city": "Urban",
                "time_taken_min": 25,
            },
        ]
    )

    assert len(partners) == 1
    partner = partners[0]
    assert partner["rating"] == 4.5
    assert partner["current_load"] == 1
    assert partner["avg_time_taken_min"] == 25
    assert partner["raw_vehicle_type"] == "MOTORCYCLE"
    assert partner["latitude"] == 12.9736
    assert partner["longitude"] == 77.5966


def test_build_partner_pool_averages_vehicle_condition():
    partners = build_partner_pool(
        [
            {
                "partner_id": "P1",
                "rating": 4.4,
                "restaurant_lat": 12.9716,
                "restaurant_lon": 77.5946,
                "delivery_lat": 12.9816,
                "delivery_lon": 77.6046,
                "vehicle_type_raw": "MOTORCYCLE",
                "vehicle_type_core": "bike",
                "order_type": "Meal",
                "current_load": 0,
                "vehicle_condition": 2,
                "weather": "Sunny",
                "traffic_density": "Low",
                "city": "Urban",
                "time_taken_min": 20,
            },
            {
                "partner_id": "P1",
                "rating": 4.5,
                "restaurant_lat": 12.9726,
                "restaurant_lon": 77.5956,
                "delivery_lat": 12.9826,
                "delivery_lon": 77.6056,
                "vehicle_type_raw": "MOTORCYCLE",
                "vehicle_type_core": "bike",
                "order_type": "Meal",
                "current_load": 1,
                "vehicle_condition": 0,
                "weather": "Sunny",
                "traffic_density": "Low",
                "city": "Urban",
                "time_taken_min": 20,
            },
        ]
    )

    assert partners[0]["vehicle_condition"] == 1


def test_build_order_set_respects_max_orders():
    clean_rows = [
        {
            "partner_id": "P1",
            "rating": 4.5,
            "restaurant_lat": 12.9716 + index,
            "restaurant_lon": 77.5946 + index,
            "delivery_lat": 12.9816 + index,
            "delivery_lon": 77.6046 + index,
            "vehicle_type_raw": "MOTORCYCLE",
            "vehicle_type_core": "bike",
            "order_type": "Meal",
            "current_load": 1,
            "vehicle_condition": 1,
            "weather": "Sunny",
            "traffic_density": "Low",
            "city": "Urban",
            "time_taken_min": 20,
        }
        for index in range(3)
    ]

    orders = build_order_set(clean_rows, max_orders=2)

    assert len(orders) == 2
    assert orders[0]["order_id"] == "ORD_0001"
    assert orders[1]["order_id"] == "ORD_0002"


def test_generate_realistic_sample_produces_valid_json(tmp_path: Path):
    csv_path = _write_csv(
        tmp_path,
        [
            "0x1,P1,25,4.5,12.9716,77.5946,12.9816,77.6046,12-02-2022,10:15,10:25,Sunny,Low,1,Meal,motorcycle,1,No,Urban,20",
            "0x2,P2,25,4.6,12.9726,77.5956,12.9826,77.6056,12-02-2022,10:15,10:25,Cloudy,Medium,2,Snack,scooter,0,No,Urban,18",
        ],
    )
    output_path = tmp_path / "realistic.json"

    generate_realistic_sample(str(csv_path), str(output_path), max_orders=2)

    payload = json.loads(output_path.read_text())
    AllocationRequest.model_validate(payload)
    assert payload["metadata"]["generator"] == "scripts/generate_realistic_sample.py"
    assert len(payload["orders"]) == 2
    assert len(payload["partners"]) == 2
