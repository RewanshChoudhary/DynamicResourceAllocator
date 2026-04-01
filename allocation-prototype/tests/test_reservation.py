from __future__ import annotations

from datetime import datetime, timezone

from allocation.api.routers.allocate import allocate
from allocation.api.schemas import AllocationRequest
from allocation.reservation import store as reservation_store_module
from api_test_utils import build_api_test_context


def _set_fake_clock(monkeypatch, *, wall_clock: float, monotonic_clock: float) -> None:
    monkeypatch.setattr(reservation_store_module.time, "time", lambda: wall_clock)
    monkeypatch.setattr(reservation_store_module.time, "monotonic", lambda: monotonic_clock)


def _single_partner_payload() -> dict:
    created_at = datetime(2026, 2, 22, 12, 0, tzinfo=timezone.utc).isoformat()
    return {
        "orders": [
            {
                "order_id": "ORD-1",
                "latitude": 12.9716,
                "longitude": 77.5946,
                "amount_paise": 30000,
                "requested_vehicle_type": "bike",
                "created_at": created_at,
            },
            {
                "order_id": "ORD-2",
                "latitude": 12.9720,
                "longitude": 77.5950,
                "amount_paise": 24000,
                "requested_vehicle_type": "bike",
                "created_at": created_at,
            },
        ],
        "partners": [
            {
                "partner_id": "PT-1",
                "latitude": 12.9717,
                "longitude": 77.5947,
                "is_available": True,
                "rating": 4.8,
                "vehicle_types": ["bike"],
                "active": True,
            }
        ],
    }


def setup_function() -> None:
    reservation_store_module._store_instance = None


def test_reserve_grants_first_caller(monkeypatch):
    store = reservation_store_module.PartnerReservationStore(ttl_seconds=30)
    _set_fake_clock(monkeypatch, wall_clock=1_000.0, monotonic_clock=50.0)

    reserved = store.reserve("PT-1", "ORD-1")

    assert reserved is True
    assert store.current_reservations()["PT-1"]["order_id"] == "ORD-1"
    assert store.current_reservations()["PT-1"]["expires_at"] == 1_030.0


def test_reserve_denies_concurrent_caller_for_same_partner(monkeypatch):
    store = reservation_store_module.PartnerReservationStore(ttl_seconds=30)
    _set_fake_clock(monkeypatch, wall_clock=1_000.0, monotonic_clock=50.0)
    assert store.reserve("PT-1", "ORD-1") is True

    denied = store.reserve("PT-1", "ORD-2")

    assert denied is False
    assert store.current_reservations()["PT-1"]["order_id"] == "ORD-1"


def test_reserve_allows_after_release(monkeypatch):
    store = reservation_store_module.PartnerReservationStore(ttl_seconds=30)
    _set_fake_clock(monkeypatch, wall_clock=1_000.0, monotonic_clock=50.0)
    assert store.reserve("PT-1", "ORD-1") is True

    store.release("PT-1", "ORD-1")
    allowed = store.reserve("PT-1", "ORD-2")

    assert allowed is True
    assert store.current_reservations()["PT-1"]["order_id"] == "ORD-2"


def test_reserve_allows_after_ttl_expiry(monkeypatch):
    store = reservation_store_module.PartnerReservationStore(ttl_seconds=30)
    _set_fake_clock(monkeypatch, wall_clock=1_000.0, monotonic_clock=50.0)
    assert store.reserve("PT-1", "ORD-1") is True

    _set_fake_clock(monkeypatch, wall_clock=1_200.0, monotonic_clock=81.0)
    allowed = store.reserve("PT-1", "ORD-2")

    assert allowed is True
    assert store.current_reservations()["PT-1"]["order_id"] == "ORD-2"
    assert store.current_reservations()["PT-1"]["expires_at"] == 1_230.0


def test_release_all_for_order_clears_multiple_partners(monkeypatch):
    store = reservation_store_module.PartnerReservationStore(ttl_seconds=30)
    _set_fake_clock(monkeypatch, wall_clock=1_000.0, monotonic_clock=50.0)
    assert store.reserve("PT-1", "ORD-1") is True
    assert store.reserve("PT-2", "ORD-1") is True
    assert store.reserve("PT-3", "ORD-2") is True

    store.release_all_for_order("ORD-1")

    reservations = store.current_reservations()
    assert "PT-1" not in reservations
    assert "PT-2" not in reservations
    assert reservations["PT-3"]["order_id"] == "ORD-2"


def test_is_reserved_returns_false_after_expiry(monkeypatch):
    store = reservation_store_module.PartnerReservationStore(ttl_seconds=30)
    _set_fake_clock(monkeypatch, wall_clock=1_000.0, monotonic_clock=50.0)
    assert store.reserve("PT-1", "ORD-1") is True

    _set_fake_clock(monkeypatch, wall_clock=1_200.0, monotonic_clock=81.0)

    assert store.is_reserved("PT-1") is False
    assert "PT-1" not in store.current_reservations()


def test_allocate_route_marks_conflicting_selection_as_partner_reserved(tmp_path):
    context = build_api_test_context(tmp_path)
    payload = AllocationRequest.model_validate(
        {
            "orders": [
                {
                    "order_id": "ORD-LOCKED",
                    "latitude": 12.9716,
                    "longitude": 77.5946,
                    "amount_paise": 30000,
                    "requested_vehicle_type": "bike",
                    "created_at": datetime(2026, 2, 22, 12, 0, tzinfo=timezone.utc).isoformat(),
                }
            ],
            "partners": _single_partner_payload()["partners"],
        }
    )
    store = reservation_store_module.get_reservation_store()
    assert store.reserve("PT-1", "ORD-OTHER") is True

    response = allocate(
        payload,
        context.request("POST", "/allocations"),
        x_idempotency_key="api-allocate-partner-reserved",
    )

    allocations = response.model_dump()["allocations"]

    assert len(allocations) == 1
    assert sum(1 for allocation in allocations if allocation["partner_id"] is not None) == 0
    assert sum(1 for allocation in allocations if allocation["reason"] == "partner_reserved") == 1
    assert response.aggregate_diagnostics["allocated"] == 0
    assert response.aggregate_diagnostics["unallocated"] == 1
