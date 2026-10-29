#!/usr/bin/env python3
"""Scenarios layer: Monte Carlo simulator (10,000 runs) over the 35 Senate seats, 36 governorships and the Michigan House
districts that carry a public rating. Reads the polls layer (desk averages), the ratings layer (labels) and the early-vote
layer (context only — turnout indicators are "who voted, not how" and move no probability here). Writes ONLY
data/scenarios/latest.json and data/scenarios/history.jsonl. Nothing here is a call; the UI labels every output internal.

Model (one draw per simulation):
    margin_i = mu_i + shift + e_nat + e_region(i) + e_race_i            (D minus R, percentage points)
    e_nat ~ N(0, s_nat)  shared by every race;  e_region ~ N(0, s_reg) shared within a Census region;
    e_race ~ N(0, s_race_i), s_race_i^2 = s_base^2 + s_poll^2 / n_eff for polled races (n_eff = min(n_polls, 8)),
    s_race_i = s_rating for races with a rating and no desk average.
    mu_i = w * poll_margin + (1 - w) * rating_margin, w = n_polls / (n_polls + 2); rating_margin from the primary label
    (Solid 15, Likely 8, Lean 4, Tilt/Battleground 2, Toss-up 0, signed toward the favoured party).
    A race with neither a desk average nor a rating has no baseline and is left out (reported as such).
Error scales come from tools/simulate.py backtest (fixtures/fivethirtyeight, real 2018 and 2022 Senate and Governor polls and
results): the grid point with the best interval coverage and Brier score is written to data/scenarios/backtest.json and read
back here; the shipped defaults below are the fallback. Presets are national shifts: 0, ±3, and the mean signed poll error of
2018 and of 2022 measured in that backtest (so "repeat 2022" means the polls miss by what they missed in 2022).

House: a district enters only with a real baseline or a public rating; the desk holds no 2024-on-2026-lines presidential
baselines yet, so the House block reports "no baseline" for every district without a stored rating and no chamber total.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import random
import sys
from collections import Counter, defaultdict
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA, ROOT, append_jsonl, dump_json, load_json, read_jsonl, utcnow  # noqa: E402

N_SIMS = 10_000
SEED = 20261103
DEFAULT_PARAMS = {"s_nat": 2.5, "s_reg": 1.5, "s_base": 3.5, "s_poll": 6.0, "s_rating": 6.0}
RATING_MARGIN = {-3: 15.0, -2: 8.0, -1: 4.0, 0: 0.0, 1: -4.0, 2: -8.0, 3: -15.0}
LOSSY_MARGIN = 2.0  # Tilt / Battleground labels: a lean the rater calls weaker than Lean
REGION = {}
for _r, _sts in {"Northeast": "CT ME MA NH RI VT NJ NY PA", "Midwest": "IL IN MI OH WI IA KS MN MO NE ND SD",
                 "South": "DE FL GA MD NC SC VA WV AL KY MS TN AR LA OK TX DC", "West": "AZ CO ID MT NV NM UT WY AK CA HI OR WA"}.items():
    for _s in _sts.split():
        REGION[_s] = _r
SCALE = {"Solid D": -3, "Safe D": -3, "Likely D": -2, "Lean D": -1, "Tilt D": -1, "Battleground D": -1, "Toss-up": 0,
         "Battleground R": 1, "Tilt R": 1, "Lean R": 1, "Likely R": 2, "Solid R": 3, "Safe R": 3}
DISCLAIMER = "Scenarios layer: model estimates built from the polls and ratings layers. Not a call, not a result, never written to results or calls."


# --------------------------------------------------------------------------- inputs

def _latest_ratings():
    out = []
    import glob
    for path in sorted(glob.glob(os.path.join(DATA, "ratings", "*.jsonl"))):
        if os.path.basename(path) == "changes.jsonl":
            continue
        rows = read_jsonl(path)
        if rows:
            last = rows[-1]["snapshot_id"]
            out.extend(r for r in rows if r["snapshot_id"] == last)
    return out


def rating_margin(label):
    sc = SCALE.get(label)
    if sc is None:
        return None
    if label.startswith(("Tilt", "Battleground")):
        return LOSSY_MARGIN if sc < 0 else -LOSSY_MARGIN
    return RATING_MARGIN[sc]


def race_inputs(params):
    """Build the per-race inputs table from the polls and ratings layers. Returns (races, excluded)."""
    polls = load_json(os.path.join(DATA, "polls", "site.json"), {}) or {}
    averages = polls.get("averages") or {}
    ratings = _latest_ratings()
    by_race = defaultdict(list)
    for r in ratings:
        by_race[r["race"]].append(r)
    senate = load_json(os.path.join(DATA, "contests", "senate_2026.json"), {"races": []})["races"]
    govs = load_json(os.path.join(DATA, "contests", "governors_2026.json"), {"races": []})["races"]
    house = load_json(os.path.join(DATA, "contests", "house_delegations.json"), {"states": []})["states"]
    contests = [("senate", r["id"], r["state"], r.get("holder_party")) for r in senate] + [("governor", r["id"], r["state"], r.get("holder_party")) for r in govs]
    for rid in sorted(by_race):
        if rid.startswith("us-house-"):
            contests.append(("house", rid, rid.split("-")[2], None))
    races, excluded = [], []
    for office, rid, st, holder in contests:
        avg = averages.get(rid) or {}
        pm, n = avg.get("margin"), avg.get("n_polls") or 0
        rs = by_race.get(rid, [])
        primary = next((x for x in rs if x["rater"] == "Cook Political Report"), rs[0] if rs else None)
        rm = rating_margin(primary["label"]) if primary else None
        if pm is None and rm is None:
            excluded.append({"race": rid, "office": office, "reason": "no desk average and no rating — no baseline"})
            continue
        if pm is not None and rm is not None:
            w = n / (n + 2.0)
            mu = w * pm + (1 - w) * rm
            kind = "polls+rating"
        elif pm is not None:
            mu, kind = pm, "polls"
        else:
            mu, kind = rm, "rating"
        if pm is not None:
            s_race = math.sqrt(params["s_base"] ** 2 + params["s_poll"] ** 2 / min(max(n, 1), 8))
        else:
            s_race = params["s_rating"]
        races.append({"race": rid, "office": office, "state": st, "region": REGION.get(st, "South"), "holder_party": holder, "mu": round(mu, 2), "s_race": round(s_race, 2),
                      "basis": kind, "poll_margin": pm, "n_polls": n, "rating_label": primary["label"] if primary else None, "rating_rater": primary["rater"] if primary else None,
                      "rating_date": primary.get("date") if primary else None, "rating_margin": rm,
                      "ratings_all": [{"rater": x["rater"], "label": x["label"], "date": x.get("date")} for x in rs]})
    return races, excluded, house


# --------------------------------------------------------------------------- simulation

def simulate_margins(races, params, n_sims=N_SIMS, seed=SEED):
    """Common random numbers: one noise matrix reused by every preset (presets only shift the mean)."""
    rng = random.Random(seed)
    regions = sorted({r["region"] for r in races})
    noise = []
    for _ in range(n_sims):
        e_nat = rng.gauss(0, params["s_nat"])
        e_reg = {g: rng.gauss(0, params["s_reg"]) for g in regions}
        noise.append([e_nat + e_reg[r["region"]] + rng.gauss(0, r["s_race"]) for r in races])
    return noise


def _quantiles(xs, qs=(0.1, 0.5, 0.9)):
    s = sorted(xs)
    return [round(s[min(len(s) - 1, int(q * len(s)))], 1) for q in qs]


def evaluate(races, noise, shift, chambers):
    n_sims = len(noise)
    idx_sen = [i for i, r in enumerate(races) if r["office"] == "senate"]
    idx_gov = [i for i, r in enumerate(races) if r["office"] == "governor"]
    idx_hse = [i for i, r in enumerate(races) if r["office"] == "house"]
    hold = (chambers.get("senate") or {}).get("holdovers") or {"d": 0, "r": 0, "i": 0}
    d_wins = [0] * len(races)
    margins = [[] for _ in races]
    sen_seats, gov_wins = [], []
    tipping = Counter()
    for s in range(n_sims):
        row = noise[s]
        m = [races[i]["mu"] + shift + row[i] for i in range(len(races))]
        for i in range(len(races)):
            margins[i].append(m[i])
            if m[i] > 0:
                d_wins[i] += 1
        wins_sen = sum(1 for i in idx_sen if m[i] > 0)
        seats = hold["d"] + hold["i"] + wins_sen  # independents caucus with D (chambers.json)
        sen_seats.append(seats)
        gov_wins.append(sum(1 for i in idx_gov if m[i] > 0))
        # tipping-point seat: order this sim's Senate margins from most D to most R; the seat that carries the caucus to 51
        order = sorted(idx_sen, key=lambda i: -m[i])
        need = 51 - hold["d"] - hold["i"]
        if 0 < need <= len(order):
            tipping[races[order[need - 1]]["race"]] += 1
    dist = Counter(sen_seats)
    out = {
        "shift": shift,
        "races": [{"race": r["race"], "office": r["office"], "state": r["state"], "p_dem": round(d_wins[i] / n_sims, 3), "margin_mean": round(sum(margins[i]) / n_sims, 1),
                   "margin_p10_p50_p90": _quantiles(margins[i]), "basis": r["basis"], "mu": r["mu"], "s_race": r["s_race"]} for i, r in enumerate(races)],
        "senate": {"holdovers": hold, "seats_up": len(idx_sen), "p_dem_control_51": round(sum(1 for x in sen_seats if x >= 51) / n_sims, 3),
                   "p_dem_50_tie_vp_r": round(sum(1 for x in sen_seats if x == 50) / n_sims, 3), "expected_dem_caucus": round(sum(sen_seats) / n_sims, 2),
                   "dem_caucus_p10_p50_p90": _quantiles(sen_seats, (0.1, 0.5, 0.9)), "distribution": {str(k): round(v / n_sims, 4) for k, v in sorted(dist.items())},
                   "expected_dem_wins_of_seats_up": round(sum(1 for s in range(n_sims) for i in idx_sen if races[i]["mu"] + shift + noise[s][i] > 0) / n_sims, 2),
                   "tipping_point": [{"race": k, "share": round(v / n_sims, 3)} for k, v in tipping.most_common(5)]},
        "governors": {"races": len(idx_gov), "expected_dem_wins": round(sum(gov_wins) / n_sims, 2), "dem_wins_p10_p50_p90": _quantiles(gov_wins, (0.1, 0.5, 0.9))},
        "house": {"districts_simulated": len(idx_hse), "note": "Only districts with a stored public rating; no chamber total (no 2024-on-2026-lines baselines loaded)."},
    }
    return out


def what_has_to_be_true(races, noise, chambers, target=51, lo=-15.0, hi=15.0):
    """Smallest uniform national shift at which P(D caucus >= target) crosses 50%, by bisection on the same draws."""
    def p_at(shift):
        return evaluate(races, noise, shift, chambers)["senate"]["p_dem_control_51" if target == 51 else "p_dem_control_51"]
    p_lo, p_hi = p_at(lo), p_at(hi)
    if p_lo >= 0.5:
        return {"shift_needed": lo, "note": "already above 50% at the lower bound"}
    if p_hi < 0.5:
        return {"shift_needed": None, "note": f"below 50% even at D+{hi:g}"}
    for _ in range(14):
        mid = (lo + hi) / 2
        if p_at(mid) >= 0.5:
            hi = mid
        else:
            lo = mid
    return {"shift_needed": round(hi, 2), "p_at_shift": p_at(hi)}


# --------------------------------------------------------------------------- backtest (real 2018 and 2022 polls and results)

BT_CSV = os.path.join(ROOT, "fixtures", "fivethirtyeight", "raw-polls_2018-2022_senate-governor.csv")
GRID = {"s_nat": [2.5], "s_base": [1.5, 2.5, 3.5, 4.5], "s_poll": [4.0, 6.0, 8.0, 10.0]}  # s_nat pinned: per-race coverage cannot split shared from race error; 2.5 is the shared miss seen in recent cycles


def _phi(x):
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def backtest_races():
    """One row per 2018/2022 Senate or Governor race: desk-style average of the polls fielded in the final 60 days and the
    official D−R margin FiveThirtyEight attached. Races without a D-vs-R pairing (CA 2018 D-vs-D, ME/VT independents...) are skipped."""
    rows = list(csv.DictReader(open(BT_CSV, encoding="utf-8")))
    by = defaultdict(list)
    for r in rows:
        p1, p2 = r["cand1_party"], r["cand2_party"]
        if {p1, p2} != {"DEM", "REP"}:
            continue
        sign = 1 if p1 == "DEM" else -1
        try:
            pd_ = datetime.strptime(r["polldate"], "%m/%d/%Y").date()
            ed = datetime.strptime(r["electiondate"], "%m/%d/%Y").date()
            mp = sign * float(r["margin_poll"])
            ma = sign * float(r["margin_actual"])
            n = float(r["samplesize"] or 0) or 400
        except ValueError:
            continue
        days = (ed - pd_).days
        if days < 0 or days > 60:
            continue
        w = math.exp(-math.log(2) * days / 14) * math.sqrt(n) * (0.5 if r["partisan"] else 1.0)
        by[r["race"]].append((w, mp, ma, r["year"], r["type_simple"], r["location"]))
    out = []
    for race, ps in sorted(by.items()):
        den = sum(w for w, *_ in ps)
        avg = sum(w * mp for w, mp, *_ in ps) / den
        out.append({"race": race, "year": ps[0][3], "office": "senate" if ps[0][4] == "Sen-G" else "governor", "state": ps[0][5], "n_polls": len(ps), "poll_avg": round(avg, 2), "actual": ps[0][2]})
    return out


def score(bt, params):
    errs, brier, in80, in95, ll = [], [], 0, 0, 0.0
    for r in bt:
        n_eff = min(max(r["n_polls"], 1), 8)
        s_tot = math.sqrt(params["s_nat"] ** 2 + params["s_reg"] ** 2 + params["s_base"] ** 2 + params["s_poll"] ** 2 / n_eff)
        err = r["actual"] - r["poll_avg"]
        errs.append(err)
        p = _phi(r["poll_avg"] / s_tot)
        y = 1.0 if r["actual"] > 0 else 0.0
        brier.append((p - y) ** 2)
        in80 += abs(err) <= 1.2816 * s_tot
        in95 += abs(err) <= 1.96 * s_tot
        ll += -(y * math.log(max(p, 1e-9)) + (1 - y) * math.log(max(1 - p, 1e-9)))
    n = len(bt)
    return {"n_races": n, "rmse": round(math.sqrt(sum(e * e for e in errs) / n), 2), "mean_signed_error_actual_minus_polls": round(sum(errs) / n, 2),
            "coverage_80": round(in80 / n, 3), "coverage_95": round(in95 / n, 3), "brier": round(sum(brier) / n, 4), "log_loss": round(ll / n, 4),
            "right_call_rate": round(sum(1 for r in bt if (r["poll_avg"] > 0) == (r["actual"] > 0)) / n, 3)}


def backtest(write=True):
    bt = backtest_races()
    results = []
    for s_nat in GRID["s_nat"]:
        for s_base in GRID["s_base"]:
            for s_poll in GRID["s_poll"]:
                p = dict(DEFAULT_PARAMS, s_nat=s_nat, s_base=s_base, s_poll=s_poll)
                sc = score(bt, p)
                sc["params"] = {k: p[k] for k in ("s_nat", "s_reg", "s_base", "s_poll")}
                sc["calibration_loss"] = round(abs(sc["coverage_80"] - 0.8) + abs(sc["coverage_95"] - 0.95) + sc["brier"], 4)
                results.append(sc)
    results.sort(key=lambda x: x["calibration_loss"])
    best = results[0]
    by_year = {}
    for yr in ("2018", "2022"):
        sub = [r for r in bt if r["year"] == yr]
        by_year[yr] = {"all": score(sub, dict(DEFAULT_PARAMS, **best["params"])),
                       "senate": score([r for r in sub if r["office"] == "senate"], dict(DEFAULT_PARAMS, **best["params"])),
                       "governor": score([r for r in sub if r["office"] == "governor"], dict(DEFAULT_PARAMS, **best["params"]))}
    doc = {"_layer": "scenarios", "built_at": utcnow(), "source": {"name": "FiveThirtyEight pollster-ratings raw-polls.csv (2018 and 2022 Senate and Governor general-election polls, with official results)",
                                                                  "file": os.path.relpath(BT_CSV, ROOT), "license": "CC BY 4.0"},
           "method": "Per race: desk-style weighted average of polls in the final 60 days (half-life 14 d, sqrt(n), partisan x0.5; no ratings); P(D) = Phi(avg / s_total); "
                     "s_total^2 = s_nat^2 + s_reg^2 + s_base^2 + s_poll^2 / min(n, 8). Grid over s_base and s_poll; s_nat pinned at 2.5 and s_reg at 1.5 (shared error is not identifiable from per-race coverage and is set by judgment).",
           "n_races": len(bt), "chosen_params": dict(DEFAULT_PARAMS, **best["params"]), "chosen_metrics": {k: v for k, v in best.items() if k != "params"},
           "default_metrics": score(bt, DEFAULT_PARAMS), "by_year": by_year, "grid_top10": results[:10],
           "races": bt}
    if write:
        dump_json(os.path.join(DATA, "scenarios", "backtest.json"), doc)
    return doc


# --------------------------------------------------------------------------- run

def _early_vote_context():
    import glob
    rows = []
    for path in sorted(glob.glob(os.path.join(DATA, "early_vote", "*.jsonl"))):
        rs = read_jsonl(path)
        if rs:
            last = rs[-1]["snapshot_id"]
            rows.extend(r for r in rs if r["snapshot_id"] == last and r.get("geo_level", "state") == "state" and r.get("party") in ("Democratic", "Democrat", "Republican") and r.get("mode") in ("total", None))
    ctx = defaultdict(dict)
    for r in rows:
        ctx[r["geography"]][r["party"]] = {"value": r["value"], "metric": r["metric"], "as_of": r.get("as_of"), "source": r.get("source")}
    return {"note": "Turnout indicators by party registration where a state publishes them (who voted, not how). Shown for context; they move no probability in this model.", "states": dict(ctx)}


def run(n_sims=N_SIMS, seed=SEED, write=True):
    bt = load_json(os.path.join(DATA, "scenarios", "backtest.json"), None)
    params = dict(DEFAULT_PARAMS, **(bt or {}).get("chosen_params", {}))
    races, excluded, house = race_inputs(params)
    chambers = load_json(os.path.join(DATA, "contests", "chambers.json"), {})
    if chambers and "holdovers" not in chambers.get("senate", {}):
        senate = load_json(os.path.join(DATA, "contests", "senate_2026.json"), {"races": []})["races"]
        up = Counter(r.get("holder_party") for r in senate)
        chambers["senate"]["holdovers"] = {"d": chambers["senate"]["democrat"] - up.get("D", 0), "r": chambers["senate"]["republican"] - up.get("R", 0), "i": chambers["senate"]["independent"] - up.get("I", 0)}
    noise = simulate_margins(races, params, n_sims, seed)
    shifts = {"polls_as_is": 0.0, "blue_wave_d_plus_3": 3.0, "red_wave_r_plus_3": -3.0}
    if bt:
        for yr in ("2018", "2022"):
            m = (bt.get("by_year") or {}).get(yr, {}).get("all", {}).get("mean_signed_error_actual_minus_polls")
            if m is not None:
                shifts[f"repeat_{yr}_poll_error"] = m
    presets = {}
    for name, shift in shifts.items():
        presets[name] = evaluate(races, noise, shift, chambers)
    whtbt = what_has_to_be_true(races, noise, chambers)
    inputs_hash = hashlib.sha256(json.dumps([{k: r[k] for k in ("race", "mu", "s_race")} for r in races], sort_keys=True).encode()).hexdigest()[:12]
    out = {"_layer": "scenarios", "built_at": utcnow(), "disclaimer": DISCLAIMER, "n_sims": n_sims, "seed": seed, "params": params,
           "params_source": "backtest.json chosen_params" if bt else "shipped defaults (run `python3 tools/simulate.py --backtest` to calibrate)",
           "inputs": races, "excluded": excluded, "inputs_hash": inputs_hash,
           "house_baselines": {"districts_with_2024_on_2026_lines_baseline": 0, "districts_with_public_rating": sum(1 for r in races if r["office"] == "house"),
                               "note": "No House chamber simulation: 2024 presidential results on 2026 lines are not loaded for any district; districts without a stored rating show 'no baseline'."},
           "presets": presets, "what_has_to_be_true": {"target": "Democratic caucus of 51 (the Vice President is Republican, so 50 is not control)", **whtbt},
           "early_vote_context": _early_vote_context(), "backtest_summary": {k: (bt or {}).get(k) for k in ("n_races", "chosen_metrics", "by_year")} if bt else None}
    if write:
        dump_json(os.path.join(DATA, "scenarios", "latest.json"), out)
        base = presets["polls_as_is"]
        append_jsonl(os.path.join(DATA, "scenarios", "history.jsonl"), {"at": out["built_at"], "inputs_hash": inputs_hash, "n_races": len(races),
                                                                           "p_dem_control_51": base["senate"]["p_dem_control_51"], "expected_dem_caucus": base["senate"]["expected_dem_caucus"],
                                                                           "gov_expected_dem_wins": base["governors"]["expected_dem_wins"], "shift_needed_for_51": whtbt.get("shift_needed"),
                                                                           "params": params})
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--backtest", action="store_true", help="recalibrate error scales on the 2018 and 2022 fixtures and write data/scenarios/backtest.json")
    ap.add_argument("--sims", type=int, default=N_SIMS)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.backtest:
        doc = backtest(write=not a.dry_run)
        print(json.dumps({"n_races": doc["n_races"], "chosen": doc["chosen_params"], "metrics": doc["chosen_metrics"], "by_year": {y: v["all"] for y, v in doc["by_year"].items()}}, indent=1))
    else:
        out = run(n_sims=a.sims, write=not a.dry_run)
        b = out["presets"]["polls_as_is"]["senate"]
        print(f"scenarios: {len(out['inputs'])} races ({len(out['excluded'])} without baseline); Senate P(D>=51) {b['p_dem_control_51']}, expected D caucus {b['expected_dem_caucus']}; "
              f"shift needed for 51: {out['what_has_to_be_true'].get('shift_needed')}; presets {list(out['presets'])}")
