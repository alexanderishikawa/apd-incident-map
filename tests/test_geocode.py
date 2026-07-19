from __future__ import annotations

import re

import httpx
import pytest

from apd.db import Database
from apd.geocode import (
    Geocoder,
    address_key,
    austin_street_queries,
    nominatim_candidates,
)
from helpers import sample_incident


def test_block_stripped():
    cands = nominatim_candidates("500 BLOCK W 29TH ST, AUSTIN, 78705, TX")
    assert cands[0] == "500 W 29TH ST, AUSTIN, 78705, TX"


def test_svrd_and_dir_stripped():
    cands = nominatim_candidates("204 W BEN WHITE BLVD SVRD WB, AUSTIN, 78704, TX")
    assert "SVRD" not in cands[0].upper()
    upper = cands[0].upper()
    assert not re_search_dir_token(upper)


def re_search_dir_token(upper: str) -> bool:
    return bool(re.search(r"\b(NB|SB|EB|WB)\b", upper))


def test_unincorp_city():
    cands = nominatim_candidates("7400 DAFFAN LN, UNINCORP TRAVIS, 78724, TX")
    assert "Travis County" in cands[0]


def test_intersection_fallbacks():
    cands = nominatim_candidates("AIRPORT BLVD / OAK SPRINGS DR, AUSTIN, 78721, TX")
    assert any(" and " in c for c in cands)
    assert any(c.startswith("AIRPORT BLVD,") for c in cands)


def test_unknown_skips_http_candidates():
    assert nominatim_candidates("UNKNOWN, Austin, TX") == []
    assert nominatim_candidates("UNK, Austin, TX") == []


def test_ih_normalized():
    cands = nominatim_candidates("2723 S IH 35 SVRD NB, AUSTIN, 78741, TX")
    assert any("I-35" in c for c in cands)


def test_mc_space_collapsed():
    cands = nominatim_candidates("6306 MC NEIL DR, AUSTIN, 78729, TX")
    assert any("McNeil" in c for c in cands)
    assert "MC NEIL" not in cands[0].upper()


def test_unincorp_hays_county():
    cands = nominatim_candidates("15701 FM 1826 RD, UNINCORP HAYS, 78737, TX")
    assert "Hays County" in cands[0]
    assert "FM 1826" in cands[0]
    assert " RD," not in cands[0] and not cands[0].startswith("RD")


def test_upper_deck_stripped():
    cands = nominatim_candidates("4124 N IH 35 UPPER DECK SB, AUSTIN, 78705, TX")
    assert all("UPPER" not in c.upper() for c in cands)
    assert any("I-35" in c for c in cands)


def test_house_number_letter_stripped():
    cands = nominatim_candidates("2000K E ANDERSON LN SVRD WB, AUSTIN, 78754, TX")
    assert cands[0].startswith("2000 E ANDERSON")


def test_fm_adds_travis_county_bias():
    cands = nominatim_candidates("3003 S FM 973 RD, AUSTIN, 78617, TX")
    assert any("Travis County" in c for c in cands)
    assert any(re.search(r"FM 973,", c) for c in cands)



def test_fallback_hit_on_third_candidate_counts_http(tmp_path):
    key = "AIRPORT BLVD / OAK SPRINGS DR, AUSTIN, 78721, TX"
    cands = nominatim_candidates(key)
    assert len(cands) >= 3
    hit_q = cands[2]
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        q = request.url.params["q"]
        calls.append(q)
        if q == hit_q:
            return httpx.Response(
                200,
                json=[{"lat": "30.26", "lon": "-97.72", "display_name": "hit"}],
            )
        return httpx.Response(200, json=[])

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    db = Database(tmp_path / "t.sqlite")
    db.upsert_incident(
        sample_incident(
            case_number="2026-GEO-1",
            address_raw="AIRPORT BLVD / OAK SPRINGS DR",
            city="AUSTIN",
            zip="78721",
        )
    )
    geo = Geocoder(db, client=client, min_interval=0)
    stats = geo.run(budget=10)
    assert stats["ok"] == 1
    assert stats["attempted"] == 3
    assert len(calls) == 3
    cached = db.get_geocode(key)
    assert cached is not None
    assert cached["status"] == "ok"
    assert cached["lat"] == pytest.approx(30.26)
    geo.close()
    db.close()


def test_unknown_fails_without_http(tmp_path):
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, json=[])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    db = Database(tmp_path / "t.sqlite")
    db.upsert_incident(
        sample_incident(
            case_number="2026-GEO-2",
            address_raw="UNKNOWN",
            city="Austin",
            zip="",
        )
    )
    geo = Geocoder(db, client=client, min_interval=0)
    stats = geo.run(budget=10)
    assert stats["fail"] == 1
    assert stats["attempted"] == 0
    assert calls == []
    key = address_key(
        {"address_raw": "UNKNOWN", "city": "Austin", "zip": ""}
    )
    assert db.get_geocode(key)["status"] == "fail"
    geo.close()
    db.close()


