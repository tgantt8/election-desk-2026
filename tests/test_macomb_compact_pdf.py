"""Tests for the Macomb compact-summary PDF parser, including the cross-document tie-out against the 44-page report."""
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = "/home/user/election-desk-2026"
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "tools"))
import macomb_compact_pdf as mc  # noqa: E402
import macomb_parsers  # noqa: E402
from macomb_parsers import parse_summary_pdf  # noqa: E402
from collections import OrderedDict  # noqa: E402

FIX = os.path.join(REPO, "fixtures")
PDF24 = os.path.join(FIX, "macomb_2024_general_official_summary.pdf")
PDF26 = os.path.join(FIX, "macomb_2026_general_unofficial_summary_template.pdf")
ELSTATS = os.path.join(FIX, "macomb_2024_general_summary_elstats.pdf")


@pytest.fixture(scope="module")
def c24():
    return mc.parse_compact_pdf(PDF24)


@pytest.fixture(scope="module")
def c26():
    return mc.parse_compact_pdf(PDF26)


class _DupKeepingDict(OrderedDict):
    """OrderedDict that renames a repeated key ('title #2') instead of overwriting it."""

    def __setitem__(self, key, value):
        if key in self:
            n = 2
            while f"{key} #{n}" in self:
                n += 1
            key = f"{key} #{n}"
        super().__setitem__(key, value)


@pytest.fixture(scope="module")
def report_stock():
    """parse_summary_pdf exactly as the repo ships it (keys contests by title, so equal titles overwrite)."""
    return parse_summary_pdf(ELSTATS)


@pytest.fixture(scope="module")
def report():
    """The same parser (same strict tie-out) with duplicate-titled contests kept, so every report contest is present.

    macomb_parsers.parse_summary_pdf stores contests in an OrderedDict keyed by title; the 2024 report prints nine
    contests whose title repeats (two Armada Village trustee seats, Almont / Clintondale / Lake Shore / Rochester /
    South Lake / Warren Woods school boards, ...), and the stock parser silently keeps only the last of each.
    """
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(macomb_parsers, "OrderedDict", _DupKeepingDict)
        return parse_summary_pdf(ELSTATS)


def test_report_parser_keeps_every_contest(report, report_stock):
    """Guard for the workaround above: 165 'Vote For' blocks in the report; the stock parser returns fewer."""
    assert report["tie_out"] == "PASS"
    assert len(report["contests"]) == 165
    assert len(report_stock["contests"]) <= len(report["contests"])


# ---------------------------------------------------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------------------------------------------------
SUFFIX = {"jr", "sr", "ii", "iii", "iv", "v"}


def last_name(name):
    """Normalised last name: ticket names use the first half ('Harris / Walz'); suffixes and punctuation dropped."""
    name = name.split(" / ")[0]
    toks = [re.sub(r"[^a-z']", "", t.lower()) for t in name.replace(".", " ").split()]
    toks = [t for t in toks if t and t not in SUFFIX]
    return toks[-1]


def party(p):
    """Normalise the party code across the two documents (compact 'WC' == report 'WCP')."""
    return "WCP" if p == "WC" else p


def ckey(cd):
    """Candidate match key: normalised last name + party."""
    return (last_name(cd["name"]), party(cd["party"]))


def first_initial(name):
    """First letter of the first name token (used only to separate two candidates sharing last name and party)."""
    return re.sub(r"[^a-z]", "", name.lower())[:1]


def compact_named(contest):
    """(last name, party) -> list of (first initial, votes) for the named (non write-in) compact candidates."""
    out = {}
    for c in contest["candidates"]:
        if not c["write_in"]:
            out.setdefault(ckey(c), []).append((first_initial(c["name"]), c["votes"]))
    return out


def report_named(contest):
    """(last name, party) -> list of (first initial, TOTAL) for the named candidates of a report contest."""
    out = {}
    for c in contest["candidates"]:
        if not c["write_in"]:
            out.setdefault(ckey(c), []).append((first_initial(c["name"]), c["votes"]["TOTAL"]))
    return out


def report_writein_total(contest):
    """The report's aggregate 'Write-In Totals' row (0 if the contest has none)."""
    return sum(c["votes"]["TOTAL"] for c in contest["candidates"] if c["write_in"])


