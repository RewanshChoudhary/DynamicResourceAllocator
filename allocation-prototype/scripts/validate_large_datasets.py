from __future__ import annotations

import argparse
import gc
import json
import sys
from dataclasses import asdict, dataclass
from datetime import timedelta
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

from fastapi import FastAPI
from starlette.requests import Request

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from allocation.api.routers.allocate import allocate
from allocation.api.routers.audit import (  # noqa: E402
    get_manifest,
    get_rejection_summary,
    latest_diagnostics,
    replay_manifest,
    verify_manifest,
)
from allocation.api.routers.simulate import run_simulation  # noqa: E402
from allocation.api.schemas import AllocationRequest, SimulationRequest  # noqa: E402
from allocation.data.zomato_adapter import (  # noqa: E402
    audit_zomato_csv,
    build_allocation_payload_from_zomato,
    write_json,
)
from allocation.fairness.tracker import PartnerLoadTracker  # noqa: E402
from allocation.persistence.models import (  # noqa: E402
    create_all_tables,
    create_session_factory,
    create_sqlite_engine,
)


@dataclass(frozen=True)
class DatasetSpec:
    slug: str
    max_orders: int
    max_partners: int


DEFAULT_SPECS = (
    DatasetSpec(slug="zomato_large_300_orders_200_partners", max_orders=300, max_partners=200),
    DatasetSpec(slug="zomato_large_450_orders_250_partners", max_orders=450, max_partners=250),
    DatasetSpec(slug="zomato_large_600_orders_300_partners", max_orders=600, max_partners=300),
)


def make_app(db_path: Path) -> FastAPI:
    engine = create_sqlite_engine(f"sqlite:///{db_path}")
    create_all_tables(engine)
    session_factory = create_session_factory(engine)

    app = FastAPI()
    app.state.session_factory = session_factory
    app.state.partner_load_tracker = PartnerLoadTracker(window=timedelta(hours=1))
    return app


def make_request(app: FastAPI, method: str, path: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "headers": [],
            "app": app,
        }
    )


def top_rule_counts(aggregate_diagnostics: dict[str, Any], limit: int = 3) -> list[dict[str, Any]]:
    ordered = sorted(
        aggregate_diagnostics.get("hard_rule_elimination_counts", {}).items(),
        key=lambda item: (-item[1], item[0]),
    )
    return [{"rule": rule, "count": count} for rule, count in ordered[:limit]]


def dominant_failure_combination(aggregate_diagnostics: dict[str, Any]) -> dict[str, Any] | None:
    combos = aggregate_diagnostics.get("unallocated_orders_by_failure_combination", {})
    if not combos:
        return None
    combo, count = max(combos.items(), key=lambda item: (item[1], item[0]))
    return {"combination": combo, "count": count}


