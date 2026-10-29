#!/usr/bin/env python3
"""Run the anomaly rules (tools/anomalies.py) over the results layer after every poll or manual entry.

For each results source file (data/results/<source>.jsonl, append-only) the last two snapshots of every Macomb contest
(contest ids starting "macomb-") are compared unit by unit. New flags are appended to data/anomalies.jsonl (append-only,
deduplicated by type + contest + unit + snapshot); the per-unit last-change clock lives in data/results/.state_anomalies.json.
Flags never change a number; their language is "data changed — confirm with the Clerk." The 2024 HD-58 precinct baseline
supplies the over/undervote rates for the spike rule where unit names match.

Reads results and baselines; writes only data/anomalies.jsonl and its state file. Never touches any layer file.
"""
from __future__ import annotations

import glob
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from anomalies import detect  # noqa: E402
from common import DATA, append_jsonl, load_json, ops_log, read_jsonl, utcnow  # noqa: E402

STATE = os.path.join(DATA, "results", ".state_anomalies.json")
FLAGS = os.path.join(DATA, "anomalies.jsonl")


def snapshots_in_order(recs):
    order = []
    for r in recs:
        sid = r.get("snapshot_id")
        if sid and (not order or order[-1] != sid):
            order.append(sid)
    return order


def rows_for(recs):
    """Results records → anomaly rows {contest, unit, candidate, mode, votes, ballots, over_under, complete}.
    Candidate rows pass through; a unit total row is added per (contest, unit, mode) from the candidate sum, carrying
    ballots / over_under when the source gave them on any row of that unit."""
    out, totals, extras = [], defaultdict(int), {}
    for r in recs:
        cid = r.get("contest_id") or r.get("contest")
        if not cid or not str(cid).startswith("macomb-"):
            continue
        unit, mode = r.get("unit") or "county", r.get("mode") or "TOTAL"
        if r.get("candidate") is not None and r.get("votes") is not None and not r.get("write_in"):
            out.append({"contest": cid, "unit": unit, "candidate": r["candidate"], "mode": mode, "votes": r["votes"], "complete": bool(r.get("complete"))})
            totals[(cid, unit, mode)] += r["votes"]
        if r.get("ballots") is not None or r.get("over_under") is not None or r.get("candidate") is None:
            e = extras.setdefault((cid, unit, mode), {})
            for k in ("ballots", "over_under"):
                if r.get(k) is not None:
                    e[k] = r[k]
            if r.get("candidate") is None and r.get("votes") is not None:
                e["votes"] = r["votes"]
            if r.get("complete"):
                e["complete"] = True
    for (cid, unit, mode), v in totals.items():
        e = extras.get((cid, unit, mode), {})
        out.append({"contest": cid, "unit": unit, "candidate": None, "mode": mode, "votes": e.get("votes", v), "ballots": e.get("ballots"),
                    "over_under": e.get("over_under"), "complete": bool(e.get("complete"))})
    return out


def baseline_ou_rates():
    rates = {}
    hd = load_json(os.path.join(DATA, "baselines", "macomb_2024_hd58_precincts.json"))
    if not hd:
        return rates
    for p in hd.get("precincts", []):
        ou = (p["values"].get("Overvotes/Undervotes") or {}).get("TOTAL")
        bal = (p["values"].get("Total Ballots Cast") or {}).get("TOTAL")
        if ou is not None and bal:
            rates[("macomb-hd58", p["unit"])] = ou / bal
    return rates


def run(now_iso=None, write=True):
    now_iso = now_iso or utcnow()
    state = load_json(STATE, {"last_processed": {}, "last_change_at": {}}) if write else {"last_processed": {}, "last_change_at": {}}
    last_change = {tuple(k.split("||")): v for k, v in state.get("last_change_at", {}).items()}
    existing = {(f.get("type"), f.get("contest"), f.get("unit"), f.get("snapshot_id")) for f in read_jsonl(FLAGS)} if write else set()
    rates = baseline_ou_rates()
    new_flags = []
    for path in sorted(glob.glob(os.path.join(DATA, "results", "*.jsonl"))):
        recs = read_jsonl(path)
        order = snapshots_in_order(recs)
        if not order:
            continue
        src = os.path.basename(path)[:-6]
        cur_id = order[-1]
        if state["last_processed"].get(src) == cur_id:
            continue
        cur = rows_for([r for r in recs if r.get("snapshot_id") == cur_id])
        prev = rows_for([r for r in recs if len(order) > 1 and r.get("snapshot_id") == order[-2]])
        if not cur:
            state["last_processed"][src] = cur_id
            continue
        flags, last_change = detect(prev, cur, cur_id, now_iso, baseline_ou_rate=rates, last_change_at=last_change)
        for f in flags:
            f["source_id"] = src
            key = (f["type"], f["contest"], f["unit"], f["snapshot_id"])
            if key in existing:
                continue
            existing.add(key)
            new_flags.append(f)
        state["last_processed"][src] = cur_id
    if write:
        for f in new_flags:
            append_jsonl(FLAGS, f)
        state["last_change_at"] = {"||".join(k): v for k, v in last_change.items()}
        from common import dump_json  # noqa: E402

        dump_json(STATE, state)
        if new_flags:
            ops_log("anomaly_flags_opened", count=len(new_flags), types=sorted({f["type"] for f in new_flags}))
    print(f"anomalies: {len(new_flags)} new flag(s)" + (": " + ", ".join(f"{f['type']}@{f['unit']}" for f in new_flags[:8]) if new_flags else ""))
    return new_flags


if __name__ == "__main__":
    run()
