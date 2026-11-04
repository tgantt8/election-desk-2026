#!/usr/bin/env python3
"""Poll a TotalVote (BPro/Civix) county election-night page — Wayne County, Michigan (michigan.totalvote.com/Wayne).

The Wayne County Clerk's "Unofficial Results Election Display" is a server-rendered HTML page per office type
(ResultsSW.aspx?type=REP|SEN|CON|ST&cid=05). It is reachable from the GitHub runner (reach test Nov 3, 9:40 PM ET). Each
contest block carries the contest title, "Precincts Reported: a / b", and one row per candidate (name, party class, votes).

Records are the Wayne County PORTION of each contest (unit "county", county "Wayne", mode TOTAL), in the shape
tools/mi_legislature.py sums county by county for statewide seats (mi-hd-NNN / mi-sd-NN). Nothing is parsed from memory:
the page's own "Results Last Updated" stamp is the as_of, and an unchanged stamp records nothing.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA, USER_AGENT, append_jsonl, dump_json, load_json, ops_log, record_snapshot, update_source_health, utcnow  # noqa: E402
from ingest_clarity_bundle import clarity_timestamp_to_iso  # noqa: E402  ("11/3/2026 9:17:42 PM EST" → ISO)

PARTY = {"DEM": "D", "REP": "R", "LIB": "L", "GRN": "G", "UST": "U", "NLP": "N", "WC": "W", "WCP": "W", "NPA": "I", "NON": None, "IND": "I"}
HEADERS = {"User-Agent": USER_AGENT}
_RX_UPDATED = re.compile(r"Results Last Updated:?\s*</?[^>]*>?\s*([0-9/]+\s+[0-9:]+\s*[AP]M\s*[A-Z]{2,4})", re.I)
_RX_DIST = re.compile(r"(?:(\d+)(?:st|nd|rd|th)\s+District|District\s+(\d+))", re.I)  # "28th District" and Wayne's "District 12"
_RX_PREC = re.compile(r"Precincts Reported:\s*([\d,]+)\s*/\s*([\d,]+)")


def contest_id_for(title: str, state="mi") -> str | None:
    t = title.strip()
    m = _RX_DIST.search(t)
    n = int(m.group(1) or m.group(2)) if m else None
    if re.match(r"^(State Representative|Representative in State Legislature)", t, re.I) and n:
        return f"mi-hd-{n:03d}"
    if re.match(r"^State Senator", t, re.I) and n:
        return f"mi-sd-{n:02d}"
    if re.search(r"Representative in Congress|U\.?S\.? Representative", t, re.I) and n:
        return f"us-house-MI-{n:02d}"
    if re.match(r"^United States Senator|^U\.?S\.? Senator", t, re.I):
        return "us-senate-MI"
    if re.match(r"^Governor", t, re.I) and not re.search(r"University", t, re.I):
        return "gov-MI"
    return None


_RX_TAGS = re.compile(r"<[^>]+>")
_RX_CAND = re.compile(r'display-results-box-d">\s*<h1>\s*(.*?)\s*</h1>\s*<h2 class="([A-Za-z]*)">(.*?)</h2>.*?display-results-box-f">\s*<h1>\s*([\d,]*)\s*</h1>', re.S)


def _clean(x: str) -> str:
    return re.sub(r"\s+", " ", _RX_TAGS.sub(" ", x)).strip()


def parse_page(html: str) -> tuple[str | None, list[dict]]:
    """Returns (last_updated_text, contests[{title, precincts_reporting, precincts_total, candidates[{name, party_raw, party_name, votes}]}]).
    Regex over the server-rendered markup (no third-party parser on the runner): each contest starts at a
    display-results-box-wrapper div; its candidate rows follow until the next wrapper."""
    text = _clean(html)
    m = re.search(r"Results Last Updated:?\s*([0-9]{1,2}/[0-9]{1,2}/[0-9]{4}\s+[0-9]{1,2}:[0-9]{2}:[0-9]{2}\s*[AP]M\s*[A-Z]{2,4})", text)
    updated = m.group(1).strip() if m else None
    out = []
    parts = html.split('<div class="display-results-box-wrapper">')[1:]
    for part in parts:
        hm = re.search(r"<h1>(.*?)</h1>", part, re.S)
        if not hm:
            continue
        title = _clean(hm.group(1)).split(" - ")[0].strip()
        pm = _RX_PREC.search(_clean(part))
        cands = []
        for name, party_raw, party_name, v in _RX_CAND.findall(part):
            name = _clean(name)
            if not name:
                continue
            v = v.replace(",", "").strip()
            cands.append({"name": name, "party_raw": party_raw or None, "party_name": _clean(party_name), "votes": int(v) if v.isdigit() else None})
        out.append({"title": title, "precincts_reporting": int(pm.group(1).replace(",", "")) if pm else None,
                    "precincts_total": int(pm.group(2).replace(",", "")) if pm else None, "candidates": cands})
    return updated, out


def to_records(contests, updated, source_id, county, snapshot_id, fetched_at, url):
    as_of = clarity_timestamp_to_iso(updated) or fetched_at
    recs = []
    for c in contests:
        cid = contest_id_for(c["title"])
        if not cid:
            continue
        for k in c["candidates"]:
            wi = bool(re.search(r"write-?in", k["name"], re.I))
            recs.append({"layer": "results", "source_id": source_id, "snapshot_id": snapshot_id, "contest_id": cid, "contest_name": c["title"],
                         "county": county, "unit": "county", "mode": "TOTAL", "candidate": k["name"], "party": None if wi else PARTY.get(k["party_raw"], k["party_raw"]),
                         "party_raw": k["party_raw"], "party_name": k["party_name"], "votes": k["votes"], "write_in": wi,
                         "precincts_reporting": c["precincts_reporting"], "precincts_total": c["precincts_total"],
                         "county_scope": "county_portion", "as_of": as_of, "fetched_at": fetched_at, "source_url": url, "unofficial": True})
    return recs


def run(source: dict, state_file=None, dry_run=False, session=None, now=None):
    session = session or requests.Session()
    sid = source["id"]
    tv = source.get("totalvote") or {}
    base, cid, county = tv.get("base", "https://michigan.totalvote.com/Wayne"), tv.get("cid", "05"), tv.get("county", "Wayne")
    pages = tv.get("pages") or {"REP": "", "SEN": "CTY"}
    state_file = state_file or os.path.join(DATA, "results", f".state_{sid}.json")
    state = load_json(state_file, {}) if os.path.exists(state_file) else {}
    fetched_at = now or utcnow()
    n = 0
    errors = []
    for typ, mp in pages.items():
        url = f"{base}/ResultsSW.aspx?type={typ}&cid={cid}&map={mp}"
        try:
            r = session.get(url, headers=HEADERS, timeout=90)
            r.raise_for_status()
            updated, contests = parse_page(r.text)
        except Exception as e:  # noqa: BLE001
            errors.append(f"{typ}: {str(e)[:160]}")
            continue
        if not contests:
            errors.append(f"{typ}: no contest blocks parsed")
            continue
        if updated and state.get(typ) == updated:
            print(f"{sid} {typ}: unchanged ({updated})")
            continue
        snap = None if dry_run else record_snapshot(sid, "results", r.content, "ok", keep_raw=True, note=f"{typ}: {len(contests)} contests; Results Last Updated {updated}")
        recs = to_records(contests, updated, sid, county, snap["id"] if snap else None, fetched_at, url)
        if not dry_run:
            for rec in recs:
                append_jsonl(os.path.join(DATA, "results", f"{sid}.jsonl"), rec)
            state[typ] = updated
        n += len(recs)
        print(f"{sid} {typ}: {len(contests)} contests, {len(recs)} records, updated {updated}")
    if not dry_run:
        os.makedirs(os.path.dirname(state_file) or ".", exist_ok=True)
        state["at"] = fetched_at
        dump_json(state_file, state)
        if errors and n == 0 and len(errors) == len(pages):
            update_source_health(sid, False, "; ".join(errors)[:300])
            ops_log("totalvote_failed", source_id=sid, errors=errors)
            return {"status": "error", "errors": errors}
        update_source_health(sid, True)
        ops_log("totalvote_pull", source_id=sid, records=n, errors=errors)
    return {"status": "ok", "records": n, "errors": errors}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-id", default="enr_wayne_totalvote")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    src = next((s for s in load_json(os.path.join(DATA, "sources.json"), {"sources": []})["sources"] if s["id"] == a.source_id), None)
    if not src:
        sys.exit(f"{a.source_id}: not in data/sources.json")
    out = run(src, dry_run=a.dry_run)
    print(json.dumps(out))
    return 0 if out["status"] == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
