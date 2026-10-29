"""Offline tests for poll_enhanced_voting.py. Fixtures are real Enhanced Voting payloads (see fixtures/README.md). No network."""
import copy
import gzip
import json
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.dont_write_bytecode = True
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
import poll_enhanced_voting as pev  # noqa: E402
import common  # noqa: E402  (tools/common.py, found by the poller)

FX = os.path.join(os.path.dirname(HERE), "fixtures", "enhanced_voting")


@pytest.fixture(autouse=True)
def fresh_limiter(monkeypatch):
    """The module-level RateLimiter is process-global state; isolate every test from it (and never really sleep)."""
    monkeypatch.setattr(pev, "_LIMITER", pev.RateLimiter())
    monkeypatch.setattr(pev, "INTRA_CYCLE_GAP_S", 0)


def load(name):
    with open(os.path.join(FX, name), "rb") as fh:
        return fh.read()


WA_EL, WA_BI = load("wa_election_20261103.json"), load("wa_ballot_items_20261103_subset.json")
GA_EL, GA_BI = load("ga_election_06162026GeneralPrimaryRunoff.json"), load("ga_ballot_items_06162026GeneralPrimaryRunoff_first3.json")

ALLOWED_KEYS = {
    "layer", "contest_id", "contest_name", "contest_type", "ballot_item_id", "unit", "candidate", "candidate_id", "is_write_in",
    "party", "party_raw", "votes", "votes_by_mode", "contest_vote_total", "reporting", "as_of", "is_official", "unofficial",
    "election_id", "election_date", "is_primary", "source_id", "source_url", "snapshot_id", "fetched_at", "vendor_is_winner",
}
FORBIDDEN_KEYS = {"status", "call", "called", "called_for", "called_for_party", "projected", "projection", "winner", "result",
                  "is_winner", "calls", "race_call"}


# ------------------------------------------------------------------ parsing: WA zero-vote shell

@pytest.fixture(scope="module")
def wa_recs():
    el = json.loads(WA_EL)
    return pev.parse_ballot_items(WA_BI, "WA", "wa_enhanced_voting", "2026-10-29T17:00:00Z", snapshot_id="snap-1", election=el)


def test_wa_zero_votes_unofficial(wa_recs):
    payload = json.loads(WA_BI)
    n_opts = sum(len(i["summaryResults"]["ballotOptions"]) for i in payload["data"])
    assert len(wa_recs) == n_opts == 29
    assert all(r["votes"] == 0 and isinstance(r["votes"], int) for r in wa_recs)
    assert all(r["is_official"] is False and r["unofficial"] is True for r in wa_recs)
    assert all(r["contest_vote_total"] == 0 for r in wa_recs)
    assert {r["as_of"] for r in wa_recs} == {"2026-10-22T15:55:34.6947355Z"}
    assert all(r["source_id"] == "wa_enhanced_voting" and r["snapshot_id"] == "snap-1" and r["fetched_at"] for r in wa_recs)
    assert all(r["unit"] == "state" and r["layer"] == "results" for r in wa_recs)
    assert all(r["votes_by_mode"] is None for r in wa_recs)  # WA publishes no vote-type split in summaryResults


def test_wa_has_no_us_senate_contest(wa_recs):
    assert not [r for r in wa_recs if r["contest_id"].startswith("us-senate-")]
    assert "us-senate-WA" not in {r["contest_id"] for r in wa_recs}


def test_wa_contest_id_mapping(wa_recs):
    ids = {r["contest_name"]: r["contest_id"] for r in wa_recs}
    assert ids["Congressional District 1 - U.S. Representative"] == "us-house-WA-01"
    assert ids["Congressional District 2 - U.S. Representative"] == "us-house-WA-02"
    assert ids["Congressional District 7 - U.S. Representative"] == "us-house-WA-07"
    assert ids["Congressional District 9 - U.S. Representative"] == "us-house-WA-09"
    # no statewide Governor/Senate in WA 2026; the state-legislative / judicial / measure items fall through to ev:
    assert ids["Initiative Measure No. IP26-645"] == "ev:WA:01000000-c099-693d-d4e5-08df1b1fe635"
    assert ids["Legislative District 7 - State Senator"].startswith("ev:WA:")
    assert ids["Supreme Court - Justice Position #01"].startswith("ev:WA:")
    assert not [i for i in ids.values() if i.startswith("gov-")]


