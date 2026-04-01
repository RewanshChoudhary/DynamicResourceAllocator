# Rule-Driven Allocation Engine Prototype

This project assigns delivery orders to eligible partners in a way that is deterministic, explainable, and easy to verify later.

It does more than return an allocation result. It also stores a tamper-evident manifest, exposes replay and audit endpoints, supports counterfactual simulations, and includes realistic sample datasets for demos and manual testing.

## What The System Does

At a high level, the allocation flow is:

1. Accept orders and delivery partners through the API.
2. Load and validate the active rule configuration.
3. Apply hard rules such as availability, vehicle compatibility, distance, and minimum rating.
4. Score the remaining candidates with proximity, rating, and fairness.
5. Choose the best partner deterministically.
6. Persist the result, evaluation trace, input snapshot, and sealed manifest.
7. Allow later verification, replay, diagnostics, and what-if simulation.

## Feature Overview

- **Deterministic allocation pipeline**: the same inputs and config produce the same allocation result and trace.
- **Hard-rule filtering**: availability, vehicle compatibility, distance, and rating are checked before scoring.
- **Weighted scoring**: proximity, rating, and fairness are combined into a transparent final score.
- **Fairness escalation**: if recent partner load becomes too uneven, fairness weight can be increased automatically.
- **Conflict-aware configuration loading**: broken or contradictory rule configs are detected before allocation starts.
- **Sealed Decision Manifest (SDM)**: each run stores a tamper-evident manifest tied to the input snapshot and config hash.
- **Replay and verification**: past decisions can be replayed and checked against stored signatures and trace hashes.
- **Rejection summaries and aggregate diagnostics**: the API explains why orders failed and aggregates the most common hard-rule eliminations.
- **Counterfactual simulation**: stored runs can be re-evaluated under config mutations.
- **Allocation operations console**: the browser UI loads project datasets and surfaces manifests, trace inspection, replay, diagnostics, and counterfactual runs.
- **Dataset tooling**: the repo supports both curated sample payloads and larger generated payloads adapted from the Zomato CSV.

## Stack

- FastAPI
- Pydantic v2
- SQLite + SQLAlchemy
- Alembic
- pytest
- structlog
- PyYAML
- Python stdlib `hmac` + `hashlib`

## Project Layout

```text
allocation-prototype/
├── src/allocation/
│   ├── api/
│   ├── config/
│   ├── data/
│   ├── domain/
│   ├── engine/
│   ├── fairness/
│   ├── persistence/
│   ├── rules/
│   └── simulation/
├── demo/
│   ├── sample_datasets/
│   └── demo_*.py
├── frontend/
├── scripts/
├── tests/
├── README.md
└── pyproject.toml
```

## Quick Start

Create a local virtual environment and install the project in editable mode:

```bash
cd allocation-prototype
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

Run the database migration:

```bash
.venv/bin/alembic upgrade head
```

Start the API:

```bash
.venv/bin/python -m uvicorn allocation.api.app:app --reload
```

Open the frontend:

```text
http://127.0.0.1:8000/
```

## Running The Project With Different Datasets

### 1. Versioned sample datasets

The frontend and demo sample endpoints are backed by versioned payloads in [demo/sample_datasets](/home/rewansh57/Programming/PatentProject/allocation-prototype/demo/sample_datasets). That directory now includes both synthetic scenario datasets and CSV-derived Zomato slices.

Available datasets:

- `bengaluru_lunch_rush.json`: compact weekday lunch demand with mostly bike and scooter traffic plus one car-only order.
- `hyderabad_monsoon_mixed_fleet.json`: mixed-fleet evening demand with availability pressure and car-only requests.
- `gurugram_distance_pressure.json`: spread-out suburban demand designed to surface distance-limit failures.
- `zomato_national_high_volume.json`: larger cross-city payload derived from the source Zomato CSV.
- `zomato_metro_jam_core.json`: metropolitan jam-traffic slice from the Zomato CSV.
- `zomato_urban_low_traffic.json`: lighter urban slice from the Zomato CSV.
- `zomato_festival_jam_surge.json`: festival-period jam slice from the Zomato CSV.
- `zomato_metro_high_traffic.json`: metropolitan high-traffic slice from the Zomato CSV.

Use them in the frontend:

1. Start the API.
2. Open `http://127.0.0.1:8000/`.
3. Choose a dataset from the sample dropdown.
4. Click `Load selected sample`.
5. Run the allocation.