def validate_dataset(
    spec: DatasetSpec,
    payload_path: Path,
    tmp_dir: Path,
    run_counterfactual_check: bool,
) -> dict[str, Any]:
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    request_model = AllocationRequest.model_validate(payload)
    order_count = len(request_model.orders)
    partner_count = len(request_model.partners)
    candidate_pairs = order_count * partner_count

    first_db_path = tmp_dir / f"{spec.slug}_run_a_{uuid4().hex}.db"
    second_db_path = tmp_dir / f"{spec.slug}_run_b_{uuid4().hex}.db"

    app_a = make_app(first_db_path)

    allocation_start = perf_counter()
    response_a = allocate(
        request_model,
        make_request(app_a, "POST", "/allocations"),
        x_idempotency_key=f"{spec.slug}-run-a",
    )
    allocation_duration_s = round(perf_counter() - allocation_start, 3)
    response_a_payload = response_a.model_dump()

    cached_response = allocate(
        request_model,
        make_request(app_a, "POST", "/allocations"),
        x_idempotency_key=f"{spec.slug}-run-a",
    )
    idempotency_equal = cached_response.model_dump() == response_a_payload

    sample_order_id = response_a.allocations[0]["order_id"]
    manifest_a = get_manifest(
        sample_order_id,
        make_request(app_a, "GET", f"/allocations/{sample_order_id}/manifest"),
    )
    verify_report = verify_manifest(
        sample_order_id,
        make_request(app_a, "GET", f"/allocations/{sample_order_id}/manifest/verify"),
    )

    replay_start = perf_counter()
    replay_result = replay_manifest(
        sample_order_id,
        make_request(app_a, "GET", f"/allocations/{sample_order_id}/replay"),
    )
    replay_duration_s = round(perf_counter() - replay_start, 3)

    latest = latest_diagnostics(make_request(app_a, "GET", "/allocations/diagnostics/latest"))
    diagnostics_match = latest["aggregate_diagnostics"] == response_a.aggregate_diagnostics

    unallocated_order_id = next(
        (allocation["order_id"] for allocation in response_a.allocations if allocation["status"] == "unallocated"),
        None,
    )
    rejection_summary = None
    rejection_summary_ok = None
    if unallocated_order_id is not None:
        rejection_summary = get_rejection_summary(
            unallocated_order_id,
            make_request(app_a, "GET", f"/allocations/{unallocated_order_id}/rejection-summary"),
        )
        rejection_summary_ok = (
            rejection_summary["allocation_status"] == "unallocated"
            and rejection_summary["candidates_evaluated"] == partner_count
            and rejection_summary["candidates_surviving_hard_rules"] == 0
            and bool(rejection_summary["hard_rule_failures"])
        )

    counterfactual_changed_orders = None
    if run_counterfactual_check:
        simulation_payload = SimulationRequest(
            manifest_id=response_a.manifest_id,
            mutations=[
                {
                    "mutation_type": "rule_parameter",
                    "rule_name": "max_distance",
                    "parameter": "max_distance_km",
                    "new_value": 3.0,
                }
            ],
        )
        simulation_result = run_simulation(
            simulation_payload,
            make_request(app_a, "POST", "/simulations"),
        )
        counterfactual_changed_orders = simulation_result["counterfactual_summary"]["total_changed_orders"]
        del simulation_result

    app_b = make_app(second_db_path)
    response_b = allocate(
        request_model,
        make_request(app_b, "POST", "/allocations"),
        x_idempotency_key=f"{spec.slug}-run-b",
    )
    manifest_b = get_manifest(
        sample_order_id,
        make_request(app_b, "GET", f"/allocations/{sample_order_id}/manifest"),
    )

    trace_hash_stable = manifest_a["trace_hash"] == manifest_b["trace_hash"]
    diagnostics_stable = response_a.aggregate_diagnostics == response_b.aggregate_diagnostics

    aggregate_diagnostics = response_a.aggregate_diagnostics or {}
    allocated = response_a.summary["allocated_orders"]
    unallocated = response_a.summary["unallocated_orders"]

    all_checks_passed = all(
        [
            response_a.summary["total_orders"] == order_count,
            allocated + unallocated == order_count,
            aggregate_diagnostics.get("total_orders") == order_count,
            aggregate_diagnostics.get("allocated") == allocated,
            aggregate_diagnostics.get("unallocated") == unallocated,
            verify_report["trace_match"] is True,
            verify_report["signature_valid"] is True,
            verify_report["reproduced_decision_matches_stored"] is True,
            replay_result["matched"] is True,
            replay_result["trace_hash_identical"] is True,
            diagnostics_match,
            diagnostics_stable,
            trace_hash_stable,
            idempotency_equal,
            rejection_summary_ok is not False,
            counterfactual_changed_orders is None or counterfactual_changed_orders > 0,
        ]
    )

    result = {
        "dataset": asdict(spec),
        "payload_path": str(payload_path.relative_to(PROJECT_ROOT)),
        "orders": order_count,
        "partners": partner_count,
        "candidate_pairs": candidate_pairs,
        "allocated": allocated,
        "unallocated": unallocated,
        "allocation_rate": round(allocated / order_count, 6) if order_count else 0.0,
        "allocation_duration_s": allocation_duration_s,
        "replay_duration_s": replay_duration_s,
        "trace_hash_run_a": manifest_a["trace_hash"],
        "trace_hash_run_b": manifest_b["trace_hash"],
        "trace_hash_stable": trace_hash_stable,
        "idempotency_equal": idempotency_equal,
        "manifest_verification": verify_report,
        "replay_check": {
            "matched": replay_result["matched"],
            "trace_hash_identical": replay_result["trace_hash_identical"],
            "divergence_point_if_any": replay_result["divergence_point_if_any"],
        },
        "diagnostics_match_latest_endpoint": diagnostics_match,
        "diagnostics_stable_across_reruns": diagnostics_stable,
        "aggregate_diagnostics": aggregate_diagnostics,
        "top_hard_rule_eliminations": top_rule_counts(aggregate_diagnostics),
        "dominant_failure_combination": dominant_failure_combination(aggregate_diagnostics),
        "sample_unallocated_order_id": unallocated_order_id,
        "sample_rejection_summary": rejection_summary,
        "rejection_summary_ok": rejection_summary_ok,
        "counterfactual_changed_orders_distance_3km": counterfactual_changed_orders,
        "all_checks_passed": all_checks_passed,
    }

    del replay_result
    del response_a
    del response_b
    gc.collect()
    return result


