# Agent Notes

## Explicitly Out Of Scope

- `post_gini_projection` still mirrors the pre-change Gini value. Fixing that requires a product decision about what a projected fairness score should mean.
- The fairness tracker is still in-memory and app-local. Externalizing it for cross-process consistency would require an infrastructure decision and was intentionally left out of this run.

## Environment Notes

- In-process HTTP client probing remains unreliable in this sandbox, so API coverage was added through direct route-function tests instead of `TestClient` or live `uvicorn` requests.
- The `sqlite3` CLI is not installed on this machine. Direct database verification was done with Python's built-in `sqlite3` module instead.
