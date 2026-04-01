from __future__ import annotations

import importlib
from pathlib import Path
import sys

from fastapi.responses import FileResponse


def load_app_module(tmp_path, monkeypatch):
    monkeypatch.setenv("ALLOCATION_DB_URL", f"sqlite:///{tmp_path / 'frontend.db'}")
    sys.modules.pop("allocation.api.app", None)
    return importlib.import_module("allocation.api.app")


def test_frontend_root_serves_human_readable_page(tmp_path, monkeypatch):
    app_module = load_app_module(tmp_path, monkeypatch)
    app = app_module.create_app()
    routes = {route.path: route for route in app.routes}

    response = routes["/"].endpoint()

    assert isinstance(response, FileResponse)
    assert Path(response.path) == app_module.FRONTEND_PATH
    html = app_module.FRONTEND_PATH.read_text()
    assert "Human-readable allocation results in one page" in html
    assert "Run allocation" in html
    assert "Hard rules currently applied" in html


def test_frontend_sample_payload_endpoint_returns_orders_and_partners(tmp_path, monkeypatch):
    app_module = load_app_module(tmp_path, monkeypatch)
    app = app_module.create_app()
    routes = {route.path: route for route in app.routes}

    payload = routes["/demo/sample-payload"].endpoint()
    assert payload["metadata"]["name"] == "Bengaluru Lunch Rush"
    assert "orders" in payload
    assert "partners" in payload
    assert len(payload["orders"]) > 0
    assert len(payload["partners"]) > 0


def test_frontend_sample_dataset_catalog_lists_curated_payloads(tmp_path, monkeypatch):
    app_module = load_app_module(tmp_path, monkeypatch)
    app = app_module.create_app()
    routes = {route.path: route for route in app.routes}

    payload = routes["/demo/sample-datasets"].endpoint()

    assert payload["default"] == "bengaluru_lunch_rush"
    slugs = {dataset["slug"] for dataset in payload["datasets"]}
    assert "bengaluru_lunch_rush" in slugs
    assert "hyderabad_monsoon_mixed_fleet" in slugs
    assert "gurugram_distance_pressure" in slugs
