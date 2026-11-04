#!/usr/bin/env python3
"""Poll NPR's public election-results app (apps.npr.org/2026-election-results) for AP race calls and AP-tabulated counts.

What this is: NPR is an AP member; its results app is a static site whose front end reads plain JSON files
(data/senate.json, data/gov.json, data/house.json; states/<ST>.json for statewide offices). apps.npr.org/robots.txt allows
everything. This poller reads those same files — the public page's own data, not AP's licensed API, which the desk still
does not touch — and attributes every number and call to "AP via NPR" with NPR's own timestamps.

Two layers, never cross-written:
  * calls   — a race with raceCallStatus "Called" / candidate.winner == "X" becomes ONE append-only call record
              {contest, outlet "AP (via NPR)", called_for, called_for_party, called_at = winnerDateTime, url, status "Projected"};
              deduplicated on (contest, outlet, called_at). A race that was called and later is not (AP retraction)
              appends a status "retracted" record once. Nothing here ever decides a call from vote totals.
  * results — per-candidate AP-tabulated counts as published by NPR (source_id results_ap_via_npr, unit "state",
              tabulator "AP via NPR", UNOFFICIAL). These are media-tabulated counts, not an election office's figures; the
              card shows the source. Only written when the race's `updated` stamp moved since the last pass (append-only).

Contest ids follow the desk: us-senate-<ST>[-special], gov-<ST>, us-house-<ST>-<NN|AL>.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA, USER_AGENT, append_jsonl, dump_json, load_json, ops_log, read_jsonl, record_snapshot, update_source_health, utcnow  # noqa: E402

BASE = "https://apps.npr.org/2026-election-results"
FILES = {"senate": "data/senate.json", "gov": "data/gov.json", "house": "data/house.json"}
OUTLET = "AP (via NPR)"
SOURCE_ID = "results_ap_via_npr"
CALLS_SOURCE_ID = "calls_ap_via_npr"
PARTY = {"Dem": "D", "GOP": "R", "Ind": "I", "Lib": "L", "Grn": "G", "Oth": "O", "Other": "O"}
AT_LARGE = {"AK", "DE", "ND", "SD", "VT", "WY"}
HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json"}


def ms_iso(ms):
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:  # noqa: BLE001
        return None


def contest_id(race: dict) -> str | None:
    st = (race.get("state") or "").upper()
    off = race.get("office")
    if off == "S":
        special = str(race.get("seat") or "").lower().startswith("class iii") or "special" in str(race.get("seat") or "").lower()
        return f"us-senate-{st}-special" if special else f"us-senate-{st}"
    if off == "G":
        return f"gov-{st}"
    if off == "H":
        n = str(race.get("seatNumber") or "").strip()
        if st in AT_LARGE:
            return f"us-house-{st}-AL"
        return f"us-house-{st}-{int(n):02d}" if n.isdigit() else None
    return None


def cand_name(c: dict) -> str:
    return " ".join(x for x in (c.get("first"), c.get("last")) if x).strip() or c.get("last") or "?"


def race_records(race: dict, cid: str, snapshot_id: str | None, fetched_at: str, url: str) -> list[dict]:
    as_of = ms_iso(race.get("updated")) or fetched_at
    out = []
    for c in race.get("candidates", []):
        if c.get("party") == "Other" and not c.get("first"):
            name = "Other (AP aggregate)"
        else:
            name = cand_name(c)
        out.append({"layer": "results", "source_id": SOURCE_ID, "snapshot_id": snapshot_id, "contest_id": cid, "contest_name": f"{race.get('stateName')} · {race.get('officeName')}" + (f" {race.get('seat')}" if race.get("office") == "H" else ""),
                    "state": race.get("state"), "office": race.get("officeName"), "unit": "state", "mode": "TOTAL", "candidate": name,
                    "party": PARTY.get(c.get("party"), c.get("party")), "party_raw": c.get("party"), "votes": c.get("votes"), "votes_advance": c.get("avotes"),
                    "percent": c.get("percent"), "precincts_reporting": race.get("reporting"), "precincts_total": race.get("precincts"),
                    "eevp": race.get("eevp"), "tabulation_status": race.get("tabulationStatus"), "race_call_status": race.get("raceCallStatus"),
                    "vendor_is_winner": c.get("winner") == "X", "tabulator": "AP via NPR", "as_of": as_of, "fetched_at": fetched_at,
                    "source_url": url, "ap_race_id": race.get("id"), "unofficial": True, "is_official": False})
    return out


def call_record(race: dict, cid: str, url: str, fetched_at: str) -> dict | None:
    w = next((c for c in race.get("candidates", []) if c.get("winner") == "X"), None)
    if not (w and (race.get("called") or race.get("raceCallStatus") == "Called")):
        return None
    return {"layer": "calls", "contest": cid, "outlet": OUTLET, "basis": "AP race call as published by NPR's results app", "called_for": cand_name(w),
            "called_for_party": PARTY.get(w.get("party"), w.get("party")), "called_at": w.get("winnerDateTime") or ms_iso(race.get("updated")) or fetched_at,
            "url": url, "status": "Projected", "entered_by": "poll_npr_ap", "entered_at": fetched_at, "ap_race_id": race.get("id"), "source_id": CALLS_SOURCE_ID,
            "flipped_seat": bool(race.get("flippedSeat")), "previous_party": PARTY.get(race.get("previousParty"), race.get("previousParty"))}


def run(state_file=None, dry_run=False, session=None, files=None, now=None):
    session = session or requests.Session()
    state_file = state_file or os.path.join(DATA, "results", f".state_{SOURCE_ID}.json")
    state = load_json(state_file, {}) if os.path.exists(state_file) else {}
    updated_seen = state.get("updated", {})      # ap_race_id -> last `updated` ms written to results
    calls_path = os.path.join(DATA, "calls", "calls.jsonl")
    existing = read_jsonl(calls_path) if os.path.exists(calls_path) else []
    have = {(c.get("contest"), c.get("outlet"), c.get("called_at")) for c in existing}
    latest_status = {}
    for c in existing:
        if c.get("outlet") == OUTLET:
            latest_status[c.get("contest")] = c.get("status")
    fetched_at = now or utcnow()
    n_res = n_calls = n_retr = 0
    errors = []
    for key, rel in (files or FILES).items():
        url = f"{BASE}/{rel}"
        try:
            r = session.get(url, headers=HEADERS, timeout=60)
            r.raise_for_status()
            doc = r.json()
        except Exception as e:  # noqa: BLE001
            errors.append(f"{key}: {str(e)[:160]}")
            continue
        races = doc.get("results") if isinstance(doc, dict) else doc
        races = [x for x in (races or []) if not x.get("test")]
        snap = None if dry_run else record_snapshot(SOURCE_ID, "results", r.content, "ok", keep_raw=True, note=f"{rel}: {len(races)} races; etag {r.headers.get('ETag', '')}")
        res_rows, call_rows, retr_rows = [], [], []
        for race in races:
            cid = contest_id(race)
            if not cid:
                continue
            rid = str(race.get("id"))
            upd = race.get("updated")
            if upd is not None and updated_seen.get(rid) != upd:
                res_rows.extend(race_records(race, cid, snap["id"] if snap else None, fetched_at, url))
                updated_seen[rid] = upd
            call = call_record(race, cid, url, fetched_at)
            if call and (call["contest"], call["outlet"], call["called_at"]) not in have:
                call_rows.append(call)
                have.add((call["contest"], call["outlet"], call["called_at"]))
                latest_status[cid] = "Projected"
            elif not call and latest_status.get(cid) == "Projected":
                retr_rows.append({"layer": "calls", "contest": cid, "outlet": OUTLET, "status": "retracted", "called_at": fetched_at, "url": url,
                                  "basis": "AP call no longer shown by NPR's results app", "entered_by": "poll_npr_ap", "entered_at": fetched_at, "source_id": CALLS_SOURCE_ID})
                latest_status[cid] = "retracted"
        if not dry_run:
            for row in res_rows:
                append_jsonl(os.path.join(DATA, "results", f"{SOURCE_ID}.jsonl"), row)
            for row in call_rows + retr_rows:
                append_jsonl(calls_path, row)
        n_res += len(res_rows); n_calls += len(call_rows); n_retr += len(retr_rows)
        print(f"npr_ap {key}: {len(races)} races, {len(res_rows)} result rows, {len(call_rows)} new calls, {len(retr_rows)} retractions")
    if not dry_run:
        os.makedirs(os.path.dirname(state_file) or ".", exist_ok=True)
        dump_json(state_file, {"updated": updated_seen, "at": fetched_at})
        if errors and n_res == 0 and n_calls == 0:
            update_source_health(SOURCE_ID, False, "; ".join(errors)[:300])
            ops_log("npr_ap_failed", source_id=SOURCE_ID, errors=errors)
            return {"status": "error", "errors": errors}
        update_source_health(SOURCE_ID, True)
        ops_log("npr_ap_pull", source_id=SOURCE_ID, result_rows=n_res, new_calls=n_calls, retractions=n_retr, errors=errors)
    return {"status": "ok", "result_rows": n_res, "new_calls": n_calls, "retractions": n_retr, "errors": errors}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--state-file")
    a = ap.parse_args(argv)
    out = run(state_file=a.state_file, dry_run=a.dry_run)
    print(json.dumps(out))
    return 0 if out["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
