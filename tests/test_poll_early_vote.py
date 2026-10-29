"""Offline tests for the early-vote pollers. Fixtures are real public source files (fixtures/ncsbe, fixtures/florida, fixtures/uf)."""
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import poll_early_vote as pev  # noqa: E402

NC_CSV = os.path.join(ROOT, "fixtures", "ncsbe", "absentee_counts_state_20261103_fetched-2026-10-29.csv")
NC_PDF = os.path.join(ROOT, "fixtures", "ncsbe", "2026-10-29 Daily Absentee Stats Report - 2026 General.pdf")
FL_DIR = os.path.join(ROOT, "fixtures", "florida")
UF_CSV = os.path.join(ROOT, "fixtures", "uf", "US_2026-10-29.csv")
FORBIDDEN = {"vote_choice", "modeled_party", "candidate", "votes", "winner", "status", "call"}


def rb(p):
    with open(p, "rb") as fh:
        return fh.read()


# ------------------------------------------------------------------ North Carolina

def test_nc_csv_ties_out_to_the_daily_pdf():
    c = pev.parse_nc_counts(rb(NC_CSV))
    p = pev.parse_nc_daily_pdf(rb(NC_PDF))
    assert c["total"] == p["total"] == 2_150_024
    assert c["in_person"] == p["in_person"] == 2_073_467
    assert c["mail"] == p["civilian"] + p["military"] + p["overseas"] == 76_557
    assert c["by_party"]["DEM"] == 856_352 and c["by_party"]["REP"] == 543_174 and c["by_party"]["UNA"] == 744_744
    assert p["through"] == "10/28/2026" and p["published"] == "10/29/2026"
    assert (p["cmp_2022_early"], p["cmp_2022_mail"], p["cmp_2022_total"]) == (1_472_047, 113_941, 1_585_988)


def test_nc_records_carry_source_as_of_and_official_baseline_only():
    c = pev.parse_nc_counts(rb(NC_CSV))
    p = pev.parse_nc_daily_pdf(rb(NC_PDF))
    recs = pev.nc_records(c, p, "ev_nc_absentee_counts_csv", "snap-1", "2026-10-29T18:00:00Z", pdf_url="https://example.invalid/daily.pdf")
    assert all(r["layer"] == "early_vote" and r["source"] and r["as_of"] == "2026-10-28" and r["url"] for r in recs)
    assert not any(FORBIDDEN & set(r) for r in recs)
    tot = next(r for r in recs if r["mode"] == "total" and r["party"] is None)
    assert tot["value"] == 2_150_024 and tot["vs_2022"] == 1_585_988 and "Comparison to 2022" in tot["vs_2022_source"]
    party = [r for r in recs if r["party"]]
    assert party and all(r["vs_2022"] is None for r in party)  # no official same-point party comparison → no baseline
    assert all(r["vs_2024"] is None for r in recs)


def test_nc_bad_row_fails_closed():
    raw = rb(NC_CSV).decode().replace("CIVILIAN,DEM,FEMALE,ASIAN,HISPANIC or LATINO,1", "CIVILIAN,DEM,FEMALE,ASIAN,HISPANIC or LATINO,x,1")
    with pytest.raises(ValueError):
        pev.parse_nc_counts(raw.encode())
    with pytest.raises(ValueError):
        pev.parse_nc_counts(b"a,b,c\n1,2,3\n")


def test_nc_pdf_mismatch_withholds_the_comparison(monkeypatch, tmp_path):
    """If the CSV and the PDF disagree, the CSV is shown and the PDF's 2022 comparison is withheld (nothing is interpolated)."""
    import common
    monkeypatch.setattr(common, "DATA", str(tmp_path / "data"))
    monkeypatch.setattr(pev, "DATA", str(tmp_path / "data"))
    (tmp_path / "data" / "snapshots").mkdir(parents=True)
    import shutil
    shutil.copy(os.path.join(ROOT, "data", "sources.json"), tmp_path / "data" / "sources.json")
    pdf = rb(NC_PDF)
    bad_csv = rb(NC_CSV).decode().replace("CIVILIAN,DEM,FEMALE,ASIAN,HISPANIC or LATINO,1\r\n", "CIVILIAN,DEM,FEMALE,ASIAN,HISPANIC or LATINO,2\r\n").encode()
    res = pev.run_nc({"id": "ev_nc_absentee_counts_csv", "poller": "ev_nc_s3"}, csv_raw=bad_csv, pdf_raw=pdf)
    assert res["status"] == "recorded"
    rows = common.read_jsonl(str(tmp_path / "data" / "early_vote" / "ev_nc_absentee_counts_csv.jsonl"))
    tot = next(r for r in rows if r["mode"] == "total" and r["party"] is None)
    assert tot["value"] == 2_150_025 and tot["vs_2022"] is None


# ------------------------------------------------------------------ Florida

@pytest.mark.skipif(not os.path.isdir(FL_DIR), reason="Florida fixtures not present")
def test_fl_state_totals_and_counties():
    raws = {k: rb(os.path.join(FL_DIR, f"Stats_49894_{k}_2026-10-29.txt")) for k in pev.FL_FILES}
    parsed = {k: pev.parse_fl_txt(raws[k], k) for k in pev.FL_FILES}
    st = next(r for r in parsed["EarlyVoted"] if r["county"] == "State Totals")
    assert st["GrandTotal"] == 2_210_593 and st["TotalRep"] == 972_753 and st["TotalDem"] == 788_137
    assert len([r for r in parsed["EarlyVoted"] if r["county"] != "State Totals"]) == 67
    recs = pev.fl_records(parsed, "ev_fl_publicstats", "snap", "now")
    state = [r for r in recs if r["geo_level"] == "state"]
    assert len(state) == 15 and all(r["as_of"] and r["as_of_raw"] for r in state)  # 3 stat types × (4 parties + total)
    assert all(r["party"] in ("Republican", "Democrat", "Other", "No Party Affiliation", None) for r in recs)
    assert not any(FORBIDDEN & set(r) for r in recs)


@pytest.mark.skipif(not os.path.isdir(FL_DIR), reason="Florida fixtures not present")
def test_fl_row_that_does_not_tie_out_fails():
    raw = rb(os.path.join(FL_DIR, "Stats_49894_EarlyVoted_2026-10-29.txt")).decode().replace("972,753", "972,754").encode()
    with pytest.raises(ValueError):
        pev.parse_fl_txt(raw, "EarlyVoted")


# ------------------------------------------------------------------ UF (display only)

@pytest.mark.skipif(not os.path.exists(UF_CSV), reason="UF fixture not present")
def test_uf_rows_are_display_only_and_unmodified():
    rows = pev.parse_uf_csv(rb(UF_CSV))
    assert len(rows) == 49
    recs = pev.uf_records(rows, "ev_ufl_election_lab", "snap", "now")
    mi = [r for r in recs if r["state"] == "MI"]
    assert all(r["display_only"] and r["license"].startswith("CC BY-NC-ND") and "UF Election Lab" in r["attribution"] for r in recs)
    assert {r["metric"]: r["value"] for r in mi if r["party"] is None}["Mail ballots requested"] == 2_170_628
    assert not [r for r in mi if r["party"]]  # Michigan publishes no party registration → no party rows invented
    assert all(r["vs_2022"] is None and r["vs_2024"] is None for r in recs)  # no ratios: ND means unmodified display
