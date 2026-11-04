#!/usr/bin/env python3
"""Ingest a Clarity (Scytl) detail-XML bundle captured in a real browser by tools/browser/clarity_capture.js.

Why this exists: Clarity ENR hosts answer plain HTTP clients (GitHub runners, this sandbox) with an AWS WAF JavaScript
challenge (HTTP 202, empty body). A browser that loads the county's public results page passes the challenge the way any
visitor does, and the capture script reads the same version file and reports/detailxml.zip the page itself loads, then
hands back one gzip'd JSON bundle (county totals by vote type for every contest; precinct × choice × vote type for the
state legislative, congressional, statewide and county-executive contests). Nothing is spoofed or worked around.

This tool is the poller half: the bundle (gzip bytes) is the append-only snapshot's raw payload (its note carries the
Clarity version and the sha256 of the detailxml.zip the browser read), and the records it appends to
data/results/<source_id>.jsonl use the same shapes the Macomb cards, detail table, seat sums and anomaly rules already read:
  * unit "county", mode TOTAL      one row per candidate (the card)  — carries precincts_reporting / precincts_total
  * unit "county", mode AVCB/ED/EV one row per candidate per vote type (the mode strip)
  * unit "<precinct>", mode AVCB/ED/EV and TOTAL, one row per candidate (detail table + anomaly rules), `complete` when the
    precinct's turnout row says it has reported
Contest ids come from macomb_compact_pdf.compact_contest_id (same ids as the Clerk's summary PDF), so a Clarity capture and
a PDF snapshot of the same contest are the same card id with different source_id.

An unchanged capture (same Clarity version and same zip sha256 as the last ingested one) records nothing.

Usage:
  python3 tools/ingest_clarity_bundle.py --bundle capture.b64 [--source-id macomb_clarity_enr] [--dry-run]
"""
from __future__ import annotations

import argparse
import base64
import gzip
import json
import os
import re
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA, append_jsonl, dump_json, load_json, ops_log, record_snapshot, update_source_health, utcnow  # noqa: E402
from macomb_compact_pdf import _PARTY, compact_contest_id  # noqa: E402

MODE_OF = {"Absentee": "AVCB", "Election Day": "ED", "Early Voting": "EV", "Absentee by Mail": "AVCB", "Early In-Person": "EV"}
WRITE_IN_RX = re.compile(r"write-?in", re.I)
_TZ = {"EDT": -4, "EST": -5, "CDT": -5, "CST": -6}


def clarity_timestamp_to_iso(ts: str | None) -> str | None:
    """'10/9/2026 9:47:45 AM EDT' -> '2026-10-09T13:47:45Z'. Unknown shapes return None (callers fall back to fetched_at)."""
    if not ts:
        return None
    m = re.match(r"^\s*(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{2}):(\d{2})\s*([AP]M)\s*([A-Z]{3})?\s*$", ts)
    if not m:
        return None
    mo, d, y, hh, mm, ss, ap, tz = m.groups()
    h = int(hh) % 12 + (12 if ap == "PM" else 0)
    off = _TZ.get(tz or "", -5)
    local = datetime(int(y), int(mo), int(d), h, int(mm), int(ss), tzinfo=timezone(timedelta(hours=off)))
    return local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def candidate_name(text: str, party: str | None) -> str:
    """Clarity prefixes the party code to the choice text ('DEM Katrina Manetta'); the desk stores the bare name."""
    t = (text or "").strip()
    if party and t.upper().startswith(party.upper() + " "):
        t = t[len(party) + 1:].strip()
    return t


def crc32_js(text: str) -> int:
    """CRC-32 the way clarity_capture_compact.js computes it: over UTF-16 code units (charCodeAt), xor'd whole into the register."""
    crc = 0xFFFFFFFF
    units = text.encode("utf-16-le")
    for i in range(0, len(units), 2):
        crc ^= units[i] | (units[i + 1] << 8)
        for _ in range(8):
            crc = (crc >> 1) ^ (0xEDB88320 if crc & 1 else 0)
    return (crc ^ 0xFFFFFFFF) & 0xFFFFFFFF


