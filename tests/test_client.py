from datetime import date
from pathlib import Path

import httpx
import respx

from apd.client import BASE, ApdClient

FIXTURE = (Path(__file__).parent / "fixtures" / "card_mail_theft.html").read_text(
    encoding="utf-8"
)


@respx.mock
def test_search_window_acks_then_searches():
    respx.get(f"{BASE}/index.cfm").mock(return_value=httpx.Response(200, text="index"))
    respx.post(f"{BASE}/alt_search.cfm").mock(
        return_value=httpx.Response(200, text="acked")
    )
    respx.get(f"{BASE}/search2.cfm").mock(
        return_value=httpx.Response(200, text=FIXTURE)
    )
    with ApdClient() as client:
        html = client.search_window(date(2026, 7, 15), numdays=0)
    assert "2026-5010278" in html


@respx.mock
def test_lookup_case():
    respx.get(f"{BASE}/index.cfm").mock(return_value=httpx.Response(200, text="index"))
    respx.post(f"{BASE}/alt_search.cfm").mock(
        return_value=httpx.Response(200, text="acked")
    )
    respx.get(f"{BASE}/search2.cfm").mock(
        return_value=httpx.Response(200, text=FIXTURE)
    )
    with ApdClient() as client:
        html = client.lookup_case("2026-5010278")
    assert "MAIL THEFT" in html
