from __future__ import annotations

from allocation.api.routers.audit import get_manifest, verify_manifest
from api_test_utils import build_api_test_context, run_minimal_allocation


def test_manifest_route_returns_trace_hash_and_signature(tmp_path):
    context = build_api_test_context(tmp_path)
    _, allocation_response = run_minimal_allocation(context, idempotency_key="api-audit-manifest")
    order_id = allocation_response.allocations[0]["order_id"]

    manifest = get_manifest(order_id, context.request("GET", f"/allocations/{order_id}/manifest"))

    assert "trace_hash" in manifest
    assert "manifest_signature" in manifest


def test_manifest_verify_route_confirms_manifest_is_valid(tmp_path):
    context = build_api_test_context(tmp_path)
    _, allocation_response = run_minimal_allocation(context, idempotency_key="api-audit-verify")
    order_id = allocation_response.allocations[0]["order_id"]

    verification = verify_manifest(order_id, context.request("GET", f"/allocations/{order_id}/manifest/verify"))

    assert verification["trace_match"] is True
    assert verification["signature_valid"] is True
    assert verification["reproduced_decision_matches_stored"] is True
