from apd.db import Database
from helpers import sample_incident


def test_upsert_incident_idempotent(tmp_path):
    db = Database(tmp_path / "t.sqlite")
    row = sample_incident()
    assert db.upsert_incident(row) is True
    assert db.upsert_incident(row) is False
    updated = sample_incident(area_command="NORTH EAST")
    assert db.upsert_incident(updated) is True
    assert db.count_incidents() == 1
    got = db.get_incident(row["case_number"])
    assert got["area_command"] == "NORTH EAST"
    assert got["property"] == [{"status": "STOLEN", "type": "OTHER"}]
    db.close()
