from __future__ import annotations

import re
import time
from typing import Any

import httpx

from apd.db import Database

NOMINATIM = "https://nominatim.openstreetmap.org/search"
DEFAULT_UA = "apd-incident-map/0.1 (research; contact via project README)"


def address_key(incident: dict[str, Any]) -> str | None:
    addr = (incident.get("address_raw") or "").strip()
    if not addr:
        return None
    city = (incident.get("city") or "Austin").strip()
    z = (incident.get("zip") or "").strip()
    parts = [addr, city]
    if z:
        parts.append(z)
    parts.append("TX")
    key = ", ".join(parts)
    return re.sub(r"\s+", " ", key).strip()


def normalize_key(key: str) -> str:
    return re.sub(r"\s+", " ", key).strip().upper()


class Geocoder:
    def __init__(
        self,
        db: Database,
        client: httpx.Client | None = None,
        min_interval: float = 1.05,
        user_agent: str = DEFAULT_UA,
    ):
        self.db = db
        self._owns = client is None
        self.client = client or httpx.Client(
            headers={"User-Agent": user_agent},
            timeout=60.0,
        )
        self.min_interval = min_interval
        self._last = 0.0

    def close(self) -> None:
        if self._owns:
            self.client.close()

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last = time.monotonic()

    def lookup_nominatim(self, query: str) -> tuple[float, float] | None:
        self._throttle()
        r = self.client.get(
            NOMINATIM,
            params={
                "q": query,
                "format": "json",
                "limit": 1,
                "countrycodes": "us",
            },
        )
        r.raise_for_status()
        data = r.json()
        if not data:
            return None
        return float(data[0]["lat"]), float(data[0]["lon"])

    def pending_keys(self) -> list[str]:
        """Newest offense_datetime first; unique address keys without ok/fail cache."""
        seen: set[str] = set()
        ordered: list[str] = []
        for row in self.db.all_incidents():
            key = address_key(row)
            if not key:
                continue
            nk = normalize_key(key)
            if nk in seen:
                continue
            cached = self.db.get_geocode(key)
            if cached and cached["status"] in {"ok", "fail"}:
                continue
            seen.add(nk)
            ordered.append(key)
        return ordered

    def run(self, budget: int = 300) -> dict[str, int]:
        pending = self.pending_keys()
        stats = {"attempted": 0, "ok": 0, "fail": 0, "skipped_cached": 0}
        for key in pending:
            if stats["attempted"] >= budget:
                break
            cached = self.db.get_geocode(key)
            if cached and cached["status"] in {"ok", "fail"}:
                stats["skipped_cached"] += 1
                continue
            stats["attempted"] += 1
            try:
                coords = self.lookup_nominatim(key)
            except Exception:
                self.db.upsert_geocode(key, status="fail")
                stats["fail"] += 1
                continue
            if coords:
                self.db.upsert_geocode(key, status="ok", lat=coords[0], lon=coords[1])
                stats["ok"] += 1
            else:
                self.db.upsert_geocode(key, status="fail")
                stats["fail"] += 1
        return stats
