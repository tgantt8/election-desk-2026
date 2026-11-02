"""Offline tests for the Michigan state legislative seats: contest definitions (data/contests/mi_legislature_2026.json),
the OnPoint ratings rows, multi-county summing with the "N of M counties" state, the chamber tally (calls layer only),
manual-entry validation and party fill, per-contest handling of hand entries in the results builder and the anomaly step.
Numbers below are test values in temporary structures; nothing under data/ is written."""
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import build_results_site as brs  # noqa: E402
import manual_entry  # noqa: E402
import mi_legislature as mil  # noqa: E402
import run_anomalies as ra  # noqa: E402
from build_site_data import RATING_SCALE  # noqa: E402

REG = mil.load_registry()
MACOMB = {c["id"]: c for c in json.load(open(os.path.join(ROOT, "data", "contests", "macomb_2026.json")))["contests"]}
SEATS = {s["seat_id"]: s for s in REG["seats"]}
HOUSE_COMP = [27, 28, 29, 31, 42, 44, 46, 49, 51, 52, 54, 55, 57, 58, 61, 62, 68, 72, 86, 88, 92, 96, 107, 109]
SENATE_COMP = [9, 12, 13, 30, 32, 35, 37]


# ---------------------------------------------------------------- definitions
def test_competitive_set_is_complete_and_ids_are_padded():
    comp = {s["seat_id"] for s in REG["seats"] if "competitive" in s["sets"]}
    assert comp == {f"mi-hd-{n:03d}" for n in HOUSE_COMP} | {f"mi-sd-{n:02d}" for n in SENATE_COMP}
    for s in REG["seats"]:
        assert mil.valid_seat_id(s["seat_id"])
        if s["scope"] == "statewide":
            assert s["contest_id"] == s["seat_id"]


def test_macomb_only_seats_reuse_the_macomb_contest():
    for sid, mid in (("mi-hd-058", "macomb-hd58"), ("mi-hd-061", "macomb-hd61"), ("mi-hd-062", "macomb-hd62"), ("mi-sd-24", "macomb-sd24")):
        s = SEATS[sid]
        assert s["scope"] == "macomb_only" and s["contest_id"] == mid and [p["county"] for p in s["counties"]] == ["Macomb"]
        assert mid in s["call_ids"] and sid in s["call_ids"]
    # SD-24 lies entirely in Macomb under the 2024 remedial Senate plan: no statewide copy, no second contest
    assert not any(s["contest_id"] == "mi-sd-24" for s in REG["seats"])
    assert len([c for c in mil.contests_index(REG) if c in ("macomb-hd58", "mi-hd-058")]) == 1


def test_every_macomb_legislative_contest_is_tracked_once():
    mac_leg = {cid for cid in MACOMB if cid.startswith(("macomb-hd", "macomb-sd"))}
    in_reg = {s.get("macomb_contest_id") for s in REG["seats"] if s.get("macomb_contest_id")}
    assert mac_leg == in_reg
    for s in REG["seats"]:
        if s.get("macomb_contest_id"):
            assert "Macomb" in [p["county"] for p in s["counties"]]
            assert "macomb_ballot" in s["sets"]
            mp = [p for p in s["counties"] if p["county"] == "Macomb"][0]
            assert mp["portion_contest_id"] == s["macomb_contest_id"]
        else:
            assert "Macomb" not in [p["county"] for p in s["counties"]]


def test_county_coverage_and_county_directory():
    for s in REG["seats"]:
        assert s["counties"] and s["county_coverage"] == "CONFIRMED"
        assert abs(sum(p["area_share_pct"] for p in s["counties"]) - 100) < 0.2, s["seat_id"]
        if s["scope"] == "statewide":
            for p in s["counties"]:
                c = REG["counties"][p["county"]]
                assert c["status"] in ("CONFIRMED", "NOT_CONFIRMED")
                assert (c["results_url"] or "").startswith("https://") if c["status"] == "CONFIRMED" else c["results_url"] is None
    # spot checks against the MICRC plans in effect for 2026
    assert [p["county"] for p in SEATS["mi-hd-031"]["counties"]] == ["Lenawee", "Monroe", "Washtenaw", "Wayne"]
    assert [p["county"] for p in SEATS["mi-sd-13"]["counties"]] == ["Oakland"]
    assert [p["county"] for p in SEATS["mi-sd-12"]["counties"]] == ["Macomb", "St. Clair", "Wayne"]
    assert REG["chambers"]["house"] == {"name": "Michigan House of Representatives", "seats": 110, "majority": 56}
    assert REG["chambers"]["senate"] == {"name": "Michigan Senate", "seats": 38, "majority": 20}


