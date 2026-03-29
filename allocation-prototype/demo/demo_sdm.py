from __future__ import annotations

import json
import os

from common import load_default_config, make_orders, make_partners, new_session, store_config

from allocation.engine.manifest import ManifestBuilder, ManifestVerifier, SealedDecisionManifest, build_input_snapshot
from allocation.engine.pipeline import DeterministicAllocationPipeline
from allocation.persistence.config_versions import ConfigVersionStore
from allocation.rules.registry import build_rule_set


if __name__ == "__main__":
    os.environ.setdefault("SDM_SIGNING_KEY", "demo-signing-key")

    config, conflict_report_hash = load_default_config()
    session, db_path = new_session("demo_sdm")

    try:
        config_version = store_config(session, config)

        hard_rules, scoring_rules = build_rule_set(config)
        pipeline = DeterministicAllocationPipeline(hard_rules, scoring_rules)

        orders = make_orders()
        partners = make_partners()
        pipeline_result = pipeline.evaluate(
            orders=orders,
            partners=partners,
            scoring_weights=config["weights"],
            partner_loads={partner.partner_id: 0 for partner in partners},
            fairness_escalation_event=None,
            conflict_resolution_report_hash=conflict_report_hash,
        )

        snapshot = build_input_snapshot(orders, partners)
        manifest_builder = ManifestBuilder(signing_key=os.environ["SDM_SIGNING_KEY"])
        manifest = manifest_builder.build(
            pipeline_result=pipeline_result,
            input_snapshot=snapshot,
            config_version_hash=config_version.config_version_hash,
            conflict_resolution_report_hash=conflict_report_hash,
        )

        verifier = ManifestVerifier(signing_key=os.environ["SDM_SIGNING_KEY"])
        config_store = ConfigVersionStore(session)
        report = verifier.verify(manifest, orders, partners, config_store=config_store)
        print("Original manifest verification:")
        print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
        print("Aggregate diagnostics:")
        print(json.dumps(pipeline_result.aggregate_diagnostics, indent=2, sort_keys=True))

        tampered = manifest.to_dict()
        tampered["evaluation_trace"]["orders"][0]["candidates"][0]["weighted_score"] = 0.999999
        tampered_manifest = SealedDecisionManifest.from_dict(tampered)
        tampered_report = verifier.verify(
            tampered_manifest,
            orders,
            partners,
            config_store=config_store,
        )

        print("Tampered manifest verification:")
        print(json.dumps(tampered_report.to_dict(), indent=2, sort_keys=True))
        print(f"Demo DB used: {db_path}")
    finally:
        session.close()
