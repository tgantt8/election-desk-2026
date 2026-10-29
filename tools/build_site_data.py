#!/usr/bin/env python3
"""Assemble docs/data/*.json (what the Pages client reads) from the layer files under data/.

Read-only with respect to the layers: this script never writes into data/<layer>/.
Each output carries the source and timestamp of every number it contains.
"""
import glob
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA, ROOT, load_json, read_jsonl, utcnow  # noqa: E402

OUT = os.path.join(ROOT, "docs", "data")
RATING_SCALE = {"Solid D": -3, "Safe D": -3, "Likely D": -2, "Lean D": -1, "Leans D": -1, "Tilt D": -1,
                "Toss-up": 0, "Toss Up": 0, "Tossup": 0,
                "Tilt R": 1, "Lean R": 1, "Leans R": 1, "Likely R": 2, "Solid R": 3, "Safe R": 3}


def write(name, obj):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=1, ensure_ascii=False)
        fh.write("\n")


def health(s):
    if not s.get("last_success_at"):
        return "gray"
    age = (datetime.now(timezone.utc) - datetime.strptime(s["last_success_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)).total_seconds() / 60
    limit = s.get("expected_cadence_min", 60)
    if s.get("last_error") and age > limit:
        return "red"
    return "green" if age <= 2 * limit else "amber"


def build():
    sources = load_json(os.path.join(DATA, "sources.json"), {"sources": []})["sources"]
    snaps = read_jsonl(os.path.join(DATA, "snapshots", "index.jsonl"))
    latest = max((s["fetched_at"] for s in snaps), default=None)
    cadence = load_json(os.path.join(DATA, "config.json"), {}).get("expected_cadence_min", 60)
    write("meta.json", {
        "built_at": utcnow(), "latest_snapshot_at": latest, "expected_cadence_min": cadence,
        "snapshot_count": len(snaps),
        "sources": [{"id": s["id"], "name": s["name"], "layer": s["layer"], "url": s["url"], "terms_note": s.get("terms_note", ""),
                     "last_success_at": s.get("last_success_at"), "last_error": s.get("last_error", ""), "health": health(s)} for s in sources],
        "disclaimer": "All figures UNOFFICIAL until certified. Every record carries its source and timestamp.",
    })

    chambers = load_json(os.path.join(DATA, "contests", "chambers.json"), {})
    senate = load_json(os.path.join(DATA, "contests", "senate_2026.json"), {"races": []})["races"]
    govs = load_json(os.path.join(DATA, "contests", "governors_2026.json"), {"races": []})["races"]
    house = load_json(os.path.join(DATA, "contests", "house_delegations.json"), {"states": []})["states"]
    new_lines = load_json(os.path.join(DATA, "contests", "new_lines.json"), {})
    ratings_latest = read_jsonl(os.path.join(DATA, "ratings", "latest.jsonl"))
    rat_by_race = {}
    for r in ratings_latest:
        rat_by_race.setdefault(r["race"], []).append(r)
    for race in senate + govs:
        rs = rat_by_race.get(race["id"], [])
        race["ratings"] = [{"rater": r["rater"], "label": r["label"], "date": r.get("date"), "url": r.get("url")} for r in rs]
        primary = next((r for r in rs if r["rater"] == "Cook Political Report"), rs[0] if rs else None)
        race["rating_scale"] = RATING_SCALE.get(primary["label"]) if primary else None
    # Senate holdovers: seats not up in 2026, by party of the current holder.
    if chambers and senate:
        up = {r["state"] + ":" + str(r.get("class", "")) for r in senate}
        hold = chambers["senate"].get("holdovers")
        if not hold:
            n_up = len(senate)
            # Derive from the seat list when it carries current-holder party; else leave for the contests file.
            up_d = sum(1 for r in senate if r.get("holder_party") == "D")
            up_r = sum(1 for r in senate if r.get("holder_party") == "R")
            up_i = sum(1 for r in senate if r.get("holder_party") == "I")
            hold = {"d": chambers["senate"]["democrat"] - up_d, "r": chambers["senate"]["republican"] - up_r, "i": chambers["senate"]["independent"] - up_i, "note": f"{n_up} seats up in 2026"}
            chambers["senate"]["holdovers"] = hold
    write("contests.json", {"chambers": chambers, "senate_2026": senate, "governors_2026": govs, "house_delegations": house, "new_lines": new_lines})

    write("ratings.json", {"primary_rater": "Cook Political Report", "as_of": max((r.get("date") or "" for r in ratings_latest), default=None) or None,
                           "latest": ratings_latest, "changes": read_jsonl(os.path.join(DATA, "ratings", "changes.jsonl"))})
    write("polls.json", load_json(os.path.join(DATA, "polls", "site.json"), None) or {"records": [], "averages": {}, "dedupe_log": []})
    write("early_vote.json", {"records": read_jsonl(os.path.join(DATA, "early_vote", "latest.jsonl"))})
    results = load_json(os.path.join(DATA, "results", "site.json"), None) or {"national": [], "macomb_tier1": [], "macomb_detail": {}, "chamber_calls": {"senate": {"d": 0, "r": 0, "i": 0}, "house": {"d": 0, "r": 0, "i": 0}}}
    results["macomb_snapshots"] = [s for s in snaps if s["source_id"].startswith("macomb")][-50:]
    write("results.json", results)
    write("calls.json", {"records": read_jsonl(os.path.join(DATA, "calls", "calls.jsonl"))})
    write("anomalies.json", {"records": read_jsonl(os.path.join(DATA, "anomalies.jsonl"))})
    write("baselines.json", {"files": sorted(os.path.relpath(p, ROOT) for p in glob.glob(os.path.join(DATA, "baselines", "*.json")))})
    print(f"site data built: {len(sources)} sources, {len(snaps)} snapshots, latest {latest}")


if __name__ == "__main__":
    build()
