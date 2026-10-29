import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from poll_votehub import dedupe_key, race_id, to_records  # noqa: E402

FX = json.load(open(os.path.join(ROOT, "fixtures", "votehub_polls_sample.json")))["items"]


def test_fixture_is_real_and_maps():
    recs = to_records(FX, "polls_votehub_api", "snap", "2026-10-29T17:15:00Z")
    assert len(FX) >= 100 and len(recs) >= 100
    races = {r["race"] for r in recs}
    assert "us-senate-MI" in races and "gov-MI" in races and "generic-ballot-2026" in races
    assert all(r["url"] and r["pollster"] and r["field_end"] for r in recs)
    assert all(r["grade"] is None and r["grade_source"] is None for r in recs)  # no grades in this feed; stays ungraded


def test_dedupe_key_ignores_republication_noise():
    p = next(x for x in FX if x["poll_type"] == "us-senator")
    rid = race_id(p)
    k1 = dedupe_key(p, rid)
    p2 = dict(p, id="different-source-id", url="https://example.org/mirror", created_at="2026-10-30")
    assert dedupe_key(p2, rid) == k1
    p3 = dict(p, population="lv" if p["population"] != "lv" else "rv")
    assert dedupe_key(p3, rid) != k1  # one row per population


def test_primary_polls_are_not_mapped_to_general():
    assert race_id({"poll_type": "us-senator", "subject": "2026 Texas Republican"}) is None
    assert race_id({"poll_type": "us-senator", "subject": "2026 Florida Special"}) == "us-senate-FL-special"
    assert race_id({"poll_type": "governor", "subject": "2026 Michigan"}) == "gov-MI"
