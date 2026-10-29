"""Offline tests for tools/run_anomalies.py (the step that runs the anomaly rules after every poll or manual entry) and the
manual-entry party fill. Uses a temporary data directory; nothing under data/ is touched."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import manual_entry  # noqa: E402
import run_anomalies as ra  # noqa: E402


def _rows(snap, a, b, ballots=None, unit="Warren City, Precinct 50"):
    base = {"contest_id": "macomb-hd58", "unit": unit, "mode": "TOTAL", "snapshot_id": snap, "source_id": "manual_results"}
    out = [dict(base, candidate="Manetta", party="D", votes=a), dict(base, candidate="Robinson", party="R", votes=b)]
    if ballots is not None:
        out.append(dict(base, candidate=None, votes=a + b, ballots=ballots))
    return out


def _setup(tmp_path, recs):
    d = tmp_path / "data"
    (d / "results").mkdir(parents=True)
    with open(d / "results" / "manual_results.jsonl", "w") as fh:
        for r in recs:
            fh.write(json.dumps(r) + "\n")
    ra.DATA, ra.STATE, ra.FLAGS = str(d), str(d / "results" / ".state_anomalies.json"), str(d / "anomalies.jsonl")
    return d


def test_rows_for_builds_unit_totals_with_ballots():
    rows = ra.rows_for(_rows("s1", 400, 300, ballots=720))
    tot = [r for r in rows if r["candidate"] is None][0]
    assert tot["votes"] == 700 and tot["ballots"] == 720 and tot["unit"] == "Warren City, Precinct 50"
    assert len([r for r in rows if r["candidate"]]) == 2


def test_decrease_between_snapshots_opens_one_flag_once(tmp_path, monkeypatch):
    d = _setup(tmp_path, _rows("s1", 400, 300, 720) + _rows("s2", 395, 300, 720))
    monkeypatch.setattr(ra, "ops_log", lambda *a, **k: None)
    flags = ra.run(now_iso="2026-11-03T21:00:00Z")
    assert [f["type"] for f in flags] == ["decrease"] and "confirm with the Clerk" in flags[0]["detail"] and "fraud" not in flags[0]["detail"].lower()
    assert flags[0]["source_id"] == "manual_results" and flags[0]["contest"] == "macomb-hd58"
    assert len(open(d / "anomalies.jsonl").read().splitlines()) == 1
    assert ra.run(now_iso="2026-11-03T21:05:00Z") == []  # same snapshot pair is not re-run
    assert len(open(d / "anomalies.jsonl").read().splitlines()) == 1


def test_clean_increase_opens_nothing(tmp_path, monkeypatch):
    _setup(tmp_path, _rows("s1", 100, 90, 200) + _rows("s2", 400, 300, 720))
    monkeypatch.setattr(ra, "ops_log", lambda *a, **k: None)
    assert ra.run(now_iso="2026-11-03T21:00:00Z") == []


def test_votes_over_ballots_flags(tmp_path, monkeypatch):
    _setup(tmp_path, _rows("s1", 400, 350, 720))
    monkeypatch.setattr(ra, "ops_log", lambda *a, **k: None)
    assert [f["type"] for f in ra.run(now_iso="2026-11-03T21:00:00Z")] == ["votes_gt_ballots"]


def test_party_fill_from_contest_list():
    c = {"id": "macomb-hd58", "candidates": [{"name": "Nicole Manetta", "party": "D"}, {"name": "Ron Robinson", "party": "R"}]}
    assert manual_entry.match_party(c, "Manetta") == "D" and manual_entry.match_party(c, "Ron Robinson") == "R" and manual_entry.match_party(c, "Smith") is None
    assert manual_entry.norm_party("DEM") == "D" and manual_entry.norm_party("rep") == "R" and manual_entry.norm_party("") is None
