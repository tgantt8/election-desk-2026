#!/usr/bin/env python3
"""North Carolina SBE election-night bulk results (S3 zip) -> RESULTS layer only.

Source: https://s3.amazonaws.com/dl.ncsbe.gov/ENRS/2026_11_03/results_pct_20261103.zip (tab-delimited precinct file inside).
One conditional GET per pass (If-None-Match / If-Modified-Since from the state file); 304 -> "unchanged", no snapshot, no records.

Layer discipline: writes ONLY data/results/<source_id>.jsonl (+ snapshot index/raw store, ops log, source health). Records are
UNOFFICIAL (`is_official` False). No race calls: `vendor_is_winner` is always None here.

Emitted contests: US Senate, US House, NC State Senate, NC State House (statewide sums per candidate). US Senate additionally
gets one county row per candidate per county (unit "county"). Everything else (judicial, local, measures) is skipped.

Reporting is an approximation: units_total = distinct (County, Precinct) rows seen for the contest, units_reporting = those
whose contest total votes > 0 (method "precincts_with_votes"). Pseudo-precincts (absentee/provisional buckets) are counted too.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
import zipfile
from collections import defaultdict
from datetime import timezone
from email.utils import parsedate_to_datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA, USER_AGENT, append_jsonl, dump_json, load_json, ops_log, record_snapshot, update_source_health, utcnow  # noqa: E402

SOURCE_ID = "enr_nc_s3_results"
ELECTION_DATE = "2026-11-03"
TIMEOUT_S = 120
MAX_UNZIPPED = 300 * 1024 * 1024
MODES = ("Election Day", "Early Voting", "Absentee by Mail", "Provisional")
PARTY = {"DEM": "D", "REP": "R", "LIB": "L", "GRE": "G", "CST": "C", "UNA": "I", "IND": "I"}

_RX_USSEN = re.compile(r"^\s*US\s+SENATE\b", re.I)
_RX_USH = re.compile(r"^\s*US\s+HOUSE\s+OF\s+REPRESENTATIVES\s+DISTRICT\s+(\d+)\s*$", re.I)
_RX_NCS = re.compile(r"^\s*NC\s+STATE\s+SENATE\s+DISTRICT\s+(\d+)\s*$", re.I)
_RX_NCH = re.compile(r"^\s*NC\s+HOUSE\s+OF\s+REPRESENTATIVES\s+DISTRICT\s+(\d+)\s*$", re.I)


def map_contest_id(name: str) -> str:
    n = (name or "").strip()
    if _RX_USSEN.match(n):
        return "us-senate-NC"
    m = _RX_USH.match(n)
    if m:
        return f"us-house-NC-{int(m.group(1)):02d}"
    m = _RX_NCS.match(n)
    if m:
        return f"nc-sd-{int(m.group(1)):02d}"
    m = _RX_NCH.match(n)
    if m:
        return f"nc-hd-{int(m.group(1)):03d}"
    return "nc-other-" + (re.sub(r"[^a-z0-9]+", "-", n.lower()).strip("-") or "unnamed")


def normalize_party(raw):
    """-> (party, is_write_in-by-party). Blank -> None."""
    r = (raw or "").strip().upper()
    if not r:
        return None, False
    if r.startswith("WRI"):
        return None, True
    return PARTY.get(r, "other"), False


def _int(v):
    try:
        return int(str(v).replace(",", "").strip() or 0)
    except ValueError:
        return 0


def _decode(b: bytes) -> str:
    try:
        return b.decode("utf-8-sig")
    except UnicodeDecodeError:
        return b.decode("latin-1")


def read_rows(zip_bytes: bytes):
    """Zip bytes -> list of dict rows from the first .txt (header-driven; trailing empty column dropped)."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = [i for i in zf.infolist() if i.filename.lower().endswith(".txt") and not i.is_dir()]
        if not names:
            raise ValueError("no .txt member in zip")
        info = names[0]
        if info.file_size > MAX_UNZIPPED:
            raise ValueError(f"txt member too large: {info.file_size}")
        text = _decode(zf.read(info))
    rdr = csv.reader(io.StringIO(text, newline=""), delimiter="\t", quoting=csv.QUOTE_NONE)
    header = None
    out = []
    for row in rdr:
        if header is None:
            header = [h.strip() for h in row]
            while header and not header[-1]:
                header.pop()
            if "Contest Name" not in header or "Total Votes" not in header:
                raise ValueError(f"unexpected header: {header[:6]}")
            continue
        if not any(c.strip() for c in row):
            continue
        out.append({h: (row[i].strip() if i < len(row) else "") for i, h in enumerate(header)})
    return out


