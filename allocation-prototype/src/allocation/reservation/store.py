from __future__ import annotations

import threading
import time
from typing import Any


class PartnerReservationStore:
    def __init__(self, ttl_seconds: int = 30) -> None:
        self._locks: dict[str, threading.Lock] = {}
        self._reservations: dict[str, dict[str, Any]] = {}
        self._expiry_deadlines: dict[str, float] = {}
        self._store_lock = threading.Lock()
        self.ttl_seconds = ttl_seconds

    def _evict_expired_locked(self, partner_id: str, now_monotonic: float | None = None) -> None:
        deadline = self._expiry_deadlines.get(partner_id)
        if deadline is None:
            return

        current_monotonic = time.monotonic() if now_monotonic is None else now_monotonic
        if current_monotonic < deadline:
            return

        self._reservations.pop(partner_id, None)
        self._expiry_deadlines.pop(partner_id, None)

    def reserve(self, partner_id: str, order_id: str) -> bool:
        with self._store_lock:
            self._locks.setdefault(partner_id, threading.Lock())
            self._evict_expired_locked(partner_id)
            if partner_id in self._reservations:
                return False

            reserved_at = time.time()
            expires_at = reserved_at + self.ttl_seconds
            self._reservations[partner_id] = {
                "order_id": order_id,
                "reserved_at": reserved_at,
                "expires_at": expires_at,
            }
            self._expiry_deadlines[partner_id] = time.monotonic() + self.ttl_seconds
            return True

    def release(self, partner_id: str, order_id: str) -> None:
        with self._store_lock:
            self._evict_expired_locked(partner_id)
            reservation = self._reservations.get(partner_id)
            if reservation is None or reservation.get("order_id") != order_id:
                return

            self._reservations.pop(partner_id, None)
            self._expiry_deadlines.pop(partner_id, None)

    def is_reserved(self, partner_id: str) -> bool:
        with self._store_lock:
            self._evict_expired_locked(partner_id)
            return partner_id in self._reservations

    def release_all_for_order(self, order_id: str) -> None:
        with self._store_lock:
            partner_ids = list(self._reservations.keys())
            for partner_id in partner_ids:
                self._evict_expired_locked(partner_id)

            matching_partner_ids = [
                partner_id
                for partner_id, reservation in self._reservations.items()
                if reservation.get("order_id") == order_id
            ]
            for partner_id in matching_partner_ids:
                self._reservations.pop(partner_id, None)
                self._expiry_deadlines.pop(partner_id, None)

    def current_reservations(self) -> dict[str, dict[str, Any]]:
        with self._store_lock:
            partner_ids = list(self._reservations.keys())
            for partner_id in partner_ids:
                self._evict_expired_locked(partner_id)
            return {partner_id: dict(record) for partner_id, record in self._reservations.items()}


_store_instance: PartnerReservationStore | None = None


def get_reservation_store() -> PartnerReservationStore:
    global _store_instance
    if _store_instance is None:
        _store_instance = PartnerReservationStore()
    return _store_instance
