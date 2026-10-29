#!/usr/bin/env python3
"""Anomaly detection over consecutive results snapshots (Macomb precinct × mode rows, or any unit-level rows).

Flags are neutral: "data changed — confirm with the Clerk". They open review items; they never change a number.

Rules (from the desk spec):
  1. decrease         — a unit's total for a candidate/contest decreases between snapshots
  2. votes_gt_ballots — votes cast exceed ballots cast for a unit (when ballots are reported)
  3. complete_changed — a unit marked complete in an earlier snapshot changes later
  4. stalled          — a unit has not changed for > 90 minutes while other units in the same contest moved
  5. overvote_spike   — over/undervote rate more than 3× the 2024 rate for that unit (needs a baseline rate)
"""
from __future__ import annotations

from datetime import datetime, timezone

STALL_MINUTES = 90
OU_SPIKE_FACTOR = 3.0


def _t(iso):
    return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _flag(kind, unit, contest, detail, snapshot_id, at):
    return {"type": kind, "unit": unit, "contest": contest, "detail": detail + " Data changed — confirm with the Clerk.",
            "snapshot_id": snapshot_id, "at": at, "status": "open"}


def detect(prev_rows, cur_rows, cur_snapshot_id, now_iso, baseline_ou_rate=None, last_change_at=None):
    """prev_rows / cur_rows: lists of {contest, unit, candidate|None, mode, votes, ballots|None, over_under|None, complete|bool}.
    A row with candidate None and mode "TOTAL" is the unit's contest total; ballots is Total Ballots Cast when known.
    baseline_ou_rate: {(contest, unit): rate} of (over+under votes) / ballots in 2024.
    last_change_at: {(contest, unit): iso} maintained by the caller across snapshots (returned updated).
    Returns (flags, last_change_at)."""
    flags = []

    def key(r):
        return (r["contest"], r["unit"], r.get("candidate"), r.get("mode", "TOTAL"))

    prev = {key(r): r for r in prev_rows or []}
    cur = {key(r): r for r in cur_rows}
    last_change_at = dict(last_change_at or {})
    changed_units = set()
    for k, r in cur.items():
        p = prev.get(k)
        label = k[2] or "total"
        if p is not None and r.get("votes") is not None and p.get("votes") is not None:
            if r["votes"] < p["votes"]:
                flags.append(_flag("decrease", r["unit"], r["contest"], f"{label} [{k[3]}] went from {p['votes']:,} to {r['votes']:,}.", cur_snapshot_id, now_iso))
            if r["votes"] != p["votes"]:
                changed_units.add((r["contest"], r["unit"]))
            if p.get("complete") and (r["votes"] != p["votes"] or not r.get("complete")):
                flags.append(_flag("complete_changed", r["unit"], r["contest"], f"Unit was marked complete; {label} [{k[3]}] changed {p['votes']:,} → {r['votes']:,}.", cur_snapshot_id, now_iso))
        elif p is None and r.get("votes"):
            changed_units.add((r["contest"], r["unit"]))
        if r.get("candidate") is None and r.get("ballots") is not None and r.get("votes") is not None and r["votes"] > r["ballots"]:
            flags.append(_flag("votes_gt_ballots", r["unit"], r["contest"], f"Votes cast {r['votes']:,} exceed ballots cast {r['ballots']:,} [{k[3]}].", cur_snapshot_id, now_iso))
        if r.get("candidate") is None and k[3] == "TOTAL" and baseline_ou_rate and r.get("ballots") and r.get("over_under") is not None:
            base = baseline_ou_rate.get((r["contest"], r["unit"]))
            rate = r["over_under"] / r["ballots"]
            if base is not None and base > 0 and rate > OU_SPIKE_FACTOR * base:
                flags.append(_flag("overvote_spike", r["unit"], r["contest"], f"Over/undervote rate {rate:.1%} vs 2024 {base:.1%} (>{OU_SPIKE_FACTOR:g}×).", cur_snapshot_id, now_iso))
    for cu in changed_units:
        last_change_at[cu] = now_iso
    for c in {r["contest"] for r in cur_rows}:
        units = {r["unit"] for r in cur_rows if r["contest"] == c}
        moved = {u for (cc, u) in changed_units if cc == c}
        if not moved:
            continue
        for u in units - moved:
            if any(r.get("complete") for r in cur_rows if r["contest"] == c and r["unit"] == u):
                continue
            last = last_change_at.get((c, u))
            if last is None:
                last_change_at[(c, u)] = now_iso
                continue
            if (_t(now_iso) - _t(last)).total_seconds() / 60 > STALL_MINUTES:
                flags.append(_flag("stalled", u, c, f"No change for over {STALL_MINUTES} minutes while {len(moved)} other units in this contest moved.", cur_snapshot_id, now_iso))
    return flags, last_change_at
