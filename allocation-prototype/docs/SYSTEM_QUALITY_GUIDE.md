# System Quality Guide

This guide explains what the allocation prototype is doing from the bottom of the stack to the top, with a focus on improving quality. The key idea is simple:

- every upper layer trusts the layer below it
- if a lower layer is noisy, every higher layer becomes harder to trust
- the fastest way to improve quality is to fix the lowest layer that is still introducing mistakes

## 1. Ground Truth Inputs

### What this layer does

This is where the system gets its raw truth:

- static rule configuration in `src/allocation/config/rules.yaml`
- broken-config demo in `src/allocation/config/rules_broken.yaml`
- external real-world proxy data in `../Zomato Dataset.csv`

The Zomato adapter in `src/allocation/data/zomato_adapter.py` audits the CSV, fixes known coordinate sign issues, normalizes vehicle types, drops invalid rows, and emits the API-ready payload.

### Why this matters

If the input payload is wrong, the rest of the system can still be deterministic and auditable while making bad decisions. Determinism does not imply correctness.

### Current quality signal

- the Zomato dataset still contains missing values, invalid ages, invalid ratings, coordinate sign problems, and speed outliers
- the generated sample is usable, but it is still shaped by cleaning assumptions
- vehicle normalization is coarse (`motorcycle`, `bicycle`, and `bike` all map to `bike`)

### Quality improvements

- version the generated payload alongside the audit summary so runs can be compared cleanly
- add tests for more adapter edge cases, especially timestamp parsing and vehicle normalization
- make every cleaning assumption visible in metadata, not just dropped-row counts
- separate “fixed” rows from “accepted but suspicious” rows so downstream analysis can compare them

## 2. Domain Contracts

### What this layer does

The domain layer defines the objects the engine actually reasons about:

- `src/allocation/domain/order.py`
- `src/allocation/domain/partner.py`
- `src/allocation/domain/allocation.py`
- `src/allocation/domain/enums.py`

These classes are intentionally small and deterministic. They are the internal contract between the API/data layer and the engine.

### Why this matters

If domain objects are ambiguous, the rule engine becomes harder to reason about. Small domain models are a quality advantage because they reduce hidden behavior.

### Quality improvements

- keep domain models free from transport concerns and persistence concerns
- document invariants more explicitly, such as acceptable rating range and coordinate assumptions
- add validation closer to construction if bad in-memory states become a problem later

## 3. Persistence Foundation

### What this layer does

SQLite and SQLAlchemy provide the storage base:

- `src/allocation/persistence/models.py`
- `src/allocation/persistence/repository.py`
- `src/allocation/persistence/config_versions.py`

This layer stores:

- allocation events
- sealed manifests
- input snapshots
- config versions
- idempotency records

### Why this matters

This is the auditability backbone. Replay, counterfactual simulation, and manifest verification all depend on these persisted records being complete and consistent.

### Quality strengths

- config versioning is explicit
- snapshots and manifests are stored separately
- idempotency is persisted rather than kept only in memory

### Quality weaknesses

- most records are stored as JSON blobs, which makes querying and debugging harder
- there are no database-level uniqueness rules beyond primary keys for business semantics like one latest manifest per request
- there are no explicit migration tools yet

### Quality improvements

- add migration support before schema growth makes changes risky
- add integrity checks between `allocation_events`, `sealed_manifests`, and `input_snapshots`
- consider promoting some manifest fields out of JSON blobs if operational querying becomes important

## 4. Rule Framework

### What this layer does

The rule framework defines the reusable mechanics for filtering and scoring:

- `src/allocation/rules/base.py`
- `src/allocation/rules/registry.py`
- `src/allocation/rules/utils.py`

Rules are registered centrally and then instantiated from config.

### Why this matters

This layer controls extensibility. If rule registration or rule metadata becomes inconsistent, the engine may still run but stop reflecting the intended config.

### Quality improvements

- require stronger rule metadata contracts if more rules are added
- add tests that assert every configured rule name maps to the expected class and kind
- surface rule ordering more explicitly because hard-rule order affects failure statistics and explainability

## 5. Hard Rules

### What this layer does

Hard rules remove ineligible partners before scoring:

- availability: `src/allocation/rules/hard/availability.py`
- vehicle type: `src/allocation/rules/hard/vehicle_type.py`
- max distance: `src/allocation/rules/hard/distance.py`
- rating thresholds: `src/allocation/rules/hard/rating.py`