def ordinal_district(c):
    """'9th District' -> '9th' (compact contests carry their district separately)."""
    return c["district"].split()[0]


def report_title_for(c):
    """Title of the Summary Results Report contest matching a compact partisan/county contest, or None."""
    t, d = c["title"], c.get("district")
    base = t.split(" - ")[0]
    fixed = {
        "U.S. SENATOR": "United States Senator", "PROSECUTING ATTORNEY": "Prosecuting Attorney Macomb County",
        "SHERIFF": "Sheriff Macomb County", "CLERK & REGISTER OF DEEDS": "Clerk and Register of Deeds Macomb County",
        "TREASURER": "Treasurer Macomb County", "PUBLIC WORKS COMMISSIONER": "Public Works Commissioner Macomb County",
        "STATE BOARD OF EDUCATION (2)": "Member of the State Board of Education",
        "UNIVERSITY OF MICHIGAN REGENT (2)": "Regent of the University of Michigan",
        "MICHIGAN STATE UNIVERSITY TRUSTEE (2)": "Trustee of Michigan State University",
        "WAYNE STATE UNIVERSITY GOVERNOR (2)": "Governor of Wayne State University",
    }
    if base == "PRESIDENT / VICE PRESIDENT":
        return "Electors of President and Vice-President of the United States"
    if base in fixed:
        return fixed[base]
    if base == "REPRESENTATIVE IN CONGRESS":
        return f"Representative in Congress {d}"
    if base == "STATE REPRESENTATIVE":
        return f"Representative in State Legislature {d}"
    if base == "COUNTY COMMISSIONER":
        return f"County Commissioner {d}"
    if base == "COUNTY EXECUTIVE":
        return "County Executive Macomb County"
    return None


def tie_out(c, rc):
    """Return a list of mismatch strings between one compact contest and its report contest.

    Candidates match on normalised last name + party; two candidates sharing both inside a contest are told apart by
    first initial.
    """
    problems = []
    a, b = compact_named(c), report_named(rc)

    def flat(d):
        out = {}
        for k, lst in d.items():
            for ini, v in lst:
                out[k + ((ini,) if len(lst) > 1 or len(other.get(k, [])) > 1 else ())] = v
        return out

    other = b
    fa = flat(a)
    other = a
    fb = flat(b)
    for k in sorted(set(fa) | set(fb), key=str):
        if k not in fa:
            problems.append(f"{c['key']}: {k} only in report ({fb[k]})")
        elif k not in fb:
            problems.append(f"{c['key']}: {k} only in compact ({fa[k]})")
        elif fa[k] != fb[k]:
            problems.append(f"{c['key']}: {k} compact {fa[k]} != report TOTAL {fb[k]}")
    wi = sum(x["votes"] for x in c["candidates"] if x["write_in"])
    if wi > report_writein_total(rc):
        problems.append(f"{c['key']}: named write-ins {wi} exceed report Write-In Totals {report_writein_total(rc)}")
    return problems


# ---------------------------------------------------------------------------------------------------------------------
# 2024 compact fixture
# ---------------------------------------------------------------------------------------------------------------------
def test_2024_header(c24):
    h = c24["header"]
    assert h["number_voted"] == 512450
    assert h["eligible_voters"] == 733287
    assert h["turnout_pct"] == 69.9
    assert h["official_flag"] == "OFFICIAL"
    assert h["macomb_only"] is True
    assert "November 5, 2024" in h["election_label"]
    assert c24["parse_status"] == "ok"
    assert c24["pages"] == 4


def test_2024_contest_count_and_schema(c24):
    assert len(c24["contests"]) >= 100
    for c in c24["contests"]:
        assert {"title", "section", "jurisdiction", "multi_county", "candidates"} <= set(c)
        assert c["multi_county"] is False  # the 2024 sheet carries no multi-county labels
        assert c["candidates"]
        for cd in c["candidates"]:
            assert {"name", "party", "votes", "write_in"} <= set(cd)
            assert isinstance(cd["votes"], int)  # official sheet: nothing blank
    keys = [c["key"] for c in c24["contests"]]
    assert len(keys) == len(set(keys))
    assert c24["warnings"] == []


