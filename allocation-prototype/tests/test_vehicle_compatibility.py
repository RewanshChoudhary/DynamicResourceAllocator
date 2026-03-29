from __future__ import annotations

from datetime import datetime, timezone

from allocation.domain.enums import VehicleType
from allocation.domain.order import Order
from allocation.domain.partner import DeliveryPartner
from allocation.rules.hard.vehicle_type import VehicleTypeRule


def test_vehicle_compatibility_map_allows_scooter_partner_to_fill_bike_order():
    order = Order(
        order_id="ORD-BIKE",
        latitude=12.9716,
        longitude=77.5946,
        amount_paise=20000,
        requested_vehicle_type=VehicleType.BIKE,
        created_at=datetime(2026, 2, 22, 12, 0, tzinfo=timezone.utc),
    )
    partner = DeliveryPartner(
        partner_id="PT-SCOOTER",
        latitude=12.9717,
        longitude=77.5947,
        is_available=True,
        rating=4.7,
        vehicle_types=(VehicleType.SCOOTER,),
        active=True,
    )

    compatible_rule = VehicleTypeRule(enabled=True, vehicle_compatibility={"bike": ["bike", "scooter"]})
    absent_map_rule = VehicleTypeRule(enabled=True)
    incompatible_map_rule = VehicleTypeRule(enabled=True, vehicle_compatibility={"bike": ["bike"]})

    assert compatible_rule.evaluate(order, partner).passed is True
    assert absent_map_rule.evaluate(order, partner).passed is False
    assert incompatible_map_rule.evaluate(order, partner).passed is False