### Why this matters

This is currently the biggest quality and behavior lever in the whole system. If a partner fails here, scoring never gets a chance to help.

### Current quality signal

With the current default config:

- `vehicle_type` is an exact hard match
- `max_distance_km` is `5.0`
- `min_rating` is `3.5`

In the latest real-data sample:

- `53` orders were allocated
- `67` were unallocated
- all `67` unallocated orders had the same failure combination across their candidate pool:
  - `DISTANCE_LIMIT_EXCEEDED`
  - `VEHICLE_TYPE_MISMATCH`

This means the current allocation rate is being limited mainly by hard constraints, not by scoring logic.

### Quality improvements

- decide which constraints are truly safety constraints versus business preferences
- if the goal is higher allocation rate, move some filters into scoring penalties instead of hard rejection
- add reporting that shows per-order and aggregate hard-rule elimination rates by rule
- test alternative configs as first-class scenarios instead of relying on one default ruleset

## Product Decision Log

On the previously validated exact-match baseline run, the engine allocated `53` of `120` orders, which is an allocation rate of `44.17%`. In that baseline, the hard constraints driving all unallocated orders were `vehicle_type` matching and the `max_distance_km = 5.0` cutoff, not the downstream scoring logic. The repository now includes a `vehicle_compatibility` map and the `demo/demo_scenario_compare.py` tool so teams can measure how those constraints change outcomes before committing to a new default. That choice should be treated as a product policy decision about service quality and substitution risk, not as a routine refactor.

## 6. Scoring and Fairness

### What this layer does

Once a partner passes all hard rules, scoring rules rank the remaining candidates:

- proximity score: `src/allocation/rules/scoring/proximity.py`
- rating score: `src/allocation/rules/scoring/rating.py`
- fairness score: `src/allocation/rules/scoring/fairness.py`
- fairness adjustment logic: `src/allocation/fairness/gini.py`
- rolling load tracking: `src/allocation/fairness/tracker.py`

### Why this matters

This layer improves quality among eligible choices, but it cannot rescue orders that were already filtered out below.

### Quality strengths

- scoring is deterministic
- fairness escalation is explicit and recorded
- Gini-based logic is simple enough to reason about

### Quality weaknesses

- fairness quality is limited by in-memory partner load tracking inside the app process
- the `post_gini_projection` field is currently not a true projection; it echoes the pre-change value
- scoring weights only matter after hard-rule survival

### Quality improvements

- persist or externalize the fairness load tracker if cross-process consistency matters
- compute a genuine projected post-change fairness metric
- add scenario tests that isolate scoring changes from hard-rule changes

## 7. Allocation Engine

### What this layer does

The engine combines hard rules and scoring into a deterministic decision:

- `src/allocation/engine/pipeline.py`

The pipeline:

1. sorts orders and partners for determinism
2. evaluates hard rules in order
3. scores surviving candidates
4. breaks ties deterministically by partner id
5. records a full trace

### Why this matters

This file is the behavioral center of the project. Most system-level quality questions eventually reduce to “what did the pipeline see and why did it choose this partner?”

### Quality strengths

- deterministic sorting
- explicit evaluation trace
- deterministic tie breaking

### Quality weaknesses

- there is no separate analytics pass for “why orders were unallocated” beyond reading traces after the fact
- the pipeline mixes decision-making and trace assembly in one function, which is manageable now but will get harder to maintain as rules grow

### Quality improvements

- add structured aggregate diagnostics on top of the trace
- split decision logic from trace serialization if the pipeline becomes more complex
- add performance checks if partner counts increase significantly

## 8. Trust and Explainability Layers

### What this layer does

These layers make the engine auditable after the decision:

- manifest sealing and verification: `src/allocation/engine/manifest.py`
- replay support: `src/allocation/engine/replay.py`
- counterfactual simulation: `src/allocation/simulation/counterfactual.py`

### Why this matters

This is what makes the prototype more than just a scorer. It can explain, verify, and mutate historical decisions.

### Quality strengths

- manifest signing is deterministic and tamper-evident
- replay is tied to stored config and stored input
- counterfactual simulation reuses the real pipeline instead of a separate approximation

### Quality weaknesses

- replay and simulation quality still depend on the completeness of stored snapshots and config history
- counterfactual mutation support is powerful, but broad `Any` values can hide bad mutation shapes until runtime

