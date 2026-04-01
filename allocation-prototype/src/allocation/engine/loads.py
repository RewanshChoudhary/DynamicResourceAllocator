from __future__ import annotations

from typing import Any

from allocation.domain.partner import DeliveryPartner


def initial_partner_loads_for_replay(
    evaluation_trace: dict[str, Any],
    partners: list[DeliveryPartner],
) -> dict[str, int]:
    # Historical traces may not include this key (backward compatibility).
    stored = evaluation_trace.get("initial_partner_loads", {})
    if not isinstance(stored, dict):
        stored = {}

    resolved: dict[str, int] = {}
    for partner in partners:
        value = stored.get(partner.partner_id, 0)
        try:
            resolved[partner.partner_id] = int(value)
        except (TypeError, ValueError):
            resolved[partner.partner_id] = 0
    return resolved
