from __future__ import annotations

from dataclasses import dataclass

from allocation.domain.enums import AllocationStatus


@dataclass(frozen=True)
class Allocation:
    order_id: str
    partner_id: str | None
    status: AllocationStatus
    reason: str
    weighted_score: float | None = None
