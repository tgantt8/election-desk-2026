#!/usr/bin/env python3
"""Poll the Macomb County Clerk's unofficial summary results PDF (overwritten in place on election night).

Conditional GET on Last-Modified/ETag; every distinct payload is an append-only snapshot (gzip'd raw PDF kept, hash
indexed). Parsing into results records is done by tools/macomb_compact_pdf.py when present; until then the poller
records the snapshot and the parse_status "unparsed".
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA, USER_AGENT, append_jsonl, last_snapshot_hash, ops_log, record_snapshot, sha256_bytes, update_source_health, utcnow  # noqa: E402

URL = "https://macombgovdocs.org/clerk/pdfs/elect-2026-11-03-unofficial-summary-results.pdf"


def run(url, source_id, state_file, dry_run=False):
    state = json.load(open(state_file)) if os.path.exists(state_file) else {}
    headers = {"User-Agent": USER_AGENT}
    if state.get("etag"):
        headers["If-None-Match"] = state["etag"]
    if state.get("last_modified"):
        headers["If-Modified-Since"] = state["last_modified"]
    try:
        r = requests.get(url, headers=headers, timeout=60)
    except Exception as e:  # noqa: BLE001
        update_source_health(source_id, False, str(e))
        ops_log("pdf_fetch_failed", source_id=source_id, error=str(e)[:300])
        print(f"{source_id}: fetch failed: {e}")
        return 1
    if r.status_code == 304:
        print(f"{source_id}: not modified")
        update_source_health(source_id, True)
        return 0
    r.raise_for_status()
    raw = r.content
    h = sha256_bytes(raw)
    if h == last_snapshot_hash(source_id):
        print(f"{source_id}: unchanged payload ({h[:12]})")
        update_source_health(source_id, True)
    else:
        parse_status = "unparsed"
        recs = []
        try:
            from macomb_compact_pdf import parse_compact_pdf_bytes  # optional, lands with the compact parser

            parsed = parse_compact_pdf_bytes(raw)
            parse_status = parsed.get("parse_status", "ok")
            recs = parsed.get("records", [])
        except ImportError:
            pass
        except Exception as e:  # noqa: BLE001
            parse_status = f"parse_error: {str(e)[:120]}"
        snap = record_snapshot(source_id, "results", raw, parse_status, keep_raw=True, note=f"Last-Modified {r.headers.get('Last-Modified', '')}")
        if not dry_run:
            for rec in recs:
                rec.update({"source_id": source_id, "snapshot_id": snap["id"], "as_of": r.headers.get("Last-Modified") or snap["fetched_at"], "unofficial": True})
                append_jsonl(os.path.join(DATA, "results", f"{source_id}.jsonl"), rec)
        ops_log("pdf_pull", source_id=source_id, snapshot=snap["id"], parse_status=parse_status, bytes=len(raw))
        update_source_health(source_id, True)
        print(f"{source_id}: new payload {h[:12]} ({len(raw)} bytes) parse_status={parse_status} records={len(recs)}")
    if not dry_run:
        os.makedirs(os.path.dirname(state_file) or ".", exist_ok=True)
        json.dump({"etag": r.headers.get("ETag"), "last_modified": r.headers.get("Last-Modified"), "at": utcnow()}, open(state_file, "w"))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=URL)
    ap.add_argument("--source-id", default="macomb_clerk_unofficial_summary_pdf")
    ap.add_argument("--state-file", default=os.path.join(DATA, "results", ".state_macomb_pdf.json"))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    sys.exit(run(a.url, a.source_id, a.state_file, a.dry_run))
