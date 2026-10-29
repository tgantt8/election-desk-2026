# National ENR and calls: source registry notes (recon, 2026-10-29)

Companion to `national_enr.json` in this folder. Results are UNOFFICIAL until certified; every row the desk stores carries source, publisher timestamp (asOf), fetched_at and UNOFFICIAL.

## 0. How this was researched, and what is NOT verified

- The agent shell has no network. WebFetch could not reach most hosts (ENOTFOUND). Probing was done from the Composio remote workbench with plain `requests` and a browser-like User-Agent, plus WebSearch for corroboration.
- Status values in the JSON: `VERIFIED_PARTIAL` means a page, API response or file for that state was actually fetched on 2026-10-29. It does NOT mean a full results night has been tested. `UNVERIFIED` means not fetched (blocked, unreachable, or inferred). Nothing is "VERIFIED" in the strong sense because no 2026 general-election results exist yet.
- 22 of 51 jurisdictions are VERIFIED_PARTIAL; 29 are UNVERIFIED. States where a machine-readable results API/file was actually read: NC, GA, WA, UT, ID, VA (Enhanced Voting JSON or S3 file), TX (static JSON version files), NE (JSON web service answers). That is 8 states (6 fully read, TX and NE partly). Another ~12 are "likely" machine-readable but the endpoint is inferred.
- Blocked or unreachable from the probe (not evidence the sites are down): Clarity/Scytl hosts (CO, IA, SC, AR, six Michigan counties) answer HTTP 202 with an empty body, an AWS WAF JavaScript challenge; Cloudflare "Just a moment" on AZ, MT, NY, WI, mvic.sos.state.mi.us; Access Denied on NH and Wayne County; Radware captcha on MN; 403 "Website Maintenance" page on all Ohio SOS hosts; no connection to mielections.us, elections.alaska.gov, enrpages.sos.mo.gov, results.arkansas.gov, results.elections.delaware.gov, alabamavotes.gov, Wyoming hosts.
- Consequence for the build: any Clarity feed (Colorado, Iowa, South Carolina, Oakland/Macomb/Genesee) needs a client that passes the WAF challenge, or manual entry. Test this from the production network BEFORE Nov 3. Do not try to defeat a challenge by spoofing; if the host challenges your client, use the manual path for that state.

## 1. Vendor-by-vendor parsing guidance

### 1a. Enhanced Voting (most useful finding; verified)
States/jurisdictions verified: Georgia (results.sos.ga.gov), Washington (results.votewa.gov, moved from results.vote.wa.gov), Utah (electionresults.utah.gov), Idaho (results.voteidaho.gov), Virginia (enr.elections.virginia.gov), and 15 Michigan counties (app.enhancedvoting.com). Same Angular app and same JSON API everywhere:

- Base: `https://<host>/results/public/api` (app config: `api.endpoint = /results/public/api`, `cdn = /cdn/results`).
- `GET /jurisdictions/<slug>`: slug is the last path segment of the public URL (`Georgia`, `washington`, `Utah`, `id`, `virginia`, `ingham-county-mi`). Returns `elections[]` with `publicElectionId`, `electionDate`, `name`, plus `childLocalities[]` (counties with `percentReporting`, `precinctsReporting`).
- `GET /elections/<slug>/<publicElectionId>` (about 2KB): `asOf`, `lastUpdated`, `publishDate`, `nextUpdateAt`, `isOfficialResults`, `isProduction`, `ballotItemCount`, `precinctsReporting`, `ballotsCast`, `totalVoters`, `isPrimary`, `parties`, `closeRaceThreshold`. Use this as the cheap change detector.
- `GET /elections/<slug>/<id>/ballot-items` (GA 2024: 295 items, about 600KB): each item has `name[0].text`, `voteFor`, `contestType`, `voteTotal`, `reportingStatus {reportingUnits,totalUnits,asOf}`, `isCloseRace`, `partyName`, and `summaryResults.ballotOptions[]` with `name[0].text` (candidate with party, e.g. "Donald J. Trump (Rep)"), `nativeId`, `voteCount`, `party{abbreviation}`, `isWinner`, and `groupResults[]` (vote type: Election Day, Absentee by Mail, Provisional, Advanced Voting). Also `/localities` (child jurisdictions), `/stats`, `/turnout`.
- Gotchas: election IDs are free text and not predictable (`06162026GeneralPrimaryRunoff`, `20261103`, `General11032026`, `2026-November-General`, `NovemberElection11032026`), so poll `/jurisdictions/<slug>` and match on `electionDate == 2026-11-03`. Georgia has NOT yet published its Nov 3 election; Idaho neither. `isWinner` is a vendor/publisher flag, NOT a media call: never map it to the calls layer. `summaryResults` for candidates names include the party in parentheses; parse from `party.abbreviation`. `nextUpdateAt` was null on completed elections.
- No documented rate limit or terms were found for these APIs (UNVERIFIED). The pages are public and the API is what the public front end calls; still, identify the client with a real User-Agent, keep cadence low, and stop on 403/429.