def test_macomb_ballot_matches_the_clerk_template_parser_output():
    pytest.importorskip("pdfplumber")
    import macomb_compact_pdf as mc
    parsed = mc.parse_compact_pdf(os.path.join(ROOT, "fixtures", "macomb_2026_general_unofficial_summary_template.pdf"))
    ids = {mc.compact_contest_id(c) for c in parsed["contests"]}
    leg = {i for i in ids if i.startswith(("macomb-hd", "macomb-sd"))}
    assert leg == {s["macomb_contest_id"] for s in REG["seats"] if s.get("macomb_contest_id")}


def test_onpoint_ratings_are_label_date_link_only():
    rows = []
    for ch in ("house", "senate"):
        rows += [json.loads(x) for x in open(os.path.join(ROOT, "data", "ratings", f"ratings_onpoint_mi_{ch}.jsonl"))]
    assert len(rows) == 31
    races = {r["race"] for r in rows}
    assert races == {s["contest_id"] for s in REG["seats"] if "competitive" in s["sets"]}
    for r in rows:
        assert r["rater"] == "OnPoint Politics" and r["date"] == "2026-11-02" and r["url"].startswith("https://onpointpolitics.us/forecast/legislatures/mi/")
        assert r["label"] in RATING_SCALE
        assert not any(k in r for k in ("probability", "p_dem", "votes", "projected", "forecast", "margin"))
    assert {r["label"] for r in rows if r["race"] == "macomb-hd58"} == {"Lean D"}


# ---------------------------------------------------------------- summing county by county
def _rec(snap, contest, county, cand, votes, unit="County total", mode="TOTAL", party=None, as_of="2026-11-04T02:00:00Z"):
    r = {"contest_id": contest, "unit": unit, "mode": mode, "candidate": cand, "votes": votes, "snapshot_id": f"manual_results:{as_of}:{snap:0>12}",
         "source_id": "manual_results", "as_of": as_of, "party": party}
    if county:
        r["county"] = county
    return r


def _card(cards, sid):
    return [c for c in cards if c["seat_id"] == sid][0]


def test_multi_county_seat_sums_entered_counties_and_never_zero_fills():
    reg = {"seats": [dict(SEATS["mi-hd-031"], candidates=[{"name": "Shannon Dare Wayne", "party": "D"}, {"name": "Laura Perry", "party": "R"}])],
           "counties": REG["counties"], "chambers": REG["chambers"]}
    man = [
        _rec("a1", "mi-hd-031", "Monroe", "Wayne", 100, as_of="2026-11-04T01:00:00Z"), _rec("a1", "mi-hd-031", "Monroe", "Perry", 90, as_of="2026-11-04T01:00:00Z"),
        _rec("a2", "mi-hd-031", "Wayne", "Shannon Dare Wayne", 50, as_of="2026-11-04T01:10:00Z"), _rec("a2", "mi-hd-031", "Wayne", "Laura Perry", 40, as_of="2026-11-04T01:10:00Z"),
        _rec("a3", "mi-hd-031", "Washtenaw", "Wayne", 30, as_of="2026-11-04T01:20:00Z"), _rec("a3", "mi-hd-031", "Washtenaw", "Perry", 20, as_of="2026-11-04T01:20:00Z"),
        # a later Wayne entry replaces the earlier one (append-only: the newest entry for a county wins)
        _rec("a4", "mi-hd-031", "Wayne", "Shannon Dare Wayne", 70, as_of="2026-11-04T01:30:00Z"), _rec("a4", "mi-hd-031", "Wayne", "Laura Perry", 60, as_of="2026-11-04T01:30:00Z"),
    ]
    c = _card(mil.seat_cards(reg, {"manual_results": man}, []), "mi-hd-031")
    assert (c["counties_entered"], c["counties_total"]) == (3, 4)
    assert c["entered_label"].startswith("3 of 4 counties entered") and not c["complete_counties"]
    tot = {k["name"]: k["votes"] for k in c["candidates"]}
    assert tot == {"Shannon Dare Wayne": 200, "Laura Perry": 170}
    len_ = [p for p in c["counties"] if p["county"] == "Lenawee"][0]
    assert len_["entered"] is False and len_["candidates"] is None
    assert {k["party"] for k in c["candidates"]} == {"D", "R"}
    assert c["status"] == "Too early"


