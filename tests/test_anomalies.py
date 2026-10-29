import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from anomalies import detect  # noqa: E402

T0, T1, T2 = "2026-11-03T20:30:00Z", "2026-11-03T21:00:00Z", "2026-11-03T23:00:00Z"


def rows(votes_a, votes_b, total, ballots, complete=False, unit="Warren City, Precinct 50", contest="HD-58"):
    return [
        {"contest": contest, "unit": unit, "candidate": "A", "mode": "TOTAL", "votes": votes_a, "complete": complete},
        {"contest": contest, "unit": unit, "candidate": "B", "mode": "TOTAL", "votes": votes_b, "complete": complete},
        {"contest": contest, "unit": unit, "candidate": None, "mode": "TOTAL", "votes": total, "ballots": ballots, "complete": complete},
    ]


def test_seeded_decrease_fires():
    prev = rows(400, 300, 700, 720)
    cur = rows(395, 300, 695, 720)  # seeded bad row: candidate A went down
    flags, _ = detect(prev, cur, "snap2", T1)
    assert any(f["type"] == "decrease" and "395" in f["detail"] for f in flags)
    assert all("fraud" not in f["detail"].lower() and "confirm with the Clerk" in f["detail"] for f in flags)


def test_votes_exceed_ballots_fires():
    flags, _ = detect([], rows(400, 350, 750, 720), "s1", T1)
    assert any(f["type"] == "votes_gt_ballots" for f in flags)


def test_complete_then_change_fires():
    flags, _ = detect(rows(400, 300, 700, 720, complete=True), rows(410, 300, 710, 720, complete=True), "s2", T1)
    assert any(f["type"] == "complete_changed" for f in flags)


def test_stall_fires_after_90_minutes():
    a = rows(100, 100, 200, 210, unit="P1")
    b = rows(100, 100, 200, 210, unit="P2")
    flags, last = detect([], a + b, "s1", T0)
    assert not flags
    a2 = rows(150, 120, 270, 280, unit="P1")
    flags, last = detect(a + b, a2 + b, "s2", T1, last_change_at=last)
    assert not any(f["type"] == "stalled" for f in flags)
    a3 = rows(180, 130, 310, 320, unit="P1")
    flags, last = detect(a2 + b, a3 + b, "s3", T2, last_change_at=last)
    assert any(f["type"] == "stalled" and f["unit"] == "P2" for f in flags)


def test_clean_update_is_quiet():
    flags, _ = detect(rows(400, 300, 700, 720), rows(420, 310, 730, 750), "s2", T1)
    assert flags == []
