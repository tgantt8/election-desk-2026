# Election-night runbook — Tue Nov 3, 2026

All times ET. Michigan polls close 8:00 PM (Upper Peninsula CT counties 9:00 PM ET). Everything the desk shows is
UNOFFICIAL until certified (Macomb canvass ~Nov 17; state canvass ~Nov 23).

## Before
- **Mon Nov 2, 11:59 PM — code freeze.** No pushes to `main` after this except data commits by the workflows.
- **7:30 PM Tue** — Source health check: open the desk → Ops. Every results source green or amber; red → note it and plan the fallback below.
- **7:50 PM** — Fire the election-night loop: GitHub → Actions → **election-night** → Run workflow (interval 3, duration 340, layers `results,calls`).
  It runs ~5 h 40 m. **Fire a second run at ~1:20 AM** to carry overnight (the `pollers` concurrency group queues it behind the first).
  The private overlay is refreshed separately (every 15 min) from the committed JSON.

## During (from 8:00 PM)
- The page: Refresh button re-reads the committed JSON; the Auto selector sets 1/5/15/30 min. A yellow banner means the last poll is more than two intervals old.
- **Calls:** the desk never calls a race. When AP (via apnews.com/npr.org) or a network desk calls one, enter it: desk → Ops → Call entry → Copy call JSON → Actions → **manual-entry** (layer `calls`). Outlet and time are required. A retraction is a new entry with status `retracted`.
- **Macomb results:** primary = the Clerk's unofficial summary PDF (polled; each change is a snapshot). Clarity ENR (`results.enr.clarityelections.com/MI/Macomb/127293/`) sits behind a WAF challenge from the runner, so precinct detail comes from a browser: open it, copy the table, desk → Ops → Manual entry → Parse → Copy as JSON → Actions → **manual-entry** (layer `results`). Do not try to defeat the challenge.
- **Anomaly flags** (Macomb detail view): a decrease, votes > ballots, a complete precinct that changed, a stall > 90 min, an over/undervote spike. Language is "data changed — confirm with the Clerk." Open flags get a one-tap note into the Election Defense Plan doc.
- **Digest cadence** (private channel only): post when a Tier 1 or battleground margin moves more than 2 points, a status changes, a chamber-control number changes, or an anomaly opens.

## Failure modes
- **A source goes down:** the poller backs off; the stale banner shows. Nothing to do unless it stays red for 2 intervals → switch that source to manual entry.
- **A format changes:** the parser records the snapshot with `parse_status` = `parse_error`; the raw payload is kept. Switch to manual entry and fix forward after the night.
- **Actions fails:** re-run from Actions (workflow_dispatch). If GitHub Actions is down, pull through the Composio workbench into the private overlay and keep the public desk on its last good snapshot (banner shows staleness).
- **Pages cache:** the site reads JSON with a cache-busting query; if a number looks stale, hard-refresh. Pages deploys take ~1 min after each commit.

## After
- **Wed Nov 4:** switch to the scheduled poller (every 30 min; `poll-scheduled`), then daily. Start the unofficial→certified diff log.
- **Nov 4–23:** certification diffs, Macomb planner, 2028/2030 module (P5).