def compact_to_bundle(cc: dict) -> dict:
    """cc1 (arrays, from clarity_capture_compact.js) -> the v1 bundle shape bundle_to_records reads."""
    vt = cc.get("vt") or []
    pr = {k: {"totalVoters": v[0], "ballotsCast": v[1], "percentReporting": v[2]} for k, v in (cc.get("pr") or {}).items() if v}
    contests = []
    for key, text, tp, prd, regv, choices, pd in cc.get("c", []):
        rows = []
        for ci, ch in enumerate(choices):
            row = {"key": None, "text": ch[0], "party": ch[1], "totalVotes": ch[2], "by_type": {vt[i]: ch[3 + i] for i in range(len(vt)) if 3 + i < len(ch)}}
            if pd is not None:
                row["precincts"] = {pn: {vt[i]: vals[ci][i] for i in range(len(vt))} for pn, vals in pd.items() if ci < len(vals) and vals[ci]}
            rows.append(row)
        contests.append({"key": key, "text": text, "voteFor": None, "isQuestion": False, "precinctsTotal": tp, "precinctsReported": prd,
                         "regVoters": regv, "detail": pd is not None, "choices": rows})
    t = cc.get("turnout") or [None, None]
    return {"kind": "clarity_detailxml_bundle", "v": 1, "compact": True, "base": cc.get("base"), "ver": cc.get("ver"), "fetched_at": cc.get("fetched"),
            "zip_sha256": cc.get("zsha"), "zip_bytes": cc.get("zb"), "timestamp": cc.get("ts"), "region": None,
            "turnout": {"totalVoters": t[0], "ballotsCast": t[1]}, "precinct_reporting": pr, "contests": contests}


def decode_bundle(path: str) -> tuple[bytes, dict]:
    """Returns (raw bytes to store as the snapshot payload, v1 bundle dict). Accepts: base64 of gzip'd v1 JSON (clarity_capture.js),
    plain v1 JSON, or compact cc1 JSON with its CRC-32 (clarity_capture_compact.js) — a CRC mismatch refuses the file."""
    with open(path, "rb") as fh:
        raw = fh.read().strip()
    text = raw.decode("utf-8")
    if text.startswith("{"):
        doc = json.loads(text)
        if doc.get("k") == "cc1":
            m = re.search(r',"crc":(\d+)\}\s*$', text)
            if not m:
                raise SystemExit("cc1 capture has no trailing crc field")
            want, got = int(m.group(1)), crc32_js(text[:m.start()] + "}")
            if want != got:
                raise SystemExit(f"cc1 capture CRC mismatch (file {want}, computed {got}) — copy error; re-run the capture and paste again")
            return raw, compact_to_bundle(doc)
        if doc.get("kind") != "clarity_detailxml_bundle":
            raise SystemExit("not a clarity bundle")
        return raw, doc
    gz = base64.b64decode(raw, validate=False)
    doc = json.loads(gzip.decompress(gz).decode("utf-8"))  # gzip's own CRC catches a corrupted paste
    if doc.get("kind") != "clarity_detailxml_bundle":
        raise SystemExit("not a clarity_detailxml_bundle")
    return gz, doc


