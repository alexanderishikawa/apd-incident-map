import gzip
import json

from apd.db import Database
from apd.export import export_site_data
from apd.geocode import address_key
from helpers import sample_incident


def test_export_writes_meta_and_incidents(tmp_path):
    db = Database(tmp_path / "t.sqlite")
    row = sample_incident()
    db.upsert_incident(row)
    key = address_key(row)
    assert key
    db.upsert_geocode(key, status="ok", lat=30.24, lon=-97.77)
    out = tmp_path / "data"
    meta = export_site_data(db, out)
    assert meta["count"] == 1
    assert meta["geocoded_count"] == 1
    assert "MAIL THEFT" in meta["offenses"]
    assert "78704" in meta["zips"]
    assert (out / "incidents.json").exists()
    assert (out / "incidents.json.gz").exists()
    assert (out / "meta.json").exists()
    raw = json.loads((out / "incidents.json").read_text(encoding="utf-8"))
    with gzip.open(out / "incidents.json.gz", "rt", encoding="utf-8") as f:
        assert json.load(f) == raw
    db.close()
