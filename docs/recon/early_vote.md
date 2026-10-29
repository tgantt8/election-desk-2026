# Early-vote source recon (layer: early_vote) - 2026-10-29

Registry: `early_vote.json` (24 entries). Status key: VERIFIED = fetched by me in the Composio workbench on 2026-10-29 (python requests). UNVERIFIED = blocked, not reachable, or search-only; the entry's `verification_evidence` says which.

Method note: the first pass used WebSearch only (WebFetch could not resolve hosts). After the coordinator's correction, I fetched in the workbench. Several state sites (GA, IA, MN, OH, TX SOS) return bot walls (Cloudflare, Radware, WAF) to the workbench IP; AK fails TLS. Those stay UNVERIFIED, and a GitHub Actions runner will probably hit the same walls. Illustrative numbers below are timestamped schema examples from the fetch, not data to ingest.

## Headline answers

1. **VoteHub.** Tracker: `https://votehub.com/2026-early-vote-tracker` (domain is votehub.com, not .us). `api.votehub.com` is a Polling API only (docs at votehub.com/polls/api/, CC BY 4.0): `/early-vote`, `/early_vote`, `/earlyvote`, `/ballots`, `/elections`, `/states` all 404. **No early-vote API.** The tracker's React app reads undocumented static JSON from `cdn.votehub.com/early-vote-tracker/` (`catalog.json` lists 16 states -> `{state}/config.json` -> `toplines.json`, `components.json`, county files). Fields: aggregate count, early in-person count, mail returns count, projected remaining, plus MODELED components (2024 vote, primary-history party, race, age) and modeled Senate/Governor estimates. No explicit as_of per ballot type beyond `updated_at` per file (e.g. MI `2026-10-28T17:36:25Z`). Built "in partnership with L2" (voter-file vendor). Terms: site T&C bar redistribution and derivative works; the CC BY 4.0 grant covers the polls API, not this CDN. **Recommendation: link-only; ask VoteHub for written permission before polling.** Never ingest its modeled vote share or "who is ahead" fields.
2. **Other aggregators.**
   - **UF Election Lab** is the one genuinely machine-readable cross-state feed: `https://election.lab.ufl.edu/data-downloads/earlyvote/2026/US.csv` (49 jurisdictions; per-state `official source URL`, `last_update`, caveat notes; requested/accepted/in-person/voted, each by party registration, age, gender, race where the state gives it; `turn_2022`), plus `{ST}_county.csv` and `{ST}_cd.csv`. License: **CC BY-NC-ND 4.0** (attribution mandatory, non-commercial, no derivatives). The ND term means display unmodified and attributed; do not blend or renormalize into our own series without written OK from [UF Election Lab contact address on its site]. It lacks AL and NH.
   - **TargetSmart TargetEarly 2026**: client-only (MyTargetSmart, "Request Access"); voter-file-derived. Exclude.
   - **NBC News** `nbcnews.com/politics/2026-elections/early-vote`: public page, data "sourced from TargetSmart and state officials", party = state-provided plus TargetSmart model. Link-only.
   - **Decision Desk HQ / NewsNation**: `newsnation-votes.decisiondeskhq.com` root returns Vercel DEPLOYMENT_NOT_FOUND; primary-race early-vote pages were seen only in search. Treat as absent for November.
   - OnPoint Politics and PollCheck (UK): unknown or secondary provenance. Do not use.
3. **Michigan (priority).**
   - Official live source: **Michigan Voting Dashboard**, `https://www.michigan.gov/sos/elections/election-results-and-data/voter-participation-dashboard`. A public **Power BI Gov embed** (no CSV/XLSX export on the page). Geography: county and municipality. Fields: mail ballots requested, mail ballots returned for tabulation, early in-person ballots cast. Source: voter history in the Qualified Voter File as keyed by clerks; counts "will not match official or unofficial election results"; values of 10 or fewer show "Less than 10". Updated daily from 45 days out; the Oct 20 release says daily "between now and the Monday before Election Day" (through Mon Nov 2); archived and frozen 30 days after Election Day. **No party** (Michigan has no party registration).
   - Statewide milestone numbers: SOS news releases (Oct 13 = 3 weeks, Oct 20 = 2 weeks; expect ~1 week and a final), each with a 2026-vs-2022 table and an attached 2022 XLSX by jurisdiction.
   - **Baseline file (verified, downloaded):** `.../Press-releases/2026/documents/PRNov2022AV-BallotStats2022_10_24.xlsx`, one sheet, columns COUNTY, JURISDICTION, APPS RECEIVED, BALLOTS SENT, BALLOTS RECEIVED, BALLOTS SPOILED, BALLOTS REJECTED (Macomb rows present). Also 3-week (`PRNov2022BallotStatsByJurisdiction_10_17_2022.xlsx`) and 1-week (`10-31-2022-PR-Nov-2022-AV--Ballot-Stats.xlsx`) files.
   - **Macomb County Clerk**: the Elections page (fetched) has no AV-return statistics, only unofficial results links and a per-voter "Track Your Absent Voter Ballot" link (excluded, voter-level). Use the dashboard's county and municipality view plus the 2022 XLSX rows.
   - Two Michigan traps: (a) statewide early in-person voting did not exist in the 2022 midterm, so "vs 2022" for Michigan is mail-only (use 2024 for a combined comparison); (b) UF's Michigan in-person count is an estimate from application data and differs from the dashboard.
