from __future__ import annotations

import copy
import os
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Request

from allocation.api.schemas import AllocationRequest, AllocationResponse
from allocation.config.loader import ConfigLoader
from allocation.domain.allocation import Allocation
from allocation.domain.enums import AllocationStatus
from allocation.domain.order import Order
from allocation.domain.partner import DeliveryPartner
from allocation.engine.manifest import ManifestBuilder, build_input_snapshot
from allocation.engine.pipeline import (
    DeterministicAllocationPipeline,
    EvaluationTrace,
    PipelineResult,
    build_aggregate_diagnostics,
)
from allocation.fairness.gini import FairnessEnforcer
from allocation.persistence.config_versions import ConfigVersionStore
from allocation.persistence.repository import (
    AllocationRepository,
    IdempotencyRepository,
    InputSnapshotRepository,
    ManifestRepository,
)
from allocation.reservation.store import get_reservation_store
from allocation.rules.conflict import RuleConflictError
from allocation.rules.registry import build_rule_set


router = APIRouter()
CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "rules.yaml"


def _to_domain_orders(request_payload: AllocationRequest) -> list[Order]:
    return [
        Order(
            order_id=order.order_id,
            latitude=order.latitude,
            longitude=order.longitude,
            amount_paise=order.amount_paise,
            requested_vehicle_type=order.requested_vehicle_type,
            created_at=order.created_at,
        )
        for order in request_payload.orders
    ]


def _to_domain_partners(request_payload: AllocationRequest) -> list[DeliveryPartner]:
    return [
        DeliveryPartner(
            partner_id=partner.partner_id,
            latitude=partner.latitude,
            longitude=partner.longitude,
            is_available=partner.is_available,
            rating=partner.rating,
            vehicle_types=tuple(partner.vehicle_types),
            active=partner.active,
        )
        for partner in request_payload.partners
    ]


def _active_hard_rule_names(config: dict) -> list[str]:
    return [
        rule["name"]
        for rule in config.get("hard_rules", [])
        if rule.get("enabled", True)
    ]


def _apply_partner_reservations(pipeline_result: PipelineResult) -> tuple[PipelineResult, list[tuple[str, str]], list[str]]:
    reservation_store = get_reservation_store()
    adjusted_allocations: list[Allocation] = []
    adjusted_order_traces: list[dict] = []
    successful_reservations: list[tuple[str, str]] = []
    attempted_order_ids: list[str] = []
    request_reserved_partner_ids: set[str] = set()

    for allocation, order_trace in zip(pipeline_result.allocations, pipeline_result.trace.orders):
        trace_payload = copy.deepcopy(order_trace)

        if allocation.partner_id is None:
            adjusted_allocations.append(allocation)
            adjusted_order_traces.append(trace_payload)
            continue

        if allocation.partner_id in request_reserved_partner_ids:
            adjusted_allocations.append(allocation)
            adjusted_order_traces.append(trace_payload)
            continue

        attempted_order_ids.append(allocation.order_id)
        reserved = reservation_store.reserve(allocation.partner_id, allocation.order_id)
        if reserved:
            request_reserved_partner_ids.add(allocation.partner_id)
            successful_reservations.append((allocation.order_id, allocation.partner_id))
            adjusted_allocations.append(allocation)
            adjusted_order_traces.append(trace_payload)
            continue

        adjusted_allocations.append(
            Allocation(
                order_id=allocation.order_id,
                partner_id=None,
                status=AllocationStatus.UNALLOCATED,
                reason="partner_reserved",
                weighted_score=None,
            )
        )
        trace_payload["selected_partner_id"] = None
        trace_payload["selected_weighted_score"] = None
        trace_payload["decision_reason"] = "partner_reserved"
        adjusted_order_traces.append(trace_payload)

    adjusted_trace = EvaluationTrace(
        orders=tuple(adjusted_order_traces),
        scoring_weights=pipeline_result.trace.scoring_weights,
        initial_partner_loads=pipeline_result.trace.initial_partner_loads,
        fairness_escalation_event=pipeline_result.trace.fairness_escalation_event,
        conflict_resolution_report_hash=pipeline_result.trace.conflict_resolution_report_hash,
    )
    adjusted_diagnostics = build_aggregate_diagnostics(
        order_traces=adjusted_order_traces,
        hard_rule_names=list(
            pipeline_result.aggregate_diagnostics.get("hard_rule_elimination_counts", {}).keys()
        ),
    )
    adjusted_result = PipelineResult(
        allocations=tuple(adjusted_allocations),
        trace=adjusted_trace,
        aggregate_diagnostics=adjusted_diagnostics,
    )
    return adjusted_result, successful_reservations, attempted_order_ids


@router.get("/allocations/reservations/active")
def get_active_reservations() -> dict[str, dict]:
    return get_reservation_store().current_reservations()


