import json
import sqlite3
from pathlib import Path

root = Path(__file__).resolve().parents[1]
c = sqlite3.connect(root / "data" / "incidents.sqlite")
cache = dict(c.execute("select status, count(*) from geocode_cache group by status"))
n = c.execute(
    """
    select count(*) from (
      select distinct upper(trim(address_raw)), coalesce(trim(zip), '')
      from incidents
      where address_raw is not null and trim(address_raw) != ''
    )
    """
).fetchone()[0]
ok = cache.get("ok", 0)
fail = cache.get("fail", 0)
meta = json.loads((root / "site/public/data/meta.json").read_text(encoding="utf-8"))
inc_path = root / "site/public/data/incidents.json"
print("incidents", c.execute("select count(*) from incidents").fetchone()[0])
print("cache", cache)
print("distinct_addr", n)
print("pending_est", max(0, n - ok - fail))
print("export_geocoded", meta.get("geocoded_count"), "/", meta.get("count"))
print("export_bytes", inc_path.stat().st_size)
