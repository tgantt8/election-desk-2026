#!/usr/bin/env python3
"""VoteHub Polling API poller (polls layer). License: CC BY 4.0 (beta) — every display credits VoteHub and links the
original poll URL. The API returns every poll in one payload (~3 MB); we snapshot it by hash and dedupe into
data/polls/polls.jsonl (append-only; a changed topline is a new row with `supersedes`).

Dedupe key = sha1 of normalized pollster | field_start | field_end | population | race_id | normalized sponsors.
Grades are NOT in this feed; an ungraded poll stays ungraded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA, USER_AGENT, append_jsonl, last_snapshot_hash, ops_log, read_jsonl, record_snapshot, sha256_bytes, update_source_health  # noqa: E402

URL = "https://api.votehub.com/polls"
ATTRIBUTION = "Polling data via VoteHub (CC BY 4.0); each poll links to its original publisher."
STATES = {"Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR", "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE", "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID", "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS", "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD", "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS", "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV", "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY", "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK", "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC", "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX", "Utah": "UT", "Vermont": "VT", "Virginia": "VA", "Washington": "WA", "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY"}
POP = {"lv": "LV", "rv": "RV", "a": "A", "v": "V", None: "?", "None": "?"}


def race_id(p):
    """Map a VoteHub poll to the desk's contest ids. Returns None for races the desk does not track."""
    t, subj = p.get("poll_type"), (p.get("subject") or "").strip()
    if t == "generic-ballot":
        return "generic-ballot-2026"
    if t == "approval" and subj == "Donald Trump":
        return "presidential-approval"
    m = re.match(r"^2026 (.+?)(?: (Special|Republican|Democratic))?$", subj)
    if t == "us-senator" and m:
        st = STATES.get(m.group(1))
        if not st:
            return None
        if m.group(2) in ("Republican", "Democratic"):
            return None  # primary poll
        return f"us-senate-{st}" + ("-special" if m.group(2) == "Special" else "")
    if t == "governor" and m and m.group(2) is None:
        st = STATES.get(m.group(1))
        return f"gov-{st}" if st else None
    if t == "us-representative" and p.get("seat_name") and re.match(r"^[A-Z]{2}-\d{1,2}$", p["seat_name"]) and subj.startswith("2026"):
        st, d = p["seat_name"].split("-")
        return f"us-house-{st}-{int(d):02d}"
    return None


def dedupe_key(p, rid):
    s = "|".join([re.sub(r"[^a-z0-9]", "", (p.get("pollster") or "").lower()), p.get("start_date") or "", p.get("end_date") or "",
                  POP.get(p.get("population"), "?"), rid, ",".join(sorted(re.sub(r"[^a-z0-9]", "", x.lower()) for x in (p.get("sponsors") or [])))])
    return hashlib.sha1(s.encode()).hexdigest()[:16]


def margin_dem(answers):
    """D − R in points when both are present (candidate party inferred from VoteHub's choice labels is NOT available here,
    so margin is computed only for generic-ballot / approval; race margins are computed downstream with the contests file)."""
    d = {a["choice"]: a.get("pct") for a in answers or []}
    for dk, rk in (("Democrats", "Republicans"), ("Democrat", "Republican"), ("Democratic", "Republican")):
        if dk in d and rk in d and d[dk] is not None and d[rk] is not None:
            return round(d[dk] - d[rk], 1)
    if "Approve" in d and "Disapprove" in d and d["Approve"] is not None and d["Disapprove"] is not None:
        return round(d["Approve"] - d["Disapprove"], 1)
    return None


def to_records(items, source_id, snapshot_id, fetched_at):
    out = []
    for p in items:
        rid = race_id(p)
        if not rid:
            continue
        out.append({"layer": "polls", "id": dedupe_key(p, rid), "race": rid, "pollster": p.get("pollster"), "sponsor": ", ".join(p.get("sponsors") or []) or None,
                    "field_start": p.get("start_date"), "field_end": p.get("end_date"), "population": POP.get(p.get("population"), "?"), "n": p.get("sample_size"),
                    "mode": None, "toplines": {a["choice"]: a.get("pct") for a in p.get("answers") or []}, "margin": margin_dem(p.get("answers")),
                    "partisan": p.get("partisan"), "internal": bool(p.get("internal")), "grade": None, "grade_source": None,
                    "url": p.get("url"), "source_poll_id": p.get("id"), "source_id": source_id, "snapshot_id": snapshot_id, "retrieved_at": fetched_at,
                    "attribution": ATTRIBUTION})
    return out


def merge(existing, new_recs, log_path):
    """Append only the records whose dedupe key is new, or whose toplines changed (new row with `supersedes`)."""
    latest = {}
    for r in existing:
        latest[r["id"]] = r
    added = 0
    for r in new_recs:
        prev = latest.get(r["id"])
        if prev is None:
            append_jsonl(os.path.join(DATA, "polls", "polls.jsonl"), r)
            latest[r["id"]] = r
            added += 1
        elif prev.get("toplines") != r["toplines"] or prev.get("n") != r.get("n"):
            r["supersedes"] = prev.get("snapshot_id")
            append_jsonl(os.path.join(DATA, "polls", "polls.jsonl"), r)
            append_jsonl(log_path, {"at": r["retrieved_at"], "note": f"{r['pollster']} {r['race']} {r['field_start']}–{r['field_end']} ({r['population']}) republished with changed toplines; superseded earlier row"})
            latest[r["id"]] = r
            added += 1
        else:
            append_jsonl(log_path, {"at": r["retrieved_at"], "note": f"duplicate skipped: {r['pollster']} {r['race']} {r['field_start']}–{r['field_end']} ({r['population']})"}) if False else None
    return added


def run(url, source_id, state_file=None, dry_run=False, items=None):
    fetched = None
    if items is None:
        try:
            r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=120)
            r.raise_for_status()
            raw = r.content
        except Exception as e:  # noqa: BLE001
            update_source_health(source_id, False, str(e))
            ops_log("votehub_fetch_failed", source_id=source_id, error=str(e)[:300])
            print(f"{source_id}: fetch failed: {e}")
            return 1
        if sha256_bytes(raw) == last_snapshot_hash(source_id):
            print(f"{source_id}: unchanged payload")
            update_source_health(source_id, True)
            return 0
        snap = record_snapshot(source_id, "polls", raw, "ok", keep_raw=True)
        items = json.loads(raw.decode("utf-8"))
        fetched = snap
    else:
        fetched = {"id": "test", "fetched_at": "1970-01-01T00:00:00Z"}
    recs = to_records(items, source_id, fetched["id"], fetched["fetched_at"])
    if dry_run:
        print(f"{source_id}: {len(items)} polls in feed, {len(recs)} mapped to tracked races (dry run)")
        return 0
    existing = read_jsonl(os.path.join(DATA, "polls", "polls.jsonl"))
    added = merge(existing, recs, os.path.join(DATA, "polls", "dedupe_log.jsonl"))
    update_source_health(source_id, True)
    ops_log("votehub_pull", source_id=source_id, in_feed=len(items), mapped=len(recs), added=added, snapshot=fetched["id"])
    print(f"{source_id}: {len(items)} polls in feed, {len(recs)} mapped, {added} new/changed rows appended")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=URL)
    ap.add_argument("--source-id", default="polls_votehub_api")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    sys.exit(run(a.url, a.source_id, dry_run=a.dry_run))