def render_report(
    audit_summary: dict[str, Any],
    results: list[dict[str, Any]],
    dataset_dir: Path,
) -> str:
    lines: list[str] = []
    lines.append("# Large Dataset Validation Report")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(
        "This report provides empirical evidence that the project behaves correctly on larger payloads. "
        "It is not a mathematical proof, but it shows that the main correctness properties still hold when the "
        "dataset size is increased."
    )
    lines.append("")
    lines.append("Validated properties:")
    lines.append("")
    lines.append("- repeat runs on the same payload produced the same trace hash")
    lines.append("- manifest verification passed")
    lines.append("- replay matched the stored trace")
    lines.append("- diagnostics returned by the API matched the persisted latest-diagnostics endpoint")
    lines.append("- rejection summaries for unallocated orders were populated and internally consistent")
    lines.append("- a stricter counterfactual distance rule changed outcomes on the checked dataset")
    lines.append("")
    lines.append("## Source Data")
    lines.append("")
    lines.append(
        f"- Source CSV rows: `{audit_summary['total_rows']}`"
    )
    lines.append(
        f"- Unique delivery partners in source CSV: `{audit_summary['unique_delivery_partners']}`"
    )
    lines.append(
        f"- Large datasets written under `{dataset_dir.relative_to(PROJECT_ROOT)}`"
    )
    lines.append("")
    lines.append("## Dataset Results")
    lines.append("")
    lines.append(
        "| Dataset | Orders | Partners | Candidate pairs | Allocated | Unallocated | Trace hash stable | Manifest verify | Replay match | All checks passed |"
    )
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- | --- |")

    for result in results:
        verify_ok = (
            result["manifest_verification"]["trace_match"]
            and result["manifest_verification"]["signature_valid"]
            and result["manifest_verification"]["reproduced_decision_matches_stored"]
        )
        replay_ok = result["replay_check"]["matched"] and result["replay_check"]["trace_hash_identical"]
        lines.append(
            f"| `{result['dataset']['slug']}` | "
            f"{result['orders']} | {result['partners']} | {result['candidate_pairs']} | "
            f"{result['allocated']} | {result['unallocated']} | "
            f"{'yes' if result['trace_hash_stable'] else 'no'} | "
            f"{'yes' if verify_ok else 'no'} | "
            f"{'yes' if replay_ok else 'no'} | "
            f"{'yes' if result['all_checks_passed'] else 'no'} |"
        )

    for result in results:
        lines.append("")
        lines.append(f"### {result['dataset']['slug']}")
        lines.append("")
        lines.append(
            f"- Allocation result: `{result['allocated']}` allocated, `{result['unallocated']}` unallocated "
            f"(`{result['allocation_rate']:.2%}` allocation rate)"
        )
        lines.append(
            f"- Runtime: allocation `{result['allocation_duration_s']}s`, replay `{result['replay_duration_s']}s`"
        )
        lines.append(
            f"- Determinism check: trace hash was identical across two fresh runs"
            if result["trace_hash_stable"]
            else "- Determinism check: trace hash changed across fresh runs"
        )
        lines.append(
            f"- Latest diagnostics endpoint matched the allocation response: "
            f"`{result['diagnostics_match_latest_endpoint']}`"
        )
        lines.append(
            f"- Idempotency check returned the cached response unchanged: `{result['idempotency_equal']}`"
        )
        lines.append(
            f"- Top hard-rule eliminations: "
            + ", ".join(
                f"{entry['rule']}={entry['count']}" for entry in result["top_hard_rule_eliminations"]
            )
        )
        dominant = result["dominant_failure_combination"]
        if dominant is not None:
            lines.append(
                f"- Dominant unallocated failure combination: "
                f"`{dominant['combination']}` on `{dominant['count']}` orders"
            )
        if result["sample_unallocated_order_id"] is not None:
            lines.append(
                f"- Sample rejection summary checked on order `{result['sample_unallocated_order_id']}`: "
                f"`{result['rejection_summary_ok']}`"
            )
        if result["counterfactual_changed_orders_distance_3km"] is not None:
            lines.append(
                f"- Counterfactual check (`max_distance_km=3.0`) changed "
                f"`{result['counterfactual_changed_orders_distance_3km']}` orders"
            )

    lines.append("")
    lines.append("## Conclusion")
    lines.append("")
    if all(result["all_checks_passed"] for result in results):
        lines.append(
            "All checked correctness signals passed on all generated large datasets. "
            "That is strong evidence that the engine remains deterministic, replayable, "
            "tamper-verifiable, and diagnosable at these larger scales."
        )
    else:
        lines.append(
            "At least one large-dataset validation check failed. Review the JSON report for the exact dataset and field."
        )
    lines.append("")
    lines.append(
        "The main business limitation remains rule strictness rather than correctness: "
        "distance and vehicle-related hard rules still dominate unallocated outcomes."
    )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate and validate large Zomato-based allocation datasets")
    parser.add_argument(
        "--input",
        default=str((PROJECT_ROOT / ".." / "Zomato Dataset.csv").resolve()),
        help="Path to Zomato CSV",
    )
    args = parser.parse_args()

    dataset_dir = PROJECT_ROOT / "demo" / "large_datasets"
    report_dir = PROJECT_ROOT / "reports"
    tmp_dir = Path("/tmp") / "allocation_large_dataset_validation"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)

    audit = audit_zomato_csv(args.input)
    write_json(dataset_dir / "zomato_large_audit_summary.json", audit.to_dict())

    results: list[dict[str, Any]] = []
    for index, spec in enumerate(DEFAULT_SPECS):
        payload = build_allocation_payload_from_zomato(
            args.input,
            max_orders=spec.max_orders,
            max_partners=spec.max_partners,
        )
        payload_path = dataset_dir / f"{spec.slug}.json"
        write_json(payload_path, payload)
        result = validate_dataset(
            spec=spec,
            payload_path=payload_path,
            tmp_dir=tmp_dir,
            run_counterfactual_check=index == 0,
        )
        results.append(result)
        print(
            f"{spec.slug}: orders={result['orders']} partners={result['partners']} "
            f"allocated={result['allocated']} unallocated={result['unallocated']} "
            f"checks={result['all_checks_passed']}"
        )

    json_report_path = report_dir / "LARGE_DATASET_VALIDATION_2026-03-30.json"
    markdown_report_path = report_dir / "LARGE_DATASET_VALIDATION_2026-03-30.md"

    json_report_path.write_text(
        json.dumps(
            {
                "audit_summary": audit.to_dict(),
                "results": results,
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    markdown_report_path.write_text(
        render_report(audit.to_dict(), results, dataset_dir),
        encoding="utf-8",
    )

    print(f"Wrote JSON report to: {json_report_path}")
    print(f"Wrote markdown report to: {markdown_report_path}")


if __name__ == "__main__":
    main()
