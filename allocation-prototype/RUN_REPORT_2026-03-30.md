# Allocation Prototype Feature Report (2026-03-30)

## Scope

This run implemented and revalidated the full Allocation Engine Improvement Guide:

- first-class aggregate diagnostics
- diagnostics and rejection-summary audit endpoints
- vehicle compatibility mapping
- scenario comparison tooling
- direct in-process API route tests
- Alembic migration support
- denormalized per-order allocation event metadata

## Commands Executed

- `.venv/bin/python -m pytest -v`
- `.venv/bin/python demo/demo_sdm.py`
- `.venv/bin/python demo/demo_counterfactual.py`
- `.venv/bin/python demo/demo_fairness.py`
- `.venv/bin/python demo/demo_conflict.py`
- `.venv/bin/python demo/demo_replay.py`
- `.venv/bin/python demo/demo_scenario_compare.py`
- `.venv/bin/python scripts/prepare_zomato_data.py --input "../Zomato Dataset.csv" --audit-out demo/zomato_audit_report.json --payload-out demo/zomato_allocation_payload.json --max-orders 120 --max-partners 80`
- `ALLOCATION_DB_URL=sqlite:////tmp/allocation_final_alembic_20260330.db .venv/bin/alembic upgrade head`

## Results

### 1) Tests

- Result: `22 passed in 1.21s`
- New coverage areas:
  - aggregate diagnostics
  - vehicle compatibility
  - direct allocation API route tests
  - manifest/audit API route tests
  - lifecycle replay validation
  - rejection summary query

### 2) Core Feature Demos

- SDM verification passed and tamper detection failed as expected.
- Counterfactual demo still changed `2` orders when `max_distance_km` tightened to `3.0`.
- Fairness demo still escalated the fairness weight and redistributed assignments away from the overloaded partner.
- Conflict demo still blocked the broken config before evaluation.
- Replay demo still reported `matched: true` and `trace_hash_identical: true`.

### 3) Refreshed Zomato Payload

- Audit still reported `45,584` rows and `1,320` unique delivery partners.
- Regenerated payload metadata still produced `120` orders and `80` partners.
- The refreshed payload is the basis for the scenario comparison results below.

### 4) Hard-Rule Scenario Comparison

Using `demo/demo_scenario_compare.py` on the refreshed `120`-order payload:

| Scenario | Allocated | Unallocated | Top hard-rule elimination |
| --- | ---: | ---: | --- |
| Baseline (exact vehicle matching, `5.0 km`) | 53 | 67 | `DISTANCE+VEHICLE (67)` |
| Relaxed distance (`8.0 km`, exact vehicle matching) | 86 | 34 | `DISTANCE+VEHICLE (34)` |
| Compatibility (current default config) | 67 | 53 | `DISTANCE (53)` |

This shows the exact-match baseline remains the previously observed `44.17%` allocation rate, while the current compatibility-enabled default improves the same payload to `67 / 120` allocated.

### 5) Diagnostics And Operator Surfaces

- `POST /allocations` now returns `aggregate_diagnostics`.
- `GET /allocations/diagnostics/latest` returns the latest stored diagnostics summary.
- `GET /allocations/{order_id}/rejection-summary` now returns hard-rule failure details, candidates evaluated, and candidates surviving hard rules.
- A direct Zomato-payload check returned a populated rejection summary for an unallocated order with `150` candidate failures recorded and `0` surviving hard-rule candidates.

### 6) Persistence And Migrations

- Alembic was added and configured against the existing SQLAlchemy metadata.
- Initial schema migration generated cleanly.
- A follow-up migration added denormalized `trace_hash` and `config_version_hash` columns to `allocation_events`.
- Fresh-database migration verification passed with `alembic upgrade head`.
- Direct database verification confirmed populated per-order rows such as:
  - `ORD-1 | assigned | <trace_hash> | <config_version_hash>`
  - `ORD-2 | assigned | <trace_hash> | <config_version_hash>`

## Tasks Skipped

- None from the implementation guide.
- Two items remained intentionally out of scope and are recorded in `AGENT_NOTES.md`: projected fairness semantics and externalizing the fairness tracker.

## Notes

- Live HTTP client verification is still constrained by the sandbox, so API validation in this run was done through direct route-function tests rather than socket-based or `TestClient` requests.
