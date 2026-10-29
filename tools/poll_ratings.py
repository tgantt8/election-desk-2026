#!/usr/bin/env python3
"""Ratings pollers -> RATINGS layer only (label + date + link; never analysis text).

Raters and parse targets (structures read 2026-10-29):
  * Cook Political Report — the print pages /print/ratings/races/{senate,governor,house} are one-page PDFs. Senate and
    Governor list every race in a 7-column grid (SOLID D … SOLID R) under "DEMOCRATS | N HELD SEATS" / "REPUBLICANS | N HELD
    SEATS"; the House page lists only the competitive races in a 6-column grid (LIKELY DEMOCRATIC … LIKELY REPUBLICAN) with a
    per-column "<n> Dem • <m> Rep" tally. The page date ("Oct 20, 2026") is the page's last update, not a per-race change date.
    robots.txt (read 2026-10-29): the default group allows these paths and signals search=yes, ai-input=yes, ai-train=no.
    Scope (Tabu, decision 5): Senate, Governor and Michigan House labels are stored and shown; other House districts are
    link-only (counted, never stored). Raw PDFs are not kept (hash only) so the public repo never carries the full label set.
  * Inside Elections — the public ratings pages load a cached JSON the site itself documents as "public, cached files — no
    auth required": /wp-content/themes/inside-elections/cache/ratings_latest_{senate,house,governor}_year=all_district=all_public.json
    with per-race {district, office, date, rating, previous_rating}. Same storage scope as Cook. robots.txt: ai-train=no,
    use=reference; the desk stores labels, dates and links only.
  * Sabato's Crystal Ball — Cloudflare challenge from the sandbox (2026-10-29); manual entry (tools/manual_entry.py --layer
    ratings) until a runner fetch is proven. Never try to defeat a challenge.

Layer discipline: writes only data/ratings/<source_id>.jsonl (append-only rows per snapshot), data/ratings/changes.jsonl
(append-only change log), the snapshot index, the ops log and source health. Never touches any other layer.
A new row set is appended only when the label set or the page date differs from the previous snapshot for that source.
Hard stops (no parse, no write, health red): HTTP 401/403/429, a login redirect, a Cloudflare/WAF challenge page.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA, USER_AGENT, append_jsonl, load_json, ops_log, read_jsonl, record_snapshot, update_source_health  # noqa: E402

SCALE = {"Solid D": -3, "Likely D": -2, "Lean D": -1, "Tilt D": -1, "Battleground D": -1, "Toss-up": 0,
         "Battleground R": 1, "Tilt R": 1, "Lean R": 1, "Likely R": 2, "Solid R": 3}
LOSSY = {"Tilt D", "Tilt R", "Battleground D", "Battleground R"}
PUBLIC_HOUSE_STATES = {"MI"}  # House labels stored/shown only for these states; every other district is link-only
COOK_PAGE = {"senate": "https://www.cookpolitical.com/ratings/senate-race-ratings",
             "governor": "https://www.cookpolitical.com/ratings/governor-race-ratings",
             "house": "https://www.cookpolitical.com/ratings/house-race-ratings"}
IE_PAGE = {"senate": "https://insideelections.com/ratings/senate/", "governor": "https://insideelections.com/ratings/governor/",
           "house": "https://insideelections.com/ratings/house/"}


class StopFetch(RuntimeError):
    """A hard stop: do not parse, do not retry in a loop."""


# --------------------------------------------------------------------------- fetch

def fetch(url, session=None, timeout=60, accept="*/*"):
    import requests
    s = session or requests.Session()
    r = s.get(url, headers={"User-Agent": USER_AGENT, "Accept": accept}, timeout=timeout, allow_redirects=True)
    if r.status_code in (401, 403, 429):
        raise StopFetch(f"HTTP {r.status_code} — stop (terms/robots rule; no retry loop)")
    if r.status_code != 200:
        raise StopFetch(f"HTTP {r.status_code}")
    final = r.url or url
    if re.search(r"/(login|signin|user/login)\b", final, re.I):
        raise StopFetch("redirected to a login page — stop")
    head = r.content[:4000].decode("utf-8", "replace")
    if "<title>Just a moment" in head or "cf-chl" in head or "challenge-platform" in head:
        raise StopFetch("Cloudflare challenge page — stop (never defeat a challenge)")
    return r.content, dict(r.headers)


# --------------------------------------------------------------------------- Cook print PDFs

_RX_PAGE_DATE = re.compile(r"\b([A-Z][a-z]{2,8})\.? (\d{1,2}), (\d{4})\b")
_MONTHS = {m: i for i, m in enumerate(["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}
_SEN_GOV_COLS = ["Solid D", "Likely D", "Lean D", "Toss-up", "Lean R", "Likely R", "Solid R"]
_HOUSE_COLS = [("Likely Democratic", "Likely D"), ("Lean Democratic", "Lean D"), ("Democratic Toss Up", "Toss-up"),
               ("Republican Toss Up", "Toss-up"), ("Lean Republican", "Lean R"), ("Likely Republican", "Likely R")]


def _words(pdf_bytes):
    import pdfplumber
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        if len(pdf.pages) != 1:
            raise ValueError(f"expected a one-page print PDF, got {len(pdf.pages)} pages")
        ws = pdf.pages[0].extract_words(x_tolerance=1.5, keep_blank_chars=False)
    return [{"t": w["text"], "x0": float(w["x0"]), "x1": float(w["x1"]), "top": float(w["top"])} for w in ws]


def _rows(words, tol=2.0):
    rows = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if rows and abs(rows[-1][0] - w["top"]) <= tol:
            rows[-1][1].append(w)
        else:
            rows.append([w["top"], [w]])
    return [(top, sorted(ws, key=lambda w: w["x0"])) for top, ws in rows]


def _page_date(words):
    text = " ".join(w["t"] for w in words[:40])
    m = _RX_PAGE_DATE.search(text)
    if not m or m.group(1)[:3] not in _MONTHS:
        raise ValueError("page date not found in the PDF header")
    return f"{int(m.group(3)):04d}-{_MONTHS[m.group(1)[:3]]:02d}-{int(m.group(2)):02d}"


def _col_index(x0, centers):
    """Assign an entry (by its left edge) to the column whose header center is nearest to the right of it."""
    bounds = [(centers[i] + centers[i + 1]) / 2 for i in range(len(centers) - 1)]
    for i, b in enumerate(bounds):
        if x0 < b:
            return i
    return len(centers) - 1


def _header_centers(row_words, labels):
    """Header row like SOLID D | LIKELY D | ... → center x of each label group, in order."""
    text = [w["t"] for w in row_words]
    centers = []
    i = 0
    for lab in labels:
        toks = lab.upper().replace("TOSS-UP", "TOSS UP").split()
        # find toks at position >= i
        for j in range(i, len(text) - len(toks) + 1):
            if [t.upper() for t in text[j:j + len(toks)]] == toks:
                centers.append((row_words[j]["x0"] + row_words[j + len(toks) - 1]["x1"]) / 2)
                i = j + len(toks)
                break
        else:
            return None
    return centers


def parse_cook_senate_governor(pdf_bytes, office):
    """-> {"page_date", "entries": [{state, raw, label, holder_party}], "held": {"D": n, "R": n}, "validation"}"""
    words = _words(pdf_bytes)
    page_date = _page_date(words)
    rows = _rows(words)
    entries, held = [], {}
    block_party, centers = None, None
    for top, ws in rows:
        text = " ".join(w["t"] for w in ws)
        m = re.match(r"^(DEMOCRATS|REPUBLICANS) \| (\d+) HELD SEATS", text)
        if m:
            block_party = "D" if m.group(1) == "DEMOCRATS" else "R"
            held[block_party] = int(m.group(2))
            centers = None
            continue
        if block_party and centers is None:
            c = _header_centers(ws, ["SOLID D", "LIKELY D", "LEAN D", "TOSS UP", "LEAN R", "LIKELY R", "SOLID R"])
            if c:
                centers = c
            continue
        if block_party and centers and not text.startswith("Copyright"):
            for w in ws:
                m2 = re.match(r"^([A-Z]{2})-(.+)$", w["t"])
                if not m2:
                    continue
                col = _col_index(w["x0"], centers)
                entries.append({"state": m2.group(1), "raw": w["t"], "incumbent": m2.group(2), "label": _SEN_GOV_COLS[col],
                                "label_raw": _SEN_GOV_COLS[col].replace("Toss-up", "Toss Up"), "holder_party": block_party})
    n_d = sum(1 for e in entries if e["holder_party"] == "D")
    n_r = sum(1 for e in entries if e["holder_party"] == "R")
    ok = held.get("D") == n_d and held.get("R") == n_r and entries
    return {"office": office, "page_date": page_date, "entries": entries, "held": held,
            "validation": "ok" if ok else f"tally_mismatch: page says D {held.get('D')} R {held.get('R')}, parsed D {n_d} R {n_r}"}


def parse_cook_house(pdf_bytes):
    """Competitive races only (that is all the print page lists). -> {"page_date", "entries": [{district, state, label, label_raw,
    incumbent}], "column_tallies": [{"label_raw", "dem", "rep", "parsed"}], "summary": {...}, "validation"}"""
    words = _words(pdf_bytes)
    page_date = _page_date(words)
    rows = _rows(words)
    centers, tallies, entries, summary = None, [], [], {}
    for top, ws in rows:
        text = " ".join(w["t"] for w in ws)
        m = re.match(r"^D - (\d+) R - (\d+) D - (\d+) R - (\d+) D - (\d+) R - (\d+)$", text)
        if m:
            g = [int(x) for x in m.groups()]
            summary = {"solid": {"D": g[0], "R": g[1]}, "likely_lean": {"D": g[2], "R": g[3]}, "tossup_or_worse": {"D": g[4], "R": g[5]}}
            continue
        if centers is None:
            c = _header_centers(ws, [lab.upper() for lab, _ in _HOUSE_COLS])
            if c:
                centers = c
            continue
        if not tallies:
            ms = re.findall(r"(\d+) Dem • (\d+) Rep", text)
            if len(ms) == len(_HOUSE_COLS):
                tallies = [{"label_raw": lab, "dem": int(d), "rep": int(r), "parsed": 0} for (lab, _), (d, r) in zip(_HOUSE_COLS, ms)]
                continue
        if centers and tallies and not text.startswith("Copyright"):
            # group words by column; the first token of a group is the district code
            groups = {}
            for w in ws:
                groups.setdefault(_col_index(w["x0"], centers), []).append(w["t"])
            for col, toks in groups.items():
                m2 = re.match(r"^([A-Z]{2})-(\d{2}|AL)$", toks[0])
                if not m2:
                    continue
                lab_raw, lab = _HOUSE_COLS[col]
                entries.append({"district": toks[0], "state": m2.group(1), "number": m2.group(2), "label": lab, "label_raw": lab_raw,
                                "incumbent": " ".join(toks[1:])})
                tallies[col]["parsed"] += 1
    bad = [t for t in tallies if t["parsed"] != t["dem"] + t["rep"]]
    ok = tallies and not bad and entries
    return {"office": "house", "page_date": page_date, "entries": entries, "column_tallies": tallies, "summary": summary,
            "validation": "ok" if ok else ("tally_mismatch: " + "; ".join(f"{t['label_raw']} {t['parsed']} vs {t['dem'] + t['rep']}" for t in bad) if tallies else "no_tally_row")}


def _race_id(office, state, number=None, senate_ids=None):
    if office == "governor":
        return f"gov-{state}"
    if office == "house":
        return f"us-house-{state}-{number}"
    ids = senate_ids or set()
    if f"us-senate-{state}" in ids:
        return f"us-senate-{state}"
    if f"us-senate-{state}-special" in ids:
        return f"us-senate-{state}-special"
    return f"us-senate-{state}"


def cook_records(parsed, office, source_id, url, snapshot_id, fetched_at, senate_ids=None):
    out, skipped = [], 0
    for e in parsed["entries"]:
        if office == "house" and e["state"] not in PUBLIC_HOUSE_STATES:
            skipped += 1
            continue
        out.append({"layer": "ratings", "race": _race_id(office, e["state"], e.get("number"), senate_ids), "rater": "Cook Political Report",
                    "office": office, "state": e["state"], "district": e.get("district"), "label": e["label"], "label_raw": e["label_raw"],
                    "label_scale": SCALE.get(e["label"]), "label_lossy": e["label"] in LOSSY, "date": parsed["page_date"], "date_kind": "page",
                    "incumbent_text": e.get("incumbent"), "url": url, "source_id": source_id, "snapshot_id": snapshot_id, "fetched_at": fetched_at,
                    "attribution": f"Rating: Cook Political Report, {parsed['page_date']}"})
    return out, skipped


# --------------------------------------------------------------------------- Inside Elections JSON

_IE_LABEL = [(re.compile(r"^Solid (Democrat|Republican)$"), "Solid {p}"), (re.compile(r"^Likely (Democrat|Republican)$"), "Likely {p}"),
             (re.compile(r"^Lean (Democrat|Republican)$"), "Lean {p}"), (re.compile(r"^Tilt (Democrat|Republican)$"), "Tilt {p}"),
             (re.compile(r"^Battleground (Democrat|Republican)$"), "Battleground {p}"), (re.compile(r"^Toss[- ]?up$", re.I), "Toss-up")]


def ie_normalize(raw):
    raw = (raw or "").strip()
    for rx, fmt in _IE_LABEL:
        m = rx.match(raw)
        if m:
            p = m.group(1)[0] if m.groups() else ""
            return fmt.format(p=p)
    if raw in ("Not Up This Cycle", "No Rating", ""):
        return None
    return raw  # e.g. "Lean Independent": kept verbatim, no scale


def parse_ie_json(raw_bytes, office):
    j = json.loads(raw_bytes.decode("utf-8-sig"))
    rs = j.get("ratings")
    if not isinstance(rs, list):
        raise ValueError("ratings list missing")
    entries = []
    for r in rs:
        label = ie_normalize(r.get("rating"))
        if label is None:
            continue
        dist = str(r.get("district") or "").upper()
        m = re.match(r"^([A-Z]{2})(?:-(\d{2}|AL))?$", dist)
        if not m:
            continue
        date = (r.get("date") or "")[:10] or None
        entries.append({"state": m.group(1), "number": m.group(2), "district": dist, "label": label, "label_raw": r.get("rating"),
                        "previous_raw": r.get("previous_rating"), "date": date, "special": bool(r.get("special")),
                        "office_code": r.get("office"), "incumbent": r.get("incumbent_name") or ", ".join(i.get("name", "") for i in (r.get("incumbent") or []))})
    return {"office": office, "page_date": (j.get("last_updated") or j.get("generated_at") or "")[:10] or None, "entries": entries,
            "total": j.get("total"), "validation": "ok" if entries else "no_entries"}


def ie_records(parsed, office, source_id, url, snapshot_id, fetched_at, senate_ids=None):
    out, skipped = [], 0
    for e in parsed["entries"]:
        if office == "house" and e["state"] not in PUBLIC_HOUSE_STATES:
            skipped += 1
            continue
        if office == "senate":
            ids = senate_ids or set()
            rid = f"us-senate-{e['state']}-special" if e["special"] and f"us-senate-{e['state']}-special" in ids else _race_id("senate", e["state"], None, ids)
        else:
            rid = _race_id(office, e["state"], e.get("number"))
        out.append({"layer": "ratings", "race": rid, "rater": "Inside Elections", "office": office, "state": e["state"], "district": e.get("district") if office == "house" else None,
                    "label": e["label"], "label_raw": e["label_raw"], "label_scale": SCALE.get(e["label"]), "label_lossy": e["label"] in LOSSY,
                    "date": e["date"] or parsed["page_date"], "date_kind": "race" if e["date"] else "page", "previous_label_raw": e.get("previous_raw"),
                    "incumbent_text": e.get("incumbent"), "url": url, "source_id": source_id, "snapshot_id": snapshot_id, "fetched_at": fetched_at,
                    "attribution": f"Rating: Inside Elections, {e['date'] or parsed['page_date']}"})
    return out, skipped


# --------------------------------------------------------------------------- common run

def _senate_ids():
    return {r["id"] for r in load_json(os.path.join(DATA, "contests", "senate_2026.json"), {"races": []})["races"]}


def _previous(source_id):
    rows = read_jsonl(os.path.join(DATA, "ratings", f"{source_id}.jsonl"))
    if not rows:
        return []
    last = rows[-1]["snapshot_id"]
    return [r for r in rows if r["snapshot_id"] == last]


def _label_set(rows):
    return {(r["race"], r["rater"]): (r["label"], r["date"]) for r in rows}


def _write(source_id, records, parsed, fetched_at):
    prev = _previous(source_id)
    prev_labels = {(r["race"], r["rater"]): r["label"] for r in prev}
    changed = _label_set(prev) != _label_set(records)
    if not changed:
        return 0, 0
    path = os.path.join(DATA, "ratings", f"{source_id}.jsonl")
    for r in records:
        append_jsonl(path, r)
    n_changes = 0
    if prev:
        for r in records:
            old = prev_labels.get((r["race"], r["rater"]))
            if old is not None and old != r["label"]:
                append_jsonl(os.path.join(DATA, "ratings", "changes.jsonl"), {"date": r["date"], "seen_at": fetched_at, "race": r["race"], "rater": r["rater"],
                                                                              "from": old, "to": r["label"], "url": r["url"], "source_id": source_id})
                n_changes += 1
        gone = set(prev_labels) - {(r["race"], r["rater"]) for r in records}
        for race, rater in sorted(gone):
            ops_log("rating_label_no_longer_present", source_id=source_id, race=race, rater=rater, note="label no longer present on page")
    return len(records), n_changes


def run(source, dry_run=False, session=None, raw=None):
    """One pull for a source row from data/sources.json: {id, poller: cook_ratings|ie_ratings, fetch_url, url, office}."""
    sid, office, poller = source["id"], source["office"], source["poller"]
    fetch_url = source.get("fetch_url") or source["url"]
    try:
        if raw is None:
            raw, _hdrs = fetch(fetch_url, session=session, accept="application/json, application/pdf, text/html;q=0.9, */*;q=0.8")
    except Exception as e:  # noqa: BLE001
        if not dry_run:
            update_source_health(sid, False, str(e)[:300])
            ops_log("ratings_fetch_stopped", source_id=sid, error=str(e)[:300])
        print(f"{sid}: {e}")
        return {"status": "error", "error": str(e), "source_id": sid}
    try:
        if poller == "cook_ratings":
            parsed = parse_cook_house(raw) if office == "house" else parse_cook_senate_governor(raw, office)
            maker = cook_records
        else:
            parsed = parse_ie_json(raw, office)
            maker = ie_records
    except Exception as e:  # noqa: BLE001
        if not dry_run:
            snap = record_snapshot(sid, "ratings", raw, f"parse_error: {type(e).__name__}: {e}"[:200], keep_raw=False)
            update_source_health(sid, False, f"parse_error: {e}"[:300])
            ops_log("ratings_parse_failed", source_id=sid, snapshot=snap["id"], error=str(e)[:300])
        print(f"{sid}: parse error: {e}")
        return {"status": "error", "error": f"parse_error: {e}", "source_id": sid}
    if parsed["validation"] != "ok":
        if not dry_run:
            snap = record_snapshot(sid, "ratings", raw, parsed["validation"][:200], keep_raw=False)
            update_source_health(sid, False, parsed["validation"][:300])
            ops_log("ratings_validation_failed", source_id=sid, snapshot=snap["id"], detail=parsed["validation"][:300])
        print(f"{sid}: {parsed['validation']} — nothing written")
        return {"status": "error", "error": parsed["validation"], "source_id": sid}
    if dry_run:
        recs, skipped = maker(parsed, office, sid, source["url"], "dry", "dry", _senate_ids())
        return {"status": "dry_run", "page_date": parsed["page_date"], "entries": len(parsed["entries"]), "records": len(recs), "link_only_skipped": skipped, "source_id": sid}
    snap = record_snapshot(sid, "ratings", raw, "ok", keep_raw=False, note=f"page_date {parsed['page_date']} entries {len(parsed['entries'])}")
    recs, skipped = maker(parsed, office, sid, source["url"], snap["id"], snap["fetched_at"], _senate_ids())
    written, n_changes = _write(sid, recs, parsed, snap["fetched_at"])
    update_source_health(sid, True)
    ops_log("ratings_pull", source_id=sid, snapshot=snap["id"], page_date=parsed["page_date"], entries=len(parsed["entries"]), stored=written,
            link_only_skipped=skipped, changes=n_changes)
    print(f"{sid}: page {parsed['page_date']}, {len(parsed['entries'])} entries, {written} rows written ({skipped} link-only), {n_changes} changes")
    return {"status": "recorded", "written": written, "changes": n_changes, "snapshot_id": snap["id"], "source_id": sid}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-id", required=True)
    ap.add_argument("--file", help="parse a local file instead of fetching (the hash of these bytes is recorded)")
    ap.add_argument("--words-json", help="Cook only: a {w,h,words:[[text,x0,x1,top],...]} dump of the print page's word positions made off-runner; "
                                         "used for the House page, whose raw copy the repo never keeps (decision 5)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    srcs = {s["id"]: s for s in load_json(os.path.join(DATA, "sources.json"), {"sources": []})["sources"]}
    raw = open(a.file, "rb").read() if a.file else None
    if a.words_json:
        raw = open(a.words_json, "rb").read()
        _dump = json.loads(raw)["words"]
        _words = lambda b, _d=_dump: [{"t": t, "x0": x0, "x1": x1, "top": top} for t, x0, x1, top in _d]  # noqa: E731
    print(json.dumps(run(srcs[a.source_id], dry_run=a.dry_run, raw=raw), sort_keys=True))
