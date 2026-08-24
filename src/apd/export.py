from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any

from apd.db import Database
from apd.geocode import address_key


def export_site_data(db: Database, out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    geo = db.geocode_map()
    incidents_out: list[dict[str, Any]] = []
    offenses: set[str] = set()
    zips: set[str] = set()
    zones: set[str] = set()
    areas: set[str] = set()
    geocoded = 0

    for row in db.all_incidents():
        for o in row.get("offenses") or []:
            offenses.add(o)
        if row.get("zip"):
            zips.add(row["zip"])
        if row.get("district_zone"):
            zones.add(row["district_zone"])
        if row.get("area_command"):
            areas.add(row["area_command"])

        key = address_key(row)
        g = geo.get(key) if key else None
        status = g["status"] if g else "pending"
        lat = g.get("lat") if g and status == "ok" else None
        lon = g.get("lon") if g and status == "ok" else None
        if lat is not None and lon is not None:
            geocoded += 1

        incidents_out.append(
            {
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
                "lat": lat,
                "lon": lon,
                "geocode_status": status if key else "no_address",
            }
        )

    meta = {
        "last_pulled_at": db.last_pulled_at(),
        "count": len(incidents_out),
        "geocoded_count": geocoded,
        "offenses": sorted(offenses),
        "zips": sorted(zips),
        "zones": sorted(zones, key=lambda z: (len(z), z)),
        "area_commands": sorted(areas),
    }

    incidents_path = out_dir / "incidents.json"
    gz_path = out_dir / "incidents.json.gz"
    meta_path = out_dir / "meta.json"
    payload = json.dumps(incidents_out, ensure_ascii=False).encode("utf-8")
    incidents_path.write_bytes(payload)
    with gzip.open(gz_path, "wb") as f:
        f.write(payload)
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    return meta
