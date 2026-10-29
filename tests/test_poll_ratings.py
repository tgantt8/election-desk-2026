"""Offline tests for the ratings pollers. Fixtures: Cook print PDFs (Senate, Governor — public pages whose labels the desk shows),
Inside Elections public cached JSON (Senate, Governor; a Michigan-plus-10 subset for the House). The Cook House page is not
committed (decision 5: only Michigan House labels are shown); its parser is exercised through the words of the real page when
COOK_HOUSE_WORDS points at a local dump, and through the per-column tally checksum at runtime."""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import poll_ratings as pr  # noqa: E402

COOK = os.path.join(ROOT, "fixtures", "cook")
IE = os.path.join(ROOT, "fixtures", "inside_elections")
COOK_SEN = os.path.join(COOK, "cook_senate_print_2026-10-29.pdf")
COOK_GOV = os.path.join(COOK, "cook_governor_print_2026-10-29.pdf")
IE_SEN = os.path.join(IE, "ie_senate_2026-10-29.json")
IE_GOV = os.path.join(IE, "ie_governor_2026-10-29.json")
IE_HOUSE = os.path.join(IE, "ie_house_subset_2026-10-29.json")
SENATE_IDS = {"us-senate-" + s for s in "AL AK AR CO DE GA ID IL IA KS KY LA ME MA MI MN MS MT NE NH NJ NM NC OK OR RI SC SD TN TX VA WV WY".split()} | {"us-senate-FL-special", "us-senate-OH-special"}
FORBIDDEN = {"analysis", "text", "body", "summary", "probability", "forecast"}


def rb(p):
    with open(p, "rb") as fh:
        return fh.read()


# ------------------------------------------------------------------ Cook

@pytest.mark.skipif(not os.path.exists(COOK_SEN), reason="Cook Senate fixture not present")
def test_cook_senate_every_race_lands_in_one_column_and_tallies_match():
    p = pr.parse_cook_senate_governor(rb(COOK_SEN), "senate")
    assert p["validation"] == "ok" and p["page_date"] == "2026-10-20"
    assert p["held"] == {"D": 13, "R": 22} and len(p["entries"]) == 35
    by = {e["state"]: e for e in p["entries"]}
    assert by["MI"]["label"] == "Toss-up" and by["MI"]["holder_party"] == "D" and by["MI"]["incumbent"] == "OPEN"
    assert by["NC"]["label"] == "Lean D" and by["NC"]["holder_party"] == "R"
    assert by["ME"]["label"] == "Toss-up" and by["TX"]["label"] == "Toss-up" and by["OH"]["label"] == "Toss-up"
    assert by["AK"]["label"] == "Toss-up" and by["SC"]["label"] == "Lean R" and by["MS"]["label"] == "Likely R" and by["AL"]["label"] == "Solid R"
    assert by["CO"]["label"] == "Solid D" and by["GA"]["label"] == "Likely D" and by["MN"]["label"] == "Lean D"
    recs, skipped = pr.cook_records(p, "senate", "ratings_cook_senate", pr.COOK_PAGE["senate"], "snap", "now", SENATE_IDS)
    assert skipped == 0 and len(recs) == 35
    assert {r["race"] for r in recs} == SENATE_IDS  # FL and OH map to the special seats, the only ones up there
    assert all(r["date"] == "2026-10-20" and r["date_kind"] == "page" and r["url"] == pr.COOK_PAGE["senate"] for r in recs)
    assert not any(FORBIDDEN & set(r) for r in recs)


@pytest.mark.skipif(not os.path.exists(COOK_GOV), reason="Cook Governor fixture not present")
def test_cook_governor():
    p = pr.parse_cook_senate_governor(rb(COOK_GOV), "governor")
    assert p["validation"] == "ok" and p["page_date"] == "2026-10-27" and p["held"] == {"D": 18, "R": 18} and len(p["entries"]) == 36
    by = {e["state"]: e for e in p["entries"]}
    assert by["MI"]["label"] == "Likely D" and by["KS"]["label"] == "Lean D" and by["WI"]["label"] == "Lean D" and by["AZ"]["label"] == "Likely D"
    assert by["GA"]["label"] == "Lean D" and by["NH"]["label"] == "Likely R" and by["AK"]["label"] == "Likely D" and by["NV"]["label"] == "Lean D"
    recs, _ = pr.cook_records(p, "governor", "ratings_cook_governor", pr.COOK_PAGE["governor"], "snap", "now")
    assert {r["race"] for r in recs} == {"gov-" + e["state"] for e in p["entries"]}


@pytest.mark.skipif(not os.path.exists(COOK_SEN), reason="Cook Senate fixture not present")
def test_cook_tally_mismatch_fails_closed(monkeypatch):
    words = pr._words(rb(COOK_SEN))
    dropped = [w for w in words if w["t"] != "ME-Collins"]
    monkeypatch.setattr(pr, "_words", lambda b: dropped)
    p = pr.parse_cook_senate_governor(b"", "senate")
    assert p["validation"].startswith("tally_mismatch")
    res = pr.run({"id": "ratings_cook_senate", "poller": "cook_ratings", "office": "senate", "url": "u", "fetch_url": "f"}, dry_run=True, raw=b"")
    assert res["status"] == "error" and "tally_mismatch" in res["error"]


