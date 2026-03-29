from __future__ import annotations

from allocation.api.routers.allocate import allocate
from allocation.api.routers.audit import get_manifest, get_rejection_summary, verify_manifest
from allocation.api.schemas import AllocationRequest
from api_test_utils import (
    build_api_test_context,
    run_minimal_allocation,
    unallocated_allocation_payload,
)


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


def test_rejection_summary_route_returns_hard_rule_failures_for_unallocated_order(tmp_path):
    context = build_api_test_context(tmp_path)
    payload = AllocationRequest.model_validate(unallocated_allocation_payload())
    allocation_response = allocate(
        payload,
        context.request("POST", "/allocations"),
        x_idempotency_key="api-audit-rejection-summary",
    )
    order_id = allocation_response.allocations[0]["order_id"]

    summary = get_rejection_summary(
        order_id,
        context.request("GET", f"/allocations/{order_id}/rejection-summary"),
    )

    assert summary["allocation_status"] == "unallocated"
    assert summary["hard_rule_failures"]
    assert summary["candidates_evaluated"] == 1
