import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from macomb_parsers import TieOutError, mode_shares, parse_precinct_csv, parse_summary_pdf  # noqa: E402

PDF = os.path.join(ROOT, "fixtures", "macomb_2024_general_summary_elstats.pdf")
SHERIFF = os.path.join(ROOT, "fixtures", "macomb_2024_sheriff_precincts.csv")
HD58 = os.path.join(ROOT, "fixtures", "macomb_2024_hd58_precincts.csv")


@pytest.fixture(scope="module")
def summary():
    return parse_summary_pdf(PDF)


def test_summary_ties_out(summary):
    assert summary["tie_out"] == "PASS"
    assert summary["pages"] == 44
    titles = [c["title"] for c in summary["contests"]]
    assert "Sheriff Macomb County" in titles
    assert "Representative in State Legislature 58th District" in titles


def test_sheriff_mode_shares_match_known_calibration(summary):
    sheriff = next(c for c in summary["contests"] if c["title"] == "Sheriff Macomb County")
    sh = mode_shares(sheriff)
    # Verified calibration from the Nov 2024 report: AVCB ~66% D, Election Day ~48% D, Early in-person ~38% D.
    assert 64 <= sh["AVCB"] <= 68
    assert 46 <= sh["ED"] <= 50
    assert 36 <= sh["EV"] <= 40


def test_presidential_total_matches_printed(summary):
    pres = next(c for c in summary["contests"] if c["title"].startswith("Electors of President"))
    assert pres["totals"]["total_votes_cast"]["TOTAL"] == 510076
    harris = next(c for c in pres["candidates"] if c["party"] == "DEM")
    assert harris["votes"] == {"TOTAL": 214977, "AVCB": 106325, "ED": 72434, "EV": 36218}


def test_precinct_csvs_tie_out():
    s = parse_precinct_csv(SHERIFF)
    h = parse_precinct_csv(HD58)
    assert s["tie_out"] == "PASS" and h["tie_out"] == "PASS"
    assert h["n_precincts"] == 31
    assert {c["name"] for c in h["candidates"]} == {"Ron Robinson", "Nate Shannon"}


def test_csv_and_pdf_agree_on_hd58():
    pdf = parse_summary_pdf(PDF)
    hd = next(c for c in pdf["contests"] if "58th District" in c["title"])
    csvd = parse_precinct_csv(HD58)["district"]["values"]
    for cand in hd["candidates"]:
        if cand["write_in"]:
            continue
        assert csvd[cand["name"]]["TOTAL"] == cand["votes"]["TOTAL"]
        assert csvd[cand["name"]]["AVCB"] == cand["votes"]["AVCB"]


def test_seeded_bad_row_fails(tmp_path):
    bad = tmp_path / "bad.csv"
    lines = open(HD58, encoding="utf-8-sig").read().splitlines()
    parts = lines[4].split(",")
    parts[-1] = str(int(parts[-1]) + 7)  # perturb one precinct total → district sum no longer ties
    lines[4] = ",".join(parts)
    bad.write_text("\n".join(lines) + "\n")
    with pytest.raises(TieOutError):
        parse_precinct_csv(str(bad))