### 1b. Clarity / Scytl ENR (CO, IA, SC, AR, MI counties Oakland, Macomb, Genesee, Eaton, Grand Traverse, Roscommon)
- Not fetchable from the probe (HTTP 202 empty body for every path, including `current_ver.txt`, `json/en/summary.json`, `reports/detailxml.zip`).
- Documented pattern from public tools (the open-source Clarify library, corroborated by a search result): election page `https://results.enr.clarityelections.com/<ST>/[<County>/]<electionID>/<version>/en/summary.html`; bulk XML at `.../<electionID>/<version>/reports/detailxml.zip`. The commonly used JSON endpoints are `.../<electionID>/current_ver.txt` (returns the current version number) and `.../<electionID>/<version>/json/en/summary.json` (list of contests with keys for contest name, choices, votes, precincts reporting) plus `json/sum.json` / `electionsettings.json`. The exact key names are UNVERIFIED in this session: capture a real sample on the production network and write a schema test against it.
- Michigan Clarity counties embed the election ID in the page link on the county clerk site (example IDs seen: Oakland 126183, Macomb 127293, Genesee 119436/121072); a new ID is issued per election, so scrape the county landing page link on the night (or look it up the day before).
- Parsing rule: poll `current_ver.txt` first (tiny); fetch the big summary only when the version changes.

### 1c. North Carolina (verified, tab-delimited)
- `https://s3.amazonaws.com/dl.ncsbe.gov/ENRS/2026_11_03/results_pct_20261103.zip` already exists (zero-vote scaffold uploaded 2026-10-05, 14.6MB uncompressed, ~637KB zipped). On election night NCSBE overwrites it with live precinct results.
- Columns (tab-delimited, header row): County, Election Date, Precinct, Contest Group ID, Contest Type, Contest Name, Choice, Choice Party, Vote For, Election Day, Early Voting, Absentee by Mail, Provisional, Total Votes, Real Precinct. Vote types are separate columns. The March 2026 file has a trailing tab and extra empty column; strip it.
- Folder listing (public S3 ListObjects): `https://s3.amazonaws.com/dl.ncsbe.gov?prefix=ENRS/2026_11_03/`. Other files there now: `absentee_20261103.zip`, `absentee_county_20261103.zip`, `absentee_counts_state_20261103.csv`, `absentee_counts_county_20261103.csv`, `absentee_demo_stats_20261103.csv`, `polling_place_20261103.csv`, `provisional_20261103.txt`, daily `absentee_spoiled_outstanding_20261103_YYYYMMDD.zip` (all refreshed roughly 08:40-09:25 UTC daily). These feed the early_vote layer.
- S3 sends `Last-Modified`/`ETag`: use conditional GET. The dashboard (`https://er.ncsbe.gov/`, HTTP 200) is the human view.
- `ENRS/2026_03_03/results_pct_20260303.zip` (modified 2026-04-16) is post-canvass, and `results_precinct_sort/*.txt` has statistical noise; neither is election-night data. Use them only as parser fixtures.

