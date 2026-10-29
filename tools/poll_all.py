#!/usr/bin/env python3
"""Run every active poller listed in data/sources.json (field `poller`), one pass, with per-host spacing.

Pollers: clarity, pdf_hash, enhanced_voting (results); votehub_polls (polls); cook_ratings, ie_ratings (ratings); ev_nc_s3, ev_fl_publicstats, ev_uf_csv (early_vote).
A poller that is not implemented yet is skipped and logged. Exit code is 0 unless every poller failed.
"""
from __future__ import annotations

import argparse
import importlib
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA, dump_json, load_json, ops_log, utcnow  # noqa: E402

IMPLEMENTED = {
    "clarity": ("poll_clarity", lambda m, s, st: m.run(s["url"].rstrip("/"), s["id"], st)),
    "pdf_hash": ("poll_macomb_pdf", lambda m, s, st: m.run(s["url"], s["id"], st, layer=s["layer"])),
    "enhanced_voting": ("poll_enhanced_voting", lambda m, s, st: 1 if m.run({**s["ev"], "source_id": s["id"]}, state_file=st)["status"] == "error" else 0),
    "votehub_polls": ("poll_votehub", lambda m, s, st: m.run(s["url"], s["id"], st)),
    "cook_ratings": ("poll_ratings", lambda m, s, st: 1 if m.run(s)["status"] == "error" else 0),
    "ie_ratings": ("poll_ratings", lambda m, s, st: 1 if m.run(s)["status"] == "error" else 0),
    "ev_nc_s3": ("poll_early_vote", lambda m, s, st: 1 if m.run(s)["status"] == "error" else 0),
    "ev_fl_publicstats": ("poll_early_vote", lambda m, s, st: 1 if m.run(s)["status"] == "error" else 0),
    "ev_uf_csv": ("poll_early_vote", lambda m, s, st: 1 if m.run(s)["status"] == "error" else 0),
}


ELECTION_DATE = "2026-11-03"


def discover_election(s):
    """GA/ID: the Nov 3 election id is not published until the state creates it. Poll /jurisdictions/<slug> once per pass;
    when exactly one non-recount election dated ELECTION_DATE appears, persist its publicElectionId (and active=true) in
    data/sources.json and log it. Returns True when the source now has an election id."""
    import requests
    pev = importlib.import_module("poll_enhanced_voting")
    ev = s["ev"]
    try:
        eid, cands = pev.discover_election_id(ev["host"], ev["slug"], ELECTION_DATE, requests.Session(), min_interval_s=0)
    except Exception as e:  # noqa: BLE001
        ops_log("ev_discover_failed", source_id=s["id"], error=str(e)[:300])
        print(f"{s['id']}: discovery failed: {e}")
        return False
    if not eid:
        ops_log("ev_discover_pending", source_id=s["id"], candidates=cands)
        print(f"{s['id']}: no {ELECTION_DATE} election published yet ({len(cands)} candidates)")
        return False
    path = os.path.join(DATA, "sources.json")
    doc = load_json(path, {"sources": []})
    for row in doc["sources"]:
        if row["id"] == s["id"]:
            row["ev"]["election_id"] = eid
            row["active"] = True
            row["notes"] = (row.get("notes") or "") + f" election_id {eid} discovered {utcnow()} from /jurisdictions/{ev['slug']}."
    dump_json(path, doc)
    s["ev"]["election_id"] = eid
    s["active"] = True
    ops_log("ev_discovered", source_id=s["id"], election_id=eid, candidates=cands)
    print(f"{s['id']}: election id {eid} discovered and saved")
    return True


def main(layers, only=None):
    srcs = load_json(os.path.join(DATA, "sources.json"), {"sources": []})["sources"]
    ran = failed = 0
    for s in srcs:
        if s.get("layer") not in layers or s.get("status") in ("EXCLUDED", "LINK_ONLY") or s.get("poller") in (None, "none", "manual", "link_only"):
            continue
        if s.get("poller") == "enhanced_voting" and not (s.get("ev") or {}).get("election_id"):
            if not discover_election(s):
                continue  # Nov 3 election object not published yet; try again next pass
        if not s.get("active", True):  # registered but not switched on (e.g. Clarity states until the WAF test passes)
            continue
        if only and s["id"] not in only:
            continue
        spec = IMPLEMENTED.get(s["poller"])
        if not spec:
            ops_log("poller_not_implemented", source_id=s["id"], poller=s["poller"])
            continue
        modname, call = spec
        try:
            mod = importlib.import_module(modname)
        except ImportError as e:
            ops_log("poller_missing_module", source_id=s["id"], error=str(e))
            continue
        state_file = os.path.join(DATA, s["layer"], f".state_{s['id']}.json")
        ran += 1
        try:
            rc = call(mod, s, state_file)
            if rc not in (0, None):
                failed += 1
        except Exception as e:  # noqa: BLE001
            failed += 1
            ops_log("poller_exception", source_id=s["id"], error=str(e)[:300])
            print(f"{s['id']}: {e}")
        time.sleep(1.0)
    print(f"poll_all: ran {ran}, failed {failed}")
    return 1 if ran and failed == ran else 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--layers", default="results,polls,ratings,early_vote,calls")
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    sys.exit(main(set(a.layers.split(",")), set(filter(None, a.only.split(",")))))
