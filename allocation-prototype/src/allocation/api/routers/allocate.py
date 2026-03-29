from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Request

from allocation.api.schemas import AllocationRequest, AllocationResponse
from allocation.config.loader import ConfigLoader
from allocation.domain.order import Order
from allocation.domain.partner import DeliveryPartner
from allocation.engine.manifest import ManifestBuilder, build_input_snapshot
from allocation.engine.pipeline import DeterministicAllocationPipeline
from allocation.fairness.gini import FairnessEnforcer
from allocation.persistence.config_versions import ConfigVersionStore
from allocation.persistence.repository import (
    AllocationRepository,
    IdempotencyRepository,
    InputSnapshotRepository,
    ManifestRepository,
)
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

        input_snapshot = build_input_snapshot(orders, partners)
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
        allocation_repository.append_events(manifest.manifest_id, list(pipeline_result.allocations), commit=False)

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
                "fairness_escalation_event": fairness_event.to_dict() if fairness_event else None,
                "conflict_resolution_report_hash": conflict_report_hash,
            },
            "aggregate_diagnostics": pipeline_result.aggregate_diagnostics,
        }

        response = AllocationResponse.model_validate(response_payload)
        idempotency_repository.save(x_idempotency_key, "completed", response.model_dump(), commit=False)
        session.commit()

        for allocation in pipeline_result.allocations:
            if allocation.partner_id is not None:
                tracker.record_assignment(allocation.partner_id)

        return response
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
