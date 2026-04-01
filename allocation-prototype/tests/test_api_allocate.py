from __future__ import annotations

from sqlalchemy import func, select

from allocation.api.routers.allocate import allocate
from allocation.api.schemas import AllocationRequest
from allocation.persistence.models import AllocationEventModel
from api_test_utils import build_api_test_context, minimal_allocation_payload


def test_allocate_route_happy_path_returns_allocations_and_aggregate_diagnostics(tmp_path):
    context = build_api_test_context(tmp_path)
    payload = AllocationRequest.model_validate(minimal_allocation_payload())

    response = allocate(
        payload,
        context.request("POST", "/allocations"),
        x_idempotency_key="api-allocate-happy-path",
    )
    body = response.model_dump()

    assert "allocations" in body
    assert "aggregate_diagnostics" in body
    assert body["aggregate_diagnostics"]["allocated"] == 2
    assert body["summary"]["allocated_orders"] == 2
    assert body["summary"]["active_hard_rules"] == [
        "availability",
        "vehicle_type",
        "max_distance",
        "min_rating",
    ]


def test_allocate_route_idempotency_returns_cached_response_without_duplicate_writes(tmp_path):
    context = build_api_test_context(tmp_path)
    payload = AllocationRequest.model_validate(minimal_allocation_payload())

    first = allocate(
        payload,
        context.request("POST", "/allocations"),
        x_idempotency_key="api-allocate-idempotent",
    )
    second = allocate(
        payload,
        context.request("POST", "/allocations"),
        x_idempotency_key="api-allocate-idempotent",
    )

    with context.session_factory() as session:
        event_count = session.execute(select(func.count()).select_from(AllocationEventModel)).scalar_one()

    assert first.model_dump() == second.model_dump()
    assert event_count == len(payload.orders)