def test_wa_reporting_and_parties(wa_recs):
    cd1 = [r for r in wa_recs if r["contest_id"] == "us-house-WA-01"]
    assert [r["candidate"] for r in cd1] == ["Suzan DelBene", "Mary Silva", "Write-in"]
    assert [r["party"] for r in cd1] == ["D", "R", None]
    assert cd1[0]["party_raw"] == {"abbreviation": "DEM", "name": "(Prefers Democratic Party)"}
    assert cd1[2]["party_raw"] is None and cd1[2]["is_write_in"] is True
    assert cd1[0]["reporting"] == {"units_reporting": 0, "units_total": 2, "pct": 0.0}
    meas = [r for r in wa_recs if r["contest_name"] == "Initiative Measure No. IP26-645"]
    assert [r["candidate"] for r in meas] == ["Yes", "No"]
    assert meas[0]["contest_type"] == "ballot_measure" and meas[0]["party"] is None
    assert meas[0]["reporting"]["units_total"] == 39
    sen = {r["candidate"]: r for r in wa_recs if r["contest_name"] == "Legislative District 7 - State Senator"}
    assert sen["Ronald L McCoy"]["party"] == "I" and sen["Shelly Short"]["party"] == "R"
    webster = next(r for r in wa_recs if r["candidate"] == "Thomas Franklin Webster")
    assert webster["party"] == "other" and webster["party_raw"]["abbreviation"] == "NO"


# ------------------------------------------------------------------ parsing: GA real counts

@pytest.fixture(scope="module")
def ga_recs():
    el = json.loads(GA_EL)
    return pev.parse_ballot_items(GA_BI, "GA", "ga_enhanced_voting", "2026-10-29T17:00:00Z", snapshot_id="snap-g", election=el)


def test_ga_counts_tie_out(ga_recs):
    payload = json.loads(GA_BI)
    assert len(payload["data"]) == 3 and payload["totalRecordCount"] == 27  # trimmed fixture, envelope verbatim
    by_contest = {}
    for r in ga_recs:
        assert isinstance(r["votes"], int) and r["votes"] > 0
        by_contest.setdefault(r["contest_id"], []).append(r)
    assert len(by_contest) == 3
    for cid, rs in by_contest.items():
        total = rs[0]["contest_vote_total"]
        assert total > 0 and sum(r["votes"] for r in rs) == total, cid
    senate = by_contest["us-senate-GA-primary-runoff-rep"]
    assert {r["candidate"]: r["votes"] for r in senate} == {"Mike Collins": 390174, "Derek Dooley": 312339}
    assert sum(r["votes"] for r in senate) == 702513


def test_ga_vote_types_and_reporting(ga_recs):
    for r in ga_recs:
        assert list(r["votes_by_mode"]) == ["Election Day", "Advance Voting", "Absentee by Mail", "Provisional"]
        assert sum(r["votes_by_mode"].values()) == r["votes"]
        assert r["reporting"] == {"units_reporting": 159, "units_total": 159, "pct": 100.0}
        assert r["party"] == "R" and r["party_raw"]["abbreviation"] == "REP"
        assert r["is_official"] is True and r["unofficial"] is False  # publisher flag copied verbatim, nothing inferred
        assert r["is_primary"] is True and r["election_date"] == "2026-06-16"
        assert r["as_of"] == "2026-08-20T14:15:31.593143Z"


def test_ga_primary_runoff_ids_do_not_collide_with_general(ga_recs):
    ids = {r["contest_name"]: r["contest_id"] for r in ga_recs}
    assert ids["US Senate - Rep"] == "us-senate-GA-primary-runoff-rep"
    assert ids["Governor - Rep"] == "gov-GA-primary-runoff-rep"
    assert ids["Lieutenant Governor - Rep"].startswith("ev:GA:")  # Lt. Governor is not Governor
    assert "us-senate-GA" not in ids.values() and "gov-GA" not in ids.values()


def test_without_election_object_is_conservative():
    recs = pev.parse_ballot_items(GA_BI, "GA", "x", "t")
    assert all(r["is_official"] is False for r in recs)
    assert {r["contest_id"] for r in recs if r["contest_name"] == "US Senate - Rep"} == {"us-senate-GA"}
    assert all(r["as_of"] == "2026-08-20T14:15:31.593143Z" for r in recs)


