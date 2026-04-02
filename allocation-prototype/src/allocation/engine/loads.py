from __future__ import annotations

from typing import Any

from allocation.domain.partner import DeliveryPartner


def _coerce_non_negative_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def resolve_partner_loads(
    partners: list[DeliveryPartner],
    observed_partner_loads: dict[str, int] | None = None,
) -> dict[str, int]:
    observed = observed_partner_loads if isinstance(observed_partner_loads, dict) else {}

    resolved: dict[str, int] = {}
    for partner in partners:
        payload_load = _coerce_non_negative_int(partner.current_load)
        runtime_load = _coerce_non_negative_int(observed.get(partner.partner_id, 0))
        # Treat the payload's current_load as the live floor and keep any higher runtime count.
        resolved[partner.partner_id] = max(payload_load, runtime_load)
    return resolved


def initial_partner_loads_for_replay(
    evaluation_trace: dict[str, Any],
    partners: list[DeliveryPartner],
) -> dict[str, int]:
    stored = evaluation_trace.get("initial_partner_loads", {})
    if not isinstance(stored, dict):
        stored = {}

    resolved: dict[str, int] = {}
    for partner in partners:
        resolved[partner.partner_id] = _coerce_non_negative_int(stored.get(partner.partner_id, 0))
    return resolved