### 1d. Texas (verified partially)
- `GET https://results.texas-election.com/static/data/Version.json` returns `{"___versionNo":404}`; `static/data/ElectionConstants_404.json` carries `currentelectionInfo` (today: ID 49664, "2024 NOVEMBER 5TH GENERAL ELECTION") and `electionInfo` by year (no 2026 key). `static/data/election/<ID>/Version.json` returns `{"___versionNo":1012,"elecDate":"11052024"}`. Data files (Race.json, OfficeSummary.json, County.json, StateWide.json, Federal.json, Lookups.json, Home.json) are loaded by the Angular app under a versioned path; exact path not verified. Service `https://candidate.texas-election.com/ElectionResults/Service/` has a `getResults` method.
- Plan: on election day re-read Version.json and ElectionConstants; derive the new election ID; read `main.*.js` for the file path template once, before the night.

### 1e. Nebraska / New Mexico / South Dakota / North Dakota (one vendor family)
ASP.NET pages with a JSON/WCF service: NE `https://neresultswebservice.azurewebsites.us/ResultsAjax.svc/GetCandidates?ElectionType=<t>&ElectionID=<id>`; NM `https://nmresultswebservice.azurewebsites.us/`; SD `https://sdresws.azurewebsites.us/`; ND `https://resultsws.sos.nd.gov/`. The NE service answers (500 JSON error on bad params, proving it is live). Other method names are not verified; read the page JS (`ResultsAjax.svc/...`).

### 1f. Others
- Florida: `https://floridaelectionwatch.gov/` is up now with the header "2026 General Election November 3, 2026 Unofficial Election Night Results" (routes `/TrackCounty/<ALA..>`, Election Day Turnout, County Reporting Status). Data endpoints not found; legacy `results.elections.myflorida.com` is a frameset (`ElectionRaces.asp?ElectionDate=&DATAMODE=`).
- Pennsylvania: AngularJS app at electionreturns.pa.gov with an ASP.NET Web API behind it (unknown routes return JSON 404). Find XHR route names in the browser.
- Massachusetts, Vermont: ElectionStats platform (archive-style, CSV download per election). Kent County MI also runs ElectionStats.
- Indiana: AngularJS `EnrApp` with a download directive (`enrDownloadResults.js`).
- Maryland: static HTML plus CSV on elections.maryland.gov (`/elections/2026/`); Virginia also offers CSV at apps.elections.virginia.gov/SBE_CSV/ELECTIONS/ELECTIONRESULTS/.
- Alaska, Hawaii, Maine, New Hampshire, Wisconsin: no verified state-level live feed; use local/AP-attributed sources or manual entry.

## 2. Michigan in depth

- The SOS page is a LINK LIST, not an ENR: "Candidate listings and election results by county" lists the 83 county clerk sites and says these may post unofficial results on election night; unofficial until certified by county/state boards of canvassers. Statewide aggregate only appears after all counties have reported, and the SOS says to rely on county clerk sites (search-corroborated: full unofficial totals about 24 hours after polls close). `mielections.us` CENR pages (`2016SG1_CENR.html` is linked; pattern `<YYYY><GEN|PRI>_CENR.html`) could not be reached from the probe.
- Poll close 20:00 ET; four Upper Peninsula counties on Central time close 21:00 ET.
- County vendor sweep (83 links fetched 2026-10-29): Enhanced Voting counties with a Nov 3 2026 election already published: Clare, Delta, Gratiot, Ingham, Isabella, Lake, Midland, Newaygo, Osceola, Saginaw, Shiawassee, St. Joseph, Van Buren (API URL and election ID in `michigan.enhanced_voting_counties_nov3_2026_ready`). Cass and Leelanau use Enhanced Voting but had no Nov 3 entry yet. Clarity: Oakland, Macomb, Genesee, Eaton, Grand Traverse, Roscommon (WAF-challenged). Kent: ElectionStats plus PDF "Unofficial Election Summary Report". Wayne: clerk site 403 to probe; historically PDF uploads, and Wayne cannot report until all 43 local clerks submit. Washtenaw, Ottawa, Kalamazoo, Allegan, Berrien, Livingston, Muskegon, Monroe, Jackson, St. Clair, Calhoun, Lenawee not identified (403/202 or no vendor link on landing page).
- Recommendation: for the Michigan statewide US Senate/governor race the desk needs Wayne, Oakland, Macomb, Kent, Genesee, Washtenaw, Ingham, Ottawa, Kalamazoo, Saginaw at minimum. Pre-resolve each county's results URL on Nov 2 and record manual-entry fallbacks (county, URL, last seen timestamp) for the ones that cannot be fetched.

