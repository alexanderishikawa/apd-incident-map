from pathlib import Path

from apd.parse import parse_search_results

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_mail_theft_card():
    html = (FIXTURES / "card_mail_theft.html").read_text(encoding="utf-8")
    rows = parse_search_results(html)
    assert len(rows) >= 1
    row = next(r for r in rows if r["case_number"] == "2026-5010278")
    assert row["offenses"] == ["MAIL THEFT"]
    assert row["report_datetime"] and "Jul-16-2026" in row["report_datetime"]
    assert row["offense_datetime"] and "Jul-15-2026" in row["offense_datetime"]
    assert row["location_raw"] and "PERRY" in row["location_raw"].upper()
    assert row["address_raw"] == "2301 PERRY AVE"
    assert row["apt"] == "103"
    assert row["city"] == "AUSTIN"
    assert row["zip"] == "78704"
    assert row["district_zone"] == "1"
    assert row["area_command"] == "SOUTH WEST"
    assert row["census_tract"] == "13.12"
    assert row["property"] == [{"status": "STOLEN", "type": "OTHER"}]
    assert row["source_hash"]


def test_parse_day_head_has_multiple():
    path = FIXTURES / "day_2026_07_15_head.html"
    if not path.exists():
        return
    html = path.read_text(encoding="utf-8")
    rows = parse_search_results(html)
    assert len(rows) >= 3
    assert any(r.get("zip") for r in rows)
