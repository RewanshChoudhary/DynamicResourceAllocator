from __future__ import annotations

import json
import os

from common import load_default_config, make_orders, make_partners, new_session, store_config

from allocation.engine.manifest import ManifestBuilder, build_input_snapshot
from allocation.engine.pipeline import DeterministicAllocationPipeline
from allocation.engine.replay import DeterministicReplayer
from allocation.persistence.repository import AllocationRepository, InputSnapshotRepository, ManifestRepository
from allocation.persistence.config_versions import ConfigVersionStore
from allocation.rules.registry import build_rule_set


if __name__ == "__main__":
    os.environ.setdefault("SDM_SIGNING_KEY", "demo-signing-key")

    config, conflict_report_hash = load_default_config()
    session, db_path = new_session("demo_replay")

    try:
        config_version = store_config(session, config)
        hard_rules, scoring_rules = build_rule_set(config)
        pipeline = DeterministicAllocationPipeline(hard_rules, scoring_rules)

        orders = make_orders()
        partners = make_partners()

        result = pipeline.evaluate(
            orders=orders,
            partners=partners,
            scoring_weights=config["weights"],
            partner_loads={partner.partner_id: 0 for partner in partners},
            fairness_escalation_event=None,
            conflict_resolution_report_hash=conflict_report_hash,
        )

        snapshot = build_input_snapshot(orders, partners)
        manifest = ManifestBuilder(signing_key=os.environ["SDM_SIGNING_KEY"]).build(
            pipeline_result=result,
            input_snapshot=snapshot,
            config_version_hash=config_version.config_version_hash,
            conflict_resolution_report_hash=conflict_report_hash,
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

        replayer = DeterministicReplayer(manifest_repo, input_repo, ConfigVersionStore(session))
        replay = replayer.replay(manifest.manifest_id)

        print(json.dumps(replay.to_dict(), indent=2, sort_keys=True))
        print(f"Demo DB used: {db_path}")
    finally:
        session.close()
