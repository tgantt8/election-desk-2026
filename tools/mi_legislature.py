#!/usr/bin/env python3
"""Michigan state legislative seats on the desk (data/contests/mi_legislature_2026.json).

Reads the results and calls layers; writes nothing. Used by manual_entry.py (contest ids, counties, party fill), by
build_results_site.py (seat cards summed county by county, the chamber tally) and by build_site_data.py.

Rules:
  * A seat with scope "statewide" is its own contest (mi-hd-NNN / mi-sd-NN), entered one county portion at a time. The
    Macomb portion comes from the Clerk summary-PDF contest named in portion_contest_id (or a newer hand entry).
  * A county portion counts as entered only when it carries at least one candidate vote count. A missing county is never
    summed as zero: the card says "N of M counties entered" and, with nothing entered, "no results entered".
  * Status and the chamber tally come ONLY from the calls layer. A call entered on any id in a seat's call_ids is a call on
    the seat; the latest entry wins and a "retracted" entry clears it. Nothing here projects chamber control.
"""
from __future__ import annotations

import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA, load_json  # noqa: E402

REGISTRY = os.path.join(DATA, "contests", "mi_legislature_2026.json")
MACOMB = os.path.join(DATA, "contests", "macomb_2026.json")
PDF_SOURCE = "macomb_clerk_unofficial_summary_pdf"
CLARITY_SOURCE = "macomb_clarity_enr"  # browser capture of the Clerk's Clarity ENR (tools/ingest_clarity_bundle.py); county rows only
SOURCE_LABEL = {PDF_SOURCE: "Macomb Clerk summary PDF", CLARITY_SOURCE: "Macomb Clerk Clarity ENR (browser capture)", "manual_results": "manual entry",
                "enr_wayne_totalvote": "Wayne County Clerk ENR (TotalVote)", "enr_oakland_clarity": "Oakland County Clerk Clarity ENR (browser capture)"}
COUNTY_FEEDS = ("enr_wayne_totalvote", "enr_oakland_clarity")  # polled county feeds whose records carry `county` + a statewide seat contest_id
SEAT_RE = re.compile(r"^mi-(hd|sd)-0*(\d{1,3})$")
MACOMB_LEG_RE = re.compile(r"^macomb-(hd|sd)0*(\d{1,3})$")
TOTAL_UNIT_RE = re.compile(r"^(?:(?:[a-z. ]+ )?county )?totals?$|^total votes(?: cast)?$|^district totals?$", re.I)
CHAMBER_OF = {"hd": "house", "sd": "senate"}
SEATS = {"house": 110, "senate": 38}


def normalize_contest_id(cid):
    """mi-hd-29 -> mi-hd-029, mi-sd-9 -> mi-sd-09, macomb-hd58 stays; anything else is returned stripped."""
    c = (cid or "").strip()
    m = SEAT_RE.match(c.lower())
    if m:
        return f"mi-hd-{int(m.group(2)):03d}" if m.group(1) == "hd" else f"mi-sd-{int(m.group(2)):02d}"
    m = MACOMB_LEG_RE.match(c.lower())
    if m:
        return f"macomb-{m.group(1)}{int(m.group(2)):02d}"
    return c


def seat_id_for(chamber, district):
    return f"mi-hd-{district:03d}" if chamber == "house" else f"mi-sd-{district:02d}"


def valid_seat_id(cid):
    m = SEAT_RE.match(cid or "")
    if not m:
        return False
    n = int(m.group(2))
    return 1 <= n <= SEATS[CHAMBER_OF[m.group(1)]] and normalize_contest_id(cid) == cid


def load_registry(path=None):
    return load_json(path or REGISTRY, {"seats": [], "chambers": {}, "counties": {}})


def seat_index(reg):
    """Every id that names a seat (seat_id, contest_id, macomb_contest_id, call_ids) -> the seat."""
    idx = {}
    for s in reg.get("seats", []):
        for k in [s["seat_id"], s["contest_id"], s.get("macomb_contest_id")] + list(s.get("call_ids", [])):
            if k:
                idx[k] = s
    return idx


