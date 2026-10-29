#!/usr/bin/env python3
"""Build data/polls/site.json for the Pages client from the append-only polls layer.

Desk average per race (every weight shown in the output):
  weight = recency × √n × population × grade × (house effect off by default)
  recency: exp(-ln2 · days_since_field_end / half_life_days), half-life 14 days
  population: LV 1.0, RV 0.8, A/V 0.6, unknown 0.6
  grade: 1.0 for every poll (no grades are stored yet — an ungraded poll is neither good nor bad)
Only the latest row per dedupe id counts. Race margin = D − R from the candidate-party map in data/contests/.
Published averages are shown NEXT TO ours as links (we store no third-party averages). Never writes into any layer.
"""
from __future__ import annotations

import math
import os
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA, dump_json, load_json, read_jsonl, utcnow  # noqa: E402

WEIGHTS = {"half_life_days": 14, "lv_pref": 1.0, "rv_weight": 0.8, "adult_weight": 0.6, "grade_mult": 1.0, "house_effects": False, "min_polls": 2}
PUBLISHED = [
    {"name": "RealClearPolling", "url": "https://www.realclearpolling.com/", "value": None, "as_of": None, "note": "link only"},
    {"name": "Silver Bulletin", "url": "https://www.natesilver.net/", "value": None, "as_of": None, "note": "link only (partly paid)"},
    {"name": "Decision Desk HQ / The Hill averages", "url": "https://elections2026.thehill.com/", "value": None, "as_of": None, "note": "link only"},
    {"name": "VoteHub averages", "url": "https://votehub.com/polls/", "value": None, "as_of": None, "note": "link only; polls via VoteHub API (CC BY 4.0)"},
]


def party_map():
    """candidate last name → D/R per race, from the contests files."""
    out = defaultdict(dict)
    for f in ("senate_2026.json", "governors_2026.json"):
        for r in load_json(os.path.join(DATA, "contests", f), {"races": []})["races"]:
            for c in r["candidates"]:
                if c["party"] in ("D", "R"):
                    out[r["id"]][c["name"].split()[-1].lower()] = c["party"]
    return out


def race_margin(rec, pm):
    if rec.get("margin") is not None:
        return rec["margin"]
    m = pm.get(rec["race"])
    if not m:
        return None
    d = r = None
    for choice, pct in (rec.get("toplines") or {}).items():
        last = re.sub(r"[^a-z]", "", choice.split()[-1].lower()) if choice else ""
        p = m.get(last)
        if p == "D" and pct is not None:
            d = pct
        elif p == "R" and pct is not None:
            r = pct
    return None if d is None or r is None else round(d - r, 1)


def build(today=None):
    today = today or date.today()
    rows = read_jsonl(os.path.join(DATA, "polls", "polls.jsonl"))
    latest = {}
    for r in rows:
        latest[r["id"]] = r  # last write wins (supersedes)
    pm = party_map()
    recs = []
    for r in latest.values():
        m = race_margin(r, pm)
        recs.append({k: r.get(k) for k in ("id", "race", "pollster", "sponsor", "field_start", "field_end", "population", "n", "mode", "toplines", "grade", "grade_source", "url", "partisan", "internal", "retrieved_at")} | {"margin": m})
    by_race = defaultdict(list)
    for r in recs:
        if r["margin"] is not None and r["field_end"]:
            by_race[r["race"]].append(r)
    averages = {}
    for race, rs in sorted(by_race.items()):
        num = den = 0.0
        used = 0
        for r in rs:
            try:
                days = (today - date.fromisoformat(r["field_end"])).days
            except ValueError:
                continue
            if days > 60:
                continue
            w = math.exp(-math.log(2) * max(days, 0) / WEIGHTS["half_life_days"]) * math.sqrt(r["n"] or 400)
            w *= {"LV": WEIGHTS["lv_pref"], "RV": WEIGHTS["rv_weight"]}.get(r["population"], WEIGHTS["adult_weight"]) * WEIGHTS["grade_mult"]
            if r.get("internal") or r.get("partisan"):
                w *= 0.5  # internal / partisan-sponsored polls count half (shown in weights)
            num += w * r["margin"]
            den += w
            used += 1
        if used >= WEIGHTS["min_polls"] and den > 0:
            averages[race] = {"margin": round(num / den, 1), "n_polls": used, "weights": WEIGHTS | {"internal_partisan_mult": 0.5, "window_days": 60}, "published": PUBLISHED, "as_of": utcnow()}
        elif used:
            averages[race] = {"margin": None, "n_polls": used, "weights": WEIGHTS, "published": PUBLISHED, "note": "fewer than 2 polls in the window — no desk average", "as_of": utcnow()}
    recs.sort(key=lambda r: (r["race"], r["field_end"] or ""), reverse=True)
    dedupe_log = read_jsonl(os.path.join(DATA, "polls", "dedupe_log.jsonl"))[-50:]
    dump_json(os.path.join(DATA, "polls", "site.json"), {"_layer": "polls", "built_at": utcnow(), "attribution": "Polling data via VoteHub (CC BY 4.0) and the original pollsters; each row links to its publisher.",
                                                          "records": recs, "averages": averages, "dedupe_log": dedupe_log})
    print(f"polls site: {len(recs)} polls, {len(averages)} race averages")


if __name__ == "__main__":
    build()
