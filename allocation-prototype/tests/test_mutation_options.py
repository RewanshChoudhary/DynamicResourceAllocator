from __future__ import annotations

from test_frontend import load_app_module


def test_mutation_options_endpoint_exposes_live_rule_and_parameter_choices(tmp_path, monkeypatch):
    app_module = load_app_module(tmp_path, monkeypatch)
    app = app_module.create_app()
    routes = {route.path: route for route in app.routes}

    payload = routes["/demo/mutation-options"].endpoint()

    parameter_rules = {entry["rule_name"] for entry in payload["rule_parameter"]}
    weight_rules = {entry["rule_name"] for entry in payload["rule_weight"]}
    toggle_rules = {entry["rule_name"] for entry in payload["rule_toggle"]}

    assert {
        "load_capacity",
        "max_distance",
        "min_rating",
        "vehicle_condition",
        "weather_safety",
        "proximity_score",
        "on_time_rate",
    } <= parameter_rules
    assert {"proximity_score", "rating_score", "fairness_score", "on_time_rate"} <= weight_rules
    assert {
        "availability",
        "vehicle_type",
        "load_capacity",
        "max_distance",
        "min_rating",
        "vehicle_condition",
        "weather_safety",
        "traffic_adjusted_proximity",
    } <= toggle_rules
    assert payload["partner_pool"]["actions"] == ["remove", "add", "modify"]
    assert {"bike", "scooter", "car"} <= set(payload["partner_pool"]["vehicle_type_choices"])
