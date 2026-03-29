from __future__ import annotations

from allocation.api.routers.audit import get_manifest, replay_manifest, verify_manifest
from allocation.engine.manifest import canonical_json_bytes, sha256_hex
from api_test_utils import build_api_test_context, run_minimal_allocation


def test_allocation_request_lifecycle_replays_with_identical_trace_hash(tmp_path):
    context = build_api_test_context(tmp_path)
    _, allocation_response = run_minimal_allocation(context, idempotency_key="api-lifecycle")
    assert allocation_response.summary["allocated_orders"] == 2

    order_id = allocation_response.allocations[0]["order_id"]

    manifest = get_manifest(order_id, context.request("GET", f"/allocations/{order_id}/manifest"))
    verification = verify_manifest(order_id, context.request("GET", f"/allocations/{order_id}/manifest/verify"))
    replay = replay_manifest(order_id, context.request("GET", f"/allocations/{order_id}/replay"))

    replayed_trace_hash = sha256_hex(canonical_json_bytes(replay["replayed_trace"]))

    assert verification["trace_match"] is True
    assert replay["matched"] is True
    assert replay["trace_hash_identical"] is True
    assert replayed_trace_hash == manifest["trace_hash"]