def contests_index(reg=None, macomb_path=None):
    """All contest definitions manual entry can target: the Macomb ballot plus the statewide legislative seats."""
    out = {c["id"]: c for c in load_json(macomb_path or MACOMB, {"contests": []})["contests"]}
    reg = reg if reg is not None else load_registry()
    for s in reg.get("seats", []):
        if s["scope"] != "statewide":
            continue
        out[s["contest_id"]] = {"id": s["contest_id"], "office": s["office"], "scale": "michigan_legislature", "county_scope": "statewide_by_county",
                                "counties": [p["county"] for p in s["counties"]], "candidates": s.get("candidates", []), "seat_id": s["seat_id"]}
    return out


def seat_call(calls, ids):
    """Latest call among the given contest ids (calls in append order); None if none or the latest is a retraction."""
    ids = set(ids)
    last = None
    for c in calls:
        if normalize_contest_id(c.get("contest")) in ids:
            last = c
    if not last or (last.get("status") or "").lower() == "retracted":
        return None
    return last


def status_text(call):
    if not call:
        return "Too early"
    st = call.get("status") or "Projected"
    return f"{st} ({call.get('outlet', '?')}, {(call.get('called_at') or '')[:16].replace('T', ' ')} UTC)" if st == "Projected" else st


def _party_letter(p):
    p = (p or "").strip().upper()
    return {"DEM": "D", "REP": "R"}.get(p, p[:1]) if p else ""


def _snap_time(snapshot_id, source_id):
    """fetched_at from a snapshot id '<source>:<ISO>:<hash12>'."""
    sid = snapshot_id or ""
    if sid.startswith(source_id + ":") and len(sid) > len(source_id) + 14:
        return sid[len(source_id) + 1:-13]
    return ""


_SUFFIX = {"jr", "sr", "ii", "iii", "iv"}


def _surname(name):
    toks = [t.lower().strip(".,") for t in (name or "").replace(",", " ").split()]
    toks = [t for t in toks if t and t not in _SUFFIX]
    return toks[-1] if toks else ""


def _toks(name):
    return {t for t in (x.lower().strip(".,()") for x in (name or "").replace(",", " ").replace("/", " ").split()) if t and t not in _SUFFIX}


def match_candidate(seat_cands, name):
    """The one seat candidate a source's name refers to, or None. A full-name match (every name part of the candidate except
    initials appears: 'Deanna Martin', 'MARTIN, DEANNA L') wins; otherwise a surname that only one candidate carries
    ('Turner'). Two candidates sharing a surname (HD-68: David W. Martin, Deanna L Martin) need the first name."""
    toks = _toks(name)
    if not toks:
        return None
    full = [k for k in seat_cands if {t for t in _toks(k["name"]) if len(t) > 1} <= toks]
    if len(full) == 1:
        return full[0]
    sur = [k for k in seat_cands if _surname(k["name"]) in toks]
    return sur[0] if len(sur) == 1 else None


def _canon(seat_cands, name):
    """Map a source's candidate name onto the seat's candidate list (match_candidate); anything else passes through unchanged."""
    k = match_candidate(seat_cands, name)
    return (k["name"], k.get("party")) if k else (name, None)


def _portion_from(recs, seat_cands, use_total_units=True):
    """Candidate votes for one county portion from one snapshot's records (TOTAL mode only, write-ins left out).
    A unit labelled like a total ('Total', 'County Total') is used alone when present; otherwise units are summed."""
    rows = [r for r in recs if r.get("candidate") is not None and r.get("votes") is not None and (r.get("mode") or "TOTAL") == "TOTAL" and not r.get("write_in")]
    if use_total_units:
        tot = [r for r in rows if TOTAL_UNIT_RE.match(str(r.get("unit") or "").strip())]
        if tot:
            rows = tot
    votes, party = defaultdict(int), {}
    for r in rows:
        nm, p = _canon(seat_cands, r["candidate"])
        votes[nm] += r["votes"]
        party[nm] = p or _party_letter(r.get("party")) or party.get(nm, "")
    return dict(votes), party


def _latest_group(recs, key):
    """Records of the latest snapshot that contains each group key(r) (append order)."""
    order, groups = {}, defaultdict(lambda: defaultdict(list))
    for i, r in enumerate(recs):
        k = key(r)
        if k is None:
            continue
        sid = r.get("snapshot_id")
        groups[k][sid].append(r)
        order[(k, sid)] = i
    out = {}
    for k, by_snap in groups.items():
        sid = max(by_snap, key=lambda s: order[(k, s)])
        out[k] = (sid, by_snap[sid])
    return out


