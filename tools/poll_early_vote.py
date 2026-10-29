#!/usr/bin/env python3
"""Early-vote pollers -> EARLY_VOTE layer only. "Who voted, not how they voted": ballots requested, returned, cast, and party
registration where a state publishes it. Never vote choice, never modeled party, never voter-level files.

Sources (structures read 2026-10-29):
  * North Carolina (NCSBE): aggregate CSV s3://dl.ncsbe.gov/ENRS/2026_11_03/absentee_counts_state_20261103.csv — one row per
    request type × party × gender × race × ethnicity with the accepted-ballot count in the last column (its header cell is
    literally "0"); request types CIVILIAN / MILITARY / OVERSEAS are mail, ONE-STOP and EARLY VOTING are in-person early
    voting. The daily PDF "<date> Daily Absentee Stats Report - 2026 General.pdf" (Press/2026 General/NC Absentee Stats for
    2026 General/) restates the same totals and carries the official "Comparison to 2022 General Election" block and the
    "Ballots cast through <date>" line — that block is the only vs-2022 baseline we show for NC.
  * Florida (Division of Elections, PublicStats): three tab-separated files electionfiles.floridados.gov/countyballotreportfiles/
    Stats_49894_{VbmProvided,VbmVoted,EarlyVoted}.txt (election 49894 = 2026 General): State Totals + 67 counties by party
    registration (Republican / Democrat / Other / No Party Affiliation) with a CompileDate per row.
  * UF Election Lab (Michael McDonald) US.csv — CC BY-NC-ND 4.0: shown as-is, attributed and linked, never blended into our
    own series (Tabu, decision 2). Rows carry the lab's own last_update, data_source and notes.
  * Michigan: the SOS Voting Dashboard is a Power BI embed with no export, and michigan.gov answered 403 to the sandbox; the
    desk takes manual captures through tools/manual_entry.py --layer early_vote (Ops panel → Early-vote capture).

Layer discipline: writes only data/early_vote/<source_id>.jsonl (append-only rows per snapshot), the snapshot index, the ops
log and source health. vs_2022 / vs_2024 are filled only from an official same-source comparison; otherwise null ("no baseline").
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA, USER_AGENT, append_jsonl, last_snapshot_hash, load_json, ops_log, record_snapshot, sha256_bytes, update_source_health  # noqa: E402

NC_CSV = "https://s3.amazonaws.com/dl.ncsbe.gov/ENRS/2026_11_03/absentee_counts_state_20261103.csv"
NC_PDF = "https://s3.amazonaws.com/dl.ncsbe.gov/Press/2026%20General/NC%20Absentee%20Stats%20for%202026%20General/{d}%20Daily%20Absentee%20Stats%20Report%20-%202026%20General.pdf"
NC_PAGE = "https://www.ncsbe.gov/results-data/absentee-data"
NC_MAIL = {"CIVILIAN", "MILITARY", "OVERSEAS"}
NC_INPERSON = {"ONE-STOP", "EARLY VOTING"}
NC_PARTY = {"DEM": "Democratic", "REP": "Republican", "UNA": "Unaffiliated", "LIB": "Libertarian", "GRE": "Green", "CST": "Constitution",
            "JFA": "Justice for All", "NLB": "No Labels", "WTP": "We The People"}
FL_FILES = {"VbmProvided": "Vote-by-Mail provided (not yet returned)", "VbmVoted": "Voted vote-by-mail", "EarlyVoted": "Voted early (in person)"}
FL_URL = "https://electionfiles.floridados.gov/countyballotreportfiles/Stats_49894_{k}.txt"
FL_PAGE = "https://countyfilesvbm-ev.floridados.gov/VoteByMailEarlyVotingReports/PublicStats"
FL_PARTY = {"TotalRep": "Republican", "TotalDem": "Democrat", "TotalOth": "Other", "TotalNpa": "No Party Affiliation", "GrandTotal": None}
UF_URL = "https://election.lab.ufl.edu/data-downloads/earlyvote/2026/US.csv"
UF_PAGE = "https://election.lab.ufl.edu/early-vote/2026-early-voting/"
UF_LICENSE = "CC BY-NC-ND 4.0 — shown unmodified with attribution; not blended into the desk's own series"
UF_METRICS = [("request_all", "Mail ballots requested", None), ("accept_all", "Mail ballots returned / accepted", None),
              ("inperson_all", "In-person early votes", None), ("voted_all", "Total early votes (mail returned + in person)", None),
              ("request_dem", "Mail ballots requested", "Democratic"), ("request_rep", "Mail ballots requested", "Republican"),
              ("accept_dem", "Mail ballots returned / accepted", "Democratic"), ("accept_rep", "Mail ballots returned / accepted", "Republican"),
              ("inperson_dem", "In-person early votes", "Democratic"), ("inperson_rep", "In-person early votes", "Republican"),
              ("voted_dem", "Total early votes (mail returned + in person)", "Democratic"), ("voted_rep", "Total early votes (mail returned + in person)", "Republican"),
              ("turn_2022", "2022 general election turnout (UF figure, for context)", None)]


def fetch(url, session=None, timeout=90):
    import requests
    s = session or requests.Session()
    r = s.get(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"}, timeout=timeout)
    if r.status_code != 200:
        raise RuntimeError(f"GET {url}: HTTP {r.status_code}")
    return r.content, dict(r.headers)


def _rec(source_id, snapshot_id, fetched_at, geography, metric, value, *, geo_level="state", state=None, party=None, mode=None, as_of=None,
         as_of_raw=None, source=None, url=None, vs_2022=None, vs_2022_source=None, display_only=False, license_=None, attribution=None, note=None):
    return {"layer": "early_vote", "geography": geography, "geo_level": geo_level, "state": state, "metric": metric, "party": party, "mode": mode,
            "value": value, "as_of": as_of, "as_of_raw": as_of_raw, "vs_2022": vs_2022, "vs_2022_source": vs_2022_source, "vs_2024": None,
            "source": source, "url": url, "display_only": display_only, "license": license_, "attribution": attribution, "note": note,
            "source_id": source_id, "snapshot_id": snapshot_id, "fetched_at": fetched_at}


# --------------------------------------------------------------------------- North Carolina

def parse_nc_counts(csv_bytes):
    """-> {"total", "mail", "in_person", "by_type": {type: n}, "by_party": {party_code: n}, "by_party_mode": {(party, mode): n}, "rows"}"""
    rows = list(csv.reader(io.StringIO(csv_bytes.decode("utf-8-sig"))))
    hdr = rows[0]
    if hdr[:5] != ["abs_request_type", "party_cd", "gender", "race", "ethnicity"] or len(hdr) != 6:
        raise ValueError(f"unexpected NC header {hdr}")
    by_type, by_party, by_pm = {}, {}, {}
    n = 0
    for r in rows[1:]:
        if len(r) != 6:
            raise ValueError(f"bad NC row {r}")
        t, p, cnt = r[0], r[1], int(r[5])
        if t not in NC_MAIL | NC_INPERSON:
            raise ValueError(f"unknown NC request type {t!r}")
        mode = "mail" if t in NC_MAIL else "in_person"
        by_type[t] = by_type.get(t, 0) + cnt
        by_party[p] = by_party.get(p, 0) + cnt
        by_pm[(p, mode)] = by_pm.get((p, mode), 0) + cnt
        n += 1
    total = sum(by_type.values())
    return {"total": total, "mail": sum(v for k, v in by_type.items() if k in NC_MAIL), "in_person": sum(v for k, v in by_type.items() if k in NC_INPERSON),
            "by_type": by_type, "by_party": by_party, "by_party_mode": by_pm, "rows": n}


_RX_NUM = r"([\d,]+)"


def parse_nc_daily_pdf(pdf_bytes):
    """The first page restates the totals and carries the official comparison to 2022 and the as-of line."""
    from pypdf import PdfReader
    text = PdfReader(io.BytesIO(pdf_bytes)).pages[0].extract_text() or ""
    g = lambda rx: (lambda m: int(m.group(1).replace(",", "")) if m else None)(re.search(rx, text))  # noqa: E731
    out = {"total": g(r"Total Ballots Cast " + _RX_NUM), "in_person": g(r"In-Person Early Voting " + _RX_NUM),
           "civilian": g(r"Civilian \(Mail\) " + _RX_NUM), "military": g(r"Military \(Mail\) " + _RX_NUM), "overseas": g(r"Overseas\s+\(Mail\) " + _RX_NUM),
           "cmp_2022_early": g(r"Early Voting " + _RX_NUM + r"\s*\n?\s*Civilian, Military"), "cmp_2022_mail": g(r"Civilian, Military, & Overseas " + _RX_NUM),
           "cmp_2022_total": g(r"\(Total number of accepted ballots cast\) " + _RX_NUM), "registered": g(r"Total Eligible Voters\*? " + _RX_NUM)}
    m = re.search(r"Published (\d{1,2}/\d{1,2}/\d{4}); Ballots cast through (\d{1,2}/\d{1,2}/\d{4})", text)
    out["published"] = m.group(1) if m else None
    out["through"] = m.group(2) if m else None
    m = re.search(r"Turnout (\d+\.\d+)%", text)
    out["turnout_pct"] = float(m.group(1)) if m else None
    if not re.search(r"Comparison to 2022 General Election", text):
        out["cmp_2022_early"] = out["cmp_2022_mail"] = out["cmp_2022_total"] = None
    return out


def _mdY(s):
    try:
        return datetime.strptime(s, "%m/%d/%Y").strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001
        return None


def nc_records(counts, pdf_info, source_id, snapshot_id, fetched_at, csv_url=NC_CSV, pdf_url=None):
    src = "N.C. State Board of Elections, absentee_counts_state_20261103.csv"
    as_of = _mdY(pdf_info.get("through")) if pdf_info else None
    note = (f"Daily report published {pdf_info['published']}; ballots cast through {pdf_info['through']}." if pdf_info and pdf_info.get("published") else None)
    cmp_src = f"NCSBE daily report, 'Comparison to 2022 General Election' block ({pdf_url})" if pdf_info and pdf_info.get("cmp_2022_total") else None
    R = lambda metric, value, **kw: _rec(source_id, snapshot_id, fetched_at, "North Carolina", metric, value, state="NC", as_of=as_of, source=src,  # noqa: E731
                                          url=csv_url, note=note, attribution="N.C. State Board of Elections", **kw)
    out = [R("Ballots cast (mail + in-person early), accepted", counts["total"], mode="total", vs_2022=pdf_info.get("cmp_2022_total") if pdf_info else None, vs_2022_source=cmp_src),
           R("In-person early voting ballots", counts["in_person"], mode="in_person", vs_2022=pdf_info.get("cmp_2022_early") if pdf_info else None, vs_2022_source=cmp_src),
           R("Mail ballots accepted (civilian + military + overseas)", counts["mail"], mode="mail", vs_2022=pdf_info.get("cmp_2022_mail") if pdf_info else None, vs_2022_source=cmp_src)]
    for code, n in sorted(counts["by_party"].items(), key=lambda kv: -kv[1]):
        out.append(R("Ballots cast by party registration (turnout indicator)", n, party=NC_PARTY.get(code, code), mode="total"))
    for (code, mode), n in sorted(counts["by_party_mode"].items()):
        if code in ("DEM", "REP", "UNA"):
            out.append(R("Ballots cast by party registration (turnout indicator)", n, party=NC_PARTY.get(code, code), mode=mode))
    if pdf_info and pdf_info.get("registered"):
        out.append(R("Registered voters (denominator in the daily report)", pdf_info["registered"], mode=None))
    return out


def run_nc(source, dry_run=False, session=None, csv_raw=None, pdf_raw=None, today=None):
    sid = source["id"]
    try:
        if csv_raw is None:
            csv_raw, _ = fetch(source.get("fetch_url") or NC_CSV, session)
    except Exception as e:  # noqa: BLE001
        if not dry_run:
            update_source_health(sid, False, str(e)[:300])
            ops_log("early_vote_fetch_failed", source_id=sid, error=str(e)[:300])
        return {"status": "error", "error": str(e), "source_id": sid}
    pdf_url, pdf_info = None, None
    if pdf_raw is None and not dry_run or (pdf_raw is None and dry_run and session is not None):
        d = today or date.today()
        for back in range(0, 3):  # today's report lands ~9 AM ET; fall back to yesterday's
            u = NC_PDF.format(d=(d - timedelta(days=back)).isoformat())
            try:
                pdf_raw, _ = fetch(u, session)
                pdf_url = u
                break
            except Exception:  # noqa: BLE001
                continue
    if pdf_raw is not None:
        try:
            pdf_info = parse_nc_daily_pdf(pdf_raw)
        except Exception as e:  # noqa: BLE001
            ops_log("early_vote_pdf_parse_failed", source_id=sid, error=str(e)[:300])
            pdf_info = None
    try:
        counts = parse_nc_counts(csv_raw)
    except Exception as e:  # noqa: BLE001
        if not dry_run:
            snap = record_snapshot(sid, "early_vote", csv_raw, f"parse_error: {e}"[:200], keep_raw=True)
            update_source_health(sid, False, f"parse_error: {e}"[:300])
            ops_log("early_vote_parse_failed", source_id=sid, snapshot=snap["id"], error=str(e)[:300])
        return {"status": "error", "error": f"parse_error: {e}", "source_id": sid}
    if pdf_info and pdf_info.get("total") not in (None, counts["total"]):
        ops_log("early_vote_tie_out_mismatch", source_id=sid, csv_total=counts["total"], pdf_total=pdf_info["total"], note="CSV and daily PDF disagree; CSV shown, PDF comparison withheld")
        pdf_info = {k: v for k, v in pdf_info.items() if k in ("published", "through")}
    if dry_run:
        return {"status": "dry_run", "total": counts["total"], "mail": counts["mail"], "in_person": counts["in_person"], "pdf": pdf_info, "source_id": sid}
    if sha256_bytes(csv_raw) == last_snapshot_hash(sid):
        update_source_health(sid, True)
        return {"status": "skipped_unchanged", "source_id": sid}
    snap = record_snapshot(sid, "early_vote", csv_raw, "ok", keep_raw=True, note=f"total {counts['total']}; through {pdf_info.get('through') if pdf_info else '?'}")
    if pdf_raw is not None and pdf_url:
        record_snapshot(sid + "_daily_pdf", "early_vote", pdf_raw, "ok" if pdf_info else "parse_error", keep_raw=True, note=pdf_url)
    recs = nc_records(counts, pdf_info, sid, snap["id"], snap["fetched_at"], source.get("fetch_url") or NC_CSV, pdf_url)
    for r in recs:
        append_jsonl(os.path.join(DATA, "early_vote", f"{sid}.jsonl"), r)
    update_source_health(sid, True)
    ops_log("early_vote_pull", source_id=sid, snapshot=snap["id"], records=len(recs), total=counts["total"])
    return {"status": "recorded", "records": len(recs), "snapshot_id": snap["id"], "source_id": sid}


# --------------------------------------------------------------------------- Florida

def parse_fl_txt(raw, kind):
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig")), delimiter="\t"))
    need = {"ElectionNumber", "CountyName", "StatType", "TotalRep", "TotalDem", "TotalOth", "TotalNpa", "GrandTotal", "CompileDate"}
    if not rows or not need <= set(rows[0].keys()):
        raise ValueError(f"unexpected FL columns {list(rows[0].keys()) if rows else None}")
    out = []
    for r in rows:
        vals = {k: int(r[k].replace(",", "")) for k in ("TotalRep", "TotalDem", "TotalOth", "TotalNpa", "GrandTotal")}
        if vals["TotalRep"] + vals["TotalDem"] + vals["TotalOth"] + vals["TotalNpa"] != vals["GrandTotal"]:
            raise ValueError(f"FL row does not tie out: {r}")
        out.append({"county": r["CountyName"].strip(), "stat_type": r["StatType"].strip(), "kind": kind, "election": r["ElectionNumber"], **vals,
                    "compiled_raw": re.sub(r"\s+", " ", r["CompileDate"].strip())})
    return out


def _fl_iso(s):
    try:
        return datetime.strptime(s, "%m/%d/%Y %I:%M%p").strftime("%Y-%m-%dT%H:%M:00-04:00")  # Division of Elections compiles in Eastern time
    except Exception:  # noqa: BLE001
        return None


def fl_records(parsed_by_kind, source_id, snapshot_id, fetched_at):
    out = []
    for kind, rows in parsed_by_kind.items():
        label = FL_FILES[kind]
        mode = "mail" if kind.startswith("Vbm") else "in_person"
        for r in rows:
            is_state = r["county"] == "State Totals"
            geo = "Florida" if is_state else f"{r['county']} County, FL"
            for col, party in FL_PARTY.items():
                out.append(_rec(source_id, snapshot_id, fetched_at, geo, label, r[col], geo_level="state" if is_state else "county", state="FL", party=party, mode=mode,
                                as_of=_fl_iso(r["compiled_raw"]), as_of_raw=r["compiled_raw"], source="Florida Division of Elections, County Vote-by-Mail and Early Voting Reports",
                                url=FL_URL.format(k=kind), attribution="Florida Division of Elections", note="party = voter registration (turnout indicator), per the Division's report"))
    return out


def run_fl(source, dry_run=False, session=None, raws=None):
    sid = source["id"]
    raws = dict(raws or {})
    try:
        for k in FL_FILES:
            if k not in raws:
                raws[k], _ = fetch(FL_URL.format(k=k), session)
    except Exception as e:  # noqa: BLE001
        if not dry_run:
            update_source_health(sid, False, str(e)[:300])
            ops_log("early_vote_fetch_failed", source_id=sid, error=str(e)[:300])
        return {"status": "error", "error": str(e), "source_id": sid}
    try:
        parsed = {k: parse_fl_txt(raws[k], k) for k in FL_FILES}
    except Exception as e:  # noqa: BLE001
        if not dry_run:
            update_source_health(sid, False, f"parse_error: {e}"[:300])
            ops_log("early_vote_parse_failed", source_id=sid, error=str(e)[:300])
        return {"status": "error", "error": f"parse_error: {e}", "source_id": sid}
    combined = b"".join(raws[k] for k in FL_FILES)
    if dry_run:
        st = {k: next((r for r in v if r["county"] == "State Totals"), None) for k, v in parsed.items()}
        return {"status": "dry_run", "state_totals": {k: (r["GrandTotal"], r["compiled_raw"]) if r else None for k, r in st.items()}, "counties": len(parsed["EarlyVoted"]) - 1, "source_id": sid}
    if sha256_bytes(combined) == last_snapshot_hash(sid):
        update_source_health(sid, True)
        return {"status": "skipped_unchanged", "source_id": sid}
    snap = record_snapshot(sid, "early_vote", combined, "ok", keep_raw=True, note="VbmProvided+VbmVoted+EarlyVoted concatenated")
    recs = fl_records(parsed, sid, snap["id"], snap["fetched_at"])
    for r in recs:
        append_jsonl(os.path.join(DATA, "early_vote", f"{sid}.jsonl"), r)
    update_source_health(sid, True)
    ops_log("early_vote_pull", source_id=sid, snapshot=snap["id"], records=len(recs))
    return {"status": "recorded", "records": len(recs), "snapshot_id": snap["id"], "source_id": sid}


# --------------------------------------------------------------------------- UF Election Lab (display only)

def parse_uf_csv(raw):
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    need = {"state", "state_abbv", "turn_2022", "last_update", "data_source", "notes", "request_all", "accept_all", "inperson_all", "voted_all"}
    if not rows or not need <= set(rows[0].keys()):
        raise ValueError("unexpected UF columns")
    return rows


def uf_records(rows, source_id, snapshot_id, fetched_at):
    out = []
    for r in rows:
        as_of = _mdY(r.get("last_update") or "")
        for col, metric, party in UF_METRICS:
            v = r.get(col)
            if v in (None, "", "NA"):
                continue
            try:
                v = int(float(v))
            except ValueError:
                continue
            if party and v == 0:
                continue  # the lab writes 0 where a state publishes no party breakdown
            out.append(_rec(source_id, snapshot_id, fetched_at, r["state"], metric, v, state=r["state_abbv"], party=party, as_of=as_of, as_of_raw=r.get("last_update"),
                            source="University of Florida Election Lab, 2026 Early Voting (US.csv)", url=UF_PAGE, display_only=True, license_=UF_LICENSE,
                            attribution="UF Election Lab (Michael McDonald); state source: " + (r.get("data_source") or ""), note=(r.get("notes") or "").strip() or None))
    return out


def run_uf(source, dry_run=False, session=None, raw=None):
    sid = source["id"]
    try:
        if raw is None:
            raw, _ = fetch(source.get("fetch_url") or UF_URL, session)
        rows = parse_uf_csv(raw)
    except Exception as e:  # noqa: BLE001
        if not dry_run:
            update_source_health(sid, False, str(e)[:300])
            ops_log("early_vote_fetch_failed", source_id=sid, error=str(e)[:300])
        return {"status": "error", "error": str(e), "source_id": sid}
    if dry_run:
        return {"status": "dry_run", "states": len(rows), "source_id": sid}
    if sha256_bytes(raw) == last_snapshot_hash(sid):
        update_source_health(sid, True)
        return {"status": "skipped_unchanged", "source_id": sid}
    snap = record_snapshot(sid, "early_vote", raw, "ok", keep_raw=True)
    recs = uf_records(rows, sid, snap["id"], snap["fetched_at"])
    for r in recs:
        append_jsonl(os.path.join(DATA, "early_vote", f"{sid}.jsonl"), r)
    update_source_health(sid, True)
    ops_log("early_vote_pull", source_id=sid, snapshot=snap["id"], records=len(recs), display_only=True)
    return {"status": "recorded", "records": len(recs), "snapshot_id": snap["id"], "source_id": sid}


RUNNERS = {"nc_s3": run_nc, "fl_publicstats": run_fl, "uf_csv": run_uf}


def run(source, dry_run=False, session=None):
    return RUNNERS[source["poller"]](source, dry_run=dry_run, session=session)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-id", required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    srcs = {s["id"]: s for s in load_json(os.path.join(DATA, "sources.json"), {"sources": []})["sources"]}
    print(json.dumps(run(srcs[a.source_id], dry_run=a.dry_run), sort_keys=True, default=str))