def bundle_to_records(doc: dict, source_id: str, snapshot_id: str | None, fetched_at: str, county: str | None = None) -> list[dict]:
    """county=None (or "Macomb"): Macomb contest ids (macomb-hd58, ...). Any other county: the records are that county's PORTION of
    statewide seats — ids mi-hd-NNN / mi-sd-NN / us-house-MI-NN (tools/poll_totalvote.contest_id_for) with a `county` field, which
    tools/mi_legislature.py sums county by county; contests that map to nothing (local offices, proposals) are skipped."""
    as_of = clarity_timestamp_to_iso(doc.get("timestamp")) or fetched_at
    pr = doc.get("precinct_reporting") or {}
    scope = {c["id"]: c.get("county_scope") for c in load_json(os.path.join(DATA, "contests", "macomb_2026.json"), {"contests": []})["contests"]}
    portion = bool(county) and county.lower() != "macomb"
    if portion:
        from poll_totalvote import contest_id_for
    recs = []
    for c in doc.get("contests", []):
        if portion:
            cid = contest_id_for(c.get("text") or "")
            if not cid:
                continue
        else:
            cid = compact_contest_id({"title": c.get("text")})
        multi = bool(re.search(r"State Senator|State Representative|Representative in Congress|Governor|United States Senator|Secretary of State|Attorney General", c.get("text") or ""))
        base = {"layer": "results", "contest_id": cid, "contest_name": c.get("text"), "source_id": source_id, "snapshot_id": snapshot_id,
                "as_of": as_of, "unofficial": True, "clarity_key": c.get("key"), "clarity_ver": doc.get("ver"),
                "county_scope": "county_portion" if portion else (scope.get(cid) or ("macomb_portion" if multi else "macomb_only"))}
        if portion:
            base["county"] = county
        for ch in c.get("choices", []):
            party_raw = ch.get("party")
            wi = bool(WRITE_IN_RX.search(ch.get("text") or ""))
            party = None if wi else _PARTY.get(party_raw, party_raw)
            name = candidate_name(ch.get("text"), party_raw)
            common = {**base, "candidate": name, "party": party, "party_raw": party_raw, "write_in": wi}
            recs.append({**common, "unit": "county", "mode": "TOTAL", "votes": ch.get("totalVotes"),
                         "precincts_reporting": c.get("precinctsReported"), "precincts_total": c.get("precinctsTotal"), "reg_voters": c.get("regVoters")})
            for vt, v in (ch.get("by_type") or {}).items():
                mode = MODE_OF.get(vt)
                if mode and v is not None:
                    recs.append({**common, "unit": "county", "mode": mode, "votes": v})
            for pname, by_vt in (ch.get("precincts") or {}).items():
                info = pr.get(pname) or {}
                # Clarity percentReporting codes seen live Nov 3: 1 = not reporting, 2 = partial, 4 = complete (matches precinctsReported)
                complete = info.get("percentReporting") == 4
                tot = 0
                for vt, v in by_vt.items():
                    mode = MODE_OF.get(vt)
                    if mode and v is not None:
                        tot += v
                        recs.append({**common, "unit": pname, "mode": mode, "votes": v, "complete": complete, "ballots": info.get("ballotsCast")})
                recs.append({**common, "unit": pname, "mode": "TOTAL", "votes": tot, "complete": complete, "ballots": info.get("ballotsCast")})
    return recs


def run(bundle_path: str, source_id: str, state_file: str, dry_run: bool = False, county: str | None = None) -> int:
    gz, doc = decode_bundle(bundle_path)
    state = load_json(state_file, {}) if os.path.exists(state_file) else {}
    ver, zsha = doc.get("ver"), doc.get("zip_sha256")
    if state.get("ver") == ver and state.get("zip_sha256") == zsha:
        print(f"{source_id}: unchanged (ver {ver}, zip {str(zsha)[:12]})")
        update_source_health(source_id, True)
        ops_log("clarity_browser_unchanged", source_id=source_id, ver=ver)
        return 0
    fetched_at = utcnow()
    if dry_run:
        snap = {"id": f"{source_id}:{fetched_at}:dryrun", "fetched_at": fetched_at}
    else:
        snap = record_snapshot(source_id, "results", gz, "ok", keep_raw=True,
                               note=f"browser capture; ver {ver}; detailxml.zip sha256 {zsha} ({doc.get('zip_bytes')} bytes); timestamp {doc.get('timestamp')}")
    recs = bundle_to_records(doc, source_id, snap["id"], snap["fetched_at"], county=county)
    if not dry_run:
        out = os.path.join(DATA, "results", f"{source_id}.jsonl")
        for r in recs:
            append_jsonl(out, r)
        os.makedirs(os.path.dirname(state_file) or ".", exist_ok=True)
        dump_json(state_file, {"ver": ver, "zip_sha256": zsha, "timestamp": doc.get("timestamp"), "at": fetched_at})
        update_source_health(source_id, True)
        ops_log("clarity_browser_pull", source_id=source_id, ver=ver, records=len(recs), snapshot=snap["id"],
                contests=len(doc.get("contests", [])), timestamp=doc.get("timestamp"), ballots_cast=(doc.get("turnout") or {}).get("ballotsCast"))
    print(f"{source_id}: ver {ver}, timestamp {doc.get('timestamp')}, {len(doc.get('contests', []))} contests, {len(recs)} records"
          f"{' (dry run)' if dry_run else ''}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True, help="file holding the base64 string the capture script returned (or the plain JSON bundle)")
    ap.add_argument("--source-id", default="macomb_clarity_enr")
    ap.add_argument("--state-file", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--county", default=None, help="for a county other than Macomb: records become that county's portion of statewide seats (mi-hd-NNN, mi-sd-NN, us-house-MI-NN)")
    a = ap.parse_args(argv)
    st = a.state_file or os.path.join(DATA, "results", f".state_{a.source_id}_browser.json")
    return run(a.bundle, a.source_id, st, a.dry_run, county=a.county)


if __name__ == "__main__":
    sys.exit(main())
