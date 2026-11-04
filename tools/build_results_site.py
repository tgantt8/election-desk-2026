#!/usr/bin/env python3
"""Turn results-layer records (data/results/*.jsonl, append-only) into data/results/site.json for the Pages client.

Rules: latest snapshot per source per contest wins for display; the previous snapshot gives the delta; status comes
ONLY from the calls layer (data/calls/calls.jsonl) — never from vote totals. Everything is UNOFFICIAL.
Hand entries (data/results/manual_results.jsonl) arrive one contest — and, for a statewide legislative seat, one county
portion — per snapshot, so for them "latest snapshot" is taken per contest (per contest + county for a seat), never per file.
Michigan legislative seats (tools/mi_legislature.py): seat cards summed county by county ("N of M counties entered", never a
missing county as zero) and the House / Senate tally of calls (calls layer only; no projected control).

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
import mi_legislature as mil  # noqa: E402

TIER1_TITLES = {  # Summary Results Report title → Macomb contest id
    "Representative in State Legislature 58th District": "macomb-hd58",
    "State Senator 24th District": "macomb-sd24",
    "Representative in Congress 10th District": "macomb-mi10",
    "Governor and Lieutenant Governor": "macomb-gov",
    "Governor": "macomb-gov",
    "United States Senator": "macomb-ussen",
}
LADDER = ["Too early", "Leaning", "Likely", "Projected", "Final unofficial", "Certified"]


SEATS = mil.seat_index(mil.load_registry())


def status_for(contest_id, calls):
    seat = SEATS.get(contest_id)
    if seat:  # a call on any id of a Michigan legislative seat is a call on the seat
        return mil.status_text(mil.seat_call(calls, seat.get("call_ids") or [contest_id]))
    rows = [c for c in calls if c.get("contest") == contest_id]
    if not rows:
        return "Too early"
    last = rows[-1]
    if last.get("status") == "retracted":
        return "Too early"
    st = last.get("status", "Projected")
    return f"{st} ({last.get('outlet', '?')}, {last.get('called_at', '')[:16].replace('T', ' ')} UTC)" if st == "Projected" else st


def _card_rows(recs):
    """A feed that carries both the jurisdiction's totals (unit county/state) and unit detail (precincts) is carded from the
    totals only, so precinct rows are never added on top of the county line. Detail-only sets (hand-entered precincts) sum as before."""
    recs = recs or []
    tot = [r for r in recs if r.get("unit") in (None, "county", "state")]
    return tot if tot and any(r.get("unit") not in (None, "county", "state") for r in recs) else recs


def card_from_records(title, contest_id, recs, prev_recs, calls, source_name, county_scope=None):
    recs, prev_recs = _card_rows(recs), _card_rows(prev_recs)
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
    tier = {c["id"]: c.get("tier") for c in contests}
    national, tier1, detail = [], [], {}
    by_source = {}
    # Live records: group by source → snapshot → contest.
    for path in sorted(glob.glob(os.path.join(DATA, "results", "*.jsonl"))):
        recs = read_jsonl(path)
        if not recs:
            continue
        src = recs[-1].get("source_id", os.path.basename(path))
        by_source[src] = recs
        for cid, crec, prec in contest_snapshots(recs, per_contest=src.startswith("manual_")):
            if str(cid).startswith("mi-"):
                continue  # statewide legislative seats: county-portion entries, carded by mil.seat_cards below
            if re.match(r"^us-(senate|house)-[A-Z]{2}", str(cid)):  # per-county rows (e.g. NC S3 Senate) must not be summed into the statewide card
                crec = [r for r in crec if r.get("unit") != "county"] or crec
                prec = [r for r in prec if r.get("unit") != "county"]
            card = card_from_records(crec[0].get("contest_name") or cid, cid, crec, prec, calls, src, scope.get(cid))
            card["tier"] = tier.get(cid)
            if str(cid).startswith("macomb-"):
                tier1.append(card)
                units = [r for r in crec if r.get("unit") and r.get("unit") != "county" and r.get("candidate") is not None and r.get("votes") is not None]
                if units:  # precinct (or other unit) rows from a hand entry or a detail feed fill the Macomb detail table
                    detail[f"{cid} ({src})"] = {"rows": [{"unit": r["unit"], "mode": r.get("mode", "TOTAL"), "candidate": r["candidate"], "votes": r["votes"], "complete": bool(r.get("complete"))} for r in units],
                                                "source": src, "as_of": card["as_of"]}
            elif re.match(r"^(us-senate|gov|us-house)-", str(cid)):
                if crec and all(r.get("county_scope") == "county_portion" for r in crec):
                    continue  # one county's share of a statewide/congressional race (Oakland, Wayne feeds) is not a national card
                m = re.match(r"^(?:us-senate|gov|us-house)-([A-Z]{2})", str(cid))
                if m and not card["title"].startswith(m.group(1)):
                    card["title"] = f"{m.group(1)} · {card['title']}"  # the feed's own contest name, prefixed with the state
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
    tier1.sort(key=lambda c: (c.get("tier") or 9, 1 if c.get("replay") else 0, str(c["id"])))
    reg = mil.load_registry()
    mi_leg = {"seats": mil.seat_cards(reg, by_source, calls, {c["id"]: c for c in contests}), "chambers": mil.chamber_tally(reg, calls),
              "note": "Michigan House and Senate seats on the desk. Sums are of entered county portions only; status and seat counts come only from attributed outlet calls. UNOFFICIAL."}
    out = {"_layer": "results", "national": national, "macomb_tier1": tier1, "macomb_detail": detail,
           "chamber_calls": chamber_calls(calls), "mi_legislature": mi_leg, "replay_2024": replay_2024,
           "disclaimer": "UNOFFICIAL until certified. Status comes only from attributed outlet calls."}
    dump_json(os.path.join(DATA, "results", "site.json"), out)
    print(f"results site: {len(national)} national cards, {len(tier1)} Macomb cards, {len(detail)} detail tables, "
          f"{len(mi_leg['seats'])} MI legislative seats ({sum(1 for c in mi_leg['seats'] if c['counties_entered'])} with entries), replay={replay_2024}")


def contest_snapshots(recs, per_contest=False):
    """Yield (contest_id, current records, previous records) for one source file in append order.
    per_contest=False: the file's last snapshot is current (a poller writes every contest each pull).
    per_contest=True: each contest's own last snapshot is current and its own previous one gives the delta (hand entries)."""
    snaps = []
    for r in recs:
        if not snaps or snaps[-1] != r["snapshot_id"]:
            snaps.append(r["snapshot_id"])
    cid_of = lambda r: r.get("contest_id") or r.get("contest")  # noqa: E731
    if not per_contest:
        cur = [r for r in recs if r["snapshot_id"] == snaps[-1]]
        prev = [r for r in recs if len(snaps) > 1 and r["snapshot_id"] == snaps[-2]]
        for cid in sorted({cid_of(r) for r in cur}, key=str):
            yield cid, [r for r in cur if cid_of(r) == cid], [r for r in prev if cid_of(r) == cid]
        return
    seen = {}
    for r in recs:
        seen.setdefault(cid_of(r), [])
        if not seen[cid_of(r)] or seen[cid_of(r)][-1] != r["snapshot_id"]:
            seen[cid_of(r)].append(r["snapshot_id"])
    for cid in sorted(seen, key=str):
        order = seen[cid]
        cur = [r for r in recs if r["snapshot_id"] == order[-1] and cid_of(r) == cid]
        prev = [r for r in recs if len(order) > 1 and r["snapshot_id"] == order[-2] and cid_of(r) == cid]
        yield cid, cur, prev


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
