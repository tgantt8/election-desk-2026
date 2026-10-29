#!/usr/bin/env python3
"""Macomb County parsers.

1. parse_summary_pdf(path): the Clerk's "Summary Results Report" (Hart/Civera layout) — contest × candidate × mode
   (TOTAL / AVCB / Election Day / Early Voting) with a strict tie-out:
     - every row: TOTAL == AVCB + Election Day + Early Voting
     - every contest, every column: sum(candidates + write-ins) == Total Votes Cast
     - every contest, every column: Total Votes Cast + Overvotes + Undervotes == Contest Totals × VoteFor
   Any mismatch raises TieOutError. Parsed totals must equal the printed totals exactly, or the parser fails.

2. parse_precinct_csv(path): the Past Elections database per-contest CSV with vote_channels=all
   (precinct × candidate × mode: Election Day / Absentee / Early) with a tie-out against the district total row.

Mode name normalization: AVCB == Absentee (absent voter counting boards); ED == Election Day; EV == Early Voting.
"""
from __future__ import annotations

import csv
import re
from collections import OrderedDict

MODES = ("TOTAL", "AVCB", "ED", "EV")
NUM = r"-?[\d,]+"
ROW_RE = re.compile(rf"^(?P<label>.+?)\s+(?P<a>{NUM})\s+(?P<b>{NUM})\s+(?P<c>{NUM})\s+(?P<d>{NUM})$")
PARTY_RE = re.compile(r"^(?P<party>DEM|REP|LIB|UST|GRN|NLP|WCP|NPA|WC)\s+(?P<name>.+)$")
TOTAL_LABELS = {"Total Votes Cast": "total_votes_cast", "Overvotes": "overvotes", "Undervotes": "undervotes", "Contest Totals": "contest_totals"}
SKIP = {"Summary Results Report", "Macomb County", "TOTAL AVCB Election Early", "Day Voting"}


class TieOutError(Exception):
    pass


def _n(s):
    return int(s.replace(",", ""))


def _row(m):
    return {"TOTAL": _n(m["a"]), "AVCB": _n(m["b"]), "ED": _n(m["c"]), "EV": _n(m["d"])}


def _check_total(label, r, where):
    if r["TOTAL"] != r["AVCB"] + r["ED"] + r["EV"]:
        raise TieOutError(f"{where}: '{label}' TOTAL {r['TOTAL']} != AVCB+ED+EV {r['AVCB'] + r['ED'] + r['EV']}")


def parse_summary_pdf(path):
    import pdfplumber

    contests = OrderedDict()
    statistics = {}
    header = {}
    cur = None
    pending_title = []
    with pdfplumber.open(path) as pdf:
        n_pages = len(pdf.pages)
        for pi, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            for ln in lines:
                if ln in SKIP or ln.startswith("Election Summary - ") or re.match(r"^(November|August|May) \d{4}$", ln):
                    if re.match(r"^(November|August|May) \d{4}$", ln):
                        header["election"] = ln
                    if ln.startswith("Election Summary - "):
                        header["generated"] = ln.split(" - ", 1)[1].rsplit(" Page", 1)[0]
                    continue
                if ln.startswith("Statistics"):
                    cur = {"title": "Statistics", "kind": "statistics", "rows": OrderedDict()}
                    statistics = cur
                    continue
                m = re.match(r"^Vote For (\d+)$", ln)
                if m:
                    title = " ".join(pending_title).strip()
                    pending_title = []
                    cur = {"title": title, "vote_for": int(m.group(1)), "candidates": [], "totals": {}, "page": pi + 1}
                    contests[title] = cur
                    continue
                rm = ROW_RE.match(ln)
                if rm and cur is not None:
                    label = rm["label"].strip()
                    r = _row(rm)
                    if cur.get("kind") == "statistics":
                        cur["rows"][label] = r
                        continue
                    if label in TOTAL_LABELS:
                        _check_total(label, r, cur["title"])
                        cur["totals"][TOTAL_LABELS[label]] = r
                        continue
                    _check_total(label, r, cur["title"])
                    pm = PARTY_RE.match(label)
                    cand = {"name": pm["name"] if pm else label, "party": pm["party"] if pm else None, "votes": r,
                            "write_in": label == "Write-In Totals"}
                    cur["candidates"].append(cand)
                    continue
                # Statistics block has "x of y" rows and percentage rows; keep them as text.
                if cur is not None and cur.get("kind") == "statistics":
                    sm = re.match(rf"^(.+?)\s+(\d+ of \d+|{NUM}|[\d.]+%)((\s+{NUM})*)$", ln)
                    if sm:
                        cur["rows"][sm.group(1).strip()] = ln[len(sm.group(1)):].strip()
                    continue
                # Otherwise it is (part of) a contest title.
                pending_title.append(ln)
    # Tie-out per contest.
    for title, c in contests.items():
        need = {"total_votes_cast", "overvotes", "undervotes", "contest_totals"}
        missing = need - set(c["totals"])
        if missing:
            raise TieOutError(f"{title}: missing total rows {sorted(missing)}")
        for mode in MODES:
            s = sum(cd["votes"][mode] for cd in c["candidates"])
            tvc = c["totals"]["total_votes_cast"][mode]
            if s != tvc:
                raise TieOutError(f"{title} [{mode}]: candidates+write-ins {s} != Total Votes Cast {tvc}")
            lhs = tvc + c["totals"]["overvotes"][mode] + c["totals"]["undervotes"][mode]
            rhs = c["totals"]["contest_totals"][mode]  # Contest Totals is in vote positions (ballots × VoteFor) already
            if lhs != rhs:
                raise TieOutError(f"{title} [{mode}]: votes+over+under {lhs} != Contest Totals {rhs}")
    return {"source_file": path, "header": header, "pages": n_pages, "statistics": statistics.get("rows", {}) if statistics else {},
            "contests": list(contests.values()), "tie_out": "PASS"}


