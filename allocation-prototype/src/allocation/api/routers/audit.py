from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Request

from allocation.engine.pipeline import build_aggregate_diagnostics
from allocation.engine.manifest import ManifestVerifier
from allocation.engine.replay import DeterministicReplayer, snapshot_to_orders, snapshot_to_partners
from allocation.persistence.config_versions import ConfigVersionStore
from allocation.persistence.repository import AllocationRepository, InputSnapshotRepository, ManifestRepository


router = APIRouter()


@router.get("/allocations/diagnostics/latest")
def latest_diagnostics(request: Request):
    session = request.app.state.session_factory()
    try:
        manifest_repo = ManifestRepository(session)
        config_store = ConfigVersionStore(session)

        manifest = manifest_repo.get_latest()
        if manifest is None:
            raise HTTPException(status_code=404, detail="No stored allocation runs found")

        config_payload = config_store.get_by_hash(manifest.config_version_hash)
        hard_rule_names = []
        if config_payload is not None:
            hard_rule_names = [
                rule["name"]
                for rule in config_payload.get("config", {}).get("hard_rules", [])
                if rule.get("enabled", True)
            ]

        aggregate_diagnostics = build_aggregate_diagnostics(
            order_traces=manifest.evaluation_trace.get("orders", []),
            hard_rule_names=hard_rule_names,
        )
        return {
            "manifest_id": manifest.manifest_id,
            "decided_at": manifest.decided_at,
            "aggregate_diagnostics": aggregate_diagnostics,
        }
    finally:
        session.close()


def _manifest_from_order(order_id: str, request: Request):
    session = request.app.state.session_factory()
    allocation_repo = AllocationRepository(session)
    manifest_repo = ManifestRepository(session)

    manifest_id = allocation_repo.find_manifest_id_by_order(order_id)
    if manifest_id is None:
        session.close()
        raise HTTPException(status_code=404, detail=f"No manifest found for order {order_id}")

    manifest = manifest_repo.get(manifest_id)
    if manifest is None:
        session.close()
        raise HTTPException(status_code=404, detail=f"Manifest {manifest_id} not found")

    return session, manifest


@router.get("/allocations/{order_id}/manifest")
def get_manifest(order_id: str, request: Request):
    session, manifest = _manifest_from_order(order_id, request)
    try:
        return manifest.to_dict()
    finally:
        session.close()


@router.get("/allocations/{order_id}/manifest/verify")
def verify_manifest(order_id: str, request: Request):
    session, manifest = _manifest_from_order(order_id, request)
    try:
        input_repo = InputSnapshotRepository(session)
        config_store = ConfigVersionStore(session)

        snapshot = input_repo.get(manifest.input_hash)
        if snapshot is None:
            raise HTTPException(status_code=404, detail=f"Input snapshot {manifest.input_hash} not found")

        orders = snapshot_to_orders(snapshot)
        partners = snapshot_to_partners(snapshot)

        verifier = ManifestVerifier()
        report = verifier.verify(
            manifest=manifest,
            original_orders=orders,
            original_partners=partners,
            config_store=config_store,
        )
        return report.to_dict()
    finally:
        session.close()


@router.get("/allocations/{order_id}/replay")
def replay_manifest(order_id: str, request: Request):
    session, manifest = _manifest_from_order(order_id, request)
    try:
        manifest_repo = ManifestRepository(session)
        input_repo = InputSnapshotRepository(session)
        config_store = ConfigVersionStore(session)

        replayer = DeterministicReplayer(manifest_repo, input_repo, config_store)
        result = replayer.replay(manifest.manifest_id)
        return result.to_dict()
    finally:
        session.close()


@router.get("/allocations/{order_id}/trace")
def get_trace(order_id: str, request: Request):
    session, manifest = _manifest_from_order(order_id, request)
    try:
        return {
            "order_id": order_id,
            "trace": manifest.evaluation_trace,
            "formatted_trace_json": json.dumps(manifest.evaluation_trace, indent=2, sort_keys=True),
        }
    finally:
        session.close()


@router.get("/allocations/{order_id}/rejection-summary")
def get_rejection_summary(order_id: str, request: Request):
    session = request.app.state.session_factory()
    try:
        allocation_repo = AllocationRepository(session)
        summary = allocation_repo.get_rejection_summary(order_id)
        if summary is None:
            raise HTTPException(status_code=404, detail=f"No stored rejection summary found for order {order_id}")
        return summary
    finally:
        session.close()
