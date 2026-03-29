from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from common import new_session, store_config

from allocation.domain.enums import VehicleType
from allocation.domain.order import Order
from allocation.domain.partner import DeliveryPartner
from allocation.engine.manifest import ManifestBuilder, build_input_snapshot
from allocation.engine.pipeline import DeterministicAllocationPipeline
from allocation.persistence.config_versions import ConfigVersionStore
from allocation.persistence.repository import AllocationRepository, InputSnapshotRepository, ManifestRepository
from allocation.rules.registry import build_rule_set
from allocation.simulation.counterfactual import CounterfactualSimulator, SimulationSpec


if __name__ == "__main__":
    os.environ.setdefault("SDM_SIGNING_KEY", "demo-signing-key")

    config = {
        "hard_rules": [
            {"name": "availability", "enabled": True},
            {"name": "vehicle_type", "enabled": True},
            {"name": "max_distance", "enabled": True, "params": {"max_distance_km": 5.0}},
            {"name": "min_rating", "enabled": True, "params": {"min_rating": 3.5}},
        ],
        "scoring_rules": [
            {"name": "proximity_score", "enabled": True, "params": {"scale_km": 10.0}},
            {"name": "rating_score", "enabled": True},
            {"name": "fairness_score", "enabled": True},
        ],
        "weights": {
            "proximity_score": 0.45,
            "rating_score": 0.25,
            "fairness_score": 0.30,
        },
    }

    session, db_path = new_session("demo_counterfactual")

    try:
        config_version = store_config(session, config)
        hard_rules, scoring_rules = build_rule_set(config)
        pipeline = DeterministicAllocationPipeline(hard_rules, scoring_rules)

        orders = [
            Order(
                order_id="CF-1",
                latitude=12.9716,
                longitude=77.5946,
                amount_paise=25000,
                requested_vehicle_type=VehicleType.BIKE,
                created_at=datetime(2026, 2, 22, 11, 0, tzinfo=timezone.utc),
            ),
            Order(
                order_id="CF-2",
                latitude=12.9718,
                longitude=77.5948,
                amount_paise=22000,
                requested_vehicle_type=VehicleType.BIKE,
                created_at=datetime(2026, 2, 22, 11, 1, tzinfo=timezone.utc),
            ),
        ]

        partners = [
            DeliveryPartner(
                partner_id="P-CLOSE-WRONG-VEHICLE",
                latitude=12.9720,
                longitude=77.5950,
                is_available=True,
                rating=4.7,
                vehicle_types=(VehicleType.CAR,),
                active=True,
            ),
            DeliveryPartner(
                partner_id="P-FAR-BIKE",
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
            scoring_weights=config["weights"],
            partner_loads={p.partner_id: 0 for p in partners},
            fairness_escalation_event=None,
            conflict_resolution_report_hash="demo",
        )

        snapshot = build_input_snapshot(orders, partners)
        manifest = ManifestBuilder(signing_key=os.environ["SDM_SIGNING_KEY"]).build(
            pipeline_result=baseline,
            input_snapshot=snapshot,
            config_version_hash=config_version.config_version_hash,
            conflict_resolution_report_hash="demo",
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

        simulator = CounterfactualSimulator(manifest_repo, input_repo, ConfigVersionStore(session))
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

        simulation = simulator.simulate(manifest.manifest_id, spec)

        print("Baseline allocations:")
        print(
            json.dumps(
                [
                    {
                        "order_id": a.order_id,
                        "partner_id": a.partner_id,
                        "status": a.status.value,
                    }
                    for a in baseline.allocations
                ],
                indent=2,
                sort_keys=True,
            )
        )
        print("Counterfactual result (distance threshold 3km):")
        print(json.dumps(simulation.to_dict(), indent=2, sort_keys=True))
        print(f"Demo DB used: {db_path}")
    finally:
        session.close()
