from __future__ import annotations

from allocation.domain.enums import VehicleType
from allocation.domain.order import Order
from allocation.domain.partner import DeliveryPartner
from allocation.rules.hard.vehicle_condition import VehicleConditionRule


def _order() -> Order:
    return Order(
        order_id="ORD-1",
        latitude=12.9716,
        longitude=77.5946,
        amount_paise=25000,
        requested_vehicle_type=VehicleType.BIKE,
    )


def _partner(condition: int) -> DeliveryPartner:
    return DeliveryPartner(
        partner_id=f"PT-{condition}",
        latitude=12.9717,
        longitude=77.5947,
        is_available=True,
        rating=4.8,
        vehicle_types=(VehicleType.BIKE,),
        vehicle_condition=condition,
    )


def test_rejects_partner_with_condition_zero():
    result = VehicleConditionRule().evaluate(_order(), _partner(0))

    assert result.passed is False


def test_accepts_partner_with_condition_one():
    result = VehicleConditionRule().evaluate(_order(), _partner(1))

    assert result.passed is True


def test_accepts_partner_with_condition_two():
    result = VehicleConditionRule().evaluate(_order(), _partner(2))

    assert result.passed is True


def test_config_min_condition_zero_accepts_all():
    rule = VehicleConditionRule(min_condition=0)

    assert rule.evaluate(_order(), _partner(0)).passed is True
    assert rule.evaluate(_order(), _partner(1)).passed is True
    assert rule.evaluate(_order(), _partner(2)).passed is True


def test_failure_code_is_correct_string():
    result = VehicleConditionRule().evaluate(_order(), _partner(0))

    assert result.failure_code == "VEHICLE_CONDITION_BELOW_MINIMUM"
