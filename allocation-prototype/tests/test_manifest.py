from __future__ import annotations

import copy
import os

from allocation.engine.manifest import ManifestBuilder, ManifestVerifier, SealedDecisionManifest, build_input_snapshot
from allocation.engine.pipeline import DeterministicAllocationPipeline
from allocation.persistence.config_versions import ConfigVersionStore
from allocation.rules.registry import build_rule_set


def test_manifest_verification_and_tamper_detection(session, sample_orders, sample_partners, base_config):
    os.environ["SDM_SIGNING_KEY"] = "test-key"

    config_store = ConfigVersionStore(session)
    config_version = config_store.put_if_absent(base_config)

    hard_rules, scoring_rules = build_rule_set(base_config)
    pipeline = DeterministicAllocationPipeline(hard_rules, scoring_rules)

    result = pipeline.evaluate(
        orders=sample_orders,
        partners=sample_partners,
        scoring_weights=base_config["weights"],
        partner_loads={p.partner_id: 0 for p in sample_partners},
        fairness_escalation_event=None,
        conflict_resolution_report_hash="conflict-hash",
    )

    snapshot = build_input_snapshot(sample_orders, sample_partners)
    manifest = ManifestBuilder(signing_key="test-key").build(
        pipeline_result=result,
        input_snapshot=snapshot,
        config_version_hash=config_version.config_version_hash,
        conflict_resolution_report_hash="conflict-hash",
    )

    verifier = ManifestVerifier(signing_key="test-key")
    report = verifier.verify(manifest, sample_orders, sample_partners, config_store)
    assert report.trace_match is True
    assert report.signature_valid is True
    assert report.reproduced_decision_matches_stored is True

    tampered_payload = copy.deepcopy(manifest.to_dict())
    tampered_payload["evaluation_trace"]["orders"][0]["selected_partner_id"] = "tampered"
    tampered_manifest = SealedDecisionManifest.from_dict(tampered_payload)

    tampered_report = verifier.verify(tampered_manifest, sample_orders, sample_partners, config_store)
    assert tampered_report.signature_valid is False
