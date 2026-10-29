#!/usr/bin/env python3
"""Build data/baselines/*.json from the Macomb fixtures (real results, 2024 lines; HD-58/SD lines unchanged for 2026).

Outputs:
  data/baselines/macomb_2024_general.json        every contest in the Summary Results Report, with D two-party share by mode
  data/baselines/macomb_2024_<contest>_precincts.json  precinct × mode rows for the contests we have CSVs for
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA, ROOT, dump_json  # noqa: E402
from macomb_parsers import mode_shares, parse_precinct_csv, parse_summary_pdf  # noqa: E402

FIX = os.path.join(ROOT, "fixtures")
SRC_PDF = {"file": "fixtures/macomb_2024_general_summary_elstats.pdf", "url": "https://macombmi.elstats2.civera.com/eng/files/serve/3931",
           "name": "Macomb County Clerk, Summary Results Report, November 2024 (Past Elections database document 3931)"}


def main():
    s = parse_summary_pdf(os.path.join(FIX, "macomb_2024_general_summary_elstats.pdf"))
    contests = []
    for c in s["contests"]:
        rec = {"title": c["title"], "vote_for": c["vote_for"], "page": c["page"],
               "candidates": [{"name": k["name"], "party": k["party"], "write_in": k["write_in"], "votes": k["votes"]} for k in c["candidates"]],
               "totals": c["totals"]}
        sh = mode_shares(c)
        if sh:
            rec["dem_two_party_share_by_mode"] = sh
        contests.append(rec)
    dump_json(os.path.join(DATA, "baselines", "macomb_2024_general.json"), {
        "_layer": "baselines", "cycle": 2024, "election": "2024-11-05 General", "geography": "Macomb County, MI", "line_vintage": "2022 MICRC maps (in effect 2022–2030)",
        "source": SRC_PDF, "tie_out": s["tie_out"], "header": s["header"], "statistics": s["statistics"], "contests": contests,
        "mode_key": {"AVCB": "absent voter counting boards (mail/absentee)", "ED": "Election Day precincts", "EV": "early in-person voting"}})
    for key, fname, url in [("sheriff", "macomb_2024_sheriff_precincts.csv", "https://pastelections.macombgov.org/api/download_contest/11957_table.csv?split_party=false&vote_channels=all"),
                            ("hd58", "macomb_2024_hd58_precincts.csv", "https://pastelections.macombgov.org/api/download_contest/11815_table.csv?split_party=false&vote_channels=all")]:
        p = parse_precinct_csv(os.path.join(FIX, fname))
        dump_json(os.path.join(DATA, "baselines", f"macomb_2024_{key}_precincts.json"), {
            "_layer": "baselines", "cycle": 2024, "contest": key, "line_vintage": "2022 MICRC maps", "source": {"file": "fixtures/" + fname, "url": url, "name": "Macomb County Clerk Past Elections database (Civera ElectionStats), vote_channels=all"},
            "tie_out": p["tie_out"], "candidates": p["candidates"], "district": p["district"], "precincts": p["precincts"], "suppressed_cells": p["suppressed_cells"],
            "note": "\"*\" cells in the source are suppressed by the Clerk for small precincts and are stored as null."})
        print(key, p["n_precincts"], "precincts; suppressed columns:", len(p["suppressed_cells"]))
    # 2022 general, HD-58 on the same MICRC lines (Past Elections division 779 in both cycles): the midterm turnout base.
    p = parse_precinct_csv(os.path.join(FIX, "macomb_2022_hd58_precincts.csv"))
    d = p["district"]["values"]
    dump_json(os.path.join(DATA, "baselines", "macomb_2022_hd58_precincts.json"), {
        "_layer": "baselines", "cycle": 2022, "election": "2022-11-08 General", "contest": "hd58", "line_vintage": "2022 MICRC maps (same division as 2024; precincts consolidated from 35 to 31 by 2024)",
        "source": {"file": "fixtures/macomb_2022_hd58_precincts.csv", "url": "https://pastelections.macombgov.org/api/download_contest/685_table.csv?split_party=false&vote_channels=all",
                   "name": "Macomb County Clerk Past Elections database (Civera ElectionStats), contest 685, vote_channels=all"},
        "tie_out": p["tie_out"], "channels": p["channels"], "candidates": p["candidates"], "district": p["district"], "precincts": p["precincts"], "suppressed_cells": p["suppressed_cells"],
        "summary": {"ballots_cast": d["Total Ballots Cast"]["TOTAL"], "votes_cast": d["Total Votes Cast"]["TOTAL"],
                    "undervote_rate": round(1 - d["Total Votes Cast"]["TOTAL"] / d["Total Ballots Cast"]["TOTAL"], 4),
                    "dem_two_party_share_by_mode": {m: round(100 * d["Nate Shannon"][m] / (d["Nate Shannon"][m] + d["Michelle Smith"][m]), 2) for m in ("TOTAL", "AVCB", "ED") if d["Nate Shannon"][m] + d["Michelle Smith"][m]},
                    "mode_mix_of_votes_cast": {m: round(d["Total Votes Cast"][m] / d["Total Votes Cast"]["TOTAL"], 4) for m in ("AVCB", "ED")}},
        "note": "2022 had no early in-person voting; the ballots count sits in the source's Poll Book Totals column (PBT) and is not split by mode. Overvotes/undervotes are not reported per mode in this file (zeros)."})
    print("hd58-2022", p["n_precincts"], "precincts; ballots", d["Total Ballots Cast"]["TOTAL"], "votes", d["Total Votes Cast"]["TOTAL"])
    print("contests:", len(contests), "| ballots cast:", s["statistics"].get("Ballots Cast - Total"))


if __name__ == "__main__":
    main()