def test_2024_sections_and_nesting(c24):
    secs = {c["section"] for c in c24["contests"]}
    assert {"PARTISAN", "TOWNSHIPS", "JUDICIAL", "CITIES", "VILLAGES", "BOARDS OF EDUCATION", "LIBRARY BOARDS",
            "PROPOSALS"} <= secs
    armada = [c for c in c24["contests"] if c["jurisdiction"] == "ARMADA TWP"]
    assert [c["title"] for c in armada] == ["Supervisor", "Clerk", "Treasurer", "Trustee (2)"]
    assert all(c["section"] == "TOWNSHIPS" for c in armada)
    pres = next(c for c in c24["contests"] if c["title"].startswith("PRESIDENT"))
    assert [cd["votes"] for cd in pres["candidates"][:2]] == [214977, 284660]
    assert sum(cd["write_in"] for cd in pres["candidates"]) == 4
    props = [c for c in c24["contests"] if c["section"] == "PROPOSALS"]
    assert len(props) == 13
    e911 = next(c for c in props if "9-1-1" in c["title"])
    assert [(x["name"], x["votes"]) for x in e911["candidates"]] == [("Yes", 284949), ("No", 149620)]


def test_2024_internal_bounds(c24):
    nv = c24["header"]["number_voted"]
    for c in c24["contests"]:
        total = sum(cd["votes"] for cd in c["candidates"])
        assert total <= nv * c["vote_for"], c["key"]


REQUIRED_FAMILIES = ["PRESIDENT / VICE PRESIDENT", "U.S. SENATOR", "REPRESENTATIVE IN CONGRESS", "STATE REPRESENTATIVE",
                     "PROSECUTING ATTORNEY", "SHERIFF", "CLERK & REGISTER OF DEEDS", "TREASURER", "COUNTY COMMISSIONER",
                     "PUBLIC WORKS COMMISSIONER"]


def test_cross_document_tie_out_partisan(c24, report):
    """Every partisan contest in the compact sheet must equal the 44-page report's TOTAL, candidate by candidate."""
    by_title = {c["title"]: c for c in report["contests"]}
    problems, matched, seen_families = [], 0, set()
    for c in c24["contests"]:
        if c["section"] != "PARTISAN":
            continue
        rt = report_title_for(c)
        assert rt is not None, f"no report-title mapping for {c['key']}"
        assert rt in by_title, f"report has no contest {rt!r} for {c['key']}"
        problems += tie_out(c, by_title[rt])
        matched += 1
        seen_families.add(c["title"].split(" - ")[0])
    assert not problems, "\n".join(problems)
    assert set(REQUIRED_FAMILIES) <= seen_families
    # 1 president + 1 senate + 2 congress + 13 state house + 4 education boards + 5 county-wide + 13 commissioners
    assert matched == 39
    districts = {ordinal_district(c) for c in c24["contests"] if c["title"].startswith("COUNTY COMMISSIONER")}
    assert len(districts) == 13
    assert not any(c["title"].startswith("COUNTY EXECUTIVE") for c in c24["contests"])  # not on the 2024 ballot


def candidate_set(c):
    return frozenset(compact_named(c))


def test_cross_document_tie_out_all_contests(c24, report):
    """Every non-partisan contest too: matched to the report by exact named-candidate set, then votes compared.

    A compact contest that finds no report contest with the same named candidates, or two, is itself a failure.
    """
    rep_by_set = {}
    for rc in report["contests"]:
        if rc["title"] and rc["candidates"] and not {"Yes", "No"} >= {x["name"] for x in rc["candidates"]}:
            rep_by_set.setdefault(frozenset(report_named(rc)), []).append(rc)
    problems, unmatched, n = [], [], 0
    used = set()
    for c in c24["contests"]:
        if c["section"] in ("PARTISAN", "PROPOSALS"):
            continue
        fs = candidate_set(c)
        if not fs:
            # write-in-only contest (Romeo Village Clerk, partial term): the report carries only 'Write-In Totals'
            only = [rc for rc in report["contests"] if rc["title"] and rc["candidates"] and not report_named(rc)
                    and not {"Yes", "No"} >= {x["name"] for x in rc["candidates"]}]
            assert [rc["title"] for rc in only] == ["Clerk Village of Romeo"], [rc["title"] for rc in only]
            assert c["jurisdiction"] == "Romeo Village" and c["title"].startswith("Clerk")
            assert sum(x["votes"] for x in c["candidates"]) <= report_writein_total(only[0])
            n += 1
            continue
        cands = rep_by_set.get(fs, [])
        if not cands:
            unmatched.append(c["key"])
            continue
        # several report contests can share a name set only if the same people ran twice; pick the one whose votes tie
        ok = [rc for rc in cands if not tie_out(c, rc)]
        if not ok:
            problems += tie_out(c, cands[0])
            continue
        used.add(ok[0]["title"])
        n += 1
    assert not problems, "\n".join(problems)
    assert unmatched == [], unmatched
    assert n >= 100