4. **State sources** are in the table below. Only NC and FL (and the MI releases) were fully readable from the workbench.
5. **Baselines:** strong in NC (complete daily PDF archives for 2022 and 2024); good in MI (three 2022 snapshots by jurisdiction); partial elsewhere; none located for AK, NE, NH. Details below.

## State table (Senate battlegrounds)

| State | Official URL (best known) | Format | Party reg published? | Baseline available? | Verified? |
| --- | --- | --- | --- | --- | --- |
| Michigan | michigan.gov/sos/elections/election-results-and-data/voter-participation-dashboard (Power BI); releases at michigan.gov/sos/resources/news | Power BI dashboard (no export); HTML releases; XLSX for 2022 | No (state has no party registration) | Yes for mail: 2022 snapshots at 3/2/1 weeks by county and jurisdiction. Dashboard has no 2022 data. No 2022 early in-person exists | Yes |
| North Carolina | s3.amazonaws.com/dl.ncsbe.gov/Press/2026%20General/NC%20Absentee%20Stats%20for%202026%20General/YYYY-MM-DD%20Daily%20Absentee%20Stats%20Report%20-%202026%20General.pdf; counts CSV `ENRS/2026_11_03/absentee_counts_state_20261103.csv` | PDF (text-extractable) + CSV | Yes (D, R, UNA, LIB, GRN; also race, ethnicity, gender) | Yes: daily PDFs 2022-09-12..2022-11-19 and 2024-09-21..2024-11-26 in the same S3 folder pattern; each report prints a "Comparison to 2022" block | Yes |
| Florida | countyfilesvbm-ev.floridados.gov/VoteByMailEarlyVotingReports/PublicStats | HTML tables with "Download File" links | Yes (R, D, Other, NPA) | Partial: "Archived statistical reports" link on the page (not opened); UF history | Yes |
| Georgia | sos.ga.gov/page/election-data-hub-unofficial-turnout (dashboard); mvp.sos.ga.gov/s/voter-absentee-files (voter-level file: excluded) | Interactive dashboard with county downloads | No party registration in state; dashboard offers "party affiliation" (likely primary history, unconfirmed) | Per-election Data Hub pages exist for 2022 (search); unverified | No (Cloudflare 403) |
| Texas | goelect.txelections.civixapps.com/ivis-evr-ui/evr (IVIS EVR SPA); SOS pages 403 from workbench | SPA over JSON API (not inspected) | No (no party registration) | Not located | Partial (SPA shell 200; data not read) |
| Ohio | data.ohiosos.gov/portal/election-dashboards; press releases on ohiosos.gov | Dashboard; past county XLSX | No (no party registration; some counties report by primary-derived affiliation) | Partial (press releases for 2022 and 2024) | No (403) |
| Iowa | sos.iowa.gov (absentee stats PDFs); per UF, a Vivid dashboard with two public JSON files | PDF and/or JSON | Yes | Partial (2024 primary PDFs exist; general daily not confirmed) | No (Cloudflare 403) |
| Maine | maine.gov/sos/elections-voting/voter-data (Statewide Absentee Voter Data File) | Text file, VOTER-LEVEL | Yes (enrollment field) | Prior files kept (voter-level) | No (403); excluded by VAN firewall |
| Alaska | elections.alaska.gov/research/statistics/ | Reports (format unknown) | Division report has party share (per Alaska Beacon); UF row has none | Not located | No (TLS failure) |
| Nebraska | No public state page located; UF lists "data file provided by Nebraska SOS" | n/a | Via UF only (party columns present) | Not located | No |
| New Hampshire | app.sos.nh.gov (per-voter lookup; excluded) | n/a | Not published in an aggregate | 2024 total only (99,524 absentee, NHPR) | No; absent from UF |
| Minnesota | sos.mn.gov/election-administration-campaigns/data-maps/absentee-data/ | HTML/Excel (unconfirmed); weekly | No (no party registration) | Page keeps statewide summary back to 2018 (search) | No (Radware CAPTCHA); UF row last updated 10/23 |

