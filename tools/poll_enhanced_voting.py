#!/usr/bin/env python3
"""Enhanced Voting election-night JSON poller -> RESULTS layer only.

Used by Georgia, Washington, Utah, Idaho, Virginia and 13 Michigan counties. Base: https://<host>/results/public/api

  GET /jurisdictions/<slug>                    -> list of elections (publicElectionId, electionDate)
  GET /elections/<slug>/<id>                   -> ~3-6 KB election object (asOf, lastUpdated, nextUpdateAt, isOfficialResults,
                                                  publishVersionId, isPrimary, countGroups): the cheap change detector
  GET /elections/<slug>/<id>/ballot-items      -> {"data": [ballot items], "limit", "offset", "totalRecordCount"}

Layer discipline (non-negotiable):
  * Writes ONLY data/results/<source_id>.jsonl (+ the snapshot index/raw store via tools/common.record_snapshot, the ops log
    and source health). It never touches polls, ratings, early_vote, calls or scenarios.
  * Records are official counts from an election office and are UNOFFICIAL until certified (`is_official` is the publisher's
    own flag, copied verbatim; `unofficial` is its negation).
  * No automatic race calls. The vendor's per-candidate `isWinner` is kept as `vendor_is_winner` (a vendor display flag, raw
    value) and is never turned into a status/call field and never read by this module for any decision.
  * Append-only: records are only ever appended; every heavy pull is recorded as a snapshot with the sha256 of the raw bytes.
  * Per-host minimum interval between polls (default 120 s), enforced in-process (RateLimiter) and across processes (state file).

Change detection: the election object's (lastUpdated, asOf, isOfficialResults, publishVersionId) tuple is stored in the state file
after a successful pull. If the next election object has the same tuple the heavy ballot-items call is skipped: no snapshot row,
no records. If the tuple changed but the ballot-items bytes hash identically to the last snapshot for this source, a snapshot row is
still appended (proof of the pull, parse_status "ok_unchanged") but result records are NOT duplicated.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import sys
from datetime import datetime, timezone

sys.dont_write_bytecode = True  # never write __pycache__ next to a read-only reference clone


def _find_tools_dir():
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.environ.get("ELECTION_DESK_TOOLS"),
        here,
        os.path.join(os.path.dirname(here), "tools"),
    ]
    for c in candidates:
        if c and os.path.exists(os.path.join(c, "common.py")):
            return c
    raise ImportError("tools/common.py not found; set ELECTION_DESK_TOOLS")


sys.path.insert(0, _find_tools_dir())
import common  # noqa: E402
from common import RateLimiter, USER_AGENT, append_jsonl, last_snapshot_hash, load_json, ops_log, record_snapshot, update_source_health  # noqa: E402

DEFAULT_MIN_INTERVAL_S = 120.0
INTRA_CYCLE_GAP_S = 1.0  # election-object call and ballot-items call of one poll cycle are one "poll"; keep them 1 s apart
HEADERS = {"User-Agent": USER_AGENT, "Accept": "application/json"}

_LIMITER = RateLimiter()


class FetchError(RuntimeError):
    pass


# --------------------------------------------------------------------------- fetch

def api_base(host: str) -> str:
    return f"https://{host}/results/public/api"


def _get(url, session, limiter, host, min_interval_s, timeout=60):
    (limiter or _LIMITER).wait(host, min_interval_s)
    try:
        r = session.get(url, headers=HEADERS, timeout=timeout)
    except Exception as e:  # noqa: BLE001
        raise FetchError(f"GET {url}: {type(e).__name__}: {e}") from e
    status = getattr(r, "status_code", 200)
    if status != 200:
        raise FetchError(f"GET {url}: HTTP {status}")
    raw = r.content
    try:
        obj = json.loads(raw.decode("utf-8-sig"))
    except Exception as e:  # noqa: BLE001
        raise FetchError(f"GET {url}: not JSON ({e})") from e
    return raw, obj


def fetch_election(host, slug, election_id, session, limiter=None, min_interval_s=DEFAULT_MIN_INTERVAL_S):
    """Election object (cheap change detector). Returns (raw_bytes, parsed_dict)."""
    url = f"{api_base(host)}/elections/{slug}/{election_id}"
    return _get(url, session, limiter, host, min_interval_s)


def fetch_ballot_items(host, slug, election_id, session, limiter=None, min_interval_s=DEFAULT_MIN_INTERVAL_S):
    """Full ballot-items payload. Returns (raw_bytes, parsed_dict)."""
    url = f"{api_base(host)}/elections/{slug}/{election_id}/ballot-items"
    return _get(url, session, limiter, host, min_interval_s, timeout=90)


def fetch_jurisdiction(host, slug, session, limiter=None, min_interval_s=DEFAULT_MIN_INTERVAL_S):
    """Elections list for a jurisdiction (used to discover publicElectionId). Returns (raw_bytes, parsed_dict)."""
    return _get(f"{api_base(host)}/jurisdictions/{slug}", session, limiter, host, min_interval_s)


def discover_election_id(host, slug, election_date, session, limiter=None, min_interval_s=DEFAULT_MIN_INTERVAL_S):
    """Look up the publicElectionId of the election held on `election_date` (YYYY-MM-DD) in /jurisdictions/<slug>.

    Returns (election_id or None, [candidate dicts]). Recounts are skipped. Used before Nov 3 for states (GA, ID) whose
    Nov 3 election object is not published yet: the orchestrator calls this on every pass until an id appears, then
    persists it in data/sources.json. Nothing is guessed: no id -> no polling."""
    _raw, j = fetch_jurisdiction(host, slug, session, limiter, min_interval_s)
    elections = (j or {}).get("elections") or []
    cands = []
    for e in elections:
        if not isinstance(e, dict) or e.get("electionDate") != election_date:
            continue
        name = _text(e.get("name"))
        cands.append({"publicElectionId": e.get("publicElectionId"), "name": name, "electionDate": e.get("electionDate")})
    live = [c for c in cands if c["publicElectionId"] and not re.search(r"recount", c["name"] or "", re.I)]
    return (live[0]["publicElectionId"] if len(live) == 1 else None), cands


# --------------------------------------------------------------------------- parse helpers

def _text(loc, default=""):
    """Enhanced Voting localized text: [{"languageId": "en", "text": "..."}]."""
    if isinstance(loc, str):
        return loc
    if not loc:
        return default
    for t in loc:
        if isinstance(t, dict) and t.get("languageId") == "en" and t.get("text") is not None:
            return t["text"]
    first = loc[0]
    return first.get("text", default) if isinstance(first, dict) else default


_PARTY_BY_ABBR = {"R": "R", "REP": "R", "GOP": "R", "D": "D", "DEM": "D", "I": "I", "IND": "I", "L": "L", "LIB": "L",
                  "G": "G", "GRN": "G", "GRE": "G", "GREEN": "G"}
_PARTY_BY_NAME = [
    (re.compile(r"^\(?\s*(?:prefers\s+)?(?:the\s+)?republican(?:\s+party)?\s*\)?$", re.I), "R"),
    (re.compile(r"^\(?\s*(?:prefers\s+)?(?:the\s+)?democrat(?:ic)?(?:\s+party)?\s*\)?$", re.I), "D"),
    (re.compile(r"^\(?\s*(?:prefers\s+)?(?:the\s+)?independent(?:\s+party)?\s*\)?$", re.I), "I"),
    (re.compile(r"^\(?\s*(?:prefers\s+)?(?:the\s+)?libertarian(?:\s+party)?\s*\)?$", re.I), "L"),
    (re.compile(r"^\(?\s*(?:prefers\s+)?(?:the\s+)?green(?:\s+party)?\s*\)?$", re.I), "G"),
]


def normalize_party(party):
    """-> (normalized, raw). normalized in D/R/I/L/G/other, or None when the option carries no party (measures, nonpartisan, write-ins).
    raw keeps the publisher's abbreviation and display name verbatim. Unknown labels (e.g. WA 'Prefers Labor Democrat Party',
    'States No Party Preference') are 'other' rather than guessed."""
    if not party:
        return None, None
    abbr = (party.get("abbreviation") or "").strip()
    name = _text(party.get("name")).strip()
    if not abbr and not name:
        return None, None
    raw = {"abbreviation": abbr or None, "name": name or None}
    norm = _PARTY_BY_ABBR.get(abbr.upper())
    if norm is None:
        for rx, code in _PARTY_BY_NAME:
            if name and rx.match(name):
                norm = code
                break
    return (norm or "other"), raw


_RX_SENATE = re.compile(r"^\s*(?:Member,?\s+)?(?:U\.?\s?S\.?|United\s+States)\s+Senat(?:e|or)\b", re.I)
_RX_GOV = re.compile(r"^\s*Governor\b", re.I)
_RX_HOUSE = re.compile(r"(?<![A-Za-z])(?:U\.?\s?S\.?\s+House(?:\s+of\s+Representatives)?|Congressional\s+District|"
                       r"U\.?\s?S\.?\s+Representative|Representative\s+in\s+Congress)\b", re.I)
_RX_HOUSE_VA = re.compile(r"^\s*Member,?\s+House\s+of\s+Representatives\s*\(", re.I)  # VA only: its state lower house is the House of Delegates
_RX_DISTRICT = re.compile(r"District\s+(\d+)|(\d+)(?:st|nd|rd|th)\s+District", re.I)
_RX_ATLARGE = re.compile(r"at[\s-]*large", re.I)
_RX_SPECIAL = re.compile(r"\bspecial\b|\bunexpired\b", re.I)


def map_contest_id(name: str, state: str, ballot_item_id: str) -> str:
    """Statewide U.S. Senate -> us-senate-<ST>[-special]; Governor -> gov-<ST>; U.S. House -> us-house-<ST>-<NN|AL>;
    everything else -> ev:<state>:<ballotItemId>. (A primary/runoff suffix is added by the caller.)"""
    st = state.upper()
    if _RX_SENATE.search(name):
        return f"us-senate-{st}-special" if _RX_SPECIAL.search(name) else f"us-senate-{st}"
    if _RX_GOV.search(name):
        return f"gov-{st}"
    if _RX_HOUSE.search(name) or (st == "VA" and _RX_HOUSE_VA.search(name)):
        m = _RX_DISTRICT.search(name)
        if m:
            return f"us-house-{st}-{int(m.group(1) or m.group(2)):02d}"
        if _RX_ATLARGE.search(name):
            return f"us-house-{st}-AL"
    return f"ev:{st}:{ballot_item_id}"


def _stage(election):
    """None for a general election; 'primary', 'primary-runoff' or 'runoff' otherwise (keeps primaries out of general-election ids)."""
    if not election:
        return None
    name = _text(election.get("name")).lower()
    runoff = "runoff" in name
    if election.get("isPrimary"):
        return "primary-runoff" if runoff else "primary"
    return "runoff" if runoff else None


def _item_party_code(item, options):
    pn = (item.get("partyName") or "").strip()
    if pn:
        return pn.lower()
    codes = {normalize_party(o.get("party"))[0] for o in options if not o.get("isWriteIn")}
    codes.discard(None)
    if len(codes) == 1:
        return codes.pop().lower()
    m = re.search(r"-\s*(Rep|Dem|Lib|Gre|Grn|Ind|Non)\w*\s*$", _text(item.get("name")), re.I)
    return m.group(1).lower() if m else None


def _reporting(item):
    rs = item.get("reportingStatus")
    if not rs:
        return None
    r, t = rs.get("reportingUnits"), rs.get("totalUnits")
    pct = round(100.0 * r / t, 2) if isinstance(r, (int, float)) and isinstance(t, (int, float)) and t else None
    return {"units_reporting": r, "units_total": t, "pct": pct}


def _votes_by_mode(opt):
    gr = opt.get("groupResults")
    if not gr:
        return None
    return {_text(g.get("groupName")): g.get("voteCount") for g in gr}


# --------------------------------------------------------------------------- parse

def parse_ballot_items(payload, state, source_id, fetched_at, snapshot_id=None, election=None, source_url=None):
    """Ballot-items payload (dict, or raw bytes/str) -> list of results-layer records, one per ballot option per ballot item.

    `election` (the election object) supplies asOf, isOfficialResults and primary/runoff stage. Without it, as_of falls back to
    the item's own reportingStatus.asOf and is_official is False (conservative: UNOFFICIAL until certified).
    `unit` is always "state": counts are the contest totals as published by the state-level feed, not a county/precinct split.
    Records contain no status/call/projection field; `vendor_is_winner` is the vendor's raw isWinner display flag, informational only.
    """
    if isinstance(payload, (bytes, bytearray)):
        payload = json.loads(bytes(payload).decode("utf-8-sig"))
    elif isinstance(payload, str):
        payload = json.loads(payload)
    items = payload.get("data")
    if not isinstance(items, list):
        raise ValueError("ballot-items payload has no 'data' list")
    el = election or {}
    stage = _stage(election)
    is_official = bool(el.get("isOfficialResults")) if election else False
    out = []
    for it in items:
        bid = it.get("id")
        name = _text(it.get("name"))
        options = ((it.get("summaryResults") or {}).get("ballotOptions")) or []
        cid = map_contest_id(name, state, bid)
        if stage and not cid.startswith("ev:"):
            pc = _item_party_code(it, options)
            cid = f"{cid}-{stage}" + (f"-{pc}" if pc else "")
        as_of = el.get("asOf") or ((it.get("reportingStatus") or {}).get("asOf"))
        rep = _reporting(it)
        ctype = "ballot_measure" if it.get("contestType") == "BallotMeasure" else "candidate"
        for opt in options:
            party, party_raw = normalize_party(opt.get("party"))
            vc = opt.get("voteCount")
            rec = {
                "layer": "results",
                "contest_id": cid,
                "contest_name": name,
                "contest_type": ctype,
                "ballot_item_id": bid,
                "unit": "state",
                "candidate": _text(opt.get("name")),
                "candidate_id": opt.get("nativeId"),
                "is_write_in": bool(opt.get("isWriteIn")),
                "party": party,
                "party_raw": party_raw,
                "votes": int(vc) if isinstance(vc, (int, float)) else None,
                "votes_by_mode": _votes_by_mode(opt),
                "contest_vote_total": it.get("voteTotal"),
                "reporting": rep,
                "as_of": as_of,
                "is_official": is_official,
                "unofficial": not is_official,
                "election_id": it.get("publishPublicElectionId"),
                "election_date": el.get("electionDate"),
                "is_primary": bool(el.get("isPrimary")),
                "source_id": source_id,
                "source_url": source_url,
                "snapshot_id": snapshot_id,
                "fetched_at": fetched_at,
                # Vendor display flag, raw (True/False/None). NOT a call; never feeds status, ordering or the calls layer.
                "vendor_is_winner": opt.get("isWinner"),
            }
            out.append(rec)
    return out


# --------------------------------------------------------------------------- run

def _signature(el):
    return {k: el.get(k) for k in ("lastUpdated", "asOf", "isOfficialResults", "publishVersionId")}


@contextlib.contextmanager
def _use_root(root):
    """Point tools/common at another root (tests run in a temp dir; common.record_snapshot/ops_log/update_source_health honour it)."""
    if not root:
        yield
        return
    old = (common.ROOT, common.DATA)
    common.ROOT, common.DATA = root, os.path.join(root, "data")
    try:
        yield
    finally:
        common.ROOT, common.DATA = old


def _now():
    return datetime.now(timezone.utc)


def _parse_iso(s):
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except Exception:  # noqa: BLE001
        return None


def run(source, dry_run=False, session=None, root=None, state_file=None, out_dir=None, limiter=None, now=None):
    """One poll cycle. source = {host, slug, election_id, state, source_id, [min_interval_s]}.

    Returns a summary dict whose `status` is one of: rate_limited, skipped_unchanged, dry_run, recorded, error.
    root: directory holding data/ (default: the repo that tools/common.py lives in). state_file/out_dir default under root/data/results.
    """
    host, slug, eid, st, sid = (source[k] for k in ("host", "slug", "election_id", "state", "source_id"))
    min_iv = float(source.get("min_interval_s", DEFAULT_MIN_INTERVAL_S))
    now = now or _now
    if session is None:
        import requests
        session = requests.Session()
    with _use_root(root):
        data_dir = common.DATA
        out_dir = out_dir or os.path.join(data_dir, "results")
        state_file = state_file or os.path.join(out_dir, f".state_{sid}.json")
        state = load_json(state_file, {}) or {}

        # cross-process per-host spacing (the in-process RateLimiter does not survive between cron invocations)
        last = _parse_iso(state.get("last_request_at", ""))
        if min_iv > 0 and last and (now() - last).total_seconds() < min_iv:
            return {"status": "rate_limited", "retry_in_s": round(min_iv - (now() - last).total_seconds(), 1), "source_id": sid}

        def save_state(**upd):
            if dry_run:
                return
            state.update(upd)
            os.makedirs(os.path.dirname(state_file) or ".", exist_ok=True)
            tmp = state_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(state, fh, indent=1, sort_keys=True)
            os.replace(tmp, state_file)

        try:
            raw_e, el = fetch_election(host, slug, eid, session, limiter, min_iv)
            sig = _signature(el)
            if state.get("signature") == sig:
                save_state(last_request_at=now().strftime("%Y-%m-%dT%H:%M:%SZ"), next_update_at=el.get("nextUpdateAt"))
                if not dry_run:
                    update_source_health(sid, True)
                return {"status": "skipped_unchanged", "signature": sig, "source_id": sid}
            raw_b, payload = fetch_ballot_items(host, slug, eid, session, limiter, INTRA_CYCLE_GAP_S)
        except FetchError as e:
            if not dry_run:
                update_source_health(sid, False, str(e))
                ops_log("enhanced_voting_fetch_failed", source_id=sid, error=str(e)[:300])
            return {"status": "error", "error": str(e), "source_id": sid}

        url = f"{api_base(host)}/elections/{slug}/{eid}/ballot-items"
        total = payload.get("totalRecordCount")
        n_items = len(payload.get("data") or [])
        partial = isinstance(total, int) and total > n_items
        try:
            recs = parse_ballot_items(payload, st, sid, None, election=el, source_url=url)
            parse_status = "ok_partial" if partial else "ok"
            err = None
        except Exception as e:  # noqa: BLE001
            recs, parse_status, err = [], f"parse_error: {type(e).__name__}: {e}"[:200], e

        if dry_run:
            return {"status": "dry_run", "records": len(recs), "ballot_items": n_items, "parse_status": parse_status,
                    "signature": sig, "raw_bytes": len(raw_b), "source_id": sid}

        prev_hash = last_snapshot_hash(sid)
        snap = record_snapshot(sid, "results", raw_b, parse_status, keep_raw=True,
                               note=f"election {eid} asOf {el.get('asOf')} lastUpdated {el.get('lastUpdated')}")
        if err is not None:
            update_source_health(sid, False, parse_status)
            ops_log("enhanced_voting_parse_failed", source_id=sid, snapshot=snap["id"], error=parse_status)
            return {"status": "error", "error": parse_status, "snapshot_id": snap["id"], "source_id": sid}

        unchanged_bytes = prev_hash == snap["raw_hash"]
        written = 0
        if unchanged_bytes:
            # same bytes as the previous snapshot: the snapshot row above is the proof of the pull; do not duplicate records
            note_status = "ok_unchanged"
        else:
            note_status = parse_status
            path = os.path.join(out_dir, f"{sid}.jsonl")
            for r in recs:
                r["snapshot_id"], r["fetched_at"] = snap["id"], snap["fetched_at"]
                append_jsonl(path, r)
                written += 1
        save_state(signature=sig, last_request_at=now().strftime("%Y-%m-%dT%H:%M:%SZ"), next_update_at=el.get("nextUpdateAt"),
                   last_snapshot_id=snap["id"], last_raw_hash=snap["raw_hash"])
        update_source_health(sid, True)
        ops_log("enhanced_voting_pull", source_id=sid, election=eid, snapshot=snap["id"], records=written,
                parse_status=note_status, ballot_items=n_items, total_record_count=total, is_official=el.get("isOfficialResults"))
        return {"status": "recorded", "records": written, "ballot_items": n_items, "parse_status": note_status,
                "snapshot_id": snap["id"], "raw_hash": snap["raw_hash"], "source_id": sid}


# --------------------------------------------------------------------------- CLI

def main(argv=None):
    ap = argparse.ArgumentParser(description="Enhanced Voting poller (results layer).")
    ap.add_argument("--host", required=True, help="e.g. results.votewa.gov")
    ap.add_argument("--slug", required=True, help="jurisdiction slug, e.g. washington")
    ap.add_argument("--election", required=True, help="publicElectionId, e.g. 20261103")
    ap.add_argument("--state", required=True, help="two-letter state, e.g. WA")
    ap.add_argument("--source-id", required=True)
    ap.add_argument("--state-file")
    ap.add_argument("--out-dir")
    ap.add_argument("--root", help="directory containing data/ (default: the repo of tools/common.py)")
    ap.add_argument("--min-interval", type=float, default=DEFAULT_MIN_INTERVAL_S, help="per-host minimum seconds between polls (default 120)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    src = {"host": a.host, "slug": a.slug, "election_id": a.election, "state": a.state, "source_id": a.source_id,
           "min_interval_s": a.min_interval}
    res = run(src, dry_run=a.dry_run, root=a.root, state_file=a.state_file, out_dir=a.out_dir)
    print(json.dumps(res, sort_keys=True))
    return 1 if res["status"] == "error" else 0


if __name__ == "__main__":
    sys.exit(main())