Use them directly with the API:

```bash
curl -X POST http://127.0.0.1:8000/allocations \
  -H 'Content-Type: application/json' \
  -H 'X-Idempotency-Key: blr-sample-001' \
  --data @demo/sample_datasets/bengaluru_lunch_rush.json
```

```bash
curl -X POST http://127.0.0.1:8000/allocations \
  -H 'Content-Type: application/json' \
  -H 'X-Idempotency-Key: hyd-sample-001' \
  --data @demo/sample_datasets/hyderabad_monsoon_mixed_fleet.json
```

```bash
curl -X POST http://127.0.0.1:8000/allocations \
  -H 'Content-Type: application/json' \
  -H 'X-Idempotency-Key: ggn-sample-001' \
  --data @demo/sample_datasets/gurugram_distance_pressure.json
```

You can also inspect the sample catalog through the app:

- `GET /demo/sample-datasets`
- `GET /demo/sample-payload?dataset=bengaluru_lunch_rush`
- `GET /demo/sample-payload?dataset=hyderabad_monsoon_mixed_fleet`
- `GET /demo/sample-payload?dataset=gurugram_distance_pressure`
- `GET /demo/sample-payload?dataset=zomato_metro_jam_core`
- `GET /demo/sample-payload?dataset=zomato_urban_low_traffic`
- `GET /demo/sample-payload?dataset=zomato_festival_jam_surge`
- `GET /demo/sample-payload?dataset=zomato_metro_high_traffic`

### 2. Generated datasets from the Zomato CSV

If you want bigger, noisier, or source-derived payloads, generate them from `../Zomato Dataset.csv`.

Run the adapter:

```bash
.venv/bin/python scripts/prepare_zomato_data.py \
  --input ../Zomato\ Dataset.csv \
  --audit-out demo/zomato_audit_report.json \
  --payload-out demo/zomato_allocation_payload.json \
  --max-orders 120 \
  --max-partners 80
```

That command:

- audits the raw CSV
- writes a data-quality report to `demo/zomato_audit_report.json`
- writes an allocation-ready payload to `demo/zomato_allocation_payload.json`

To regenerate the CSV-derived sample datasets that appear in the frontend catalog:

```bash
.venv/bin/python scripts/generate_zomato_sample_datasets.py \
  --input ../Zomato\ Dataset.csv
```

Use the generated payload with the API:

```bash
curl -X POST http://127.0.0.1:8000/allocations \
  -H 'Content-Type: application/json' \
  -H 'X-Idempotency-Key: zomato-seed-001' \
  --data @demo/zomato_allocation_payload.json
```

Compare scenarios on the generated payload:

```bash
.venv/bin/python demo/demo_scenario_compare.py
```

### 3. Custom payloads

Any custom JSON payload sent to `POST /allocations` must contain:

- `orders`
- `partners`

Each order needs:

- `order_id`
- `latitude`
- `longitude`
- `amount_paise`
- `requested_vehicle_type`
- `created_at`

Each partner needs:

- `partner_id`
- `latitude`
- `longitude`
- `is_available`
- `rating`
- `vehicle_types`
- `active`

Supported vehicle types are:

- `bike`
- `scooter`
- `car`

## API Endpoints

- `POST /allocations`
- `GET /allocations/diagnostics/latest`
- `GET /allocations/{order_id}/manifest`
- `GET /allocations/{order_id}/manifest/verify`
- `GET /allocations/{order_id}/replay`
- `GET /allocations/{order_id}/rejection-summary`
- `GET /allocations/{order_id}/trace`
- `POST /simulations`
- `GET /demo/sample-datasets`
- `GET /demo/sample-payload`
- `GET /health`

`POST /allocations` requires the `X-Idempotency-Key` header.

## Demo Scripts

These scripts exercise the main claims of the project:

