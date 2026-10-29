#!/usr/bin/env python3
"""Append a manual entry to the results or calls layer. Used by the manual-entry workflow and from the shell.

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
from common import DATA, append_jsonl, ops_log, record_snapshot, utcnow  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--layer", required=True, choices=["results", "calls"])
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
    else:
        n = 0
        for r in payload.get("records", []):
            r.update({"source_id": source_id, "snapshot_id": snap["id"], "as_of": payload.get("as_of") or snap["fetched_at"], "unofficial": True, "entered_by": payload.get("entered_by", "manual")})
            append_jsonl(os.path.join(DATA, "results", f"{source_id}.jsonl"), r)
            n += 1
        print(f"results appended: {n} records (raw rows kept in snapshot {snap['id']})")
    ops_log("manual_entry", layer=a.layer, snapshot=snap["id"], note=a.note)


if __name__ == "__main__":
    main()
