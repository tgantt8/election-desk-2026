#!/usr/bin/env python3
"""Clean the raw Wikipedia-derived 2026 Senate/governor rows into data/contests/senate_2026.json and governors_2026.json.

Candidate lists are the major-party nominees plus notable independents as Wikipedia's summary tables list them,
retrieved 2026-10-29. They are a convenience for the map; the results layer uses each state's official feed
for the authoritative candidate list. Rows are marked UNVERIFIED until checked against the state SOS.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA, dump_json, load_json  # noqa: E402

RAW = os.path.join(DATA, "contests", "_raw_wiki_contests_2026.json")
GOV_HOLDERS = {"AL": "R", "AK": "R", "AZ": "D", "AR": "R", "CA": "D", "CO": "D", "CT": "D", "FL": "R", "GA": "R", "HI": "D", "ID": "R", "IL": "D", "IA": "R", "KS": "D", "ME": "D", "MD": "D", "MA": "D", "MI": "D", "MN": "D", "NE": "R", "NV": "R", "NH": "R", "NM": "D", "NY": "D", "OH": "R", "OK": "R", "OR": "D", "PA": "D", "RI": "D", "SC": "R", "SD": "R", "TN": "R", "TX": "R", "VT": "R", "WI": "D", "WY": "R"}
# Hand fixes where the wikitext parse lost the party (disambiguation links).
GOV_FIX = {"gov-MI": [{"name": "Jocelyn Benson", "party": "D"}, {"name": "John James", "party": "R"}],
           "gov-AL": [{"name": "Doug Jones", "party": "D"}, {"name": "Tommy Tuberville", "party": "R"}],
           "gov-GA": [{"name": "Keisha Lance Bottoms", "party": "D"}, {"name": "Rick Jackson", "party": "R"}],
           "gov-HI": [{"name": "Gary Cordery", "party": "R"}, {"name": "Josh Green", "party": "D", "incumbent": True}],
           "gov-ME": [{"name": "Rick Bennett", "party": "I"}, {"name": "Robert B. Charles", "party": "R"}, {"name": "Hannah Pingree", "party": "D"}],
           "gov-RI": [{"name": "Ken Block", "party": "I"}, {"name": "Helena Foulkes", "party": "D"}, {"name": "Aaron Guckian", "party": "R"}],
           "gov-SC": [{"name": "Jermaine Johnson", "party": "D"}, {"name": "Alan Wilson", "party": "R"}],
           "gov-WI": [{"name": "David Crowley", "party": "D"}, {"name": "Tom Tiffany", "party": "R"}],
           "gov-ID": [{"name": "Brad Little", "party": "R", "incumbent": True}, {"name": "Terri Pickens", "party": "D"}, {"name": "John Stegner", "party": "I"}]}
KEEP = {"D", "R", "I", "L", "G"}


def clean_name(n):
    n = re.sub(r"\[\[([^\]|]+)(\|([^\]]+))?\]\]?", lambda m: m.group(3) or m.group(1), n)
    n = n.replace("[[", "").replace("]]", "").strip()
    return re.sub(r"\s*\(.*$", "", n).strip()


def main():
    raw = load_json(RAW)
    src = lambda name: {"name": name, "retrieved_at": "2026-10-29T17:40:00Z", "status": "UNVERIFIED — confirm against state SOS ballot"}
    senate = []
    for r in raw["senate"]:
        cands, seen = [], set()
        for c in r["candidates"]:
            name = clean_name(c["name"])
            if c["party"] not in KEEP or name in seen:
                continue
            seen.add(name)
            cands.append({"name": name, "party": c["party"], "incumbent": bool(c.get("incumbent"))})
        senate.append({"id": r["id"], "state": r["state"], "office": "U.S. Senate", "class": r["class"], "special": r["special"],
                       "incumbent": r["incumbent"], "holder_party": r["holder_party"], "status_note": r["status_note"], "candidates": cands,
                       "source": src("Wikipedia, 2026 United States Senate elections (summary tables)")})
    govs = []
    for r in raw["gov"]:
        cands = GOV_FIX.get(r["id"])
        if cands is None:
            cands, seen = [], set()
            for c in r["candidates"]:
                name = clean_name(c["name"])
                if c["party"] not in KEEP or name in seen or not name:
                    continue
                seen.add(name)
                cands.append({"name": name, "party": c["party"]})
        for c in cands:
            c.setdefault("incumbent", bool(r.get("incumbent") and c["name"].split()[-1] in r["incumbent"]))
        govs.append({"id": r["id"], "state": r["state"], "office": "Governor", "incumbent": r.get("incumbent"), "holder_party": GOV_HOLDERS.get(r["state"], "?"),
                     "candidates": cands, "source": src("Wikipedia, 2026 United States gubernatorial elections (States table)")})
    dump_json(os.path.join(DATA, "contests", "senate_2026.json"), {"_layer": "contests", "_note": "Seats up Nov 3 2026: 33 Class II regular + FL (Class 3) and OH (Class 3) specials. holder_party = party holding the seat before the election (drives chamber holdovers).", "races": senate})
    dump_json(os.path.join(DATA, "contests", "governors_2026.json"), {"_layer": "contests", "_note": "36 state governorships up Nov 3 2026 (plus DC mayor and territories, not tracked).", "races": govs})
    hp = {}
    for r in senate:
        hp[r["holder_party"]] = hp.get(r["holder_party"], 0) + 1
    print(f"senate {len(senate)} races; governors {len(govs)} races; seats up by holder party: {hp}")


if __name__ == "__main__":
    main()