def test_cross_document_tie_out_proposals(c24, report):
    """Each proposal's Yes/No equals the report's, matched by title/jurisdiction word overlap and then compared."""
    rep = [rc for rc in report["contests"] if {x["name"] for x in rc["candidates"]} == {"Yes", "No"}]
    assert len(rep) == 13

    def words(t):
        return set(re.findall(r"[a-z0-9']+", t.lower()))

    props = [c for c in c24["contests"] if c["section"] == "PROPOSALS"]
    assert len(props) == len(rep)
    seen = set()
    for c in props:
        cw = words(f"{c['jurisdiction']} {c['title']}")
        best = max(rep, key=lambda rc: len(cw & words(rc["title"])))
        assert best["title"] not in seen, f"two compact proposals matched {best['title']}"
        seen.add(best["title"])
        yes = next(x for x in c["candidates"] if x["name"] == "Yes")["votes"]
        no = next(x for x in c["candidates"] if x["name"] == "No")["votes"]
        ry = next(x for x in best["candidates"] if x["name"] == "Yes")["votes"]["TOTAL"]
        rn = next(x for x in best["candidates"] if x["name"] == "No")["votes"]["TOTAL"]
        assert (yes, no) == (ry, rn), f"{c['jurisdiction']} / {c['title']} vs {best['title']}"


def test_header_turnout_tie_out_fails_on_bad_header():
    """The header tie-out (turnout = voted / eligible, to 0.1) raises instead of patching."""
    words = []

    def w(text, x0, top):
        return {"text": text, "x0": x0, "x1": x0 + 5, "top": top, "fontname": "ArialMT", "size": 8, "non_stroking_color": (0.0,)}

    row = [("ELIGIBLE", 10), ("VOTERS:", 40), ("100", 80)]
    words += [w(t, x, 10) for t, x in row]
    words += [w(t, x, 20) for t, x in (("NUMBER", 10), ("VOTED:", 40), ("50", 80))]
    words += [w(t, x, 30) for t, x in (("TURNOUT:", 10), ("49.0%", 60))]
    with pytest.raises(mc.CompactTieOutError):
        mc.parse_header(words, [])
    words[-1] = w("50.0%", 60, 30)
    h = mc.parse_header(words, [])
    assert (h["eligible_voters"], h["number_voted"], h["turnout_pct"]) == (100, 50, 50.0)


# ---------------------------------------------------------------------------------------------------------------------
# 2026 template
# ---------------------------------------------------------------------------------------------------------------------
def find(c26, title_part, **kw):
    out = [c for c in c26["contests"] if (title_part == c["title"] or (title_part in c["title"] and "GOVERNOR" not in title_part)) and all(c.get(k) == v for k, v in kw.items())]
    assert len(out) == 1, (title_part, [c["key"] for c in out])
    return out[0]


def test_2026_template_is_blank(c26):
    assert c26["parse_status"] == "template_blank"
    assert c26["pages"] == 3
    h = c26["header"]
    assert h["official_flag"] == "UNOFFICIAL"
    assert h["macomb_only"] is True
    assert h["eligible_voters"] is None and h["number_voted"] is None and h["turnout_pct"] is None
    assert "NOVEMBER 3, 2026" in h["election_label"]
    for c in c26["contests"]:
        for cd in c["candidates"]:
            assert cd["votes"] is None  # never 0