@pytest.mark.parametrize("name,state,expected", [
    ("US Senate - Rep", "GA", "us-senate-GA"),
    ("United States Senator", "MI", "us-senate-MI"),
    ("U.S. Senate (Special Election)", "OH", "us-senate-OH-special"),
    ("US Senate Special - Unexpired Term", "FL", "us-senate-FL-special"),
    ("State Senate - District 7", "GA", "ev:GA:ID"),
    ("Special State Senate - District 7/ Especial Senador Estatal del Distrito 7", "GA", "ev:GA:ID"),
    ("Governor", "GA", "gov-GA"),
    ("Governor - Dem", "GA", "gov-GA"),
    ("Lieutenant Governor", "GA", "ev:GA:ID"),
    ("US House of Representatives - District 1 - Dem", "GA", "us-house-GA-01"),
    ("U.S. Representative - District 12", "UT", "us-house-UT-12"),
    ("Congressional District 5 - U.S. Representative", "WA", "us-house-WA-05"),
    ("U.S. House - At Large", "VT", "us-house-VT-AL"),
    ("State House of Representatives - District 47 - Rep", "GA", "ev:GA:ID"),
    ("Legislative District 6 - State Representative Pos. 1", "WA", "ev:WA:ID"),
    # Virginia / Utah naming seen on the live Nov 3 2026 shells
    ("Member, United States Senate", "VA", "us-senate-VA"),
    ("Member, House of Representatives (1st District)", "VA", "us-house-VA-01"),
    ("Member, House of Representatives (11th District)", "VA", "us-house-VA-11"),
    ("Member, House of Representatives (11th District)", "MI", "ev:MI:ID"),  # bare form is VA-only
    ("Member, House of Delegates (20th District)", "VA", "ev:VA:ID"),
    ("U.S. House District 1", "UT", "us-house-UT-01"),
    ("Constitutional Amendment A", "UT", "ev:UT:ID"),
])
def test_map_contest_id(name, state, expected):
    assert pev.map_contest_id(name, state, "ID") == expected


# ------------------------------------------------------------------ vendor isWinner is never a call

def test_vendor_is_winner_is_kept_but_never_a_call():
    # test-only mutation of a real payload in memory: flip the vendor flag to prove it is carried as a raw flag and nothing else
    payload = json.loads(GA_BI)
    payload["data"][0]["summaryResults"]["ballotOptions"][0]["isWinner"] = True
    recs = pev.parse_ballot_items(payload, "GA", "x", "t", election=json.loads(GA_EL))
    flagged = [r for r in recs if r["vendor_is_winner"] is True]
    assert len(flagged) == 1 and flagged[0]["candidate"] == "Mike Collins"
    for r in recs:
        assert set(r) <= ALLOWED_KEYS
        assert not (set(r) & FORBIDDEN_KEYS)
        assert r["is_official"] is True  # publisher flag only; the winner flag did not change any status
    # leader ordering, certification wording etc. never derived
    assert not any("call" in k or "status" in k for r in recs for k in r)


def test_wa_and_ga_records_have_only_allowed_keys(wa_recs, ga_recs):
    for r in wa_recs + ga_recs:
        assert set(r) <= ALLOWED_KEYS and not (set(r) & FORBIDDEN_KEYS)


# ------------------------------------------------------------------ run(): stubbed session, temp root

class Resp:
    def __init__(self, content, status=200):
        self.content, self.status_code = content, status


class StubSession:
    """Serves an election object and a ballot-items payload by URL suffix; records every request."""

    def __init__(self, election, ballots, status=200):
        self.election, self.ballots, self.status, self.calls = election, ballots, status, []

    def get(self, url, headers=None, timeout=None):
        self.calls.append((url, dict(headers or {})))
        if self.status != 200:
            return Resp(b"", self.status)
        return Resp(self.ballots if url.endswith("/ballot-items") else self.election)


def src(**kw):
    s = {"host": "results.sos.ga.gov", "slug": "georgia", "election_id": "06162026GeneralPrimaryRunoff", "state": "GA",
         "source_id": "ga_enhanced_voting", "min_interval_s": 0}
    s.update(kw)
    return s


def jl(path):
    with open(path, encoding="utf-8") as fh:
        return [json.loads(x) for x in fh if x.strip()]


def n_calls(sess, suffix):
    return len([c for c in sess.calls if c[0].endswith(suffix)])


