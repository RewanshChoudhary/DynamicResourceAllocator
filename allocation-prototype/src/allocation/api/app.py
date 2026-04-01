from __future__ import annotations

import json
import os
from datetime import timedelta
from pathlib import Path
from typing import Any

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from allocation.api.routers.allocate import router as allocate_router
from allocation.api.routers.audit import router as audit_router
from allocation.api.routers.simulate import router as simulate_router
from allocation.fairness.tracker import PartnerLoadTracker
from allocation.persistence.models import (
    assert_schema_compatible,
    create_all_tables,
    create_session_factory,
    create_sqlite_engine,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
FRONTEND_PATH = PROJECT_ROOT / "frontend" / "index.html"
SAMPLE_DATASET_DIR = PROJECT_ROOT / "demo" / "sample_datasets"
DEFAULT_SAMPLE_DATASET = "bengaluru_lunch_rush"


def _load_json_payload(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sample_dataset_paths() -> dict[str, Path]:
    if not SAMPLE_DATASET_DIR.exists():
        return {}
    return {path.stem: path for path in sorted(SAMPLE_DATASET_DIR.glob("*.json"))}


def _default_sample_dataset(dataset_paths: dict[str, Path]) -> str:
    if DEFAULT_SAMPLE_DATASET in dataset_paths:
        return DEFAULT_SAMPLE_DATASET
    return next(iter(dataset_paths))


def _sample_dataset_catalog() -> list[dict[str, Any]]:
    datasets: list[dict[str, Any]] = []
    for slug, path in _sample_dataset_paths().items():
        payload = _load_json_payload(path)
        metadata = payload.get("metadata") or {}
        datasets.append(
            {
                "slug": slug,
                "name": metadata.get("name", slug.replace("_", " ").title()),
                "city": metadata.get("city"),
                "description": metadata.get("description"),
                "recommended_for": metadata.get("recommended_for"),
                "orders": len(payload.get("orders", [])),
                "partners": len(payload.get("partners", [])),
            }
        )
    return datasets


def create_app() -> FastAPI:
    structlog.configure(processors=[structlog.processors.JSONRenderer()])

    app = FastAPI(title="Rule-Driven Allocation Prototype")

    db_url = os.getenv("ALLOCATION_DB_URL", "sqlite:///allocation_prototype.db")
    engine = create_sqlite_engine(db_url)
    create_all_tables(engine)
    assert_schema_compatible(engine)
    session_factory = create_session_factory(engine)

    app.state.session_factory = session_factory
    app.state.partner_load_tracker = PartnerLoadTracker(window=timedelta(hours=1))

    app.include_router(allocate_router)
    app.include_router(audit_router)
    app.include_router(simulate_router)

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        if not FRONTEND_PATH.exists():
            raise HTTPException(status_code=404, detail="Frontend page is missing")
        return FileResponse(FRONTEND_PATH)

    @app.get("/demo/sample-datasets", include_in_schema=False)
    def sample_datasets() -> dict[str, Any]:
        dataset_paths = _sample_dataset_paths()
        if not dataset_paths:
            raise HTTPException(status_code=404, detail="No sample datasets are available")
        return {
            "default": _default_sample_dataset(dataset_paths),
            "datasets": _sample_dataset_catalog(),
        }

    @app.get("/demo/sample-payload", include_in_schema=False)
    def sample_payload(dataset: str | None = None) -> dict[str, Any]:
        dataset_paths = _sample_dataset_paths()
        if not dataset_paths:
            raise HTTPException(status_code=404, detail="No sample datasets are available")

        selected_dataset = dataset or _default_sample_dataset(dataset_paths)
        selected_path = dataset_paths.get(selected_dataset)
        if selected_path is None:
            available = ", ".join(sorted(dataset_paths))
            raise HTTPException(
                status_code=404,
                detail=f"Unknown sample dataset '{selected_dataset}'. Available datasets: {available}",
            )
        return _load_json_payload(selected_path)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
