from apd.parse import source_hash


def sample_incident(**overrides):
    row = {
        "case_number": "2026-5010278",
        "report_datetime": "Thu, Jul-16-2026 18:03",
        "offense_datetime": "Wed, Jul-15-2026 22:00",
        "offenses": ["MAIL THEFT"],
        "location_raw": "2301 PERRY AVE, Apt # 103, AUSTIN 78704",
        "address_raw": "2301 PERRY AVE",
        "apt": "103",
        "city": "AUSTIN",
        "zip": "78704",
        "district_zone": "1",
        "area_command": "SOUTH WEST",
        "census_tract": "13.12",
        "property": [{"status": "STOLEN", "type": "OTHER"}],
    }
    row.update(overrides)
    row["source_hash"] = source_hash(row)
    return row
