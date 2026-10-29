# Election Desk 2026

Public results and polling desk for the Nov 3, 2026 general election: a national
Senate/House/Governor map with polls, ratings, early-vote indicators, live results
and attributed media calls, plus a Macomb County (Michigan) results aggregator.

**Everything here is public.** See [`PRIVATE_LAYER.md`](PRIVATE_LAYER.md) for what
never goes in this repository. A hygiene check runs on every commit.

## Rules the desk follows

- **Six data layers, never cross-written:** `polls` (evidence), `ratings` (judgment),
  `early_vote` (turnout indicators, *who voted, not how*), `results` (official counts,
  UNOFFICIAL until certified), `calls` (media projections, outlet + time), `scenarios`
  (our assumptions, never shown as data).
- **No automatic race calls.** Status ladder: Too early → Leaning → Likely →
  Projected (outlet + time) → Final unofficial → Certified.
- **Every number shows its source and timestamp** and is marked UNOFFICIAL until certified.
- **Append-only snapshots** with a raw payload hash; polls deduplicated by
  pollster + field dates + population + race.
- **No synthetic data.** A missing baseline is shown as "no baseline".
- **Source terms respected.** Cook Political Report: label, date and link only (Senate, Governor and Michigan House labels are stored; other House districts link out). Inside Elections: label, date and link from its public cached JSON. UF Election Lab early-vote figures are shown unmodified with attribution (CC BY-NC-ND) and never blended. AP's data API is licensed and is not scraped. Bot-walled hosts (Cook from GitHub runners, Sabato, michigan.gov) are never worked around: hand entry or an off-runner fetch with the real bytes hashed.
- **Simulator outputs are the `scenarios` layer**: model estimates from polls and ratings, labeled internal in the UI, never written to `results` or `calls`. House districts without a 2024-on-2026-lines baseline or a stored rating read "no baseline".
- **Neutral anomaly language:** "data changed — confirm with the Clerk."

## Layout

| Path | What |
| --- | --- |
| `docs/` | The GitHub Pages site (static; reads only the JSON under `docs/data/`). |
| `data/sources.json` | Source registry: layer, URL, format, terms, rate limit, health. |
| `data/contests/` | Contest definitions: chamber balance, Senate/Governor races, redistricted states, Macomb ballot. |
| `data/baselines/` | Real prior results on the lines in effect for Nov 2026. |
| `data/<layer>/` | Append-only records per layer. `ratings/` and `early_vote/` hold one file per source (rows per snapshot) plus `ratings/changes.jsonl`; `scenarios/` holds the simulator's `latest.json`, `history.jsonl` and `backtest.json`. |
| `data/snapshots/index.jsonl` | Every pull: source, time, raw hash, parse status. |
| `data/raw/` | Gzip'd raw payloads, deduplicated by hash. |
| `data/anomalies.jsonl`, `data/ops_log.jsonl` | Anomaly queue and operations log. |
| `tools/` | Pollers (`poll_votehub`, `poll_enhanced_voting`, `poll_ratings`, `poll_early_vote`, `poll_macomb_pdf`, `poll_clarity`), parsers, the simulator (`simulate.py`, with `--backtest`), the site-data builders, the hygiene check. |
| `fixtures/` | Public source documents used as parser fixtures. |
| `.github/workflows/` | `hygiene` (every push), `poll-scheduled` (pre-election cadence), `election-night` (manual loop), `manual-entry` (results, calls, ratings or early-vote hand entry), `fetch-fixtures` (manual, several files per run), `reach` (manual runner reachability test), `probe`. |

## Setup

```
sh tools/install_hooks.sh      # pre-commit hygiene hook
pip install -r requirements.txt
pytest -q
```

## Attribution

Polling data via VoteHub and the original pollsters; ratings labels © their
publishers (Cook Political Report, Sabato's Crystal Ball, Inside Elections), shown
with date and link; results from state and county election offices; calls from
the named outlets. This desk is not affiliated with any of them.
