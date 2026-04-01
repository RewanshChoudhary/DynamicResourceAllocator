from __future__ import annotations

from test_frontend import load_app_module


def test_simulation_presets_endpoint_returns_required_demo_presets(tmp_path, monkeypatch):
    app_module = load_app_module(tmp_path, monkeypatch)
    app = app_module.create_app()
    routes = {route.path: route for route in app.routes}

    payload = routes["/demo/simulation-presets"].endpoint()

    preset_names = {preset["name"] for preset in payload}
    assert "max_distance.max_distance_km = 10" in preset_names
    assert "weights: fairness_score prioritized" in preset_names
    assert "min_rating disabled" in preset_names
    assert "partner_pool.remove busiest_partner" in preset_names
    assert "Enable Traffic-Aware Proximity" in preset_names
    assert len(payload) == 5
    assert all(preset["requires_manifest_id"] is True for preset in payload)
