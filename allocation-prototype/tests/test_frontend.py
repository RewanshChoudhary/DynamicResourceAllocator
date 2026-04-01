from __future__ import annotations

import importlib
from pathlib import Path
import sys

from fastapi.responses import FileResponse


def load_app_module(tmp_path, monkeypatch):
    monkeypatch.setenv("ALLOCATION_DB_URL", f"sqlite:///{tmp_path / 'frontend.db'}")
    sys.modules.pop("allocation.api.app", None)
    return importlib.import_module("allocation.api.app")


def test_frontend_root_serves_allocation_console(tmp_path, monkeypatch):
    app_module = load_app_module(tmp_path, monkeypatch)
    app = app_module.create_app()
    routes = {route.path: route for route in app.routes}

    response = routes["/"].endpoint()

    assert isinstance(response, FileResponse)
    assert Path(response.path) == app_module.FRONTEND_PATH
    html = app_module.FRONTEND_PATH.read_text()
    js = app_module.FRONTEND_JS_PATH.read_text()
    assert 'href="/styles.css"' in html
    assert 'src="/app.js"' in html
    assert "Delivery allocation audit and replay console" in html
    assert "Run allocation" in html
    assert "Audit &amp; Verify" in html
    assert "Replay" in html
    assert "Simulate" in html
    assert "Apply Preset" in html
    assert "Active hard rules in this run" in js
    assert "Runtime Diagnostics" in html
    assert "Fairness Gini: N/A" in js


def test_frontend_static_asset_routes_serve_split_css_and_js(tmp_path, monkeypatch):
    app_module = load_app_module(tmp_path, monkeypatch)
    app = app_module.create_app()
    routes = {route.path: route for route in app.routes}

    css_response = routes["/styles.css"].endpoint()
    js_response = routes["/app.js"].endpoint()

    assert isinstance(css_response, FileResponse)
    assert isinstance(js_response, FileResponse)
    assert Path(css_response.path) == app_module.FRONTEND_CSS_PATH
    assert Path(js_response.path) == app_module.FRONTEND_JS_PATH


def test_frontend_sample_payload_endpoint_returns_orders_and_partners(tmp_path, monkeypatch):
    app_module = load_app_module(tmp_path, monkeypatch)
    app = app_module.create_app()
    routes = {route.path: route for route in app.routes}

    payload = routes["/demo/sample-payload"].endpoint()
    assert payload["metadata"]["name"] == "Zomato Clear Weather Large (172 orders)"
    assert "orders" in payload
    assert "partners" in payload
    assert len(payload["orders"]) > 0
    assert len(payload["partners"]) > 0


def test_frontend_sample_dataset_catalog_lists_curated_payloads(tmp_path, monkeypatch):
    app_module = load_app_module(tmp_path, monkeypatch)
    app = app_module.create_app()
    routes = {route.path: route for route in app.routes}

    payload = routes["/demo/sample-datasets"].endpoint()

    assert payload["default"] == "realistic_clear_weather"
    slugs = {dataset["slug"] for dataset in payload["datasets"]}
    assert "realistic_clear_weather" in slugs
    assert "realistic_severe_weather" in slugs
    assert "realistic_traffic_jam" in slugs
    assert len(slugs) == 3