## Baseline reality check ("vs 2022 / vs 2024")

- **Best:** NC (daily PDFs both cycles, same S3 pattern, plus 2024 daily county turnout folder). Align by days before election, not date: Election Day was Nov 8 2022, Nov 5 2024, Nov 3 2026.
- **Good:** MI (3 weeks, 2 weeks, 1 week out in 2022, by jurisdiction; SOS pairs Oct 20 2026 with Oct 24 2022, a one-day offset). MI 2024: not checked.
- **Partial:** UF (`turn_2022` denominator and a single final 2024 snapshot), FL archives, OH/IA press materials.
- **None found:** AK, NE, NH, MN same-day series.
- **Comparability warnings:** Michigan no 2022 early in-person; Ohio's new receipt-by-Election-Day rule; NC mode shift (mail down, in-person up); registration/rule changes 2022 -> 2026. Say "no baseline" or "not comparable" rather than interpolate.

## Recommended fetch plan for a GitHub Actions poller

Principles: append-only snapshots (raw bytes + sha256 + fetched_at + source_as_of + source URL, written under `early_vote/`, never touching other layers), conditional requests (ETag / If-Modified-Since, HEAD first), one identifying User-Agent with a contact, per-source minimum interval, failures logged not retried in a loop, no bot-wall bypass, no voter-level files. Early voting is almost over, so the window is Oct 29 - Nov 3 (MI dashboard until Nov 2; FL reporting to Nov 9; MI/other archives later).

| Priority | Source | Cadence | Notes |
| --- | --- | --- | --- |
| 1 | NC daily PDF (dated URL) | Poll 09:30-10:30 ET every 20 min until 200, then stop for the day | Published ~13:12 GMT (9:12 ET); fetch once; parse with pypdf; alarm on layout change; also CSV `absentee_counts_state_20261103.csv` (updates ~08:41 GMT) via HEAD/Last-Modified |
| 2 | FL PublicStats | 08:30, 12:15, 15:15, 18:15 ET | Statewide and county tables; capture the "Compiled" timestamp as source_as_of |
| 3 | MI SOS news index + releases | Hourly | Parse the 3-row table; snapshot raw HTML; also pick up any new XLSX link |
| 4 | UF `US.csv` (+ `MI_county.csv`, `GA_county.csv`, `NC_county.csv`, `FL_county.csv`, `TX_county.csv`) | Every 30 min, If-Modified-Since | GATED on a license decision (CC BY-NC-ND): ask the lab; if no, link-only. Use per-row `last_update` as as_of; keep its `notes` column visible |
| 5 | VoteHub `catalog.json` | None until permission | If granted: ETag poll every 10 min; keep only aggregate counts |
| 6 | MI dashboard (Power BI) | Manual capture 2x/day by a person, or ask [contact address redacted — see source site] for a feed | No automation |
| 7 | Bot-walled states (GA, IA, MN, OH, TX SOS, ME, AK) | Link-only; consume via UF rows | Revisit if a state publishes a plain CSV/JSON; IA's Vivid JSON URLs need a browser to find |
| One-off | MI 2022 XLSX x3, NC 2022/2024 daily PDFs, UF 2024 `US.csv` | Once, store as baseline | Hash and commit as baseline snapshots |

Display rules: banner "Who voted, not how they voted"; party columns labeled "party registration (turnout indicator)"; modeled party from NBC/TargetSmart/VoteHub never shown as registration; MI "vs 2022" labeled mail-only; show source name, URL and source_as_of on every number.

## Open items for the coordinator

1. License ruling on UF CC BY-NC-ND (is a campaign policy-shop dashboard "non-commercial"; is normalizing a derivative). Contact: [UF Election Lab contact address on its site].
2. Ask VoteHub for permission to read `cdn.votehub.com/early-vote-tracker/*.json` (or just link).
3. VAN-firewall ruling: Maine, Georgia, NC, MN publish voter-level absentee files; recommended rule is never download them, even to aggregate.
4. A networked-browser pass to find: IA Vivid JSON URLs, TX IVIS API endpoint, GA Data Hub export links, AK stats page, MN data tables, FL "Archived statistical reports", MI 2024 same-point releases.
5. Allow-list note: the WebFetch tool only reaches hosts the session allows; the workbench reached most, but GA/IA/MN/OH/TX-SOS block it.
