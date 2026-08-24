from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

from apd.db import Database
from apd.geocode import address_key
from apd.parse import source_hash


def _load_incidents(data_dir: Path) -> list[dict[str, Any]]:
    json_path = data_dir / "incidents.json"
    gz_path = data_dir / "incidents.json.gz"
    if json_path.exists():
        return json.loads(json_path.read_text(encoding="utf-8"))
    if gz_path.exists():
        with gzip.open(gz_path, "rt", encoding="utf-8") as f:
            return json.load(f)
    raise FileNotFoundError(f"Missing {json_path.name} and {gz_path.name} in {data_dir}")


def seed_from_export(
    db: Database,
    data_dir: Path,
    *,
    skip_if_nonempty: bool = True,
) -> dict[str, int]:
    """Load incidents.json or incidents.json.gz into SQLite (for cloud/fresh checkouts)."""
    if skip_if_nonempty and db.count_incidents() > 0:
        return {"incidents": db.count_incidents(), "seeded": 0, "geocodes": 0}

    rows = _load_incidents(data_dir)
    seeded = 0
    geocodes = 0
    for row in rows:
        incident = {
            "case_number": row["case_number"],
            "report_datetime": row.get("report_datetime"),
            "offense_datetime": row.get("offense_datetime"),
            "offenses": row.get("offenses") or [],
            "location_raw": row.get("location_raw"),
            "address_raw": row.get("address_raw"),
            "apt": row.get("apt"),
            "city": row.get("city"),
            "zip": row.get("zip"),
            "district_zone": row.get("district_zone"),
            "area_command": row.get("area_command"),
            "census_tract": row.get("census_tract"),
            "property": row.get("property"),
        }
        incident["source_hash"] = source_hash(incident)
        if db.upsert_incident(incident):
            seeded += 1
        key = address_key(incident)
        if key and row.get("lat") is not None and row.get("lon") is not None:
            if not db.get_geocode(key):
                db.upsert_geocode(
                    key,
                    status="ok",
                    lat=float(row["lat"]),
                    lon=float(row["lon"]),
                )
                geocodes += 1
        elif key and row.get("geocode_status") == "fail" and not db.get_geocode(key):
            db.upsert_geocode(key, status="fail")
            geocodes += 1
    return {
        "incidents": db.count_incidents(),
        "seeded": seeded,
        "geocodes": geocodes,
    }