def test_seat_with_no_entries_reads_no_results_entered():
    c = _card(mil.seat_cards(REG, {}, []), "mi-sd-32")
    assert c["counties_entered"] == 0 and c["counties_total"] == 5
    assert c["entered_label"] == "no results entered" and c["candidates"] is None and c["margin"] is None


def test_total_line_is_used_alone_and_modes_are_not_summed():
    reg = {"seats": [SEATS["mi-hd-044"]], "counties": REG["counties"], "chambers": REG["chambers"]}
    man = [_rec("b1", "mi-hd-044", "Calhoun", "Haadsma", 10, unit="Precinct 1"), _rec("b1", "mi-hd-044", "Calhoun", "Haadsma", 15, unit="Precinct 2"),
           _rec("b1", "mi-hd-044", "Calhoun", "Haadsma", 25, unit="Total"), _rec("b1", "mi-hd-044", "Calhoun", "Frisbie", 30, unit="Total")]
    c = _card(mil.seat_cards(reg, {"manual_results": man}, []), "mi-hd-044")
    assert {k["name"]: k["votes"] for k in c["candidates"]} == {"Jim Haadsma": 25, "Steve Frisbie": 30}  # canonical names from the SoS list
    assert {k["name"]: k["party"] for k in c["candidates"]} == {"Jim Haadsma": "D", "Steve Frisbie": "R"}
    man2 = [_rec("b2", "mi-hd-044", "Calhoun", "Haadsma", 10, unit="Precinct 1"), _rec("b2", "mi-hd-044", "Calhoun", "Haadsma", 15, unit="Precinct 2")]
    assert _card(mil.seat_cards(reg, {"manual_results": man2}, []), "mi-hd-044")["candidates"][0]["votes"] == 25
    man3 = [_rec("b3", "mi-hd-044", "Calhoun", "Haadsma", 10, mode="AVCB")]
    assert _card(mil.seat_cards(reg, {"manual_results": man3}, []), "mi-hd-044")["counties_entered"] == 0


def _pdf(snap_time, contest, rows):
    sid = f"{mil.PDF_SOURCE}:{snap_time}:abcdefabcdef"
    return [{"contest_id": contest, "unit": "county", "mode": "TOTAL", "candidate": n, "party": p, "votes": v, "write_in": w, "snapshot_id": sid,
             "source_id": mil.PDF_SOURCE, "as_of": "Wed, 04 Nov 2026 01:00:00 GMT"} for n, p, v, w in rows]


def test_macomb_portion_comes_from_the_clerk_pdf_and_a_newer_hand_entry_wins():
    pdf = _pdf("2026-11-04T01:00:00Z", "macomb-hd57", [("Tom Turner", "D", 900, False), ("Thomas E. Kuhn", "R", 1000, False), ("Write-in", None, 5, True)])
    pdf += _pdf("2026-11-04T01:00:00Z", "macomb-hd58", [("Katrina Manetta", "D", 500, False), ("Ron Robinson", "R", 400, False)])
    man = [_rec("c1", "mi-hd-057", "Oakland", "Turner", 300, as_of="2026-11-04T01:05:00Z"), _rec("c1", "mi-hd-057", "Oakland", "Kuhn", 200, as_of="2026-11-04T01:05:00Z")]
    cards = mil.seat_cards(REG, {mil.PDF_SOURCE: pdf, "manual_results": man}, [], MACOMB)
    c = _card(cards, "mi-hd-057")
    assert (c["counties_entered"], c["counties_total"]) == (2, 2) and c["complete_counties"]
    assert {k["name"]: k["votes"] for k in c["candidates"]} == {"Tom Turner": 1200, "Thomas E. Kuhn": 1200}  # write-ins not summed
    mp = [p for p in c["counties"] if p["county"] == "Macomb"][0]
    assert mp["via"] == "Macomb Clerk summary PDF"
    h58 = _card(cards, "mi-hd-058")
    assert h58["entered_label"] == "1 of 1 counties entered" and h58["margin"] == round(100 * 100 / 900, 2)
    later = man + [_rec("c2", "mi-hd-057", "Macomb", "Turner", 950, as_of="2026-11-04T02:00:00Z"),
                   _rec("c2", "mi-hd-057", "Macomb", "Kuhn", 1010, as_of="2026-11-04T02:00:00Z")]
    c2 = _card(mil.seat_cards(REG, {mil.PDF_SOURCE: pdf, "manual_results": later}, [], MACOMB), "mi-hd-057")
    assert {k["name"]: k["votes"] for k in c2["candidates"]} == {"Tom Turner": 1250, "Thomas E. Kuhn": 1210}


