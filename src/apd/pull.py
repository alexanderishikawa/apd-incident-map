from __future__ import annotations

import time
from datetime import date, timedelta
from typing import Any

from apd.client import ApdClient
from apd.db import Database
from apd.parse import parse_search_results


def upsert_html(db: Database, html: str) -> int:
    n = 0
    for row in parse_search_results(html):
        if db.upsert_incident(row):
            n += 1
    return n


def pull_window(
    db: Database,
    client: ApdClient,
    start: date,
    numdays: int = 6,
    sleep_s: float = 0.35,
) -> dict[str, Any]:
    end = start + timedelta(days=numdays)
    key = (start.isoformat(), end.isoformat())
    try:
        html = client.search_window(start, numdays=numdays)
        changed = upsert_html(db, html)
        parsed = len(parse_search_results(html))
        db.record_pull_run(key[0], key[1], "ok", rows_upserted=changed)
        time.sleep(sleep_s)
        return {
            "window_start": key[0],
            "window_end": key[1],
            "parsed": parsed,
            "upserted": changed,
            "status": "ok",
        }
    except Exception as e:
        db.record_pull_run(key[0], key[1], "error", error=str(e))
        return {
            "window_start": key[0],
            "window_end": key[1],
            "parsed": 0,
            "upserted": 0,
            "status": "error",
            "error": str(e),
        }


def pull_last_days(
    db: Database,
    client: ApdClient,
    last_days: int = 7,
    sleep_s: float = 0.35,
) -> list[dict[str, Any]]:
    """Pull covering the last `last_days` offense dates (inclusive of yesterday-ish)."""
    # Search is offense-date based; include today and go back.
    end = date.today()
    start = end - timedelta(days=last_days - 1)
    results = []
    # Chunk into <=7 day windows
    cursor = start
    while cursor <= end:
        remaining = (end - cursor).days
        numdays = min(6, remaining)
        results.append(pull_window(db, client, cursor, numdays=numdays, sleep_s=sleep_s))
        cursor = cursor + timedelta(days=numdays + 1)
    return results


def pull_historical(
    db: Database,
    client: ApdClient,
    *,
    until_empty_streak: int = 5,
    max_windows: int | None = None,
    sleep_s: float = 0.5,
    resume: bool = True,
) -> list[dict[str, Any]]:
    """Walk newest → oldest in 7-day windows until empty streak or cliff."""
    done = db.successful_windows() if resume else set()
    results: list[dict[str, Any]] = []
    empty = 0
    # Start from a week that includes recent offense dates (yesterday back 6)
    cursor = date.today() - timedelta(days=1)
    windows = 0
    while True:
        if max_windows is not None and windows >= max_windows:
            break
        start = cursor - timedelta(days=6)
        key = (start.isoformat(), cursor.isoformat())
        if resume and key in done:
            cursor = start - timedelta(days=1)
            continue
        # pull_window uses start + numdays; end = start+6
        r = pull_window(db, client, start, numdays=6, sleep_s=sleep_s)
        results.append(r)
        windows += 1
        if r["status"] != "ok":
            empty += 1
        elif r["parsed"] == 0:
            empty += 1
        else:
            empty = 0
        if empty >= until_empty_streak:
            break
        cursor = start - timedelta(days=1)
    return results
