import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import poll_totalvote as p  # noqa: E402


def block(title, pr, pt, cands):
    rows = "".join(f'<div class="section group "><div class="col display-results-box-d"><h1> {n} </h1><h2 class="{pc}">{pn}</h2></div>'
                   f'<div class="col display-results-box-e"></div><div class="col display-results-box-f"><h1>{v}</h1></div></div><hr>' for n, pc, pn, v in cands)
    return (f'<div><div class="display-results-box-wrapper"><div class="display-results-box-a"><h1>{title} - <br>VOTE FOR ONE (1)</h1></div>'
            f'<div class="wrapper-mobile"><div class="section group"><div class="col display-results-box-c"><div class="precinct-fully">Precincts Reported: {pr} / {pt}</div></div></div></div></div>'
            f'{rows}<div class="section group"><div class="col display-results-box-totalvotes"><h2>Total Votes</h2></div><div class="col display-results-box-total"><h2> 9 </h2></div></div></div>')


HTML = ('<html><body><div class="x">Results Last Updated: 11/3/2026 9:17:42 PM EST</div>'
        + block("State Representative 28th District", 3, 24, [("Sherry A. Berecz", "DEM", "Democratic", "1,204"), ("Jamie Thompson", "REP", "Republican", "988"), ("Write-In", "NON", "Nonpartisan", "4")])
        + block("State Representative 2nd District", 0, 21, [("Joanna Whaley", "DEM", "Democratic", "0"), ("Ron Kokinda", "REP", "Republican", "0")])
        + block("State Senator 12th District", 1, 40, [("Kevin Hertel", "DEM", "Democratic", "500"), ("John Goldwater", "REP", "Republican", "300")])
        + "</body></html>")


def test_parse_and_records():
    updated, contests = p.parse_page(HTML)
    assert updated == "11/3/2026 9:17:42 PM EST"
    assert [c["title"] for c in contests] == ["State Representative 28th District", "State Representative 2nd District", "State Senator 12th District"]
    c28 = contests[0]
    assert (c28["precincts_reporting"], c28["precincts_total"]) == (3, 24)
    assert c28["candidates"][0] == {"name": "Sherry A. Berecz", "party_raw": "DEM", "party_name": "Democratic", "votes": 1204}
    recs = p.to_records(contests, updated, "enr_wayne_totalvote", "Wayne", "snap", "2026-11-04T02:30:00Z", "u")
    ids = {r["contest_id"] for r in recs}
    assert ids == {"mi-hd-028", "mi-hd-002", "mi-sd-12"}
    r = next(r for r in recs if r["candidate"] == "Sherry A. Berecz")
    assert r["county"] == "Wayne" and r["unit"] == "county" and r["mode"] == "TOTAL" and r["party"] == "D" and r["votes"] == 1204
    assert r["as_of"] == "2026-11-04T02:17:42Z" and r["unofficial"]
    wi = next(r for r in recs if r["write_in"])
    assert wi["party"] is None


def test_contest_ids():
    assert p.contest_id_for("State Representative 31st District") == "mi-hd-031"
    assert p.contest_id_for("State Senator 9th District") == "mi-sd-09"
    assert p.contest_id_for("Representative in Congress 13th District") == "us-house-MI-13"
    assert p.contest_id_for("County Commissioner 4th District") is None
    assert p.contest_id_for("Representative in State Legislature 51st District") == "mi-hd-051"  # Oakland's Clarity wording
    assert p.contest_id_for("Governor of Wayne State University") is None and p.contest_id_for("Governor and Lieutenant Governor") == "gov-MI"