def test_2026_named_contests(c26):
    hd58 = find(c26, "STATE REPRESENTATIVE", district="58th District")
    assert [(c["name"], c["party"]) for c in hd58["candidates"]] == [("Katrina Manetta", "DEM"), ("Ron Robinson", "REP")]
    assert hd58["section"] == "PARTISAN" and hd58["multi_county"] is False
    sen = find(c26, "U.S. SENATOR")
    names = {(c["name"], c["party"]) for c in sen["candidates"]}
    assert ("Abdul El-Sayed", "DEM") in names and ("Mike Rogers", "REP") in names
    gov = find(c26, "GOVERNOR", section="PARTISAN")
    assert gov["title"] == "GOVERNOR"
    names = {(c["name"], c["party"]) for c in gov["candidates"]}
    assert ("Jocelyn Benson", "DEM") in names and ("John James", "REP") in names
    assert sum(c["write_in"] for c in gov["candidates"]) == 9


def test_2026_multi_county_labels(c26):
    assert find(c26, "REPRESENTATIVE IN CONGRESS", district="9th District")["multi_county"] is True
    assert find(c26, "STATE SENATOR", district="11th District")["multi_county"] is False
    assert find(c26, "STATE REPRESENTATIVE", district="57th District")["multi_county"] is True
    almont = [c for c in c26["contests"] if c["jurisdiction"] == "ALMONT COMMUNITY SCHOOLS" and c["section"] == "BOARDS OF EDUCATION"]
    assert almont and all(c["multi_county"] and c["multi_county_note"] == "LAPEER" for c in almont)
    assert find(c26, "Trustee (2)", jurisdiction="CENTER LINE PUBLIC SCHOOLS")["multi_county"] is False


def test_2026_structure(c26):
    assert len(c26["contests"]) >= 100
    secs = {c["section"] for c in c26["contests"]}
    assert {"PARTISAN", "JUDICIAL", "CITIES", "VILLAGES", "BOARDS OF EDUCATION", "PROPOSALS"} <= secs
    props = [c for c in c26["contests"] if c["section"] == "PROPOSALS"]
    assert len(props) == 15
    assert [c["jurisdiction"] for c in props[:2]] == ["STATE PROPOSAL 26-1", "STATE PROPOSAL 26-2"]
    assert all([x["name"] for x in c["candidates"]] == ["Yes", "No"] for c in props)
    lenox = find(c26, "Trustee (2 Partial Terms Ending 12/01/28)")
    assert lenox["jurisdiction"] == "LENOX TOWNSHIP"
    keys = [c["key"] for c in c26["contests"]]
    assert len(keys) == len(set(keys))
    # the one clipped label in the template is surfaced as a neutral warning, not silently dropped
    assert any("clipped in source" in w for w in c26["warnings"])


def test_2026_candidates_match_official_candidate_list_counts(c26):
    """Spot checks that column assembly did not interleave lines: Governor's ticket order is the printed order."""
    gov = find(c26, "GOVERNOR", section="PARTISAN")
    assert [c["name"] for c in gov["candidates"][:3]] == ["Jocelyn Benson", "John James", "Anthony Hudson"]
    ssen = find(c26, "STATE SENATOR", district="10th District")
    assert [c["name"] for c in ssen["candidates"]] == ["Natalie Price", "Michelle Nard"]


# ---------------------------------------------------------------------------------------------------------------------
# synthetic edge cases (no data layers touched: tiny in-memory word lists)
# ---------------------------------------------------------------------------------------------------------------------
def test_candidate_line_parsing():
    def line(*toks):
        return [{"text": t} for t in toks]

    assert mc.parse_candidate_line(line("Harris", "/", "Walz", "DEM", "214,977")) == ("Harris / Walz", "DEM", 214977, False, False)
    assert mc.parse_candidate_line(line("Jay", "J.", "Bowman", "(W.I.)", "NPA", "0")) == ("Jay J. Bowman", "NPA", 0, True, False)
    assert mc.parse_candidate_line(line("Kurt", "D.", "Marter", "150"))[1:3] == (None, 150)
    assert mc.parse_candidate_line(line("Natalie", "Price", "DEM"))[1:3] == ("DEM", None)  # blank -> None, not 0
    assert mc.parse_candidate_line(line("Jody", "White"))[1:3] == (None, None)
    assert mc.parse_candidate_line(line("Jo", "Doe", "(NPA"))[4] is True


