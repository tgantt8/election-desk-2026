#!/usr/bin/env python3
"""Turn results-layer records (data/results/*.jsonl, append-only) into data/results/site.json for the Pages client.

Rules: latest snapshot per source per contest wins for display; the previous snapshot gives the delta; status comes
ONLY from the calls layer (data/calls/calls.jsonl) — never from vote totals. Everything is UNOFFICIAL.

--replay-2024 : also render the real 2024 Macomb results (data/baselines/macomb_2024_general.json) through the same
                path, tagged "REPLAY 2024 — not live", so the end-to-end flow can be exercised before Nov 3.
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA, dump_json, load_json, read_jsonl  # noqa: E402

TIER1_TITLES = {  # Summary Results Report title → Macomb contest id
    "Representative in State Legislature 58th District": "macomb-hd58",
    "State Senator 24th District": "macomb-sd24",
    "Representative in Congress 10th District": "macomb-mi10",
    "Governor and Lieutenant Governor": "macomb-gov",
    "Governor": "macomb-gov",
    "United States Senator": "macomb-ussen",
}
LADDER = ["Too early", "Leaning", "Likely", "Projected", "Final unofficial", "Certified"]


def status_for(contest_id, calls):
    rows = [c for c in calls if c.get("contest") == contest_id]
    if not rows:
        return "Too early"
    last = rows[-1]
    if last.get("status") == "retracted":
        return "Too early"
    st = last.get("status", "Projected")
    return f"{st} ({last.get('outlet', '?')}, {last.get('called_at', '')[:16].replace('T', ' ')} UTC)" if st == "Projected" else st


def card_from_records(title, contest_id, recs, prev_recs, calls, source_name, county_scope=None):
    by_cand = defaultdict(lambda: {"votes": 0, "modes": defaultdict(int)})
    party = {}
    for r in recs:
        if r.get("candidate") is None or r.get("votes") is None:
            continue
        if r.get("mode", "TOTAL") == "TOTAL":
            by_cand[r["candidate"]]["votes"] += r["votes"]
        else:
            by_cand[r["candidate"]]["modes"][r["mode"]] += r["votes"]
        if r.get("party"):
            party[r["candidate"]] = r["party"]
    cands = [{"name": n, "party": party.get(n, ""), "votes": v["votes"]} for n, v in by_cand.items()]
    cands.sort(key=lambda c: -c["votes"])
    tot = sum(c["votes"] for c in cands) or 1
    d = next((c for c in cands if (c["party"] or "").upper().startswith("D")), None)
    r_ = next((c for c in cands if (c["party"] or "").upper().startswith("R")), None)
    margin = (100 * (d["votes"] - r_["votes"]) / tot) if d and r_ else None
    modes = defaultdict(int)
    for v in by_cand.values():
        for m, x in v["modes"].items():
            modes[m] += x
    delta = None
    if prev_recs:
        pb = defaultdict(int)
        for r in prev_recs:
            if r.get("candidate") and r.get("mode", "TOTAL") == "TOTAL" and r.get("votes") is not None:
                pb[r["candidate"]] += r["votes"]
        pd_ = pb.get(d["name"]) if d else None
        pr = pb.get(r_["name"]) if r_ else None
        ptot = sum(pb.values()) or 1
        if pd_ is not None and pr is not None and margin is not None:
            delta = margin - 100 * (pd_ - pr) / ptot
    rep = next((r for r in recs if r.get("precincts_reporting") is not None), None)
    as_of = max((r.get("as_of") or "" for r in recs), default="")
    return {"id": contest_id, "title": title, "candidates": cands, "margin": None if margin is None else round(margin, 2),
            "reporting_pct": (100 * rep["precincts_reporting"] / rep["precincts_total"]) if rep and rep.get("precincts_total") else None,
            "precincts": f"{rep['precincts_reporting']} of {rep['precincts_total']} precincts" if rep and rep.get("precincts_total") else None,
            "modes": dict(modes) if modes else None, "delta": None if delta is None else round(delta, 2), "status": status_for(contest_id, calls),
            "source": source_name, "as_of": as_of, "county_scope": county_scope}


def build(replay_2024=False):
    calls = read_jsonl(os.path.join(DATA, "calls", "calls.jsonl"))
    contests = load_json(os.path.join(DATA, "contests", "macomb_2026.json"), {"contests": []})["contests"]
    scope = {c["id"]: c.get("county_scope") for c in contests}
    national, tier1, detail = [], [], {}
    # Live records: group by source → snapshot → contest.
    for path in sorted(glob.glob(os.path.join(DATA, "results", "*.jsonl"))):
        recs = read_jsonl(path)
        if not recs:
            continue
        snaps = []
        for r in recs:
            if not snaps or snaps[-1] != r["snapshot_id"]:
                snaps.append(r["snapshot_id"])
        cur = [r for r in recs if r["snapshot_id"] == snaps[-1]]
        prev = [r for r in recs if len(snaps) > 1 and r["snapshot_id"] == snaps[-2]]
        src = recs[-1].get("source_id", os.path.basename(path))
        for cid in sorted({r.get("contest_id") or r.get("contest") for r in cur}):
            crec = [r for r in cur if (r.get("contest_id") or r.get("contest")) == cid]
            prec = [r for r in prev if (r.get("contest_id") or r.get("contest")) == cid]
            card = card_from_records(crec[0].get("contest_name") or cid, cid, crec, prec, calls, src, scope.get(cid))
            if str(cid).startswith("macomb-"):
                tier1.append(card)
            elif re.match(r"^(us-senate|gov|us-house)-", str(cid)):
                national.append(card)  # state legislative, judicial and local items stay in the layer but off the national board
    if replay_2024:
        base = load_json(os.path.join(DATA, "baselines", "macomb_2024_general.json"))
        for c in base["contests"]:
            cid = TIER1_TITLES.get(c["title"])
            if not cid:
                continue
            recs = []
            for k in c["candidates"]:
                if k["write_in"]:
                    continue
                for m in ("TOTAL", "AVCB", "ED", "EV"):
                    recs.append({"candidate": k["name"], "party": k["party"], "mode": m, "votes": k["votes"][m], "as_of": "2024-11-05T00:00:00Z"})
            card = card_from_records(c["title"] + " — REPLAY 2024, not live", cid, recs, None, [], base["source"]["name"], scope.get(cid))
            card["replay"] = True
            tier1.append(card)
        hd = load_json(os.path.join(DATA, "baselines", "macomb_2024_hd58_precincts.json"))
        rows = []
        for p in hd["precincts"]:
            for cand in hd["candidates"]:
                for m in ("AVCB", "ED", "EV"):
                    rows.append({"unit": p["unit"], "mode": m, "candidate": cand["name"], "votes": p["values"][cand["name"]][m], "complete": True})
        detail["macomb-hd58 (REPLAY 2024)"] = {"rows": rows, "source": hd["source"]["name"]}
    out = {"_layer": "results", "national": national, "macomb_tier1": tier1, "macomb_detail": detail,
           "chamber_calls": chamber_calls(calls), "replay_2024": replay_2024, "disclaimer": "UNOFFICIAL until certified. Status comes only from attributed outlet calls."}
    dump_json(os.path.join(DATA, "results", "site.json"), out)
    print(f"results site: {len(national)} national cards, {len(tier1)} Macomb cards, {len(detail)} detail tables, replay={replay_2024}")


def chamber_calls(calls):
    out = {"senate": {"d": 0, "r": 0, "i": 0}, "house": {"d": 0, "r": 0, "i": 0}}
    latest = {}
    for c in calls:
        latest[c.get("contest")] = c
    for cid, c in latest.items():
        if c.get("status") == "retracted" or not c.get("called_for_party"):
            continue
        p = c["called_for_party"].lower()[0]
        if p not in ("d", "r", "i"):
            continue
        if str(cid).startswith("us-senate-"):
            out["senate"][p] += 1
        elif str(cid).startswith("us-house-"):
            out["house"][p] += 1
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--replay-2024", action="store_true")
    build(ap.parse_args().replay_2024)
