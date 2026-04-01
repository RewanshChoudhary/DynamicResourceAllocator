from __future__ import annotations

from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
import tomllib
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import text

from allocation.engine.manifest import ManifestVerifier
from allocation.engine.replay import DeterministicReplayer, snapshot_to_orders, snapshot_to_partners
from allocation.persistence.config_versions import ConfigVersionStore
from allocation.persistence.repository import AllocationRepository, InputSnapshotRepository, ManifestRepository


router = APIRouter()
PROJECT_ROOT = Path(__file__).resolve().parents[4]


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


def _manifest_by_id(manifest_id: str, request: Request):
    session = request.app.state.session_factory()
    manifest = ManifestRepository(session).get(manifest_id)
    if manifest is None:
        session.close()
        raise HTTPException(status_code=404, detail=f"Manifest {manifest_id} not found")
    return session, manifest


def _active_rules(config_payload: dict[str, Any] | None) -> list[str]:
    if config_payload is None:
        return []

    config = config_payload.get("config", {})
    active_hard_rules = [
        rule["name"] for rule in config.get("hard_rules", []) if rule.get("enabled", True)
    ]
    active_scoring_rules = [
        rule["name"] for rule in config.get("scoring_rules", []) if rule.get("enabled", True)
    ]
    return active_hard_rules + active_scoring_rules


def _trace_allocations(trace: dict[str, Any]) -> list[dict[str, Any]]:
    allocations = [
        {
            "order_id": order_trace.get("order_id"),
            "partner_id": order_trace.get("selected_partner_id"),
        }
        for order_trace in trace.get("orders", [])
    ]
    return sorted(allocations, key=lambda item: item["order_id"] or "")


def _project_version() -> str:
    try:
        return metadata.version("allocation-prototype")
    except metadata.PackageNotFoundError:
        pyproject = PROJECT_ROOT / "pyproject.toml"
        if not pyproject.exists():
            return "unknown"
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        return str(data.get("project", {}).get("version", "unknown"))


@router.get("/audit/manifest/{order_id}")
def audit_manifest(order_id: str, request: Request):
    session, manifest = _manifest_from_order(order_id, request)
    try:
        return manifest.to_dict()
    finally:
        session.close()


@router.get("/audit/trace/{order_id}")
def audit_trace(order_id: str, request: Request):
    session, manifest = _manifest_from_order(order_id, request)
    try:
        return {
            "order_id": order_id,
            "trace": manifest.evaluation_trace,
        }
    finally:
        session.close()


@router.get("/audit/rejections/{order_id}")
def audit_rejections(order_id: str, request: Request):
    session = request.app.state.session_factory()
    try:
        summary = AllocationRepository(session).get_rejection_summary(order_id)
        if summary is None:
            raise HTTPException(status_code=404, detail=f"No stored rejection summary found for order {order_id}")
        return summary
    finally:
        session.close()


@router.get("/audit/verify/{manifest_id}")
def audit_verify(manifest_id: str, request: Request):
    session, manifest = _manifest_by_id(manifest_id, request)
    try:
        input_repo = InputSnapshotRepository(session)
        config_store = ConfigVersionStore(session)

        snapshot = input_repo.get(manifest.input_hash)
        if snapshot is None:
            raise HTTPException(status_code=404, detail=f"Input snapshot {manifest.input_hash} not found")

        report = ManifestVerifier().verify(
            manifest=manifest,
            original_orders=snapshot_to_orders(snapshot),
            original_partners=snapshot_to_partners(snapshot),
            config_store=config_store,
        )
        status = "VERIFIED"
        if not (
            report.trace_match
            and report.signature_valid
            and report.reproduced_decision_matches_stored
        ):
            status = "TAMPERED"

        return {
            "manifest_id": manifest_id,
            "verified_at": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "trace_match": report.trace_match,
            "signature_valid": report.signature_valid,
            "reproduced_decision_matches_stored": report.reproduced_decision_matches_stored,
            "details": report.details,
        }
    finally:
        session.close()


@router.get("/audit/replay/{manifest_id}")
def audit_replay(manifest_id: str, request: Request):
    session, _manifest = _manifest_by_id(manifest_id, request)
    try:
        replayer = DeterministicReplayer(
            ManifestRepository(session),
            InputSnapshotRepository(session),
            ConfigVersionStore(session),
        )
        replay = replayer.replay(manifest_id)
        raw_replay_response = replay.to_dict()
        status = "SUCCESS" if replay.matched and replay.trace_hash_identical else "MISMATCH"
        return {
            "manifest_id": manifest_id,
            "status": status,
            "original_allocations": _trace_allocations(replay.original_trace),
            "replayed_allocations": _trace_allocations(replay.replayed_trace),
            "raw_replay_response": raw_replay_response,
        }
    finally:
        session.close()


@router.get("/audit/diagnostics")
def audit_diagnostics(request: Request):
    session = request.app.state.session_factory()
    try:
        manifest_repo = ManifestRepository(session)
        config_store = ConfigVersionStore(session)

        manifest = manifest_repo.get_latest()
        if manifest is None:
            raise HTTPException(status_code=404, detail="No stored allocation runs found")

        order_traces = manifest.evaluation_trace.get("orders", [])
        allocated_scores = [
            order_trace.get("selected_weighted_score")
            for order_trace in order_traces
            if order_trace.get("selected_partner_id") is not None
            and order_trace.get("selected_weighted_score") is not None
        ]
        config_payload = config_store.get_by_hash(manifest.config_version_hash)

        fairness_gini = None

        return {
            "manifest_id": manifest.manifest_id,
            "decided_at": manifest.decided_at,
            "total_allocations": sum(
                1 for order_trace in order_traces if order_trace.get("selected_partner_id") is not None
            ),
            "total_unallocated": sum(
                1 for order_trace in order_traces if order_trace.get("selected_partner_id") is None
            ),
            "avg_score": round(sum(allocated_scores) / len(allocated_scores), 6)
            if allocated_scores
            else None,
            "fairness_gini": fairness_gini,
            "active_rules": _active_rules(config_payload),
        }
    finally:
        session.close()


@router.get("/diagnostics/runtime")
def runtime_diagnostics(request: Request):
    session = request.app.state.session_factory()
    db_connected = False
    try:
        session.execute(text("SELECT 1"))
        db_connected = True
    except Exception:
        db_connected = False
    finally:
        session.close()

    return {
        "db_connected": db_connected,
        "version": _project_version(),
    }
