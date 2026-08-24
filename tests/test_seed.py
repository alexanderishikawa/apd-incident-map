import gzip
import json

from apd.db import Database
from apd.export import export_site_data
from apd.geocode import address_key
from apd.seed import seed_from_export
from helpers import sample_incident


def _export_one(tmp_path):
    db = Database(tmp_path / "src.sqlite")
    row = sample_incident()
    db.upsert_incident(row)
    key = address_key(row)
    assert key
    db.upsert_geocode(key, status="ok", lat=30.24, lon=-97.77)
    out = tmp_path / "data"
    export_site_data(db, out)
    db.close()
    return out


def test_seed_from_uncompressed_json(tmp_path):
    out = _export_one(tmp_path)
    dest = Database(tmp_path / "dest.sqlite")
    stats = seed_from_export(dest, out, skip_if_nonempty=False)
    assert stats["seeded"] == 1
    assert stats["incidents"] == 1
    dest.close()


def test_seed_from_gzip_when_json_missing(tmp_path):
    out = _export_one(tmp_path)
    (out / "incidents.json").unlink()
    dest = Database(tmp_path / "dest.sqlite")
    stats = seed_from_export(dest, out, skip_if_nonempty=False)
    assert stats["seeded"] == 1
    assert dest.count_incidents() == 1
    dest.close()


def test_seed_gzip_roundtrip_matches_json(tmp_path):
    out = _export_one(tmp_path)
    with gzip.open(out / "incidents.json.gz", "rt", encoding="utf-8") as f:
        gz_rows = json.load(f)
    raw_rows = json.loads((out / "incidents.json").read_text(encoding="utf-8"))
    assert gz_rows == raw_rows
