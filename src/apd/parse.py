from __future__ import annotations

import hashlib
import json
import re
from html import unescape
from typing import Any

from bs4 import BeautifulSoup


def _norm(s: str) -> str:
    s = unescape(s.replace("\xa0", " "))
    return re.sub(r"\s+", " ", s).strip()


def source_hash(row: dict[str, Any]) -> str:
    payload = {
        k: row.get(k)
        for k in (
            "case_number",
            "report_datetime",
            "offense_datetime",
            "offenses",
            "location_raw",
            "address_raw",
            "apt",
            "city",
            "zip",
            "district_zone",
            "area_command",
            "census_tract",
            "property",
        )
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()[:16]


def parse_location(loc: str) -> dict[str, str | None]:
    location_raw = _norm(loc)
    apt = None
    m = re.search(r"Apt\s*#\s*([^,]+)", location_raw, re.I)
    if m:
        apt = _norm(m.group(1))

    zip_m = re.search(r"\b(78\d{3})\b", location_raw)
    city = None
    address_raw = None
    cm = re.search(
        r"^(.*?),\s*([A-Za-z .]+)\s+(78\d{3})\s*$",
        location_raw,
    )
    if cm:
        street = _norm(cm.group(1))
        street = _norm(re.sub(r",?\s*Apt\s*#\s*[^,]+", "", street, flags=re.I))
        address_raw = street.rstrip(", ") or None
        city = _norm(cm.group(2))
    elif location_raw:
        address_raw = _norm(
            re.sub(r",?\s*Apt\s*#\s*[^,]+", "", location_raw.split(",")[0], flags=re.I)
        ) or None

    return {
        "location_raw": location_raw or None,
        "address_raw": address_raw,
        "apt": apt,
        "city": city,
        "zip": zip_m.group(1) if zip_m else None,
    }


def parse_property_block(text: str) -> list[dict[str, str]] | None:
    bits = [_norm(x) for x in text.splitlines() if _norm(x)]
    if not bits:
        return None
    # Also accept " | " joined plain text
    if len(bits) == 1 and " / " in bits[0]:
        bits = [_norm(x) for x in bits[0].split(" / ") if _norm(x)]
    out: list[dict[str, str]] = []
    i = 0
    while i < len(bits):
        status = bits[i]
        typ = bits[i + 1] if i + 1 < len(bits) else ""
        # Heuristic: STOLEN/DAMAGED/RECOVERED followed by category
        if status.upper() in {
            "STOLEN",
            "DAMAGED",
            "RECOVERED",
            "BURNED",
            "LOST",
            "NONE",
        } and i + 1 < len(bits):
            out.append({"status": status, "type": typ})
            i += 2
        else:
            out.append({"status": status, "type": typ if typ else "UNKNOWN"})
            i += 2 if typ else 1
    return out or None


def parse_search_results(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "lxml")
    body = soup.get_text("\n", strip=True)
    chunks = re.split(r"(?=^20\d{2}-\d{5,})", body, flags=re.M)
    rows: list[dict[str, Any]] = []

    for ch in chunks:
        m = re.match(r"(20\d{2}-\d{5,})", ch)
        if not m:
            continue
        case = m.group(1)
        report = re.search(
            r"Report Date/Time\s*((?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),\s*[A-Za-z]{3}-\d{2}-\d{4}\s+\d{2}:\d{2})",
            ch,
            re.I,
        )
        offense_dt = re.search(
            r"Offense Date/Time\s*((?:Mon|Tue|Wed|Thu|Fri|Sat|Sun),\s*[A-Za-z]{3}-\d{2}-\d{4}\s+\d{2}:\d{2})",
            ch,
            re.I,
        )
        offenses: list[str] = []
        om = re.search(r"Offense\(s\)\s*(.*?)\s*Offense Location", ch, re.I | re.S)
        if om:
            for line in om.group(1).splitlines():
                t = _norm(line)
                if t:
                    offenses.append(t)

        loc = None
        lm = re.search(r"Offense Location\s*(.*?)\s*Census Tract", ch, re.I | re.S)
        if lm:
            loc = lm.group(1)

        tract = re.search(r"Census Tract\s*:?\s*([0-9.]+)", ch, re.I)
        district = re.search(
            r"District\s*:?\s*([0-9]{1,3}|[A-Z]{1,2})\b",
            ch,
            re.I,
        )
        area_m = re.search(
            r"Area Command\s*:?\s*\n?\s*:?\s*([A-Z][A-Z ]{1,40})",
            ch,
            re.I,
        )

        prop = None
        pm = re.search(r"Property\s*(.*?)\s*End Of Offense", ch, re.I | re.S)
        if pm:
            prop = parse_property_block(pm.group(1))

        loc_fields = parse_location(loc or "")
        area_command = _norm(area_m.group(1)) if area_m else None
        if area_command and area_command.upper() in {
            "PROPERTY",
            "END OF OFFENSE",
            "ARRESTEE",
            "AREA",
            "CENSUS TRACT",
            "DISTRICT",
        }:
            area_command = None
        # Keep first line token only (stop at unexpected words)
        if area_command:
            area_command = area_command.split("\n")[0].strip()
            area_command = re.split(
                r"\b(?:Property|End|Census|District)\b",
                area_command,
                maxsplit=1,
                flags=re.I,
            )[0].strip()

        row: dict[str, Any] = {
            "case_number": case,
            "report_datetime": _norm(report.group(1)) if report else None,
            "offense_datetime": _norm(offense_dt.group(1)) if offense_dt else None,
            "offenses": offenses,
            **loc_fields,
            "district_zone": _norm(district.group(1)) if district else None,
            "area_command": area_command or None,
            "census_tract": _norm(tract.group(1)) if tract else None,
            "property": prop,
        }
        row["source_hash"] = source_hash(row)
        rows.append(row)
    return rows
