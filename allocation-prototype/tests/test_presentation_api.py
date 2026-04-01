from __future__ import annotations

from allocation.api.routers.allocate import get_active_reservations
from allocation.api.routers.presentation import (
    audit_diagnostics,
    audit_replay,
    audit_verify,
    runtime_diagnostics,
)
from allocation.reservation import store as reservation_store_module
from api_test_utils import build_api_test_context, run_minimal_allocation


def setup_function() -> None:
    reservation_store_module._store_instance = None


def test_audit_verify_alias_route_returns_verified_status(tmp_path):
    context = build_api_test_context(tmp_path)
    _, allocation_response = run_minimal_allocation(context, idempotency_key="presentation-verify")

    verification = audit_verify(
        allocation_response.manifest_id,
        context.request("GET", f"/audit/verify/{allocation_response.manifest_id}"),
    )

    assert verification["manifest_id"] == allocation_response.manifest_id
    assert verification["status"] == "VERIFIED"
    assert verification["signature_valid"] is True


def test_audit_replay_alias_route_returns_normalized_comparison_shape(tmp_path):
    context = build_api_test_context(tmp_path)
    _, allocation_response = run_minimal_allocation(context, idempotency_key="presentation-replay")

    replay = audit_replay(
        allocation_response.manifest_id,
        context.request("GET", f"/audit/replay/{allocation_response.manifest_id}"),
    )

    assert replay["manifest_id"] == allocation_response.manifest_id
    assert replay["status"] == "SUCCESS"
    assert replay["original_allocations"]
    assert replay["replayed_allocations"]
    assert replay["raw_replay_response"]["matched"] is True
    assert replay["original_allocations"][0]["order_id"] == replay["replayed_allocations"][0]["order_id"]


def test_audit_diagnostics_route_returns_sidebar_friendly_payload(tmp_path):
    context = build_api_test_context(tmp_path)
    run_minimal_allocation(context, idempotency_key="presentation-diagnostics")

    diagnostics = audit_diagnostics(context.request("GET", "/audit/diagnostics"))

    assert diagnostics["total_allocations"] == 2
    assert diagnostics["total_unallocated"] == 0
    assert diagnostics["fairness_gini"] is None
    assert "availability" in diagnostics["active_rules"]
    assert "fairness_score" in diagnostics["active_rules"]


def test_runtime_diagnostics_reports_database_and_version(tmp_path):
    context = build_api_test_context(tmp_path)

    runtime = runtime_diagnostics(context.request("GET", "/diagnostics/runtime"))

    assert runtime["db_connected"] is True
    assert runtime["version"] == "0.1.0"


def test_active_reservations_route_returns_wall_clock_expiry(monkeypatch):
    store = reservation_store_module.get_reservation_store()
    monkeypatch.setattr(reservation_store_module.time, "time", lambda: 1_000.0)
    monkeypatch.setattr(reservation_store_module.time, "monotonic", lambda: 50.0)
    assert store.reserve("PT-1", "ORD-1") is True

    payload = get_active_reservations()

    assert payload["PT-1"]["order_id"] == "ORD-1"
    assert payload["PT-1"]["expires_at"] == 1_030.0
