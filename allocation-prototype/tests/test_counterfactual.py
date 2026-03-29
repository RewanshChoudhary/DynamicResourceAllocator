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
from allocation.simulation.counterfactual import CounterfactualSimulator, SimulationSpec


def test_counterfactual_distance_mutation_changes_outcome(session, base_config):
    config_store = ConfigVersionStore(session)
    config_version = config_store.put_if_absent(base_config)

    hard_rules, scoring_rules = build_rule_set(base_config)
    pipeline = DeterministicAllocationPipeline(hard_rules, scoring_rules)

    orders = [
        Order(
            order_id="CF-ORD-1",
            latitude=12.9716,
            longitude=77.5946,
            amount_paise=20000,
            requested_vehicle_type=VehicleType.BIKE,
            created_at=datetime(2026, 2, 22, 12, 10, tzinfo=timezone.utc),
        )
    ]

    partners = [
        DeliveryPartner(
            partner_id="NEAR-WRONG-VEHICLE",
            latitude=12.9717,
            longitude=77.5947,
            is_available=True,
            rating=4.8,
            vehicle_types=(VehicleType.CAR,),
            active=True,
        ),
        DeliveryPartner(
            partner_id="FAR-BIKE",
            latitude=13.0000,
            longitude=77.6100,
            is_available=True,
            rating=4.5,
            vehicle_types=(VehicleType.BIKE,),
            active=True,
        ),
    ]

    baseline = pipeline.evaluate(
        orders=orders,
        partners=partners,
        scoring_weights=base_config["weights"],
        partner_loads={p.partner_id: 0 for p in partners},
        fairness_escalation_event=None,
        conflict_resolution_report_hash="hash",
    )

    snapshot = build_input_snapshot(orders, partners)
    manifest = ManifestBuilder(signing_key="test-counterfactual").build(
        pipeline_result=baseline,
        input_snapshot=snapshot,
        config_version_hash=config_version.config_version_hash,
        conflict_resolution_report_hash="hash",
    )

    manifest_repo = ManifestRepository(session)
    input_repo = InputSnapshotRepository(session)
    allocation_repo = AllocationRepository(session)

    manifest_repo.save(manifest)
    input_repo.save(manifest.input_hash, snapshot)
    allocation_repo.append_events(
        manifest.manifest_id,
        list(baseline.allocations),
        trace_hash=manifest.trace_hash,
        config_version_hash=manifest.config_version_hash,
    )

    simulator = CounterfactualSimulator(manifest_repo, input_repo, config_store)
    spec = SimulationSpec.model_validate(
        {
            "mutations": [
                {
                    "mutation_type": "rule_parameter",
                    "rule_name": "max_distance",
                    "parameter": "max_distance_km",
                    "new_value": 3.0,
                }
            ]
        }
    )

    result = simulator.simulate(manifest.manifest_id, spec)

    assert result.counterfactual_summary["total_changed_orders"] >= 1
    assert any(item["hypothetical_partner"] is None for item in result.trace_diff)