def seat_cards(reg, results_by_source, calls, macomb_contests=None):
    """results_by_source: {source_id: [records in append order]}. Returns one card per tracked seat."""
    if macomb_contests is None:
        macomb_contests = {c["id"]: c for c in load_json(MACOMB, {"contests": []})["contests"]}
    manual = results_by_source.get("manual_results", [])
    pdf = results_by_source.get(PDF_SOURCE, [])
    pdf_latest = None
    if pdf:
        pdf_latest = pdf[-1].get("snapshot_id")
    pdf_cur = [r for r in pdf if r.get("snapshot_id") == pdf_latest] if pdf_latest else []
    clar = results_by_source.get(CLARITY_SOURCE, [])
    clar_latest = clar[-1].get("snapshot_id") if clar else None
    clar_cur = [r for r in clar if r.get("snapshot_id") == clar_latest and r.get("unit") == "county"] if clar_latest else []
    man_by_cc = _latest_group(manual, lambda r: (normalize_contest_id(r.get("contest_id") or r.get("contest")), r.get("county")) if r.get("county") else None)
    feed_by_cc = {}  # (seat contest_id, county) -> (source_id, snapshot_id, records) from polled county feeds, latest snapshot per pair
    for fsid in COUNTY_FEEDS:
        for key, (sid, rs) in _latest_group(results_by_source.get(fsid, []), lambda r: (normalize_contest_id(r.get("contest_id")), r.get("county")) if r.get("county") and r.get("unit") == "county" else None).items():
            feed_by_cc[key] = (fsid, sid, rs)
    man_by_c = _latest_group(manual, lambda r: normalize_contest_id(r.get("contest_id") or r.get("contest")) if not r.get("county") else None)
    cdir = reg.get("counties", {})
    cards = []
    for s in reg.get("seats", []):
        cands = s.get("candidates") or (macomb_contests.get(s.get("macomb_contest_id") or "", {}).get("candidates") or [])
        portions = []
        for p in s["counties"]:
            county = p["county"]
            tracked = s["scope"] == "statewide" or county == "Macomb"
            options = []  # (time, source, as_of, records, total_units)
            if s["scope"] == "statewide" and (s["contest_id"], county) in man_by_cc:
                sid, rs = man_by_cc[(s["contest_id"], county)]
                options.append((_snap_time(sid, "manual_results"), "manual_results", max((r.get("as_of") or "" for r in rs), default=""), rs))
            if s["scope"] == "statewide" and (s["contest_id"], county) in feed_by_cc:
                fsid, sid, rs = feed_by_cc[(s["contest_id"], county)]
                options.append((_snap_time(sid, fsid), fsid, max((r.get("as_of") or "" for r in rs), default=""), rs))
            if county == "Macomb" and p.get("portion_contest_id"):
                pc = p["portion_contest_id"]
                rs = [r for r in pdf_cur if r.get("contest_id") == pc]
                if rs:
                    options.append((_snap_time(pdf_latest, PDF_SOURCE), PDF_SOURCE, max((r.get("as_of") or "" for r in rs), default=""), rs))
                rs = [r for r in clar_cur if r.get("contest_id") == pc]
                if rs:
                    options.append((_snap_time(clar_latest, CLARITY_SOURCE), CLARITY_SOURCE, max((r.get("as_of") or "" for r in rs), default=""), rs))
                if pc in man_by_c:
                    sid, rs = man_by_c[pc]
                    options.append((_snap_time(sid, "manual_results"), "manual_results", max((r.get("as_of") or "" for r in rs), default=""), rs))
            best = None
            for t, src, as_of, rs in sorted(options, key=lambda o: o[0], reverse=True):
                votes, party = _portion_from(rs, cands)
                if votes:
                    best = {"source": src, "as_of": as_of, "votes": votes, "party": party}
                    break
            ci = cdir.get(county, {})
            portions.append({"county": county, "tracked": tracked, "entered": best is not None, "area_share_pct": p.get("area_share_pct"),
                             "via": None if not best else SOURCE_LABEL.get(best["source"], best["source"]),
                             "source": best["source"] if best else None, "as_of": best["as_of"] if best else None,
                             "candidates": [{"name": n, "party": best["party"].get(n, ""), "votes": v} for n, v in sorted(best["votes"].items(), key=lambda x: -x[1])] if best else None,
                             "results_url": ci.get("results_url") if s["scope"] == "statewide" else None,
                             "results_url_status": ci.get("status") if s["scope"] == "statewide" else None,
                             "sos_listed_url": ci.get("sos_listed_url") if s["scope"] == "statewide" else None,
                             "portion_contest_id": p.get("portion_contest_id")})
        tracked_p = [x for x in portions if x["tracked"]]
        entered = [x for x in tracked_p if x["entered"]]
        totals, party = defaultdict(int), {}
        for x in entered:
            for c in x["candidates"]:
                totals[c["name"]] += c["votes"]
                party[c["name"]] = c["party"] or party.get(c["name"], "")
        for k in cands:  # seat candidates with no votes in any entered county stay listed, never as 0 for a missing county
            party.setdefault(k["name"], k.get("party") or "")
        cand_out = [{"name": n, "party": party.get(n, ""), "votes": totals[n]} for n in sorted(totals, key=lambda n: -totals[n])] if entered else None
        tot = sum(totals.values())
        d = next((c for c in cand_out or [] if (c["party"] or "").upper().startswith("D")), None)
        r_ = next((c for c in cand_out or [] if (c["party"] or "").upper().startswith("R")), None)
        margin = round(100 * (d["votes"] - r_["votes"]) / tot, 2) if d and r_ and tot else None
        call = seat_call(calls, s.get("call_ids") or [s["seat_id"]])
        n, m = len(entered), len(tracked_p)
        if s["scope"] == "macomb_portion_only":
            label = ("Macomb portion entered" if n else "no results entered") + f" · Macomb portion only (seat spans {len(portions)} counties; the others are not on the desk)"
        elif not n:
            label = "no results entered"
        else:
            label = f"{n} of {m} counties entered" + ("" if n == m else " — partial sum of entered counties only")
        chamber_short = "House" if s["chamber"] == "house" else "Senate"
        cards.append({"id": s["contest_id"], "seat_id": s["seat_id"], "chamber": s["chamber"], "district": s["district"], "scope": s["scope"], "sets": s.get("sets", []),
                      "title": f"MI {chamber_short} {s['district']} · {s['office']}", "counties_total": m, "counties_entered": n, "entered_label": label,
                      "complete_counties": bool(m) and n == m, "candidates": cand_out, "margin": margin if n else None,
                      "status": status_text(call), "called_for_party": _party_letter(call.get("called_for_party")) if call else None,
                      "as_of": max((x["as_of"] or "" for x in entered), default="") or None, "counties": portions,
                      "sources": sorted({x["via"] for x in entered}), "county_pages": s.get("county_pages")})
    return cards