def test_column_split_three_columns():
    """Synthetic page: three columns of name-start words must split at the gutters, votes staying with their column."""
    def w(text, x0, x1, top, font="ArialMT"):
        return {"text": text, "x0": x0, "x1": x1, "top": top, "fontname": font, "size": 8, "non_stroking_color": (0.0,)}

    words = []
    for i in range(8):
        top = 100 + 10 * i
        words += [w("Alpha", 20, 45, top), w("DEM", 150, 170, top), w("1,000", 180, 205, top),
                  w("Bravo", 215, 240, top), w("REP", 330, 350, top), w("2,000", 360, 395, top),
                  w("Charlie", 410, 445, top), w("LIB", 520, 540, top), w("3,000", 550, 585, top)]
    cols = mc.split_columns(words)
    assert [len(c) for c in cols] == [24, 24, 24]
    assert {x["text"] for x in cols[0]} == {"Alpha", "DEM", "1,000"}
    assert {x["text"] for x in cols[2]} == {"Charlie", "LIB", "3,000"}


# ---------------------------------------------------------------------------------------------------------------------
# column heuristic vs. the drawn table rules, tie-out sensitivity, status logic
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("pdf_path,n_cols", [(PDF24, [3, 3, 3, 1]), (PDF26, [3, 3, 3])])
def test_column_boundaries_sit_on_the_drawn_table_rules(pdf_path, n_cols):
    """Independent check of the x0-peak heuristic: every boundary lies within 2 pt of a long vertical table rule."""
    import pdfplumber

    with pdfplumber.open(pdf_path) as pdf:
        for page, expect in zip(pdf.pages, n_cols):
            words = mc.page_words(page)
            top = min(w["top"] for w in words if mc._is_white(w)) - 1.0
            body = [w for w in words if w["top"] >= top]
            _, bounds = mc.find_column_boundaries(body)
            assert len(bounds) + 1 == expect, (page.page_number, bounds)
            rules = [e["x0"] for e in page.edges if e["orientation"] == "v" and e["height"] > 60]
            for b in bounds:
                assert min(abs(b - r) for r in rules) <= 2.0, (page.page_number, b)


def test_report_covers_every_compact_contest(c24, report):
    """164 titled report contests <-> 164 compact contests: nothing on either side is left unmatched by count."""
    assert len(c24["contests"]) == sum(1 for rc in report["contests"] if rc["title"]) == 164


def test_tie_out_detects_a_changed_vote(c24, report):
    """The tie-out helper must flag a single-vote difference (guards against a vacuous comparison)."""
    import copy

    by_title = {c["title"]: c for c in report["contests"]}
    c = copy.deepcopy(next(x for x in c24["contests"] if x["title"] == "SHERIFF"))
    assert tie_out(c, by_title["Sheriff Macomb County"]) == []
    c["candidates"][0]["votes"] += 1
    probs = tie_out(c, by_title["Sheriff Macomb County"])
    assert len(probs) == 1 and "wickersham" in probs[0]
    c["candidates"][0]["votes"] -= 1
    c["candidates"][1]["name"] = "Terence Mekowski"  # a renamed candidate shows up as 'only in' on both sides
    assert len(tie_out(c, by_title["Sheriff Macomb County"])) == 2  # "only in report" + "only in compact"


def test_status_and_vote_bound_logic():
    """template_blank only when every vote is blank; mixed -> ok + warning; impossible totals raise."""
    def contest(votes, vf=1):
        return {"key": "k", "vote_for": vf, "candidates": [{"name": f"C{i}", "party": None, "votes": v, "write_in": False}
                                                           for i, v in enumerate(votes)]}

    w = []
    assert mc.classify_and_check({"number_voted": None}, [contest([None, None]), contest([None])], w) == "template_blank"
    assert w == []
    assert mc.classify_and_check({"number_voted": 100}, [contest([60, 40]), contest([None, None])], w) == "ok"
    assert any("blank votes" in x for x in w)
    assert mc.classify_and_check({"number_voted": 100}, [contest([0, 0])], []) == "ok"  # a real zero is not blank
    with pytest.raises(mc.CompactTieOutError):
        mc.classify_and_check({"number_voted": 100}, [contest([60, 41])], [])
    assert mc.classify_and_check({"number_voted": 100}, [contest([60, 41], vf=2)], []) == "ok"


def test_cli_prints_json(capsys):
    import json

    assert mc.main([PDF26]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["parse_status"] == "template_blank" and len(out["source"]["sha256"]) == 64
