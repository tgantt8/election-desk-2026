#!/usr/bin/env python3
"""Append a manual entry to the results or calls layer. Used by the manual-entry workflow and from the shell.

ratings payload: {"layer":"ratings","entered_by":...,"records":[{race, rater, label, label_raw, date, url, office, state}]} — a label, a date and a link, nothing else.
early_vote payload: {"layer":"early_vote","entered_by":...,"records":[{geography, geo_level, state, metric, party, mode, value, as_of, source, url, note}]}
  (e.g. a Michigan Voting Dashboard capture: mail ballots requested / returned, early in-person ballots cast, by county or municipality).
results payload (from the Ops panel "Copy as JSON"): {"layer":"results","entered_by":..., "rows":[{"label":..., "numbers":[...]}], ...}
  → the caller must supply contest/candidate mapping in the payload as "records": [{contest_id, contest_name, unit, mode, candidate, party, votes}] for it to
    reach the site; raw "rows" are kept in the snapshot only.
calls payload (from "Copy call JSON"): {"layer":"calls","contest":..., "outlet":..., "called_for":..., "called_for_party":..., "called_at": ISO, "url":..., "status":"Projected"}
  A retraction is a new entry with "status":"retracted". Nothing is edited.

Michigan legislative seats (data/contests/mi_legislature_2026.json): a statewide seat (mi-hd-NNN / mi-sd-NN) is entered one county
portion at a time — every results record carries "county" (one of the seat's counties) and mode TOTAL. A call on any Michigan
House or Senate seat id (mi-hd-001..110, mi-sd-01..38, or the seat's Macomb contest id) needs the party it was called for; it is
filled from the seat's candidate list when the candidate matches, and the entry is refused otherwise.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA, append_jsonl, load_json, ops_log, record_snapshot, utcnow  # noqa: E402
import mi_legislature as mil  # noqa: E402

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


def _county_key(name):
    return (name or "").lower().replace("county", "").replace(".", "").replace("saint", "st").strip()


def check_results_payload(payload, contests, reg):
    """A statewide legislative seat entry must name one of the seat's counties and be mode TOTAL. Fills the canonical county
    name. Exits (nothing written) when the entry cannot be attributed to a county portion."""
    seats = mil.seat_index(reg)
    for r in payload.get("records", []):
        cid = mil.normalize_contest_id(r.get("contest_id") or payload.get("contest_id"))
        s = seats.get(cid)
        if not s or s["scope"] != "statewide" or cid != s["contest_id"]:
            continue
        county = r.get("county") or payload.get("county")
        names = {_county_key(p["county"]): p["county"] for p in s["counties"]}
        if not county:
            sys.exit(f"{cid}: a statewide seat is entered one county portion at a time — set the county ({', '.join(names.values())})")
        if _county_key(county) not in names:
            sys.exit(f"{cid}: '{county}' is not one of the seat's counties ({', '.join(names.values())})")
        if (r.get("mode") or payload.get("mode") or "TOTAL") != "TOTAL":
            sys.exit(f"{cid}: enter each county portion as mode TOTAL (the county page's district line)")
        r["county"] = names[_county_key(county)]
    if payload.get("county") and payload.get("records"):
        payload["county"] = payload["records"][0].get("county", payload["county"])


def prepare_call(payload, contests, reg):
    """Validate a call; fill called_for_party from the seat's candidates for Michigan legislative seats."""
    if not payload.get("outlet") or not payload.get("called_at"):
        sys.exit("a call needs outlet and called_at")
    cid = mil.normalize_contest_id(payload.get("contest"))
    payload["contest"] = cid
    seats = mil.seat_index(reg)
    is_mi_leg = cid in seats or bool(mil.SEAT_RE.match(cid))
    if not is_mi_leg:
        if payload.get("called_for_party"):
            payload["called_for_party"] = norm_party(payload["called_for_party"]) or payload["called_for_party"]
        return
    if cid not in seats and not mil.valid_seat_id(cid):
        sys.exit(f"{cid}: not a Michigan House (mi-hd-001..110) or Senate (mi-sd-01..38) seat id")
    if (payload.get("status") or "").lower() == "retracted":
        return
    party = norm_party(payload.get("called_for_party"))
    if not party and payload.get("called_for"):
        s = seats.get(cid)
        pool = (s.get("candidates") if s else None) or []
        if not pool and s:
            for k in s.get("call_ids", []):
                pool = (contests.get(k) or {}).get("candidates") or pool
        k = mil.match_candidate(pool, payload["called_for"]) if pool else None
        party = norm_party(k.get("party")) if k else None
    if not party:
        sys.exit(f"{cid}: a Michigan legislative call needs called_for_party (D, R, …) — the chamber tally counts seats by party")
    payload["called_for_party"] = party


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
    reg = mil.load_registry()
    contests = mil.contests_index(reg)
    if a.layer == "results":
        check_results_payload(payload, contests, reg)  # refuse before anything is written
    if a.layer == "calls":
        prepare_call(payload, contests, reg)
    snap = record_snapshot(source_id, a.layer, raw.encode("utf-8"), "manual", keep_raw=True, note=a.note)
    if a.layer == "calls":
        rec = {k: payload.get(k) for k in ("contest", "outlet", "called_for", "called_for_party", "called_at", "url", "status", "entered_by")}
        rec.update({"entered_at": utcnow(), "snapshot_id": snap["id"], "note": a.note, "basis": payload.get("basis", "outlet decision desk")})
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
        n = 0
        for r in payload.get("records", []):
            r.setdefault("contest_id", payload.get("contest_id"))
            r["contest_id"] = mil.normalize_contest_id(r.get("contest_id"))
            r.setdefault("mode", payload.get("mode") or "TOTAL")
            if payload.get("county") and not r.get("county"):
                r["county"] = payload["county"]
            c = contests.get(r.get("contest_id"))
            if c:
                r.setdefault("contest_name", c.get("office"))
                r["county_scope"] = c.get("county_scope")
            if r.get("candidate") is not None:
                if c and c.get("seat_id"):  # statewide legislative seat: the SoS candidate list, full-name aware
                    k = mil.match_candidate(c.get("candidates") or [], r["candidate"])
                    r["party"] = norm_party(r.get("party")) or (k.get("party") if k else None)
                else:
                    r["party"] = norm_party(r.get("party")) or (match_party(c, r["candidate"]) if c else None)
            r.update({"source_id": source_id, "snapshot_id": snap["id"], "as_of": payload.get("as_of") or snap["fetched_at"], "unofficial": True, "entered_by": payload.get("entered_by", "manual")})
            append_jsonl(os.path.join(DATA, "results", f"{source_id}.jsonl"), r)
            n += 1
        print(f"results appended: {n} records (raw rows kept in snapshot {snap['id']})")
    ops_log("manual_entry", layer=a.layer, snapshot=snap["id"], note=a.note)


if __name__ == "__main__":
    main()
