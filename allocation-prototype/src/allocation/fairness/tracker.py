from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone


class PartnerLoadTracker:
    def __init__(self, window: timedelta | None = None) -> None:
        self.window = window or timedelta(hours=1)
        self._assignments: dict[str, deque[datetime]] = defaultdict(deque)

    def record_assignment(self, partner_id: str, assigned_at: datetime | None = None) -> None:
        ts = assigned_at or datetime.now(timezone.utc)
        self._assignments[partner_id].append(ts)

    def get_load_counts(
        self,
        partner_ids: list[str] | tuple[str, ...],
        now: datetime | None = None,
    ) -> dict[str, int]:
        ts_now = now or datetime.now(timezone.utc)
        threshold = ts_now - self.window

        counts: dict[str, int] = {}
        for partner_id in partner_ids:
            dq = self._assignments[partner_id]
            while dq and dq[0] < threshold:
                dq.popleft()
            counts[partner_id] = len(dq)
        return counts