def test_macomb_portion_only_seat_label():
    pdf = _pdf("2026-11-04T01:00:00Z", "macomb-hd63", [("A Candidate", "D", 10, False), ("B Candidate", "R", 12, False)])
    c = _card(mil.seat_cards(REG, {mil.PDF_SOURCE: pdf}, [], MACOMB), "mi-hd-063")
    assert c["scope"] == "macomb_portion_only" and c["counties_entered"] == 1 and c["counties_total"] == 1
    assert "Macomb portion only" in c["entered_label"]
    assert [p["tracked"] for p in c["counties"] if p["county"] == "St. Clair"] == [False]


# ---------------------------------------------------------------- calls and the chamber tally
def _call(contest, party, at, status="Projected", outlet="AP"):
    return {"contest": contest, "outlet": outlet, "called_for": "x", "called_for_party": party, "called_at": at, "status": status}


def test_chamber_tally_counts_calls_only():
    calls = [_call("mi-hd-29", "D", "2026-11-04T03:00:00Z"),            # unpadded id normalizes to mi-hd-029
             _call("macomb-hd58", "R", "2026-11-04T03:05:00Z"),         # Macomb-only seat called on its Macomb id
             _call("mi-hd-001", "D", "2026-11-04T03:06:00Z"),           # an untracked seat can be called too
             _call("mi-sd-32", "R", "2026-11-04T03:07:00Z"), _call("mi-sd-32", None, "2026-11-04T03:30:00Z", status="retracted"),
             _call("us-senate-MI", "D", "2026-11-04T03:08:00Z")]       # not a legislative seat
    t = mil.chamber_tally(REG, calls)
    h, s = t["house"], t["senate"]
    assert (h["seats"], h["majority"], s["seats"], s["majority"]) == (110, 56, 38, 20)
    assert h["called"] == {"d": 2, "r": 1, "other": 0}
    assert h["counting_tracked"] == h["tracked_total"] - 2 == 31 and h["counting_competitive"] == 22
    assert h["not_tracked"] == 110 - 33 - 1
    assert s["called"] == {"d": 0, "r": 0, "other": 0} and s["counting_tracked"] == 11 and s["not_tracked"] == 27
    assert sum(h["called"].values()) + h["counting_tracked"] + h["not_tracked"] == 110
    assert not any(k in json.dumps(t).lower() for k in ("projected_control", "probability", "sim"))


def test_seat_status_follows_a_call_on_any_seat_id():
    calls = [_call("mi-hd-058", "R", "2026-11-04T03:05:00Z")]
    c = _card(mil.seat_cards(REG, {}, calls, MACOMB), "mi-hd-058")
    assert c["status"].startswith("Projected (AP") and c["called_for_party"] == "R"
    assert brs.status_for("macomb-hd58", calls).startswith("Projected (AP")


