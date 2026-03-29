# Validation Summary

This file is a short, plain-language summary of the main validation results from the latest prototype run.

For the full detailed report, see `RUN_REPORT_2026-03-30.md`.

## What Was Checked

- Core demos for manifest sealing, replay, fairness, conflict detection, and counterfactual simulation
- Real-data preparation using `Zomato Dataset.csv`
- Hard-rule scenario comparison on the generated sample payload
- Automated tests
- Direct API route validation
- Alembic migration upgrades on a fresh SQLite database

## Major Results

### 1) Core Features And New Diagnostics Worked

- Manifest verification passed on the original data.
- Tampered manifest verification failed, which shows tamper detection is working.
- Replay matched the stored decision trace exactly.
- Counterfactual simulation changed outcomes when rules were tightened.
- In the focused demo scenario, tightening the distance rule to `3.0 km` changed `2` orders from assigned to unallocated.
- Fairness logic detected imbalance and shifted assignments toward other partners.
- Conflict detection blocked a broken config before evaluation started.
- The allocation pipeline now returns aggregate diagnostics, and the latest diagnostics audit endpoint returned stored results correctly.
- The rejection-summary endpoint returned hard-rule failure details for unallocated orders.

### 2) Real Data Audit Found Noise But Was Usable

- The Zomato dataset contained `45,584` rows and `1,320` unique delivery partners.
- The audit found a few important data quality issues, including invalid age values, invalid ratings, coordinate problems, and some very high-speed outliers.
- After cleaning, a usable payload was created with `120` orders and `80` partners.

### 3) Hard-Rule Comparison Was Measurable

- On the refreshed `120`-order payload, the exact-match baseline still allocated `53` orders and left `67` unallocated.
- Raising `max_distance_km` to `8.0` increased allocation to `86` orders and reduced unallocated orders to `34`.
- The compatibility-enabled default config allocated `67` orders and left `53` unallocated.
- The dominant baseline failure combination remained `DISTANCE_LIMIT_EXCEEDED + VEHICLE_TYPE_MISMATCH`.

### 4) Counterfactual Sensitivity Was Visible

- Tightening the distance rule to `3.0 km` changed `32` orders in the generated sample.
- This suggests the allocation results are quite sensitive to the distance constraint.

### 5) API And Persistence Improvements Were Validated

- Direct route-function tests covered allocation, idempotency, manifest retrieval, manifest verification, replay, and rejection summaries.
- Alembic migrations upgraded cleanly on a fresh SQLite database.
- Per-order allocation event rows now store queryable `trace_hash` and `config_version_hash` values.

### 6) Tests Passed

- Test result: `22 passed`

### 7) HTTP Checks Were Still Limited By The Sandbox

- Direct `uvicorn` socket checks remain unavailable in this environment.
- In-process HTTP client probes are still unreliable here, so API validation was done through direct route-function tests instead.

## Simple Conclusion

The prototype's main claims are supported by the current validation run:

- deterministic allocation
- tamper-evident manifests
- replay support
- fairness adaptation
- rule conflict detection
- counterfactual analysis
- usable real-data preparation from the Zomato dataset
- aggregate diagnostics and rejection summaries for operators
- migration-backed persistence changes

The main practical limitation is still hard-rule strictness. The baseline exact-match ruleset remains fairly conservative on realistic sample data, although the new comparison tooling now makes that tradeoff visible and testable.

## Limitation

- Live `uvicorn` HTTP checks could not be completed in this sandbox because local port binding failed.
- Direct HTTP client checks remain unreliable in this sandbox, so HTTP-layer verification is still incomplete here.
- The project was still validated through demos, direct engine execution, direct route-function API tests, manifest verification, replay, fairness, conflict detection, counterfactual simulation, migrations, and tests.