def aggregate(rows):
    """-> (state_agg, county_agg). state_agg[(cid, contest_name, choice)] = {...}; county_agg[(cid, name, choice, county)] = {...}."""
    state = {}
    county = {}
    units = defaultdict(set)       # cid -> {(county, precinct)}
    units_live = defaultdict(set)  # cid -> units with contest votes > 0
    unit_votes = defaultdict(int)  # (cid, county, precinct) -> votes across choices
    for r in rows:
        name = r.get("Contest Name", "")
        cid = map_contest_id(name)
        if cid.startswith("nc-other-"):
            continue
        choice = r.get("Choice", "")
        party_raw = r.get("Choice Party", "")
        tv = _int(r.get("Total Votes"))
        modes = {m: _int(r.get(m)) for m in MODES}
        unit = (r.get("County", ""), r.get("Precinct", ""))
        units[cid].add(unit)
        unit_votes[(cid,) + unit] += tv
        for key, bucket in (((cid, name, choice), state), ((cid, name, choice, unit[0]), county if cid == "us-senate-NC" else None)):
            if bucket is None:
                continue
            a = bucket.setdefault(key, {"party_raw": party_raw, "votes": 0, "modes": {m: 0 for m in MODES}, "units": set(), "live": set()})
            a["votes"] += tv
            for m in MODES:
                a["modes"][m] += modes[m]
            a["units"].add(unit)
            if tv > 0:
                a["live"].add(unit)
    for (cid, c, p), v in unit_votes.items():
        if v > 0:
            units_live[cid].add((c, p))
    return state, county, units, units_live, unit_votes


def _is_write_in(choice, party_raw):
    return bool(re.search(r"write[\s-]*in", choice or "", re.I)) or (party_raw or "").strip().upper().startswith("WRI")


def build_records(rows, source_id, snapshot_id, fetched_at, as_of, source_url):
    state, county, units, units_live, unit_votes = aggregate(rows)
    base = {"layer": "results", "source_id": source_id, "snapshot_id": snapshot_id, "election_date": ELECTION_DATE,
            "as_of": as_of, "fetched_at": fetched_at, "source_url": source_url, "unofficial": True, "is_official": False,
            "vendor_is_winner": None, "contest_type": "candidate"}
    out = []

    def rec(cid, name, choice, a, unit, cty, rep):
        party, wi = normalize_party(a["party_raw"])
        wi = wi or _is_write_in(choice, a["party_raw"])
        if wi:
            party = None
        r = dict(base, contest_id=cid, contest_name=name, candidate=choice, party=party, party_raw=a["party_raw"] or None,
                 is_write_in=wi, votes=a["votes"], votes_by_mode=dict(a["modes"]), reporting=rep, unit=unit)
        if cty is not None:
            r["county"] = cty
        return r

    for (cid, name, choice), a in sorted(state.items()):
        ut, ur = len(units[cid]), len(units_live[cid])
        rep = {"pct": round(100.0 * ur / ut, 2) if ut else None, "units_reporting": ur, "units_total": ut, "method": "precincts_with_votes"}
        out.append(rec(cid, name, choice, a, "state", None, rep))
    for (cid, name, choice, cty), a in sorted(county.items()):
        cu = {u for u in units[cid] if u[0] == cty}
        ut, ur = len(cu), sum(1 for u in cu if unit_votes[(cid,) + u] > 0)
        rep = {"pct": round(100.0 * ur / ut, 2) if ut else None, "units_reporting": ur, "units_total": ut, "method": "precincts_with_votes"}
        out.append(rec(cid, name, choice, a, "county", cty, rep))
    return out


def _iso(lm):
    try:
        return parsedate_to_datetime(lm).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:  # noqa: BLE001
        return None


def run(source, state_file=None, dry_run=False, session=None):
    sid = source.get("id", SOURCE_ID)
    url = source["url"]
    state_file = state_file or os.path.join(DATA, "results", f".state_{sid}.json")
    state = load_json(state_file, {}) or {}
    try:
        import requests
        sess = session or requests
        hdr = {"User-Agent": USER_AGENT}
        if state.get("etag"):
            hdr["If-None-Match"] = state["etag"]
        if state.get("last_modified"):
            hdr["If-Modified-Since"] = state["last_modified"]
        resp = sess.get(url, headers=hdr, timeout=TIMEOUT_S)
        if resp.status_code == 304:
            ops_log("nc_s3_unchanged", source_id=sid)
            update_source_health(sid, True)
            return {"status": "unchanged", "records": 0}
        resp.raise_for_status()
        raw = resp.content
        lm = resp.headers.get("Last-Modified")
        etag = resp.headers.get("ETag")
        snap = record_snapshot(sid, "results", raw, "ok", keep_raw=True, note=f"Last-Modified {lm}")
        rows = read_rows(raw)
        recs = build_records(rows, sid, snap["id"], snap["fetched_at"], _iso(lm) if lm else snap["fetched_at"], url)
        if not dry_run:
            path = os.path.join(DATA, "results", f"{sid}.jsonl")
            for r in recs:
                append_jsonl(path, r)
            dump_json(state_file, {"etag": etag, "last_modified": lm, "at": utcnow()})
        ops_log("nc_s3_pull", source_id=sid, records=len(recs), snapshot=snap["id"], last_modified=lm)
        update_source_health(sid, True)
        return {"status": "ok", "records": len(recs), "snapshot": snap["id"], "last_modified": lm}
    except Exception as e:  # noqa: BLE001
        err = f"{type(e).__name__}: {e}"[:300]
        update_source_health(sid, False, err)
        ops_log("nc_s3_failed", source_id=sid, error=err)
        return {"status": "error", "error": err}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--state-file")
    a = ap.parse_args()
    src = load_json(os.path.join(DATA, "sources.json"))["sources"]
    src = next(s for s in src if s["id"] == SOURCE_ID)
    print(json.dumps(run(src, state_file=a.state_file, dry_run=a.dry_run), sort_keys=True))