@pytest.mark.skipif(not os.environ.get("COOK_HOUSE_WORDS"), reason="set COOK_HOUSE_WORDS to a local words dump of the Cook House print page")
def test_cook_house_from_local_words(monkeypatch):
    words = json.load(open(os.environ["COOK_HOUSE_WORDS"]))["words"]
    monkeypatch.setattr(pr, "_words", lambda b: [{"t": t, "x0": x0, "x1": x1, "top": top} for t, x0, x1, top in words])
    p = pr.parse_cook_house(b"")
    assert p["validation"] == "ok", p["validation"]
    assert p["page_date"] == "2026-10-23" and p["summary"]["solid"] == {"D": 183, "R": 165}
    assert sum(t["parsed"] for t in p["column_tallies"]) == len(p["entries"]) == 17 + 1 + 4 + 12 + 5 + 12 + 2 + 15 + 2 + 11
    mi = {e["district"]: e for e in p["entries"] if e["state"] == "MI"}
    assert mi["MI-08"]["label"] == "Likely D" and mi["MI-04"]["label"] == "Toss-up" and mi["MI-04"]["label_raw"] == "Republican Toss Up"
    assert mi["MI-07"]["label"] == "Toss-up" and mi["MI-10"]["label"] == "Lean R" and mi["MI-10"]["incumbent"] == "OPEN (James)"
    recs, skipped = pr.cook_records(p, "house", "ratings_cook_house", pr.COOK_PAGE["house"], "snap", "now")
    assert len(recs) == 4 and skipped == len(p["entries"]) - 4  # Michigan only; the rest stay link-only
    assert {r["race"] for r in recs} == {"us-house-MI-04", "us-house-MI-07", "us-house-MI-08", "us-house-MI-10"}


# ------------------------------------------------------------------ Inside Elections

def test_ie_house_subset_michigan_scope():
    p = pr.parse_ie_json(rb(IE_HOUSE), "house")
    assert p["validation"] == "ok" and p["page_date"] == "2026-10-29"
    recs, skipped = pr.ie_records(p, "house", "ratings_ie_house", pr.IE_PAGE["house"], "snap", "now")
    assert {r["race"] for r in recs} == {f"us-house-MI-{n:02d}" for n in range(1, 14)} and skipped == 10
    by = {r["race"]: r for r in recs}
    assert by["us-house-MI-04"]["label"] == "Toss-up" and by["us-house-MI-04"]["date"] == "2026-10-29" and by["us-house-MI-04"]["previous_label_raw"] == "Tilt Republican"
    assert by["us-house-MI-10"]["label"] == "Tilt R" and by["us-house-MI-10"]["label_scale"] == 1 and by["us-house-MI-10"]["label_lossy"] is True
    assert by["us-house-MI-08"]["label"] == "Solid D" and by["us-house-MI-08"]["label_scale"] == -3 and by["us-house-MI-08"]["date_kind"] == "race"
    assert all(r["url"] == pr.IE_PAGE["house"] and r["rater"] == "Inside Elections" for r in recs)


@pytest.mark.skipif(not os.path.exists(IE_SEN), reason="IE Senate fixture not present")
def test_ie_senate_specials_and_not_up_rows():
    p = pr.parse_ie_json(rb(IE_SEN), "senate")
    recs, _ = pr.ie_records(p, "senate", "ratings_ie_senate", pr.IE_PAGE["senate"], "snap", "now", SENATE_IDS)
    races = {r["race"] for r in recs}
    assert races <= SENATE_IDS and "us-senate-MI" in races and "us-senate-OH-special" in races and "us-senate-FL-special" in races
    assert len(races) == len(recs) == 35  # "Not Up This Cycle" rows dropped; one row per seat up
    mi = next(r for r in recs if r["race"] == "us-senate-MI")
    assert mi["label"] == "Tilt D" and mi["label_lossy"] and mi["date"] == "2026-10-01"


def test_ie_normalize_vocabulary():
    assert pr.ie_normalize("Battleground Republican") == "Battleground R" and pr.SCALE["Battleground R"] == 1
    assert pr.ie_normalize("Toss-up") == "Toss-up" and pr.ie_normalize("Toss Up") == "Toss-up"
    assert pr.ie_normalize("Not Up This Cycle") is None and pr.ie_normalize("Lean Independent") == "Lean Independent"
    assert pr.SCALE.get("Lean Independent") is None


# ------------------------------------------------------------------ hard stops

class _R:
    def __init__(self, status, body=b"", url="https://x/"):
        self.status_code, self.content, self.url = status, body, url


class _S:
    def __init__(self, r):
        self.r = r

    def get(self, *a, **k):
        return self.r


@pytest.mark.parametrize("resp", [_R(403), _R(429), _R(200, b"<html><title>Just a moment...</title>"), _R(200, b"ok", "https://x/user/login?dest=1")])
def test_fetch_stops_on_terms_signals(resp):
    with pytest.raises(pr.StopFetch):
        pr.fetch("https://x/", session=_S(resp))
