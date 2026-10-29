#!/usr/bin/env python3
"""Run every active poller listed in data/sources.json (field `poller`), one pass, with per-host spacing.

Pollers: clarity, pdf_hash, enhanced_voting (results); votehub_polls (polls); cook_ratings (ratings); nc_s3 (early_vote).
A poller that is not implemented yet is skipped and logged. Exit code is 0 unless every poller failed.
"""
from __future__ import annotations

import argparse
import importlib
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA, load_json, ops_log  # noqa: E402

IMPLEMENTED = {
    "clarity": ("poll_clarity", lambda m, s, st: m.run(s["url"].rstrip("/"), s["id"], st)),
    "pdf_hash": ("poll_macomb_pdf", lambda m, s, st: m.run(s["url"], s["id"], st)),
    "enhanced_voting": ("poll_enhanced_voting", lambda m, s, st: m.run_source(s, st)),
}


def main(layers, only=None):
    srcs = load_json(os.path.join(DATA, "sources.json"), {"sources": []})["sources"]
    ran = failed = 0
    for s in srcs:
        if s.get("layer") not in layers or s.get("status") in ("EXCLUDED", "LINK_ONLY") or s.get("poller") in (None, "none", "manual", "link_only"):
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
