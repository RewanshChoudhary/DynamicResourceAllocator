from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from allocation.domain.allocation import Allocation
from allocation.engine.manifest import SealedDecisionManifest
from allocation.persistence.models import (
    AllocationEventModel,
    IdempotencyRecordModel,
    InputSnapshotModel,
    SealedManifestModel,
)


class AllocationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def append_events(
        self,
        manifest_id: str,
        allocations: list[Allocation],
        trace_hash: str,
        config_version_hash: str,
        commit: bool = True,
    ) -> None:
        rows = []
        for allocation in allocations:
            rows.append(
                AllocationEventModel(
                    order_id=allocation.order_id,
                    manifest_id=manifest_id,
                    partner_id=allocation.partner_id,
                    status=allocation.status.value,
                    trace_hash=trace_hash,
                    config_version_hash=config_version_hash,
                )
            )
        self.session.add_all(rows)
        if commit:
            self.session.commit()

    def find_manifest_id_by_order(self, order_id: str) -> str | None:
        stmt = (
            select(AllocationEventModel.manifest_id)
            .where(AllocationEventModel.order_id == order_id)
            .order_by(AllocationEventModel.id.desc())
            .limit(1)
        )
        return self.session.execute(stmt).scalar_one_or_none()

    def get_rejection_summary(self, order_id: str) -> dict[str, Any] | None:
        stmt = (
            select(AllocationEventModel)
            .where(AllocationEventModel.order_id == order_id)
            .order_by(AllocationEventModel.id.desc())
            .limit(1)
        )
        event = self.session.execute(stmt).scalar_one_or_none()
        if event is None:
            return None

        manifest_row = self.session.get(SealedManifestModel, event.manifest_id)
        if manifest_row is None:
            return None

        manifest_payload = json.loads(manifest_row.manifest_json)
        order_trace = next(
            (
                trace
                for trace in manifest_payload.get("evaluation_trace", {}).get("orders", [])
                if trace.get("order_id") == order_id
            ),
            None,
        )
        if order_trace is None:
            return None

        hard_rule_failures: list[dict[str, str | None]] = []
        candidates = order_trace.get("candidates", [])
        for candidate in candidates:
            first_failure = next(
                (
                    hard_result
                    for hard_result in candidate.get("hard_results", [])
                    if not hard_result.get("passed", False)
                ),
                None,
            )
            if first_failure is None:
                continue

            hard_rule_failures.append(
                {
                    "rule": first_failure.get("rule"),
                    "partner_id": candidate.get("partner_id"),
                    "reason": first_failure.get("rationale"),
                }
            )

        return {
            "order_id": order_id,
            "allocation_status": event.status,
            "allocated_partner_id": event.partner_id,
            "hard_rule_failures": hard_rule_failures,
            "candidates_evaluated": len(candidates),
            "candidates_surviving_hard_rules": sum(
                1 for candidate in candidates if candidate.get("hard_passed", False)
            ),
        }


class ManifestRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def save(self, manifest: SealedDecisionManifest, commit: bool = True) -> None:
        row = SealedManifestModel(
            manifest_id=manifest.manifest_id,
            manifest_json=json.dumps(manifest.to_dict(), sort_keys=True, ensure_ascii=True),
            trace_hash=manifest.trace_hash,
            config_version_hash=manifest.config_version_hash,
            decided_at=datetime.fromisoformat(manifest.decided_at),
        )
        self.session.merge(row)
        if commit:
            self.session.commit()

    def get(self, manifest_id: str) -> SealedDecisionManifest | None:
        row = self.session.get(SealedManifestModel, manifest_id)
        if not row:
            return None
        return SealedDecisionManifest.from_dict(json.loads(row.manifest_json))

    def get_latest(self) -> SealedDecisionManifest | None:
        stmt = select(SealedManifestModel).order_by(SealedManifestModel.decided_at.desc()).limit(1)
        row = self.session.execute(stmt).scalar_one_or_none()
        if not row:
            return None
        return SealedDecisionManifest.from_dict(json.loads(row.manifest_json))


class InputSnapshotRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def save(self, input_hash: str, snapshot: dict[str, Any], commit: bool = True) -> None:
        row = InputSnapshotModel(
            input_hash=input_hash,
            snapshot_json=json.dumps(snapshot, sort_keys=True, ensure_ascii=True),
        )
        self.session.merge(row)
        if commit:
            self.session.commit()

    def get(self, input_hash: str) -> dict[str, Any] | None:
        row = self.session.get(InputSnapshotModel, input_hash)
        if not row:
            return None
        return json.loads(row.snapshot_json)


class IdempotencyRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, key: str) -> dict[str, Any] | None:
        row = self.session.get(IdempotencyRecordModel, key)
        if not row:
            return None
        return {
            "key": row.key,
            "status": row.status,
            "response": json.loads(row.response_json),
        }

    def save(self, key: str, status: str, response: dict[str, Any], commit: bool = True) -> None:
        row = IdempotencyRecordModel(
            key=key,
            status=status,
            response_json=json.dumps(response, sort_keys=True, ensure_ascii=True),
        )
        self.session.merge(row)
        if commit:
            self.session.commit()
