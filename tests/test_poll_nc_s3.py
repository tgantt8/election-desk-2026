import io
import json
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import poll_nc_s3 as p  # noqa: E402

HDR = ["County", "Election Date", "Precinct", "Contest Group ID", "Contest Type", "Contest Name", "Choice", "Choice Party",
       "Vote For", "Election Day", "Early Voting", "Absentee by Mail", "Provisional", "Total Votes", "Real Precinct"]


def _row(county, prec, contest, choice, party, ed, ev, ab, pr):
    return [county, "11/03/2026", prec, "1", "S", contest, choice, party, "1", str(ed), str(ev), str(ab), str(pr), str(ed + ev + ab + pr), "Y"]


ROWS = [
    _row("ALAMANCE", "P1", "US SENATE", "Alice Dem", "DEM", 10, 20, 5, 1),
    _row("ALAMANCE", "P1", "US SENATE", "Bob Rep", "REP", 8, 15, 4, 0),
    _row("ALAMANCE", "P1", "US SENATE", "Write-In (Miscellaneous)", "", 0, 1, 0, 0),
    _row("ALAMANCE", "P2", "US SENATE", "Alice Dem", "DEM", 0, 0, 0, 0),
    _row("ALAMANCE", "P2", "US SENATE", "Bob Rep", "REP", 0, 0, 0, 0),
    _row("WAKE", "P9", "US SENATE", "Alice Dem", "DEM", 30, 10, 2, 0),
    _row("WAKE", "P9", "US SENATE", "Bob Rep", "REP", 5, 5, 1, 0),
    _row("WAKE", "P9", "US HOUSE OF REPRESENTATIVES DISTRICT 01", "Carl Dem", "DEM", 3, 0, 0, 0),
    _row("WAKE", "P9", "NC HOUSE OF REPRESENTATIVES DISTRICT 003", "Dee Rep", "REP", 4, 0, 0, 0),
    _row("WAKE", "P9", "NC SUPERIOR COURT JUDGE", "Judge J", "", 99, 0, 0, 0),
]


def make_zip(rows=ROWS, trailing=True, enc="utf-8"):
    lines = ["\t".join(HDR + ([""] if trailing else []))]
    lines += ["\t".join(r + ([""] if trailing else [])) for r in rows]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("results_pct_20261103.txt", ("\n".join(lines) + "\n").encode(enc))
    return buf.getvalue()


def test_map_contest_id():
    assert p.map_contest_id("US SENATE") == "us-senate-NC"
    assert p.map_contest_id("US HOUSE OF REPRESENTATIVES DISTRICT 01") == "us-house-NC-01"
    assert p.map_contest_id("US HOUSE OF REPRESENTATIVES DISTRICT 1") == "us-house-NC-01"
    assert p.map_contest_id("NC STATE SENATE DISTRICT 12") == "nc-sd-12"
    assert p.map_contest_id("NC HOUSE OF REPRESENTATIVES DISTRICT 003") == "nc-hd-003"
    assert p.map_contest_id("NC SUPERIOR COURT JUDGE") == "nc-other-nc-superior-court-judge"


def test_party():
    assert p.normalize_party("DEM") == ("D", False)
    assert p.normalize_party("REP") == ("R", False)
    assert p.normalize_party("UNA") == ("I", False)
    assert p.normalize_party("WRI") == (None, True)
    assert p.normalize_party("") == (None, False)


def test_read_rows_strips_trailing_column_and_latin1():
    assert len(p.read_rows(make_zip())) == len(ROWS)
    rows = [_row("A", "P", "US SENATE", "Jos\xe9 Dem", "DEM", 1, 0, 0, 0)]
    got = p.read_rows(make_zip(rows, enc="latin-1"))
    assert got[0]["Choice"] == "Jos\xe9 Dem"


def _recs():
    return p.build_records(p.read_rows(make_zip()), p.SOURCE_ID, "snap1", "2026-11-04T01:00:00Z", "2026-11-04T00:59:00Z", "http://x")


def test_aggregation_state():
    recs = _recs()
    assert {r["contest_id"] for r in recs} == {"us-senate-NC", "us-house-NC-01", "nc-hd-003"}
    st = {r["candidate"]: r for r in recs if r["contest_id"] == "us-senate-NC" and r["unit"] == "state"}
    a = st["Alice Dem"]
    assert a["votes"] == 36 + 42 and a["party"] == "D" and a["party_raw"] == "DEM"
    assert a["votes_by_mode"] == {"Election Day": 40, "Early Voting": 30, "Absentee by Mail": 7, "Provisional": 1}
    assert a["reporting"] == {"pct": 66.67, "units_reporting": 2, "units_total": 3, "method": "precincts_with_votes"}
    assert a["unofficial"] is True and a["is_official"] is False and a["vendor_is_winner"] is None
    assert a["election_date"] == "2026-11-03" and "county" not in a
    wi = st["Write-In (Miscellaneous)"]
    assert wi["is_write_in"] is True and wi["party"] is None and wi["votes"] == 1
    assert not st["Bob Rep"]["is_write_in"]


def test_county_rows_senate_only():
    recs = _recs()
    cty = [r for r in recs if r["unit"] == "county"]
    assert cty and all(r["contest_id"] == "us-senate-NC" for r in cty)
    al = next(r for r in cty if r["county"] == "ALAMANCE" and r["candidate"] == "Alice Dem")
    assert al["votes"] == 36 and al["reporting"]["units_total"] == 2 and al["reporting"]["units_reporting"] == 1
    wk = next(r for r in cty if r["county"] == "WAKE" and r["candidate"] == "Bob Rep")
    assert wk["votes"] == 11
    # county rows sum to the statewide row
    tot = sum(r["votes"] for r in cty if r["candidate"] == "Alice Dem")
    assert tot == next(r for r in recs if r["unit"] == "state" and r["candidate"] == "Alice Dem" and r["contest_id"] == "us-senate-NC")["votes"]


class FakeResp:
    def __init__(self, code, content=b"", headers=None):
        self.status_code, self.content, self.headers = code, content, headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSess:
    def __init__(self, resp):
        self.resp, self.sent = resp, None

    def get(self, url, headers=None, timeout=None):
        self.sent = headers
        return self.resp


def test_run_304_error_and_200(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(p, "ops_log", lambda ev, **k: calls.append(ev))
    monkeypatch.setattr(p, "update_source_health", lambda *a, **k: None)
    monkeypatch.setattr(p, "record_snapshot", lambda sid, layer, raw, st, keep_raw=True, note="": {"id": "s:1", "fetched_at": "2026-11-04T01:00:00Z"})
    sf = str(tmp_path / "state.json")
    json.dump({"etag": '"abc"', "last_modified": "Tue, 03 Nov 2026 23:00:00 GMT"}, open(sf, "w"))
    src = {"id": "enr_nc_s3_results", "url": "http://x/zip"}
    s = FakeSess(FakeResp(304))
    assert p.run(src, state_file=sf, dry_run=True, session=s)["status"] == "unchanged"
    assert s.sent["If-None-Match"] == '"abc"' and s.sent["If-Modified-Since"].startswith("Tue")
    assert p.run(src, state_file=sf, dry_run=True, session=FakeSess(FakeResp(503)))["status"] == "error"
    assert calls == ["nc_s3_unchanged", "nc_s3_failed"]
    ok = FakeResp(200, make_zip(), {"Last-Modified": "Tue, 03 Nov 2026 23:00:00 GMT", "ETag": '"new"'})
    r = p.run(src, state_file=sf, dry_run=True, session=FakeSess(ok))
    assert r["status"] == "ok" and r["records"] > 0