@router.post("/allocations", response_model=AllocationResponse)
def allocate(
    payload: AllocationRequest,
    request: Request,
    x_idempotency_key: str = Header(...),
) -> AllocationResponse:
    session = request.app.state.session_factory()
    try:
        idempotency_repository = IdempotencyRepository(session)
        cached = idempotency_repository.get(x_idempotency_key)
        if cached:
            return AllocationResponse.model_validate(cached["response"])

        config_loader = ConfigLoader(CONFIG_PATH)
        try:
            loaded = config_loader.load()
        except RuleConflictError as exc:
            raise HTTPException(status_code=400, detail=exc.report.to_dict()) from exc

        config = loaded.config
        conflict_report_hash = loaded.conflict_report.sha256()

        config_store = ConfigVersionStore(session)
        config_version = config_store.put_if_absent(config, commit=False)

        hard_rules, scoring_rules = build_rule_set(config)
        pipeline = DeterministicAllocationPipeline(hard_rules=hard_rules, scoring_rules=scoring_rules)

        orders = _to_domain_orders(payload)
        partners = _to_domain_partners(payload)

        tracker = request.app.state.partner_load_tracker
        partner_ids = [partner.partner_id for partner in partners]
        if not partner_ids:
            raise HTTPException(status_code=400, detail="Gini calculation requires at least one partner load")
        partner_loads = tracker.get_load_counts(partner_ids)

        fairness_cfg = config.get("fairness", {})
        enforcer = FairnessEnforcer(
            base_weights=config.get("weights", {}),
            fairness_rule_name="fairness_score",
            fairness_threshold=float(fairness_cfg.get("threshold", 0.35)),
            escalation_factor=float(fairness_cfg.get("escalation_factor", 1.5)),
        )
        try:
            weights, fairness_event = enforcer.adjust_weights(partner_loads)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        pipeline_result = pipeline.evaluate(
            orders=orders,
            partners=partners,
            scoring_weights=weights,
            partner_loads=partner_loads,
            fairness_escalation_event=fairness_event.to_dict() if fairness_event else None,
            conflict_resolution_report_hash=conflict_report_hash,
        )
        pipeline_result, reserved_pairs, attempted_order_ids = _apply_partner_reservations(pipeline_result)

        input_snapshot = build_input_snapshot(orders, partners)
        try:
            manifest_builder = ManifestBuilder(signing_key=os.getenv("SDM_SIGNING_KEY"))
            manifest = manifest_builder.build(
                pipeline_result=pipeline_result,
                input_snapshot=input_snapshot,
                config_version_hash=config_version.config_version_hash,
                conflict_resolution_report_hash=conflict_report_hash,
            )

            manifest_repository = ManifestRepository(session)
            input_snapshot_repository = InputSnapshotRepository(session)
            allocation_repository = AllocationRepository(session)

            manifest_repository.save(manifest, commit=False)
            input_snapshot_repository.save(manifest.input_hash, input_snapshot, commit=False)
            allocation_repository.append_events(
                manifest.manifest_id,
                list(pipeline_result.allocations),
                trace_hash=manifest.trace_hash,
                config_version_hash=manifest.config_version_hash,
                commit=False,
            )

            allocated_count = sum(1 for allocation in pipeline_result.allocations if allocation.partner_id is not None)
            response_payload = {
                "manifest_id": manifest.manifest_id,
                "allocations": [
                    {
                        "order_id": allocation.order_id,
                        "partner_id": allocation.partner_id,
                        "status": allocation.status.value,
                        "reason": allocation.reason,
                        "weighted_score": allocation.weighted_score,
                    }
                    for allocation in pipeline_result.allocations
                ],
                "summary": {
                    "total_orders": len(pipeline_result.allocations),
                    "allocated_orders": allocated_count,
                    "unallocated_orders": len(pipeline_result.allocations) - allocated_count,
                    "active_hard_rules": _active_hard_rule_names(config),
                    "fairness_escalation_event": fairness_event.to_dict() if fairness_event else None,
                    "conflict_resolution_report_hash": conflict_report_hash,
                },
                "aggregate_diagnostics": pipeline_result.aggregate_diagnostics,
            }

            response = AllocationResponse.model_validate(response_payload)
            idempotency_repository.save(x_idempotency_key, "completed", response.model_dump(), commit=False)
            session.commit()
        except Exception:
            reservation_store = get_reservation_store()
            for order_id in attempted_order_ids:
                reservation_store.release_all_for_order(order_id)
            raise

        reservation_store = get_reservation_store()
        for order_id, partner_id in reserved_pairs:
            reservation_store.release(partner_id, order_id)

        for allocation in pipeline_result.allocations:
            if allocation.partner_id is not None:
                tracker.record_assignment(allocation.partner_id)

        return response
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
