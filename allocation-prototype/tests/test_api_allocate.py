from __future__ import annotations

from sqlalchemy import func, select

from allocation.api.routers.allocate import allocate
from allocation.api.schemas import AllocationRequest
from allocation.persistence.models import AllocationEventModel
from allocation.persistence.repository import ManifestRepository
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
        "vehicle_condition",
        "weather_safety",
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


def test_allocate_route_accepts_richer_realistic_payload_shape(tmp_path):
    context = build_api_test_context(tmp_path)
    payload = AllocationRequest.model_validate(
        {
            "orders": [
                {
                    "order_id": "ORD-RICH-1",
                    "restaurant_location": {"lat": 12.9716, "lon": 77.5946},
                    "delivery_location": {"lat": 12.9816, "lon": 77.6046},
                    "order_type": "Meal",
                    "vehicle_required": "bike",
                    "vehicle_required_raw": "MOTORCYCLE",
                    "priority": "NORMAL",
                    "weather_condition": "Cloudy",
                    "traffic_density": "Jam",
                }
            ],
            "partners": [
                {
                    "partner_id": "PT-RICH-1",
                    "current_location": {"lat": 12.9717, "lon": 77.5947},
                    "is_available": True,
                    "rating": 4.8,
                    "vehicle_type": "MOTORCYCLE",
                    "name": "PT-RICH-1",
                    "current_load": 1,
                    "vehicle_condition": 2,
                    "avg_time_taken_min": 18,
                    "city": "Urban",
                }
            ],
        }
    )

    response = allocate(
        payload,
        context.request("POST", "/allocations"),
        x_idempotency_key="api-allocate-rich-shape",
    )

    assert response.summary["allocated_orders"] == 1


def test_allocate_route_traces_different_fairness_scores_for_different_request_loads(tmp_path):
    context = build_api_test_context(tmp_path)
    payload = AllocationRequest.model_validate(
        {
            "orders": [
                {
                    "order_id": "ORD-FAIR-1",
                    "latitude": 12.9716,
                    "longitude": 77.5946,
                    "amount_paise": 30000,
                    "requested_vehicle_type": "bike",
                },
            ],
            "partners": [
                {
                    "partner_id": "PT-LOW",
                    "latitude": 12.9717,
                    "longitude": 77.5947,
                    "is_available": True,
                    "rating": 4.8,
                    "vehicle_types": ["bike"],
                    "active": True,
                    "current_load": 0,
                    "vehicle_condition": 2,
                },
                {
                    "partner_id": "PT-HIGH",
                    "latitude": 12.9717,
                    "longitude": 77.5947,
                    "is_available": True,
                    "rating": 4.8,
                    "vehicle_types": ["bike"],
                    "active": True,
                    "current_load": 2,
                    "vehicle_condition": 2,
                }
            ],
        }
    )

    response = allocate(
        payload,
        context.request("POST", "/allocations"),
        x_idempotency_key="api-allocate-fairness-request-loads",
    )

    with context.session_factory() as session:
        manifest = ManifestRepository(session).get(response.manifest_id)

    assert manifest is not None
    order_trace = manifest.evaluation_trace["orders"][0]
    candidates = {candidate["partner_id"]: candidate for candidate in order_trace["candidates"]}

    low_fairness = next(
        score for score in candidates["PT-LOW"]["scoring_results"] if score["rule"] == "fairness_score"
    )
    high_fairness = next(
        score for score in candidates["PT-HIGH"]["scoring_results"] if score["rule"] == "fairness_score"
    )

    assert low_fairness["score_breakdown"]["partner_current_load"] == 0.0
    assert high_fairness["score_breakdown"]["partner_current_load"] == 2.0
    assert low_fairness["raw_score"] > high_fairness["raw_score"]


def test_allocate_route_is_deterministic_for_same_payload_on_same_app(tmp_path):
    context = build_api_test_context(tmp_path)
    payload = AllocationRequest.model_validate(
        {
            "orders": [
                {
                    "order_id": "ORD-DET-1",
                    "latitude": 12.9716,
                    "longitude": 77.5946,
                    "amount_paise": 30000,
                    "requested_vehicle_type": "bike",
                }
            ],
            "partners": [
                {
                    "partner_id": "PA",
                    "latitude": 12.9717,
                    "longitude": 77.5947,
                    "is_available": True,
                    "rating": 4.8,
                    "vehicle_types": ["bike"],
                    "active": True,
                    "current_load": 0,
                    "vehicle_condition": 2,
                    "avg_time_taken_min": 20,
                },
                {
                    "partner_id": "PB",
                    "latitude": 12.9717,
                    "longitude": 77.5947,
                    "is_available": True,
                    "rating": 4.8,
                    "vehicle_types": ["bike"],
                    "active": True,
                    "current_load": 0,
                    "vehicle_condition": 2,
                    "avg_time_taken_min": 20,
                },
            ],
        }
    )

    first = allocate(
        payload,
        context.request("POST", "/allocations"),
        x_idempotency_key="api-allocate-determinism-1",
    )
    second = allocate(
        payload,
        context.request("POST", "/allocations"),
        x_idempotency_key="api-allocate-determinism-2",
    )

    first_allocation = first.model_dump()["allocations"][0]
    second_allocation = second.model_dump()["allocations"][0]

    assert first_allocation["partner_id"] == "PA"
    assert second_allocation["partner_id"] == "PA"
    assert first_allocation["weighted_score"] == second_allocation["weighted_score"]