## 3. Recommended LIVE-TEST feeds (proving the pipeline before Nov 3)

No election is under way before Nov 3, so nothing is changing vote counts today. Machine-readable and fetchable right now:
1. **Washington Nov 3 2026 shell**: `https://results.votewa.gov/results/public/api/elections/washington/20261103` (+ `/ballot-items`, 173 items, zero votes, `isOfficialResults:false`, `asOf` 2026-10-22). Same schema as the election-night feed, so the parser, change-detection on `asOf`/`lastUpdated`, and the UNOFFICIAL stamping are exercised for real. Utah `General11032026` and Virginia `2026-November-General` are equivalent second and third shells.
2. **North Carolina**: poll the S3 folder listing and conditional-GET `results_pct_20261103.zip` (zero-vote scaffold now; it will switch to live data on the 3rd) and the daily `absentee_counts_state_20261103.csv` (this one changes every day, the best real "updating feed" available now). Gives a tab-delimited-parser test.
3. **Replay fixtures with real counts** (completed, official, not election-night): Georgia `06162026GeneralPrimaryRunoff` (27 contests, 159 counties reporting, asOf 2026-08-20) and NC `ENRS/2026_03_03/results_pct_20260303.zip`. Store them as test fixtures, labelled as fixtures and never ingested into the results layer as 2026 general data.

Recommended single live-test feed: **Washington `20261103` on results.votewa.gov** (public JSON, current, production-mode, stable schema).

## 4. Fetch plan (election night)

- Cadence: 120-180 seconds per source during counting; 300 seconds before polls close and after midnight ET; one-in-flight per host; add 0-20s jitter; never more than one request per second to any host overall.
- Two-step polling: cheap change detector first (Enhanced Voting election object ~2KB; Clarity `current_ver.txt`; Texas `Version.json`; NC S3 HEAD/conditional GET), full payload only when it changes.
- Back off on 429/403/5xx (double the interval, cap at 15 min); open a circuit after 3 consecutive failures; alert to the desk and switch to manual entry. Respect robots.txt; no WAF-evasion.
- Persist append-only snapshots: raw bytes (sha256), URL, HTTP status, response headers (ETag, Last-Modified), fetched_at (UTC and ET), publisher `asOf` when present. Parsed rows reference the snapshot id. Never mutate a snapshot. Normalize but keep original strings; party comes from the source's party field.
- Per-source limits I recommend (no vendor publishes one): Enhanced Voting 1 req/120s/host for ballot-items, 1/60s for the election object; NC S3 1/120s; TX Version.json 1/60s; state sites 1/180s. Michigan: poll each priority county at 1/180s, staggered.
- Plausibility checks use neutral wording: "value decreased versus previous snapshot", "precincts reporting exceeds total", "source timestamp older than 10 minutes". Never auto-flag a source as wrong.
- Scheduled steps before the night: Nov 2: resolve all Michigan county URLs, Georgia/Idaho election IDs, Texas ElectionConstants; test the Clarity fetch from the production network; confirm that Ohio/Minnesota/Arizona/NY/WI hosts are reachable from the production IP.

## 5. CALLS: plan

