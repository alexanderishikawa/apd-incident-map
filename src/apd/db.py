from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Database:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._migrate()

    def close(self) -> None:
        self.conn.close()

    def _migrate(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS incidents (
              case_number TEXT PRIMARY KEY,
              report_datetime TEXT,
              offense_datetime TEXT,
              offenses TEXT NOT NULL,
              location_raw TEXT,
              address_raw TEXT,
              apt TEXT,
              city TEXT,
              zip TEXT,
              district_zone TEXT,
              area_command TEXT,
              census_tract TEXT,
              property TEXT,
              source_hash TEXT,
              pulled_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS geocode_cache (
              address_key TEXT PRIMARY KEY,
              lat REAL,
              lon REAL,
              status TEXT NOT NULL,
              provider TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS pull_runs (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              window_start TEXT NOT NULL,
              window_end TEXT NOT NULL,
              status TEXT NOT NULL,
              rows_upserted INTEGER NOT NULL DEFAULT 0,
              error TEXT,
              finished_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_incidents_offense_dt
              ON incidents(offense_datetime);
            CREATE INDEX IF NOT EXISTS idx_incidents_zip ON incidents(zip);
            """
        )
        self.conn.commit()

    def upsert_incident(self, row: dict[str, Any]) -> bool:
        """Insert or update. Returns True if inserted or content changed."""
        case = row["case_number"]
        existing = self.get_incident(case)
        offenses = row.get("offenses") or []
        prop = row.get("property")
        payload = {
            "case_number": case,
            "report_datetime": row.get("report_datetime"),
            "offense_datetime": row.get("offense_datetime"),
            "offenses": json.dumps(offenses, ensure_ascii=False),
            "location_raw": row.get("location_raw"),
            "address_raw": row.get("address_raw"),
            "apt": row.get("apt"),
            "city": row.get("city"),
            "zip": row.get("zip"),
            "district_zone": row.get("district_zone"),
            "area_command": row.get("area_command"),
            "census_tract": row.get("census_tract"),
            "property": json.dumps(prop, ensure_ascii=False) if prop is not None else None,
            "source_hash": row.get("source_hash"),
            "pulled_at": row.get("pulled_at") or _utc_now(),
        }
        if existing and existing.get("source_hash") == payload["source_hash"]:
            return False
        self.conn.execute(
            """
            INSERT INTO incidents (
              case_number, report_datetime, offense_datetime, offenses,
              location_raw, address_raw, apt, city, zip,
              district_zone, area_command, census_tract, property,
              source_hash, pulled_at
            ) VALUES (
              :case_number, :report_datetime, :offense_datetime, :offenses,
              :location_raw, :address_raw, :apt, :city, :zip,
              :district_zone, :area_command, :census_tract, :property,
              :source_hash, :pulled_at
            )
            ON CONFLICT(case_number) DO UPDATE SET
              report_datetime=excluded.report_datetime,
              offense_datetime=excluded.offense_datetime,
              offenses=excluded.offenses,
              location_raw=excluded.location_raw,
              address_raw=excluded.address_raw,
              apt=excluded.apt,
              city=excluded.city,
              zip=excluded.zip,
              district_zone=excluded.district_zone,
              area_command=excluded.area_command,
              census_tract=excluded.census_tract,
              property=excluded.property,
              source_hash=excluded.source_hash,
              pulled_at=excluded.pulled_at
            """,
            payload,
        )
        self.conn.commit()
        return True

    def get_incident(self, case_number: str) -> dict[str, Any] | None:
        cur = self.conn.execute(
            "SELECT * FROM incidents WHERE case_number = ?", (case_number,)
        )
        row = cur.fetchone()
        return self._incident_from_row(row) if row else None

    def count_incidents(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM incidents").fetchone()[0])

    def all_incidents(self) -> list[dict[str, Any]]:
        cur = self.conn.execute(
            "SELECT * FROM incidents ORDER BY offense_datetime DESC, case_number DESC"
        )
        return [self._incident_from_row(r) for r in cur.fetchall()]

    def _incident_from_row(self, row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        d["offenses"] = json.loads(d["offenses"] or "[]")
        d["property"] = json.loads(d["property"]) if d.get("property") else None
        return d

    def record_pull_run(
        self,
        window_start: str,
        window_end: str,
        status: str,
        rows_upserted: int = 0,
        error: str | None = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO pull_runs (window_start, window_end, status, rows_upserted, error, finished_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (window_start, window_end, status, rows_upserted, error, _utc_now()),
        )
        self.conn.commit()

    def successful_windows(self) -> set[tuple[str, str]]:
        cur = self.conn.execute(
            "SELECT window_start, window_end FROM pull_runs WHERE status = 'ok'"
        )
        return {(r[0], r[1]) for r in cur.fetchall()}

    def upsert_geocode(
        self,
        address_key: str,
        status: str,
        lat: float | None = None,
        lon: float | None = None,
        provider: str = "nominatim",
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO geocode_cache (address_key, lat, lon, status, provider, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(address_key) DO UPDATE SET
              lat=excluded.lat,
              lon=excluded.lon,
              status=excluded.status,
              provider=excluded.provider,
              updated_at=excluded.updated_at
            """,
            (address_key, lat, lon, status, provider, _utc_now()),
        )
        self.conn.commit()

    def get_geocode(self, address_key: str) -> dict[str, Any] | None:
        cur = self.conn.execute(
            "SELECT * FROM geocode_cache WHERE address_key = ?", (address_key,)
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def geocode_map(self) -> dict[str, dict[str, Any]]:
        cur = self.conn.execute("SELECT * FROM geocode_cache")
        return {r["address_key"]: dict(r) for r in cur.fetchall()}

    def last_pulled_at(self) -> str | None:
        cur = self.conn.execute("SELECT MAX(pulled_at) FROM incidents")
        return cur.fetchone()[0]