def chamber_tally(reg, calls):
    """Seats called (calls layer only), tracked seats still counting, seats not tracked — per chamber. No projection."""
    seats_by = {(s["chamber"], s["district"]): s for s in reg.get("seats", [])}
    out = {}
    for ch, total in SEATS.items():
        meta = (reg.get("chambers") or {}).get(ch, {})
        called = {"d": 0, "r": 0, "other": 0}
        called_seats, counting, counting_comp, not_tracked = [], 0, 0, 0
        comp_total = sum(1 for s in reg.get("seats", []) if s["chamber"] == ch and "competitive" in s.get("sets", []))
        tracked_total = sum(1 for s in reg.get("seats", []) if s["chamber"] == ch)
        for n in range(1, total + 1):
            s = seats_by.get((ch, n))
            ids = (s.get("call_ids") if s else None) or [seat_id_for(ch, n)]
            c = seat_call(calls, ids)
            if c:
                p = _party_letter(c.get("called_for_party"))
                called["d" if p == "D" else "r" if p == "R" else "other"] += 1
                called_seats.append({"seat_id": seat_id_for(ch, n), "party": p or None, "outlet": c.get("outlet"), "called_at": c.get("called_at"), "tracked": bool(s)})
            elif s:
                counting += 1
                counting_comp += "competitive" in s.get("sets", [])
            else:
                not_tracked += 1
        out[ch] = {"name": meta.get("name"), "seats": total, "majority": meta.get("majority"), "called": called, "called_seats": called_seats,
                   "counting_tracked": counting, "counting_competitive": counting_comp, "competitive_total": comp_total, "tracked_total": tracked_total,
                   "not_tracked": not_tracked,
                   "note": "Called = an attributed outlet call in the calls layer. Counting = a tracked seat with no call. No projection of chamber control."}
    return out