- Available now: no outlet offers a machine-readable race-call feed under free terms. AP's raw election data API is licensed; the desk does not scrape around it. AP's own `robots.txt` (fetched 2026-10-29) disallows `/api/v2/feed/`, `/apdata/`, widgets and all of ClaudeBot/anthropic-ai/Claude-User/GPTBot/PerplexityBot etc.; AP's results hub is `https://apnews.com/projects/elections-2026/` (title "2026 Midterm Election Results: Senate, House and Governors"; one page-title check was made from the probe). NBC's robots is a disallow-bots file. CBS disallows `/election-results-data/*`. The Hill (crawl-delay 20) and NewsNation (crawl-delay 5-20) host DDHQ results. CNN, ABC, Fox: no feed.
- Calls therefore enter the calls layer by **manual entry**, one append-only row per outlet call. Fields: call_id; race_id; outlet; basis (AP call, outlet decision desk, DDHQ); called_for; called_at_et as displayed by the outlet (or `unknown_displayed_time` plus entered_at); url; note or screenshot ref; entered_by; entered_at; retraction rows are new rows, never edits. Two outlets calling the same race are two rows; status ladder "Projected (outlet + time)" requires at least one such row; the desk never derives a call from vote totals or from `isWinner` flags in vendor JSON.
- Optional later: license AP Elections API or DDHQ API; then ingest calls as `basis=AP API` with the contract's terms.
- Outlets to watch (free pages): AP, NPR (AP-powered, did not connect from probe), PBS NewsHour, local AP members (Detroit Free Press, MLive, Detroit News, Michigan Public, local TV), NBC, CBS, ABC, CNN, Fox, DDHQ via The Hill/NewsNation.

## 6. Senate 2026: seats up (35 contests in 35 states)

Source: Wikipedia "2026 United States Senate elections" table parsed 2026-10-29 (35 states) and consistent with Ballotpedia counts (33 regular + 2 special). All are Class 2 regular except the two Class 3 specials.
- Class 2 regular (33): Alabama, Alaska, Arkansas, Colorado, Delaware, Georgia, Idaho, Illinois, Iowa, Kansas, Kentucky, Louisiana, Maine, Massachusetts, Michigan, Minnesota, Mississippi, Montana, Nebraska, New Hampshire, New Jersey, New Mexico, North Carolina, Oklahoma, Oregon, Rhode Island, South Carolina, South Dakota, Tennessee, Texas, Virginia, West Virginia, Wyoming.
- Class 3 special (2): Florida (Rubio seat; appointee Moody) and Ohio (Vance seat; appointee Husted).
- Seat changes this cycle per search and the Wikipedia table: Oklahoma (appointed 2026 after Mullin became DHS Secretary; appointee not on ballot), South Carolina (appointed 2026 after Sen. Graham's death, per search). Names of nominees were not verified; do not hardcode them from this note.
- States WITHOUT a Senate race in 2026 (the desk's "no race" hatch): AZ, CA, CT, DC, HI, IN, MD, MO, NV, NY, ND, PA, UT, VT, WA, WI (16 jurisdictions of the 51 rows).
- Wikipedia rating snapshot for tiering only (not the ratings layer): Tossup AK, IA, KS, ME, MI, OH(special), TX; Likely D GA; Likely D (flip) NC; Lean D MN, NH; Lean R SC; Likely R MS, NE.

## 7. Governors 2026

36 states (Wikipedia table parsed 2026-10-29, matches Ballotpedia's count): AL, AK, AZ, AR, CA, CO, CT, FL, GA, HI, ID, IL, IA, KS, ME, MD, MA, MI, MN, NE, NV, NH, NM, NY, OH, OK, OR, PA, RI, SC, SD, TN, TX, VT, WI, WY. Territories: Guam and Northern Mariana Islands appear in the table; a U.S. Virgin Islands race is reported by Ballotpedia ("three territories"), not confirmed in my parse. States with BOTH governor and Senate races: 26 (consistent with Ballotpedia).
No governor race in 2026 (15 rows: DC, DE, IN, KY, LA, MO, MS, MT, NC, ND, NJ, UT, VA, WA, WV). DC elects a mayor instead (UNVERIFIED).

## 8. Known gaps and next recon

1. Capture a real Clarity sample (production network) and write the exact key list.
2. Resolve Ohio (VoteOhio.gov / liveresults.ohiosos.gov), Minnesota, Arizona, Iowa, Colorado, South Carolina data endpoints from the production network.
3. Find Texas versioned data path from `main.*.js`; Pennsylvania API route names.
4. Michigan: confirm Wayne, Washtenaw, Ottawa, Kalamazoo election-night URLs; confirm the statewide `mielections.us` page status.
5. Alaska, Maine, New Hampshire, Kansas, Kentucky, Louisiana: identify the live host (several did not connect).
6. Verify poll-close rules in the few split-time-zone states against the SOS pages (JSON `poll_close_et` follows the Wikipedia table and my own timezone arithmetic; Nov 3 is EST).
