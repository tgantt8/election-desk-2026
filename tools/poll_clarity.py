#!/usr/bin/env python3
"""Clarity (Scytl) election-night results poller — used by Macomb County (MI/Macomb/127293) and others.

Endpoints (standard Clarity ENR layout):
  <base>/current_ver.txt                      → version string (cheap change detector)
  <base>/<ver>/json/en/electionsettings.json  → election metadata, contest list
  <base>/<ver>/json/en/summary.json           → contest totals (candidates, votes, precincts reporting)
  <base>/<ver>/reports/detailxml.zip          → precinct × contest × (vote type) detail XML, when the county publishes it
Clarity sits behind an AWS WAF JavaScript challenge for some clients (HTTP 202, empty body). The poller reports that
as `challenge` and the caller falls back to the Clerk's summary PDF or manual entry. It never tries to defeat the challenge.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import zipfile

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA, USER_AGENT, append_jsonl, ops_log, record_snapshot, update_source_health, utcnow  # noqa: E402

HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json, text/plain, */*"}


def get(url, timeout=45):
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    if r.status_code == 202 and not r.content.strip():
        raise RuntimeError("challenge: HTTP 202 empty body (WAF JavaScript challenge)")
    r.raise_for_status()
    return r


def current_version(base):
    return get(base.rstrip("/") + "/current_ver.txt").text.strip()


def fetch_summary(base, ver):
    return get(f"{base.rstrip('/')}/{ver}/json/en/summary.json").content


def fetch_detail_xml(base, ver):
    r = get(f"{base.rstrip('/')}/{ver}/reports/detailxml.zip", timeout=120)
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(".xml"))
        return z.read(name)


def parse_summary(raw, source_id, snapshot_id, as_of):
    """summary.json is a list of contests: {"A": contest name, "C": [candidate names], "V": [votes], "PR": precincts reporting, "PT": precincts total, ...}.
    Field letters vary slightly by Clarity version; this maps the common ones and keeps the raw item."""
    items = json.loads(raw.decode("utf-8-sig"))
    out = []
    for it in items:
        name = it.get("A") or it.get("C_Name") or ""
        cands = it.get("C") or []
        votes = it.get("V") or []
        for c, v in zip(cands, votes):
            out.append({"layer": "results", "source_id": source_id, "snapshot_id": snapshot_id, "contest": name, "unit": "county",
                        "mode": "TOTAL", "candidate": c, "votes": int(v) if str(v).isdigit() else None,
                        "precincts_reporting": it.get("PR"), "precincts_total": it.get("PT"), "as_of": as_of, "unofficial": True})
    return out


def run(base, source_id, state_file, dry_run=False):
    try:
        ver = current_version(base)
    except Exception as e:  # noqa: BLE001
        update_source_health(source_id, False, str(e))
        ops_log("clarity_version_failed", source_id=source_id, error=str(e)[:300])
        print(f"{source_id}: version check failed: {e}")
        return 2 if str(e).startswith("challenge") else 1
    state = json.load(open(state_file)) if os.path.exists(state_file) else {}
    if state.get("ver") == ver:
        print(f"{source_id}: unchanged (ver {ver})")
        update_source_health(source_id, True)
        return 0
    raw = fetch_summary(base, ver)
    snap = record_snapshot(source_id, "results", raw, "ok", keep_raw=True, note=f"ver {ver}")
    recs = parse_summary(raw, source_id, snap["id"], snap["fetched_at"])
    if not dry_run:
        for r in recs:
            append_jsonl(os.path.join(DATA, "results", f"{source_id}.jsonl"), r)
        os.makedirs(os.path.dirname(state_file) or ".", exist_ok=True)
        json.dump({"ver": ver, "at": utcnow()}, open(state_file, "w"))
    update_source_health(source_id, True)
    ops_log("clarity_pull", source_id=source_id, ver=ver, records=len(recs), snapshot=snap["id"])
    print(f"{source_id}: ver {ver}, {len(recs)} records, {len(raw)} bytes")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="https://results.enr.clarityelections.com/MI/Macomb/127293")
    ap.add_argument("--source-id", default="macomb_clarity_enr")
    ap.add_argument("--state-file", default=os.path.join(DATA, "results", ".state_macomb_clarity.json"))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    sys.exit(run(a.base, a.source_id, a.state_file, a.dry_run))
