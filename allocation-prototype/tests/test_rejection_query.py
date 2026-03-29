from __future__ import annotations

from datetime import datetime, timezone

from allocation.domain.enums import VehicleType
from allocation.domain.order import Order
from allocation.domain.partner import DeliveryPartner
from allocation.engine.manifest import ManifestBuilder, build_input_snapshot
from allocation.engine.pipeline import DeterministicAllocationPipeline
from allocation.persistence.config_versions import ConfigVersionStore
from allocation.persistence.repository import AllocationRepository, InputSnapshotRepository, ManifestRepository
from allocation.rules.registry import build_rule_set


def test_get_rejection_summary_returns_failed_hard_rule_details(session, base_config):
    orders = [
        Order(
            order_id="ORD-UNALLOCATED",
            latitude=12.9716,
            longitude=77.5946,
            amount_paise=30000,
            requested_vehicle_type=VehicleType.CAR,
            created_at=datetime(2026, 2, 22, 12, 0, tzinfo=timezone.utc),
        )
    ]
    partners = [
        DeliveryPartner(
            partner_id="PT-BIKE",
            latitude=12.9717,
            longitude=77.5947,
            is_available=True,
            rating=4.8,
            vehicle_types=(VehicleType.BIKE,),
            active=True,
        )
    ]

    config_store = ConfigVersionStore(session)
    config_version = config_store.put_if_absent(base_config)
    hard_rules, scoring_rules = build_rule_set(base_config)
    pipeline = DeterministicAllocationPipeline(hard_rules, scoring_rules)

    result = pipeline.evaluate(
        orders=orders,
        partners=partners,
        scoring_weights=base_config["weights"],
        partner_loads={"PT-BIKE": 0},
        fairness_escalation_event=None,
        conflict_resolution_report_hash="rejection-query",
    )

    snapshot = build_input_snapshot(orders, partners)
    manifest = ManifestBuilder(signing_key="test-rejection").build(
        pipeline_result=result,
        input_snapshot=snapshot,
        config_version_hash=config_version.config_version_hash,
        conflict_resolution_report_hash="rejection-query",
    )

    manifest_repo = ManifestRepository(session)
    input_repo = InputSnapshotRepository(session)
    allocation_repo = AllocationRepository(session)

    manifest_repo.save(manifest)
    input_repo.save(manifest.input_hash, snapshot)
    allocation_repo.append_events(
        manifest.manifest_id,
        list(result.allocations),
        trace_hash=manifest.trace_hash,
        config_version_hash=manifest.config_version_hash,
    )

    summary = allocation_repo.get_rejection_summary("ORD-UNALLOCATED")

    assert summary is not None
    assert summary["allocation_status"] == "unallocated"
    assert summary["allocated_partner_id"] is None
    assert summary["hard_rule_failures"]
    assert summary["candidates_evaluated"] == 1
    assert summary["candidates_surviving_hard_rules"] == 0
