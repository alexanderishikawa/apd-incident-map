from __future__ import annotations

import re
import time
from typing import Any

import httpx

from apd.db import Database

NOMINATIM = "https://nominatim.openstreetmap.org/search"
DEFAULT_UA = "apd-incident-map/0.1 (research; contact via project README)"

_DIR_TOKEN = re.compile(r"\b(?:SVRD|NB|SB|EB|WB)\b", re.I)
_BLOCK = re.compile(r"\bBLOCK\b", re.I)
_IH = re.compile(r"\bIH\s*(\d+)\b", re.I)
_US_HWY = re.compile(r"\bUS\s*(\d+)\s*HWY\b", re.I)
_EXPY = re.compile(r"\bEXPY\b", re.I)
_UPPER_DECK = re.compile(r"\bUPPER\s+DECK\b", re.I)
_FM_RD = re.compile(r"\b(FM\s+\d+)\s+RD\b", re.I)
_HOUSE_LETTER = re.compile(r"^(\d+)[A-Z]\b", re.I)
_MC_SPACE = re.compile(r"\bMC\s+([A-Za-z]+)", re.I)
_UNINCORP_COUNTY = re.compile(r"UNINCORP(?:ORATED)?\s+([A-Za-z]+)", re.I)
_JUNK_STREET = re.compile(r"^(UNKNOWN|UNK)$", re.I)


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


def _mc_collapse(match: re.Match[str]) -> str:
    rest = match.group(1)
    return "Mc" + rest[:1].upper() + rest[1:].lower()


def _clean_street(street: str) -> str:
    s = _BLOCK.sub("", street)
    s = _DIR_TOKEN.sub("", s)
    s = _UPPER_DECK.sub("", s)
    s = _HOUSE_LETTER.sub(r"\1", s)
    s = _FM_RD.sub(r"\1", s)
    s = _IH.sub(r"I-\1", s)
    s = _US_HWY.sub(r"US Highway \1", s)
    s = _EXPY.sub("Expressway", s)
    s = _MC_SPACE.sub(_mc_collapse, s)
    return re.sub(r"\s+", " ", s).strip(" ,")


def _clean_city(city: str) -> str:
    m = _UNINCORP_COUNTY.search(city)
    if m:
        return f"{m.group(1).title()} County"
    return city.strip()


def _compose(street: str, city: str, zip_code: str | None) -> str:
    parts = [street, city]
    if zip_code:
        parts.append(zip_code)
    parts.append("TX")
    return re.sub(r"\s+", " ", ", ".join(parts)).strip()


def nominatim_candidates(key: str) -> list[str]:
    """Ordered Nominatim query strings for an APD address_key; empty = skip HTTP."""
    parts = [p.strip() for p in key.split(",")]
    if not parts:
        return []
    street = parts[0]
    if not street or _JUNK_STREET.match(street.strip()):
        return []

    # ..., city, [zip,] TX
    tail = parts[1:]
    if tail and tail[-1].upper() == "TX":
        tail = tail[:-1]
    zip_code: str | None = None
    city = "Austin"
    if len(tail) >= 2 and re.fullmatch(r"\d{5}(?:-\d{4})?", tail[-1] or ""):
        zip_code = tail[-1]
        city = ", ".join(tail[:-1]).strip() or city
    elif tail:
        city = ", ".join(tail).strip() or city

    city = _clean_city(city)
    had_slash = "/" in street
    legs = [p.strip() for p in street.split("/")] if had_slash else [street]
    cleaned_legs = [_clean_street(leg) for leg in legs if _clean_street(leg)]
    if not cleaned_legs:
        return []

    cleaned_street = (
        " and ".join(cleaned_legs) if had_slash else cleaned_legs[0]
    )

    out: list[str] = []
    cities = [city]
    # FM routes outside city limits often resolve better with county bias
    if re.search(r"\bFM\s+\d+", cleaned_street, re.I) and city.upper() == "AUSTIN":
        if "Travis County" not in cities:
            cities.append("Travis County")

    def add(street_part: str, use_zip: bool, city_name: str) -> None:
        if not street_part:
            return
        q = _compose(street_part, city_name, zip_code if use_zip else None)
        if q not in out:
            out.append(q)

    for city_name in cities:
        if had_slash:
            add(cleaned_street, True, city_name)
            add(cleaned_legs[0], True, city_name)
            add(cleaned_street, False, city_name)
            add(cleaned_legs[0], False, city_name)
        else:
            add(cleaned_legs[0], True, city_name)
            add(cleaned_legs[0], False, city_name)

    return out


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

    def pending_keys(self, retry_fails: bool = False) -> list[str]:
        """Newest offense_datetime first; unique keys without ok (and fail unless retry)."""
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
            if cached:
                if cached["status"] == "ok":
                    continue
                if cached["status"] == "fail" and not retry_fails:
                    continue
            seen.add(nk)
            ordered.append(key)
        return ordered

    def run(self, budget: int = 300, retry_fails: bool = False) -> dict[str, int]:
        pending = self.pending_keys(retry_fails=retry_fails)
        stats = {"attempted": 0, "ok": 0, "fail": 0, "skipped_cached": 0}
        for key in pending:
            if stats["attempted"] >= budget:
                break
            cached = self.db.get_geocode(key)
            if cached and cached["status"] == "ok":
                stats["skipped_cached"] += 1
                continue
            if cached and cached["status"] == "fail" and not retry_fails:
                stats["skipped_cached"] += 1
                continue

            cands = nominatim_candidates(key)
            if not cands:
                self.db.upsert_geocode(key, status="fail")
                stats["fail"] += 1
                continue

            coords: tuple[float, float] | None = None
            stopped_early = False
            for query in cands:
                if stats["attempted"] >= budget:
                    stopped_early = True
                    break
                stats["attempted"] += 1
                try:
                    coords = self.lookup_nominatim(query)
                except Exception:
                    coords = None
                    continue
                if coords:
                    break

            if coords:
                self.db.upsert_geocode(
                    key, status="ok", lat=coords[0], lon=coords[1]
                )
                stats["ok"] += 1
            elif stopped_early:
                break
            else:
                self.db.upsert_geocode(key, status="fail")
                stats["fail"] += 1
        return stats