### Quality improvements

- tighten mutation schemas where possible
- add negative tests for malformed mutation inputs
- add cross-checks that stored input hashes and manifest trace hashes remain aligned after persistence round-trips

## 9. API Layer

### What this layer does

The API exposes the engine through FastAPI:

- app bootstrap: `src/allocation/api/app.py`
- allocation endpoint: `src/allocation/api/routers/allocate.py`
- audit/replay/trace endpoints: `src/allocation/api/routers/audit.py`
- simulation endpoint: `src/allocation/api/routers/simulate.py`
- request/response schemas: `src/allocation/api/schemas.py`

### What happens in `POST /allocations`

At a high level:

1. validate input with Pydantic
2. check idempotency
3. load config and detect conflicts
4. build rules
5. compute current partner loads
6. apply fairness weight adjustment
7. run the deterministic pipeline
8. build manifest and input snapshot
9. persist config version, snapshot, manifest, events, and idempotency response
10. update the in-memory fairness tracker

### Why this matters

This is where multiple lower layers finally meet. If the API layer is weak, the whole system feels unreliable even when the engine underneath is sound.

### Current quality signal

- the route structure is clear and the main flow is readable
- idempotency is implemented
- however, HTTP-layer verification remains incomplete in this sandbox because both socket-based and in-process probes stalled

### Quality improvements

- prioritize API-level tests in an environment that does not hang on in-process requests
- add endpoint-level timeout and observability diagnostics
- separate app construction from process-global side effects even more aggressively if testability continues to be hard

## 10. Validation Layer

### What this layer does

This layer proves whether the system behaves as intended:

- tests in `tests/`
- demo scripts in `demo/`
- reports in:
  - `VALIDATION_SUMMARY.md`
  - `RUN_REPORT_2026-03-21.md`
  - `RUN_REPORT_2026-03-29.md`

### Why this matters

Quality is not what the code claims. Quality is what this layer can prove repeatedly.

### Quality strengths

- the demos map cleanly to the major feature claims
- the tests cover core deterministic, manifest, replay, conflict, fairness, and adapter behavior

### Quality weaknesses

- API behavior is not currently covered by a reliable automated path in this sandbox
- latest validation re-ran behavior but not coverage
- repo reports can drift if they are not refreshed alongside meaningful logic changes

### Quality improvements

- add a stable API test path outside this sandbox
- distinguish “baseline revalidation” from “behavior changed” in reports
- add scenario-based quality benchmarks, not just pass/fail demos

## Bottom-To-Top Failure Propagation

This system should be debugged from the bottom up:

1. Check the payload and config.
2. Check which hard rules are eliminating candidates.
3. Only then inspect scoring and fairness.
4. After that, inspect manifest/replay/simulation.
5. Only after lower layers look healthy should you debug API behavior.

If you skip this order, you can spend time tuning scoring weights when the real problem is that no candidate survives hard filtering.

## Current Quality Priorities

If the goal is better system quality, this is the best order to work in:

### Priority 1: Make unallocated-order diagnostics first-class

The system already stores enough trace data to explain failures, but it does not summarize that well enough for operators. Add aggregated reports for:

- unallocated orders by hard-rule combination
- candidate elimination counts by rule
- allocation rate under alternate config profiles

### Priority 2: Revisit hard-rule strictness

The current `44.17%` allocation rate is being constrained mainly by:

- exact vehicle-type matching
- `max_distance_km = 5.0`

This should be treated as a product decision, not just an engine fact.

### Priority 3: Fix API-level testability

The engine-level quality story is much better than the HTTP-layer quality story right now. That gap should be closed with:

- reliable API tests
- stronger request lifecycle observability
- environment-specific debugging for the in-process hang

### Priority 4: Improve persistence and analytics ergonomics

The trust model is strong, but operational analysis is still awkward because many artifacts are JSON blobs. Make it easier to answer:

- why was this order rejected?
- what changed between config versions?
- which rules are responsible for allocation loss?

## A Practical Rule Of Thumb

When quality drops, ask these questions in order:

1. Did the input payload or config change?
2. Which hard rule removed the most candidates?
3. Are we looking at a selection problem or an eligibility problem?
4. Do replay and manifest verification still agree?
5. Is the issue in the engine, or only in the API surface?

If you follow that order, this system stays understandable even as it grows.