def test_all_candidates_miss_marks_fail(tmp_path):
    def handler(request: httpx.Request) -> httpx.Response:
        if "openstreetmap.org" in str(request.url):
            return httpx.Response(200, json=[])
        # Austin empty feature set
        return httpx.Response(200, json={"features": []})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    db = Database(tmp_path / "t.sqlite")
    db.upsert_incident(
        sample_incident(
            case_number="2026-GEO-3",
            address_raw="500 BLOCK W 29TH ST",
            city="AUSTIN",
            zip="78705",
        )
    )
    geo = Geocoder(db, client=client, min_interval=0)
    stats = geo.run(budget=10)
    assert stats["fail"] == 1
    # Nominatim candidates + Austin fallback
    assert stats["attempted"] >= 2
    key = "500 BLOCK W 29TH ST, AUSTIN, 78705, TX"
    assert db.get_geocode(key)["status"] == "fail"
    geo.close()
    db.close()


def test_austin_street_queries_keep_svrd():
    qs = austin_street_queries("2723 S IH 35 SVRD NB, AUSTIN, 78741, TX")
    assert qs == ["2723 S IH 35 SVRD NB"]
    qs2 = austin_street_queries("500 BLOCK W 29TH ST, AUSTIN, 78705, TX")
    assert qs2 == ["500 W 29TH ST"]


def test_austin_gis_first_for_highway_dialect(tmp_path):
    key = "2723 S IH 35 SVRD NB, AUSTIN, 78741, TX"
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        calls.append(url)
        if "openstreetmap.org" in url:
            raise AssertionError("Nominatim should not run when Austin hits first")
        where = request.url.params.get("where", "")
        assert "2723 S IH 35 SVRD NB" in where
        return httpx.Response(
            200,
            json={
                "features": [
                    {
                        "attributes": {"FULL_STREET_NAME": "2723 S IH 35 SVRD NB"},
                        "geometry": {"x": -97.74, "y": 30.22},
                    }
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    db = Database(tmp_path / "t.sqlite")
    db.upsert_incident(
        sample_incident(
            case_number="2026-GEO-AUS",
            address_raw="2723 S IH 35 SVRD NB",
            city="AUSTIN",
            zip="78741",
        )
    )
    geo = Geocoder(db, client=client, min_interval=0)
    stats = geo.run(budget=20)
    assert stats["ok"] == 1
    assert stats["ok_austin"] == 1
    assert stats["attempted"] == 1
    cached = db.get_geocode(key)
    assert cached["status"] == "ok"
    assert cached["provider"] == "austin_gis"
    assert cached["lat"] == pytest.approx(30.22)
    assert any("austintexas.gov" in u for u in calls)
    geo.close()
    db.close()


def test_austin_gis_fallback_after_nominatim_miss(tmp_path):
    """Non-highway miss → Nominatim first, then Austin."""
    key = "8005 LADERA VERDE DR, AUSTIN, 78739, TX"

    def handler(request: httpx.Request) -> httpx.Response:
        if "openstreetmap.org" in str(request.url):
            return httpx.Response(200, json=[])
        return httpx.Response(
            200,
            json={
                "features": [
                    {
                        "attributes": {"FULL_STREET_NAME": "8005 LADERA VERDE DR"},
                        "geometry": {"x": -97.88, "y": 30.19},
                    }
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    db = Database(tmp_path / "t.sqlite")
    db.upsert_incident(
        sample_incident(
            case_number="2026-GEO-AUS2",
            address_raw="8005 LADERA VERDE DR",
            city="AUSTIN",
            zip="78739",
        )
    )
    geo = Geocoder(db, client=client, min_interval=0)
    stats = geo.run(budget=20)
    assert stats["ok"] == 1
    assert stats["ok_austin"] == 1
    assert db.get_geocode(key)["provider"] == "austin_gis"
    geo.close()
    db.close()



def test_retry_fails_requeues(tmp_path):
    key = "500 BLOCK W 29TH ST, AUSTIN, 78705, TX"
    cleaned = nominatim_candidates(key)[0]

    def handler(request: httpx.Request) -> httpx.Response:
        q = request.url.params["q"]
        if q == cleaned:
            return httpx.Response(
                200, json=[{"lat": "30.29", "lon": "-97.74", "display_name": "hit"}]
            )
        return httpx.Response(200, json=[])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    db = Database(tmp_path / "t.sqlite")
    db.upsert_incident(
        sample_incident(
            case_number="2026-GEO-4",
            address_raw="500 BLOCK W 29TH ST",
            city="AUSTIN",
            zip="78705",
        )
    )
    db.upsert_geocode(key, status="fail")
    geo = Geocoder(db, client=client, min_interval=0)
    assert geo.run(budget=10, retry_fails=False)["attempted"] == 0
    stats = geo.run(budget=10, retry_fails=True)
    assert stats["ok"] == 1
    assert db.get_geocode(key)["status"] == "ok"
    geo.close()
    db.close()


def test_budget_stops_mid_candidates_without_fail(tmp_path):
    key = "AIRPORT BLVD / OAK SPRINGS DR, AUSTIN, 78721, TX"
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.params["q"])
        return httpx.Response(200, json=[])

    client = httpx.Client(transport=httpx.MockTransport(handler))
    db = Database(tmp_path / "t.sqlite")
    db.upsert_incident(
        sample_incident(
            case_number="2026-GEO-5",
            address_raw="AIRPORT BLVD / OAK SPRINGS DR",
            city="AUSTIN",
            zip="78721",
        )
    )
    geo = Geocoder(db, client=client, min_interval=0)
    stats = geo.run(budget=2)
    assert stats["attempted"] == 2
    assert stats["fail"] == 0
    assert stats["ok"] == 0
    assert db.get_geocode(key) is None
    assert len(calls) == 2
    geo.close()
    db.close()
