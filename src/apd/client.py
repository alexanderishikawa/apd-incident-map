from __future__ import annotations

from datetime import date

import httpx

BASE = "https://services.austintexas.gov/police/reports"
DEFAULT_UA = "apd-incident-map/0.1 (+https://github.com/local/apd-incident-map; research)"


class ApdClient:
    def __init__(
        self,
        client: httpx.Client | None = None,
        user_agent: str = DEFAULT_UA,
    ):
        self._owns = client is None
        self.client = client or httpx.Client(
            headers={
                "User-Agent": user_agent,
                "Accept": "text/html,application/xhtml+xml",
            },
            follow_redirects=True,
            timeout=120.0,
        )
        self._acked = False

    def close(self) -> None:
        if self._owns:
            self.client.close()

    def __enter__(self) -> ApdClient:
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def acknowledge(self) -> None:
        self.client.get(f"{BASE}/index.cfm")
        r = self.client.post(
            f"{BASE}/alt_search.cfm",
            data={"agreement": "Acknowledge"},
        )
        r.raise_for_status()
        self._acked = True

    def ensure_ack(self) -> None:
        if not self._acked:
            self.acknowledge()

    def _get_search(self, params: dict) -> str:
        self.ensure_ack()
        r = self.client.get(f"{BASE}/search2.cfm", params=params)
        r.raise_for_status()
        html = r.text
        if 'name="agreement"' in html or "Acknowledge" in html and "alt_search" in r.url.path:
            self._acked = False
            self.acknowledge()
            r = self.client.get(f"{BASE}/search2.cfm", params=params)
            r.raise_for_status()
            html = r.text
        if "unexpected error" in html.lower():
            raise RuntimeError(f"APD search2 unexpected error for params={params}")
        return html

    def search_window(self, start: date, numdays: int = 0) -> str:
        if numdays < 0 or numdays > 6:
            raise ValueError("numdays must be 0..6")
        return self._get_search(
            {
                "startdate": start.isoformat(),
                "numdays": str(numdays),
                "choice": "criteria",
                "Submit": "Submit",
            }
        )

    def lookup_case(self, caseno: str) -> str:
        return self._get_search(
            {"choice": "case", "caseno": caseno, "Submit": "Submit"}
        )