def test_run_records_then_change_detector_skips(tmp_path):
    root, sid = str(tmp_path), "ga_enhanced_voting"
    sess = StubSession(GA_EL, GA_BI)
    repo_before = (common.ROOT, common.DATA)
    r1 = pev.run(src(), session=sess, root=root)
    assert (common.ROOT, common.DATA) == repo_before  # injected root is restored
    assert r1["status"] == "recorded" and r1["records"] == 6 and r1["parse_status"] == "ok_partial"  # 3 of 27 items in fixture
    out = os.path.join(root, "data", "results", f"{sid}.jsonl")
    rows = jl(out)
    assert len(rows) == 6 and {r["snapshot_id"] for r in rows} == {r1["snapshot_id"]}
    snaps = jl(os.path.join(root, "data", "snapshots", "index.jsonl"))
    assert len(snaps) == 1 and snaps[0]["layer"] == "results"
    import hashlib
    assert snaps[0]["raw_hash"] == hashlib.sha256(GA_BI).hexdigest()
    with gzip.open(os.path.join(root, snaps[0]["raw_path"]), "rb") as fh:
        assert fh.read() == GA_BI  # raw bytes kept verbatim
    assert all(c[1]["User-Agent"] == common.USER_AGENT for c in sess.calls)
    assert n_calls(sess, "/ballot-items") == 1 and len(sess.calls) == 2
    before = open(out, "rb").read()

    # identical election object -> the heavy call is skipped: no new snapshot row, no new records
    r2 = pev.run(src(), session=sess, root=root)
    assert r2["status"] == "skipped_unchanged"
    assert n_calls(sess, "/ballot-items") == 1 and len(sess.calls) == 3
    assert len(jl(os.path.join(root, "data", "snapshots", "index.jsonl"))) == 1
    assert open(out, "rb").read() == before


def test_run_same_bytes_new_publish_records_snapshot_but_not_duplicate_records(tmp_path):
    root, sid = str(tmp_path), "ga_enhanced_voting"
    sess = StubSession(GA_EL, GA_BI)
    pev.run(src(), session=sess, root=root)
    # election object republished (new lastUpdated) but ballot-items bytes are identical
    el2 = json.loads(GA_EL)
    el2["lastUpdated"] = "2026-08-21T00:00:00.0000000Z"
    sess.election = json.dumps(el2, separators=(",", ":")).encode()
    r = pev.run(src(), session=sess, root=root)
    assert r["status"] == "recorded" and r["parse_status"] == "ok_unchanged" and r["records"] == 0
    snaps = jl(os.path.join(root, "data", "snapshots", "index.jsonl"))
    assert len(snaps) == 2 and snaps[0]["raw_hash"] == snaps[1]["raw_hash"]  # same hash recorded twice (the pull is on record)
    assert len(jl(os.path.join(root, "data", "results", f"{sid}.jsonl"))) == 6  # records not duplicated
    assert n_calls(sess, "/ballot-items") == 2


def test_run_is_append_only_when_payload_changes(tmp_path):
    root, sid = str(tmp_path), "ga_enhanced_voting"
    sess = StubSession(GA_EL, GA_BI)
    pev.run(src(), session=sess, root=root)
    out = os.path.join(root, "data", "results", f"{sid}.jsonl")
    first = open(out, "rb").read()
    # second pull: a different real subset of the same payload (first 2 of the 3 items) and a new election-object stamp
    two = json.loads(GA_BI)
    two["data"] = two["data"][:2]
    sess.ballots = json.dumps(two, separators=(",", ":"), ensure_ascii=False).encode()
    el2 = json.loads(GA_EL)
    el2["asOf"] = "2026-08-21T00:00:00.0000000Z"
    sess.election = json.dumps(el2, separators=(",", ":")).encode()
    r = pev.run(src(), session=sess, root=root)
    assert r["status"] == "recorded" and r["records"] == 4
    after = open(out, "rb").read()
    assert after.startswith(first) and len(jl(out)) == 6 + 4  # earlier lines untouched, new lines appended
    snaps = jl(os.path.join(root, "data", "snapshots", "index.jsonl"))
    assert len(snaps) == 2 and snaps[0]["raw_hash"] != snaps[1]["raw_hash"]
    assert {x["snapshot_id"] for x in jl(out)} == {s["id"] for s in snaps}


def test_run_writes_only_the_results_layer(tmp_path):
    pev.run(src(), session=StubSession(GA_EL, GA_BI), root=str(tmp_path))
    data = tmp_path / "data"
    top = set(os.listdir(data))
    assert top <= {"results", "snapshots", "raw", "ops_log.jsonl", "sources.json"}
    for layer in ("polls", "ratings", "early_vote", "calls", "scenarios"):
        assert layer not in top
    assert not any("call" in json.dumps(x).lower() for x in jl(str(data / "results" / "ga_enhanced_voting.jsonl")))