# ---------------------------------------------------------------- manual entry validation
def test_statewide_entry_needs_a_county_of_the_seat_and_total_mode():
    contests = mil.contests_index(REG)
    ok = {"contest_id": "mi-hd-031", "county": "monroe county", "records": [{"contest_id": "mi-hd-031", "unit": "Total", "candidate": "Perry", "votes": 5}]}
    manual_entry.check_results_payload(ok, contests, REG)
    assert ok["records"][0]["county"] == "Monroe"
    with pytest.raises(SystemExit):
        manual_entry.check_results_payload({"contest_id": "mi-hd-031", "records": [{"contest_id": "mi-hd-031", "candidate": "Perry", "votes": 5}]}, contests, REG)
    with pytest.raises(SystemExit):
        manual_entry.check_results_payload({"contest_id": "mi-hd-031", "county": "Oakland", "records": [{"contest_id": "mi-hd-031", "candidate": "Perry", "votes": 5}]}, contests, REG)
    with pytest.raises(SystemExit):
        manual_entry.check_results_payload({"contest_id": "mi-hd-031", "county": "Monroe", "mode": "AVCB", "records": [{"contest_id": "mi-hd-031", "candidate": "Perry", "votes": 5}]}, contests, REG)
    st = {"contest_id": "mi-sd-12", "county": "St Clair", "records": [{"contest_id": "mi-sd-12", "candidate": "Hertel", "votes": 5}]}
    manual_entry.check_results_payload(st, contests, REG)
    assert st["records"][0]["county"] == "St. Clair"
    # Macomb contests are unchanged: no county needed
    manual_entry.check_results_payload({"contest_id": "macomb-hd58", "records": [{"contest_id": "macomb-hd58", "unit": "Warren City, Precinct 50", "candidate": "Manetta", "votes": 5}]}, contests, REG)


def test_calls_fill_party_from_the_seat_and_refuse_bad_ids():
    contests = mil.contests_index(REG)
    p = {"contest": "mi-hd-57", "outlet": "AP", "called_for": "Tom Turner", "called_at": "2026-11-04T03:00:00Z"}
    manual_entry.prepare_call(p, contests, REG)
    assert p["contest"] == "mi-hd-057" and p["called_for_party"] == "D"
    p = {"contest": "macomb-hd58", "outlet": "AP", "called_for": "Ron Robinson", "called_at": "2026-11-04T03:00:00Z"}
    manual_entry.prepare_call(p, contests, REG)
    assert p["called_for_party"] == "R"
    with pytest.raises(SystemExit):
        manual_entry.prepare_call({"contest": "mi-hd-111", "outlet": "AP", "called_for": "x", "called_for_party": "D", "called_at": "2026-11-04T03:00:00Z"}, contests, REG)
    with pytest.raises(SystemExit):
        manual_entry.prepare_call({"contest": "mi-hd-001", "outlet": "AP", "called_for": "Somebody", "called_at": "2026-11-04T03:00:00Z"}, contests, REG)
    with pytest.raises(SystemExit):
        manual_entry.prepare_call({"contest": "mi-hd-001", "outlet": "", "called_for_party": "D", "called_at": "2026-11-04T03:00:00Z"}, contests, REG)
    q = {"contest": "mi-hd-001", "outlet": "AP", "called_for": "Somebody", "called_for_party": "dem", "called_at": "2026-11-04T03:00:00Z"}
    manual_entry.prepare_call(q, contests, REG)
    assert q["called_for_party"] == "D"
    r = {"contest": "mi-sd-32", "outlet": "AP", "status": "retracted", "called_at": "2026-11-04T03:00:00Z"}
    manual_entry.prepare_call(r, contests, REG)  # a retraction needs no party
    us = {"contest": "us-senate-MI", "outlet": "AP", "called_for": "x", "called_at": "2026-11-04T03:00:00Z"}
    manual_entry.prepare_call(us, contests, REG)  # national ids unchanged
    assert us.get("called_for_party") is None