- `demo/demo_sdm.py`: cryptographically sealed, tamper-evident decision record
- `demo/demo_counterfactual.py`: historical what-if simulation with config mutation
- `demo/demo_fairness.py`: fairness-triggered scoring adjustment
- `demo/demo_conflict.py`: pre-run conflict detection and blocking
- `demo/demo_replay.py`: deterministic replay and trace-hash verification
- `demo/demo_scenario_compare.py`: compare baseline, relaxed-distance, and compatibility-enabled scenarios on the generated Zomato payload

Run them with:

```bash
.venv/bin/python demo/demo_sdm.py
.venv/bin/python demo/demo_counterfactual.py
.venv/bin/python demo/demo_fairness.py
.venv/bin/python demo/demo_conflict.py
.venv/bin/python demo/demo_replay.py
.venv/bin/python demo/demo_scenario_compare.py
```

## Types Of Tests Performed

The automated test suite covers the project from several angles:

- **API route behavior**: allocation responses, idempotency, manifest fetch, manifest verification, replay, and rejection-summary routes
- **Allocation lifecycle**: end-to-end request lifecycle with replayed trace-hash consistency
- **Manifest integrity**: tamper detection and signature verification
- **Diagnostics and auditability**: aggregate diagnostics, hard-rule elimination counts, and stored rejection summaries
- **Counterfactual simulation**: config mutations that change historical outcomes
- **Fairness logic**: Gini-based fairness escalation and weight renormalization
- **Rule and config safety**: conflict detection, unknown-rule blocking, vehicle compatibility, and schema compatibility checks
- **Dataset quality**: Zomato adapter output validation and curated sample-dataset schema validation
- **Frontend smoke coverage**: root page rendering, sample payload loading, and curated sample catalog availability

The main test files are:

- `tests/test_api_allocate.py`
- `tests/test_api_audit.py`
- `tests/test_api_lifecycle.py`
- `tests/test_manifest.py`
- `tests/test_replay.py`
- `tests/test_counterfactual.py`
- `tests/test_diagnostics.py`
- `tests/test_rejection_query.py`
- `tests/test_fairness_gini.py`
- `tests/test_conflict_detection.py`
- `tests/test_vehicle_compatibility.py`
- `tests/test_schema_compatibility.py`
- `tests/test_zomato_adapter.py`
- `tests/test_frontend.py`
- `tests/test_sample_datasets.py`

Run the full suite:

```bash
.venv/bin/python -m pytest tests -q
```

Run only API-focused tests:

```bash
.venv/bin/python -m pytest tests/test_api_allocate.py tests/test_api_audit.py tests/test_api_lifecycle.py -q
```

Run only dataset and frontend tests:

```bash
.venv/bin/python -m pytest tests/test_frontend.py tests/test_sample_datasets.py tests/test_zomato_adapter.py -q
```

Run only manifest, replay, and simulation tests:

```bash
.venv/bin/python -m pytest tests/test_manifest.py tests/test_replay.py tests/test_counterfactual.py -q
```

## Current Validation Snapshot

As of April 2, 2026, the repository was rechecked locally with the project virtual environment:

- Full automated test suite: `29 passed`
- Scenario comparison on `demo/zomato_allocation_payload.json`:
  - `Baseline`: `53` allocated, `67` unallocated
  - `Relaxed distance`: `86` allocated, `34` unallocated
  - `Compatibility`: `67` allocated, `53` unallocated

## Notes

- The active config is [rules.yaml](/home/rewansh57/Programming/PatentProject/allocation-prototype/src/allocation/config/rules.yaml).
- The intentionally broken config for conflict demos is [rules_broken.yaml](/home/rewansh57/Programming/PatentProject/allocation-prototype/src/allocation/config/rules_broken.yaml).
- The signing key is read from `SDM_SIGNING_KEY` and defaults to `dev-signing-key`.
- The default SQLite URL is `sqlite:///allocation_prototype.db`, but you can override it with `ALLOCATION_DB_URL`.
- The system quality guide lives in [SYSTEM_QUALITY_GUIDE.md](/home/rewansh57/Programming/PatentProject/allocation-prototype/docs/SYSTEM_QUALITY_GUIDE.md).
