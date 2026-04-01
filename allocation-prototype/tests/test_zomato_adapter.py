from __future__ import annotations

from pathlib import Path

from allocation.data.zomato_adapter import audit_zomato_csv, build_allocation_payload_from_zomato


def test_zomato_adapter_audit_and_payload(tmp_path: Path):
    csv_path = tmp_path / "zomato.csv"
    csv_path.write_text(
        "\n".join(
            [
                "ID,Delivery_person_ID,Delivery_person_Age,Delivery_person_Ratings,Restaurant_latitude,Restaurant_longitude,Delivery_location_latitude,Delivery_location_longitude,Order_Date,Time_Orderd,Time_Order_picked,Weather_conditions,Road_traffic_density,Vehicle_condition,Type_of_order,Type_of_vehicle,multiple_deliveries,Festival,City,Time_taken (min)",
                "0x1,PARTNER1,25,4.5,-22.5000,-88.3000,22.5500,88.3500,12-02-2022,10:15,10:25,Fog,Low,1,Meal,motorcycle,1,No,Metropolitian,20",
                "0x2,PARTNER2,30,4.8,12.9716,77.5946,12.9816,77.6046,12-02-2022,11:15,11:25,Sunny,Medium,1,Snack,scooter,0,No,Urban,18",
                "0x3,PARTNER3,15,4.2,12.9716,77.5946,12.9916,77.6146,12-02-2022,12:15,12:25,Sunny,Medium,1,Drinks,bicycle,0,No,Urban,18",
            ]
        ),
        encoding="utf-8",
    )

    audit = audit_zomato_csv(csv_path)
    assert audit.total_rows == 3
    assert audit.anomaly_counts["negative_restaurant_coordinate_rows"] == 1
    assert audit.anomaly_counts["invalid_age_rows"] == 1

    payload = build_allocation_payload_from_zomato(csv_path, max_orders=5, max_partners=5)
    assert payload["metadata"]["orders_generated"] == 2
    assert payload["metadata"]["partners_generated"] == 2
    assert payload["metadata"]["corrected_coordinate_rows"] == 1

    first_order = payload["orders"][0]
    assert first_order["latitude"] > 0
    assert first_order["longitude"] > 0