def parse_precinct_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.reader(fh))
    cand_row, party_row, mode_row = rows[0], rows[1], rows[2]
    cols = []
    for i in range(2, len(cand_row)):
        cols.append((cand_row[i].strip(), party_row[i].strip() or None, {"Election Day": "ED", "Absentee": "AVCB", "Early": "EV"}[mode_row[i].strip()]))
    names = []
    for c, p, m in cols:
        if c not in names:
            names.append(c)
    specials = {"Write-In", "Total Votes Cast", "Overvotes/Undervotes", "Total Ballots Cast"}
    candidates = [n for n in names if n not in specials]

    def unpack(row):
        # "*" = suppressed by the Clerk (small-precinct privacy); kept as None and excluded from exact tie-out.
        out = {n: {"ED": 0, "AVCB": 0, "EV": 0} for n in names}
        for (c, p, m), v in zip(cols, row[2:]):
            v = v.strip()
            out[c][m] = None if v == "*" else (_n(v) if v else 0)
        for n in names:
            parts = [out[n][m] for m in ("ED", "AVCB", "EV")]
            out[n]["TOTAL"] = None if any(x is None for x in parts) else sum(parts)
        return out

    district = None
    precincts = []
    for row in rows[3:]:
        if not row or not any(x.strip() for x in row):
            continue
        rec = {"unit_type": row[0].strip(), "unit": row[1].strip(), "values": unpack(row)}
        if rec["unit_type"] != "Precinct" and district is None:
            district = rec
        else:
            precincts.append(rec)
    if district is None:
        raise TieOutError(f"{path}: no district total row")
    # Tie-out: precinct sums == district row for every column (exact when no cell is suppressed; otherwise the
    # known sum must not exceed the district total and the residual is recorded); per unit: candidates + write-in
    # == Total Votes Cast wherever every cell is known.
    suppressed = {}
    for n in names:
        for m in MODES:
            vals = [p["values"][n][m] for p in precincts]
            known = sum(v for v in vals if v is not None)
            n_sup = sum(1 for v in vals if v is None)
            dist = district["values"][n][m]
            if n_sup == 0:
                if known != dist:
                    raise TieOutError(f"{path}: {n} [{m}] precinct sum {known} != district total {dist}")
            else:
                if known > dist:
                    raise TieOutError(f"{path}: {n} [{m}] known precinct sum {known} exceeds district total {dist} with {n_sup} suppressed cells")
                suppressed[f"{n}|{m}"] = {"suppressed_precincts": n_sup, "residual_votes": dist - known}
    for rec in [district] + precincts:
        for m in MODES:
            cells = [rec["values"][c][m] for c in candidates] + [rec["values"].get("Write-In", {}).get(m, 0)]
            tvc = rec["values"]["Total Votes Cast"][m]
            if any(x is None for x in cells) or tvc is None:
                continue
            if sum(cells) != tvc:
                raise TieOutError(f"{path}: {rec['unit']} [{m}] candidates {sum(cells)} != Total Votes Cast {tvc}")
    party = {c: next((p for (cc, p, m) in cols if cc == c and p), None) for c in candidates}
    return {"source_file": path, "district": district, "precincts": precincts, "candidates": [{"name": c, "party": party[c]} for c in candidates],
            "n_precincts": len(precincts), "suppressed_cells": suppressed, "tie_out": "PASS"}


def mode_shares(contest_or_district, dem_name=None):
    """Democratic share of the two-party vote by mode. Works on a summary-PDF contest or a CSV district record."""
    if "candidates" in contest_or_district and "totals" in contest_or_district:
        dem = next((c for c in contest_or_district["candidates"] if c["party"] == "DEM"), None)
        rep = next((c for c in contest_or_district["candidates"] if c["party"] == "REP"), None)
        if not dem or not rep:
            return None
        return {m: round(100 * dem["votes"][m] / (dem["votes"][m] + rep["votes"][m]), 2) for m in MODES if dem["votes"][m] + rep["votes"][m]}
    v = contest_or_district["values"]
    names = [n for n in v if n not in ("Write-In", "Total Votes Cast", "Overvotes/Undervotes", "Total Ballots Cast")]
    return None if len(names) < 2 else {"names": names}
