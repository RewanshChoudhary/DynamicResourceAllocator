from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from allocation.domain.order import Order
from allocation.domain.partner import DeliveryPartner
from allocation.engine.loads import initial_partner_loads_for_replay
from allocation.engine.pipeline import DeterministicAllocationPipeline, EvaluationTrace, PipelineResult
from allocation.rules.registry import build_rule_set


def canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")


def sha256_hex(payload_bytes: bytes) -> str:
    return hashlib.sha256(payload_bytes).hexdigest()


def fairness_event_json(fairness_event: dict[str, Any] | None) -> str:
    if fairness_event is None:
        return ""
    return json.dumps(fairness_event, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def build_manifest_signing_payload(
    trace_hash: str,
    input_hash: str,
    config_version_hash: str,
    conflict_resolution_report_hash: str | None,
    fairness_event: dict[str, Any] | None,
) -> str:
    return (
        trace_hash
        + input_hash
        + config_version_hash
        + (conflict_resolution_report_hash or "")
        + fairness_event_json(fairness_event)
    )


def compute_hmac_signature(signing_key: str, signing_payload: str) -> str:
    return hmac.new(
        signing_key.encode("utf-8"),
        signing_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def serialize_orders(orders: list[Order]) -> list[dict[str, Any]]:
    serialized = []
    for order in sorted(orders, key=lambda x: x.order_id):
        serialized.append(
            {
                "order_id": order.order_id,
                "latitude": round(order.latitude, 8),
                "longitude": round(order.longitude, 8),
                "amount_paise": int(order.amount_paise),
                "requested_vehicle_type": order.requested_vehicle_type.value,
                "created_at": order.created_at.astimezone(timezone.utc).isoformat(),
            }
        )
    return serialized


def serialize_partners(partners: list[DeliveryPartner]) -> list[dict[str, Any]]:
    serialized = []
    for partner in sorted(partners, key=lambda x: x.partner_id):
        serialized.append(
            {
                "partner_id": partner.partner_id,
                "latitude": round(partner.latitude, 8),
                "longitude": round(partner.longitude, 8),
                "is_available": bool(partner.is_available),
                "rating": round(partner.rating, 8),
                "vehicle_types": sorted(v.value for v in partner.vehicle_types),
                "active": bool(partner.active),
            }
        )
    return serialized


def build_input_snapshot(orders: list[Order], partners: list[DeliveryPartner]) -> dict[str, Any]:
    return {
        "orders": serialize_orders(orders),
        "partners": serialize_partners(partners),
    }


def trace_to_payload(trace: EvaluationTrace) -> dict[str, Any]:
    return trace.to_dict()


@dataclass(frozen=True)
class SealedDecisionManifest:
    manifest_id: str
    decided_at: str
    trace_hash: str
    input_hash: str
    config_version_hash: str
    fairness_escalation_event: dict[str, Any] | None
    conflict_resolution_report_hash: str
    manifest_signature: str
    evaluation_trace: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "manifest_id": self.manifest_id,
            "decided_at": self.decided_at,
            "trace_hash": self.trace_hash,
            "input_hash": self.input_hash,
            "config_version_hash": self.config_version_hash,
            "fairness_escalation_event": self.fairness_escalation_event,
            "conflict_resolution_report_hash": self.conflict_resolution_report_hash,
            "manifest_signature": self.manifest_signature,
            "evaluation_trace": self.evaluation_trace,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SealedDecisionManifest":
        return cls(
            manifest_id=payload["manifest_id"],
            decided_at=payload["decided_at"],
            trace_hash=payload["trace_hash"],
            input_hash=payload["input_hash"],
            config_version_hash=payload["config_version_hash"],
            fairness_escalation_event=payload.get("fairness_escalation_event"),
            conflict_resolution_report_hash=payload["conflict_resolution_report_hash"],
            manifest_signature=payload["manifest_signature"],
            evaluation_trace=payload["evaluation_trace"],
        )


@dataclass(frozen=True)
class VerificationReport:
    trace_match: bool
    signature_valid: bool
    reproduced_decision_matches_stored: bool
    details: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "trace_match": self.trace_match,
            "signature_valid": self.signature_valid,
            "reproduced_decision_matches_stored": self.reproduced_decision_matches_stored,
            "details": self.details,
        }


class ManifestBuilder:
    def __init__(self, signing_key: str | None = None) -> None:
        self.signing_key = signing_key or os.getenv("SDM_SIGNING_KEY", "dev-signing-key")

    def build(
        self,
        pipeline_result: PipelineResult,
        input_snapshot: dict[str, Any],
        config_version_hash: str,
        conflict_resolution_report_hash: str,
    ) -> SealedDecisionManifest:
        trace_payload = trace_to_payload(pipeline_result.trace)
        trace_hash = sha256_hex(canonical_json_bytes(trace_payload))

        input_hash = sha256_hex(canonical_json_bytes(input_snapshot))

        fairness_event = pipeline_result.trace.fairness_escalation_event
        signing_payload = build_manifest_signing_payload(
            trace_hash=trace_hash,
            input_hash=input_hash,
            config_version_hash=config_version_hash,
            conflict_resolution_report_hash=conflict_resolution_report_hash,
            fairness_event=fairness_event,
        )
        signature = compute_hmac_signature(self.signing_key, signing_payload)

        return SealedDecisionManifest(
            manifest_id=str(uuid4()),
            decided_at=datetime.now(timezone.utc).isoformat(),
            trace_hash=trace_hash,
            input_hash=input_hash,
            config_version_hash=config_version_hash,
            fairness_escalation_event=fairness_event,
            conflict_resolution_report_hash=conflict_resolution_report_hash,
            manifest_signature=signature,
            evaluation_trace=trace_payload,
        )


class ManifestVerifier:
    def __init__(self, signing_key: str | None = None) -> None:
        self.signing_key = signing_key or os.getenv("SDM_SIGNING_KEY", "dev-signing-key")

    def _compute_signature(self, manifest: SealedDecisionManifest) -> str:
        signing_payload = build_manifest_signing_payload(
            trace_hash=manifest.trace_hash,
            input_hash=manifest.input_hash,
            config_version_hash=manifest.config_version_hash,
            conflict_resolution_report_hash=manifest.conflict_resolution_report_hash,
            fairness_event=manifest.fairness_escalation_event,
        )
        return compute_hmac_signature(self.signing_key, signing_payload)

    def verify(
        self,
        manifest: SealedDecisionManifest,
        original_orders: list[Order],
        original_partners: list[DeliveryPartner],
        config_store: Any,
    ) -> VerificationReport:
        config_payload = config_store.get_by_hash(manifest.config_version_hash)
        if config_payload is None:
            return VerificationReport(
                trace_match=False,
                signature_valid=False,
                reproduced_decision_matches_stored=False,
                details=f"No historical config for hash={manifest.config_version_hash}",
            )

        historical_config = config_payload["config"]
        hard_rules, scoring_rules = build_rule_set(historical_config)

        pipeline = DeterministicAllocationPipeline(hard_rules=hard_rules, scoring_rules=scoring_rules)

        replayed_result = pipeline.evaluate(
            orders=original_orders,
            partners=original_partners,
            scoring_weights=manifest.evaluation_trace.get("scoring_weights", {}),
            partner_loads=initial_partner_loads_for_replay(manifest.evaluation_trace, original_partners),
            fairness_escalation_event=manifest.fairness_escalation_event,
            conflict_resolution_report_hash=manifest.conflict_resolution_report_hash,
        )

        stored_trace_hash = sha256_hex(canonical_json_bytes(manifest.evaluation_trace))
        replayed_trace_payload = replayed_result.trace.to_dict()
        replayed_trace_hash = sha256_hex(canonical_json_bytes(replayed_trace_payload))
        trace_match = replayed_trace_hash == manifest.trace_hash and stored_trace_hash == manifest.trace_hash

        recomputed_input_hash = sha256_hex(
            canonical_json_bytes(build_input_snapshot(original_orders, original_partners))
        )
        internal_hashes_valid = (
            stored_trace_hash == manifest.trace_hash and recomputed_input_hash == manifest.input_hash
        )
        signature_valid = (
            hmac.compare_digest(self._compute_signature(manifest), manifest.manifest_signature)
            and internal_hashes_valid
        )

        stored_decisions = {
            order_trace["order_id"]: order_trace["selected_partner_id"]
            for order_trace in manifest.evaluation_trace.get("orders", [])
        }
        replayed_decisions = {
            order_trace["order_id"]: order_trace["selected_partner_id"]
            for order_trace in replayed_trace_payload.get("orders", [])
        }
        decisions_match = stored_decisions == replayed_decisions

        details = "ok"
        if not trace_match:
            details = "trace hash mismatch"
        elif not signature_valid:
            details = "signature mismatch"
        elif not decisions_match:
            details = "reproduced decisions mismatch"

        return VerificationReport(
            trace_match=trace_match,
            signature_valid=signature_valid,
            reproduced_decision_matches_stored=decisions_match,
            details=details,
        )