# ---------------------------------------------------------------- hand entries are per contest
def test_results_builder_keeps_each_contests_latest_hand_entry():
    recs = [dict(_rec("d1", "macomb-hd58", None, "Manetta", 10, unit="P1"), snapshot_id="s1"),
            dict(_rec("d2", "macomb-sd24", None, "Sako", 7, unit="P1"), snapshot_id="s2"),
            dict(_rec("d3", "macomb-hd58", None, "Manetta", 12, unit="P1"), snapshot_id="s3")]
    got = {cid: (cur, prev) for cid, cur, prev in brs.contest_snapshots(recs, per_contest=True)}
    assert set(got) == {"macomb-hd58", "macomb-sd24"}
    assert got["macomb-hd58"][0][0]["votes"] == 12 and got["macomb-hd58"][1][0]["votes"] == 10
    assert got["macomb-sd24"][0][0]["votes"] == 7 and got["macomb-sd24"][1] == []
    poll = {cid for cid, _, _ in brs.contest_snapshots(recs, per_contest=False)}
    assert poll == {"macomb-hd58"}  # a poller file: its last snapshot only (unchanged behaviour)


def test_anomaly_step_compares_a_contest_with_its_own_previous_entry(tmp_path, monkeypatch):
    d = tmp_path / "data"
    (d / "results").mkdir(parents=True)
    rows = [dict(_rec("e1", "macomb-hd58", None, "Manetta", 400, unit="Warren City, Precinct 50"), snapshot_id="s1"),
            dict(_rec("e2", "mi-hd-031", "Monroe", "Perry", 50), snapshot_id="s2"),
            dict(_rec("e3", "macomb-hd58", None, "Manetta", 395, unit="Warren City, Precinct 50"), snapshot_id="s3")]
    with open(d / "results" / "manual_results.jsonl", "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    monkeypatch.setattr(ra, "DATA", str(d))
    monkeypatch.setattr(ra, "STATE", str(d / "results" / ".state_anomalies.json"))
    monkeypatch.setattr(ra, "FLAGS", str(d / "anomalies.jsonl"))
    monkeypatch.setattr(ra, "ops_log", lambda *a, **k: None)
    flags = ra.run(now_iso="2026-11-04T03:00:00Z")
    assert [f["type"] for f in flags] == ["decrease"] and flags[0]["contest"] == "macomb-hd58"
    assert "confirm with the Clerk" in flags[0]["detail"]


def test_normalize_contest_ids():
    assert mil.normalize_contest_id("mi-hd-29") == "mi-hd-029"
    assert mil.normalize_contest_id("MI-SD-9") == "mi-sd-09"
    assert mil.normalize_contest_id("macomb-hd058") == "macomb-hd58"
    assert mil.normalize_contest_id("us-senate-MI") == "us-senate-MI"
    assert not mil.valid_seat_id("mi-hd-111") and not mil.valid_seat_id("mi-sd-39") and mil.valid_seat_id("mi-sd-38")


def test_candidate_matching_handles_shared_surnames():
    hd68 = SEATS["mi-hd-068"]["candidates"]
    assert [k["name"] for k in hd68 if "Martin" in k["name"]] == ["David W. Martin", "Deanna L Martin"]
    assert mil.match_candidate(hd68, "Deanna Martin")["party"] == "L"
    assert mil.match_candidate(hd68, "MARTIN, DAVID W.")["party"] == "R"
    assert mil.match_candidate(hd68, "Martin") is None  # ambiguous: never guessed
    assert mil.match_candidate(hd68, "Schlinker")["party"] == "D"
    contests = mil.contests_index(REG)
    with pytest.raises(SystemExit):  # an ambiguous name without a party is refused, not guessed
        manual_entry.prepare_call({"contest": "mi-hd-068", "outlet": "AP", "called_for": "Martin", "called_at": "2026-11-04T03:00:00Z"}, contests, REG)
    p = {"contest": "mi-hd-068", "outlet": "AP", "called_for": "Matt Schlinker", "called_at": "2026-11-04T03:00:00Z"}
    manual_entry.prepare_call(p, contests, REG)
    assert p["called_for_party"] == "D"


def test_statewide_seats_carry_the_official_candidate_list():
    for s in REG["seats"]:
        if s["scope"] == "statewide":
            assert s["candidates"] and s["candidates_source"]["url"].startswith("https://mi-boe.entellitrak.com/")
            assert {"D", "R"} <= {k["party"] for k in s["candidates"]}
    assert REG["counties"]["Wayne"]["status"] == "NOT_CONFIRMED" and REG["counties"]["Wayne"]["results_url"] is None
    assert SEATS["mi-hd-031"]["county_pages"] == "not confirmed: Wayne"
