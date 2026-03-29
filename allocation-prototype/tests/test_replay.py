from __future__ import annotations

from allocation.engine.manifest import ManifestBuilder, build_input_snapshot
from allocation.engine.pipeline import DeterministicAllocationPipeline
from allocation.engine.replay import DeterministicReplayer
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
