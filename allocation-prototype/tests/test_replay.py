from __future__ import annotations

from allocation.engine.manifest import ManifestBuilder, build_input_snapshot
from allocation.engine.pipeline import DeterministicAllocationPipeline
from allocation.engine.replay import DeterministicReplayer, snapshot_to_orders, snapshot_to_partners
from allocation.persistence.config_versions import ConfigVersionStore
from allocation.persistence.repository import AllocationRepository, InputSnapshotRepository, ManifestRepository
from allocation.rules.registry import build_rule_set


def test_deterministic_replay_matches(session, sample_orders, sample_partners, base_config):
    config_store = ConfigVersionStore(session)
    config_version = config_store.put_if_absent(base_config)

    hard_rules, scoring_rules = build_rule_set(base_config)
    pipeline = DeterministicAllocationPipeline(hard_rules, scoring_rules)

    partner_loads = {"PT-1": 5, "PT-2": 0}
    result = pipeline.evaluate(
        orders=sample_orders,
        partners=sample_partners,
        scoring_weights=base_config["weights"],
        partner_loads=partner_loads,
        fairness_escalation_event=None,
        conflict_resolution_report_hash="report-hash",
    )

    snapshot = build_input_snapshot(sample_orders, sample_partners)
    manifest = ManifestBuilder(signing_key="test-replay").build(
        pipeline_result=result,
        input_snapshot=snapshot,
        config_version_hash=config_version.config_version_hash,
        conflict_resolution_report_hash="report-hash",
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

    replayer = DeterministicReplayer(manifest_repo, input_repo, config_store)
    replay = replayer.replay(manifest.manifest_id)

    assert result.trace.initial_partner_loads == partner_loads
    assert replay.matched is True
    assert replay.trace_hash_identical is True
    assert replay.divergence_point_if_any is None


def test_snapshot_round_trip_preserves_additive_order_and_partner_fields():
    from datetime import datetime, timezone

    from allocation.domain.enums import VehicleType
    from allocation.domain.order import Order
    from allocation.domain.partner import DeliveryPartner

    orders = [
        Order(
            order_id="ORD-RICH-1",
            latitude=12.9716,
            longitude=77.5946,
            amount_paise=24000,
            requested_vehicle_type=VehicleType.BIKE,
            created_at=datetime(2026, 2, 22, 12, 0, tzinfo=timezone.utc),
            restaurant_latitude=12.9716,
            restaurant_longitude=77.5946,
            delivery_latitude=12.9816,
            delivery_longitude=77.6046,
            weather_condition="Stormy",
            traffic_density="Jam",
            order_type="Meal",
            priority="NORMAL",
            vehicle_required_raw="MOTORCYCLE",
        )
    ]
    partners = [
        DeliveryPartner(
            partner_id="PT-RICH-1",
            latitude=12.9717,
            longitude=77.5947,
            is_available=True,
            rating=4.8,
            vehicle_types=(VehicleType.BIKE,),
            active=True,
            name="PT-RICH-1",
            current_load=2,
            vehicle_condition=0,
            avg_time_taken_min=18,
            city="Urban",
            raw_vehicle_type="MOTORCYCLE",
        )
    ]

    snapshot = build_input_snapshot(orders, partners)
    restored_order = snapshot_to_orders(snapshot)[0]
    restored_partner = snapshot_to_partners(snapshot)[0]

    assert restored_order.weather_condition == "Stormy"
    assert restored_order.traffic_density == "Jam"
    assert restored_order.vehicle_required_raw == "MOTORCYCLE"
    assert restored_partner.vehicle_condition == 0
    assert restored_partner.avg_time_taken_min == 18
    assert restored_partner.raw_vehicle_type == "MOTORCYCLE"
