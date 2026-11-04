import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import poll_npr_ap as p  # noqa: E402

NC = {"test": False, "id": "35984", "office": "S", "officeName": "U.S. Senate", "seat": "Class II", "raceCallStatus": "Called", "state": "NC",
      "updated": 1793757431826, "reporting": 701, "precincts": 2626, "stateName": "North Carolina", "previousParty": "GOP", "called": True,
      "flippedSeat": True, "winnerParty": "Dem", "eevp": 0.7,
      "candidates": [{"first": "Roy", "last": "Cooper", "party": "Dem", "id": "34471", "votes": 1737424, "avotes": 1625217, "winner": "X", "winnerDateTime": "2026-11-04T01:23:59.591Z", "percent": 0.6192},
                     {"first": "Michael", "last": "Whatley", "party": "GOP", "id": "169297", "votes": 1017143, "percent": 0.3625},
                     {"first": "", "last": "Other", "party": "Other", "id": "other-35984", "votes": 51173, "count": 2, "percent": 0.0182}]}
MI = {"test": False, "id": "24463", "office": "S", "officeName": "U.S. Senate", "seat": "Class II", "raceCallStatus": "Too Early to Call", "state": "MI",
      "updated": 1793757409667, "reporting": 96, "precincts": 3946, "stateName": "Michigan", "previousParty": "Dem", "eevp": 0.126,
      "candidates": [{"first": "Abdul", "last": "El-Sayed", "party": "Dem", "id": "67151", "votes": 346846, "percent": 0.558},
                     {"first": "Mike", "last": "Rogers", "party": "GOP", "id": "1169", "votes": 264935, "percent": 0.4262}]}
FL = {**NC, "id": "84979", "state": "FL", "stateName": "Florida", "seat": "Class III", "called": False, "raceCallStatus": "Too Early to Call",
      "candidates": [{"first": "Ashley", "last": "Moody", "party": "GOP", "votes": 10}]}
TEST = {**MI, "id": "1", "test": True}


class FakeResp:
    def __init__(self, doc):
        self.content = json.dumps(doc).encode()
        self.headers = {"ETag": "x"}

    def raise_for_status(self):
        pass

    def json(self):
        return json.loads(self.content)


class FakeSession:
    def __init__(self, docs):
        self.docs = docs

    def get(self, url, headers=None, timeout=None):
        return FakeResp(self.docs[url.rsplit("/", 1)[-1]])


def test_contest_ids():
    assert p.contest_id(NC) == "us-senate-NC"
    assert p.contest_id(FL) == "us-senate-FL-special"
    assert p.contest_id({"office": "G", "state": "mi"}) == "gov-MI"
    assert p.contest_id({"office": "H", "state": "MI", "seatNumber": "10"}) == "us-house-MI-10"
    assert p.contest_id({"office": "H", "state": "VT", "seatNumber": "1"}) == "us-house-VT-AL"


def test_call_only_when_called():
    c = p.call_record(NC, "us-senate-NC", "u", "2026-11-04T01:30:00Z")
    assert c["called_for"] == "Roy Cooper" and c["called_for_party"] == "D" and c["called_at"] == "2026-11-04T01:23:59.591Z" and c["status"] == "Projected"
    assert p.call_record(MI, "us-senate-MI", "u", "t") is None


def test_run_writes_calls_once_and_results_on_change(tmp_path, monkeypatch):
    monkeypatch.setattr(p, "DATA", str(tmp_path))
    os.makedirs(tmp_path / "results"); os.makedirs(tmp_path / "calls")
    monkeypatch.setattr(p, "record_snapshot", lambda *a, **k: {"id": "snap", "fetched_at": "t"})
    monkeypatch.setattr(p, "update_source_health", lambda *a, **k: None)
    monkeypatch.setattr(p, "ops_log", lambda *a, **k: None)
    sess = FakeSession({"senate.json": {"results": [NC, MI, TEST]}})
    st = str(tmp_path / "state.json")
    out = p.run(state_file=st, session=sess, files={"senate": "data/senate.json"}, now="2026-11-04T01:30:00Z")
    assert out["new_calls"] == 1 and out["result_rows"] == 5  # 3 NC + 2 MI candidates; the test race is skipped
    calls = [json.loads(l) for l in open(tmp_path / "calls" / "calls.jsonl")]
    assert len(calls) == 1 and calls[0]["contest"] == "us-senate-NC" and calls[0]["outlet"] == "AP (via NPR)"
    rows = [json.loads(l) for l in open(tmp_path / "results" / "results_ap_via_npr.jsonl")]
    assert {r["contest_id"] for r in rows} == {"us-senate-NC", "us-senate-MI"}
    assert all(r["unofficial"] and r["tabulator"] == "AP via NPR" for r in rows)
    other = next(r for r in rows if r["party_raw"] == "Other")
    assert other["candidate"] == "Other (AP aggregate)" and other["party"] == "O"
    # second pass, nothing moved: no new rows, no duplicate call
    out2 = p.run(state_file=st, session=sess, files={"senate": "data/senate.json"}, now="2026-11-04T01:33:00Z")
    assert out2["new_calls"] == 0 and out2["result_rows"] == 0
    # AP pulls the call back: one retraction record
    NC2 = {**NC, "called": False, "raceCallStatus": "Too Early to Call", "updated": NC["updated"] + 1,
           "candidates": [{k: v for k, v in c.items() if k not in ("winner", "winnerDateTime")} for c in NC["candidates"]]}
    out3 = p.run(state_file=st, session=FakeSession({"senate.json": {"results": [NC2, MI]}}), files={"senate": "data/senate.json"}, now="2026-11-04T01:36:00Z")
    assert out3["retractions"] == 1 and out3["result_rows"] == 3
    calls = [json.loads(l) for l in open(tmp_path / "calls" / "calls.jsonl")]
    assert calls[-1]["status"] == "retracted" and calls[-1]["contest"] == "us-senate-NC"