def test_run_dry_run_writes_nothing(tmp_path):
    sess = StubSession(WA_EL, WA_BI)
    r = pev.run(src(host="results.votewa.gov", slug="washington", election_id="20261103", state="WA", source_id="wa_enhanced_voting"),
                dry_run=True, session=sess, root=str(tmp_path))
    assert r["status"] == "dry_run" and r["records"] == 29 and r["ballot_items"] == 11
    assert os.listdir(tmp_path) == []
    # and the next real run is not fooled into skipping
    r2 = pev.run(src(host="results.votewa.gov", slug="washington", election_id="20261103", state="WA", source_id="wa_enhanced_voting"),
                 session=sess, root=str(tmp_path))
    assert r2["status"] == "recorded" and r2["records"] == 29
    rows = jl(str(tmp_path / "data" / "results" / "wa_enhanced_voting.jsonl"))
    assert all(r["votes"] == 0 and r["is_official"] is False for r in rows)
    assert not [r for r in rows if r["contest_id"].startswith("us-senate-")]


def test_run_cross_process_rate_limit(tmp_path):
    t0 = datetime(2026, 11, 3, 23, 0, 0, tzinfo=timezone.utc)
    sess = StubSession(GA_EL, GA_BI)
    s = src(min_interval_s=120)
    assert pev.run(s, session=sess, root=str(tmp_path), now=lambda: t0)["status"] == "recorded"
    n = len(sess.calls)
    r = pev.run(s, session=sess, root=str(tmp_path), now=lambda: t0 + timedelta(seconds=30))
    assert r["status"] == "rate_limited" and 89 < r["retry_in_s"] <= 90 and len(sess.calls) == n  # no request made
    r = pev.run(s, session=sess, root=str(tmp_path), now=lambda: t0 + timedelta(seconds=121), limiter=pev.RateLimiter())
    assert r["status"] == "skipped_unchanged"


def test_run_http_error_and_parse_error(tmp_path):
    root = str(tmp_path)
    r = pev.run(src(), session=StubSession(GA_EL, GA_BI, status=503), root=root)
    assert r["status"] == "error" and "503" in r["error"]
    assert not os.path.exists(os.path.join(root, "data", "results", "ga_enhanced_voting.jsonl"))
    health = common.load_json(os.path.join(root, "data", "sources.json"))
    assert health == {"sources": []}  # unregistered source: nothing to mark, nothing crashes
    # ballot-items that is JSON but not the expected shape: raw bytes are still snapshotted, no records appended
    bad = b'{"unexpected": true}'
    r = pev.run(src(), session=StubSession(GA_EL, bad), root=root)
    assert r["status"] == "error" and r["error"].startswith("parse_error")
    snaps = jl(os.path.join(root, "data", "snapshots", "index.jsonl"))
    assert len(snaps) == 1 and snaps[0]["parse_status"].startswith("parse_error")
    assert not os.path.exists(os.path.join(root, "data", "results", "ga_enhanced_voting.jsonl"))
    # a failed heavy pull does not advance the change detector
    r = pev.run(src(), session=StubSession(GA_EL, GA_BI), root=root)
    assert r["status"] == "recorded" and r["records"] == 6


def test_fetch_functions_build_urls_and_respect_interval():
    sess = StubSession(GA_EL, GA_BI)
    lim = pev.RateLimiter()
    raw, el = pev.fetch_election("results.sos.ga.gov", "georgia", "E1", sess, limiter=lim, min_interval_s=0)
    raw2, bi = pev.fetch_ballot_items("results.sos.ga.gov", "georgia", "E1", sess, limiter=lim, min_interval_s=0)
    assert [c[0] for c in sess.calls] == [
        "https://results.sos.ga.gov/results/public/api/elections/georgia/E1",
        "https://results.sos.ga.gov/results/public/api/elections/georgia/E1/ballot-items"]
    assert raw == GA_EL and raw2 == GA_BI and el["isOfficialResults"] is True and len(bi["data"]) == 3
    sleeps = []
    import time as _t
    orig = _t.sleep
    _t.sleep = sleeps.append
    try:
        lim2 = pev.RateLimiter()
        pev.fetch_election("h", "s", "e", sess, limiter=lim2, min_interval_s=120)
        pev.fetch_election("h", "s", "e", sess, limiter=lim2, min_interval_s=120)
        pev.fetch_election("other-host", "s", "e", sess, limiter=lim2, min_interval_s=120)
    finally:
        _t.sleep = orig
    assert len(sleeps) == 1 and 119 < sleeps[0] <= 120  # second hit on the same host waits; a different host does not
