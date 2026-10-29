#!/usr/bin/env python3
"""Append a manual entry to the results or calls layer. Used by the manual-entry workflow and from the shell.

ratings payload: {"layer":"ratings","entered_by":...,"records":[{race, rater, label, label_raw, date, url, office, state}]} — a label, a date and a link, nothing else.
early_vote payload: {"layer":"early_vote","entered_by":...,"records":[{geography, geo_level, state, metric, party, mode, value, as_of, source, url, note}]}
  (e.g. a Michigan Voting Dashboard capture: mail ballots requested / returned, early in-person ballots cast, by county or municipality).
results payload (from the Ops panel "Copy as JSON"): {"layer":"results","entered_by":..., "rows":[{"label":..., "numbers":[...]}], ...}
  → the caller must supply contest/candidate mapping in the payload as "records": [{contest_id, contest_name, unit, mode, candidate, party, votes}] for it to
    reach the site; raw "rows" are kept in the snapshot only.
calls payload (from "Copy call JSON"): {"layer":"calls","contest":..., "outlet":..., "called_for":..., "called_at": ISO, "url":..., "status":"Projected"}
  A retraction is a new entry with "status":"retracted". Nothing is edited.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA, append_jsonl, load_json, ops_log, record_snapshot, utcnow  # noqa: E402

_PARTY = {"DEM": "D", "REP": "R", "LIB": "L", "GRN": "G", "UST": "U", "NLP": "N", "WC": "W", "WCP": "W", "NPA": "I",
          "D": "D", "R": "R", "L": "L", "G": "G", "U": "U", "I": "I", "W": "W", "N": "N"}


def norm_party(p):
    return _PARTY.get((p or "").strip().upper())


def match_party(contest, candidate):
    """Party from data/contests/macomb_2026.json by last-name match (ticket names like "Benson / Brinks" match either name)."""
    toks = [t.lower().strip(".,") for t in (candidate or "").replace("/", " ").split() if len(t) > 2]
    if not toks:
        return None
    for k in contest.get("candidates", []):
        names = [t.lower().strip(".,") for t in k["name"].replace("/", " ").split()]
        if toks[-1] in names:
            return k.get("party")
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--layer", required=True, choices=["results", "calls", "ratings", "early_vote"])
    ap.add_argument("--payload", help="JSON string")
    ap.add_argument("--payload-env", help="name of an env var holding the JSON")
    ap.add_argument("--note", default="")
    a = ap.parse_args()
    raw = a.payload if a.payload else os.environ[a.payload_env]
    payload = json.loads(raw)
    if payload.get("layer", a.layer) != a.layer:
        sys.exit(f"payload layer {payload.get('layer')} != {a.layer}")
    source_id = f"manual_{a.layer}"
    snap = record_snapshot(source_id, a.layer, raw.encode("utf-8"), "manual", keep_raw=True, note=a.note)
    if a.layer == "calls":
        rec = {k: payload.get(k) for k in ("contest", "outlet", "called_for", "called_for_party", "called_at", "url", "status", "entered_by")}
        rec.update({"entered_at": utcnow(), "snapshot_id": snap["id"], "note": a.note, "basis": payload.get("basis", "outlet decision desk")})
        if not rec["outlet"] or not rec["called_at"]:
            sys.exit("a call needs outlet and called_at")
        append_jsonl(os.path.join(DATA, "calls", "calls.jsonl"), rec)
        print("call appended:", rec["contest"], rec["outlet"], rec["status"])
    elif a.layer in ("ratings", "early_vote"):
        n = 0
        for r in payload.get("records", []):
            if a.layer == "ratings" and not (r.get("race") and r.get("rater") and r.get("label") and r.get("date") and r.get("url")):
                sys.exit("a ratings record needs race, rater, label, date and url (label + date + link only)")
            if a.layer == "early_vote" and not (r.get("geography") and r.get("metric") and r.get("value") is not None and r.get("as_of") and r.get("source")):
                sys.exit("an early-vote record needs geography, metric, value, as_of and source")
            r.update({"layer": a.layer, "source_id": source_id, "snapshot_id": snap["id"], "fetched_at": snap["fetched_at"], "entered_by": payload.get("entered_by", "manual"),
                      "entered_at": utcnow(), "note": (r.get("note") or "") + (f" {a.note}" if a.note else "")})
            r.setdefault("display_only", False)
            append_jsonl(os.path.join(DATA, a.layer, f"{source_id}.jsonl"), r)
            n += 1
        print(f"{a.layer} appended: {n} records (manual capture; snapshot {snap['id']})")
    else:
        contests = {c["id"]: c for c in load_json(os.path.join(DATA, "contests", "macomb_2026.json"), {"contests": []})["contests"]}
        n = 0
        for r in payload.get("records", []):
            r.setdefault("contest_id", payload.get("contest_id"))
            r.setdefault("mode", payload.get("mode") or "TOTAL")
            c = contests.get(r.get("contest_id"))
            if c:
                r.setdefault("contest_name", c.get("office"))
                r["county_scope"] = c.get("county_scope")
            if r.get("candidate") is not None:
                r["party"] = norm_party(r.get("party")) or (match_party(c, r["candidate"]) if c else None)
            r.update({"source_id": source_id, "snapshot_id": snap["id"], "as_of": payload.get("as_of") or snap["fetched_at"], "unofficial": True, "entered_by": payload.get("entered_by", "manual")})
            append_jsonl(os.path.join(DATA, "results", f"{source_id}.jsonl"), r)
            n += 1
        print(f"results appended: {n} records (raw rows kept in snapshot {snap['id']})")
    ops_log("manual_entry", layer=a.layer, snapshot=snap["id"], note=a.note)


if __name__ == "__main__":
    main()
