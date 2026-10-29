# Macomb County recon (2026-10-29)

Method: WebFetch cannot resolve the macombgov.org hosts and Bash has no network, so pages were fetched in the Composio workbench with Python requests. No vote counts were recorded; PDFs and CSVs were read for layout and labels only. Candidate contact data was not stored.

## 1. Live results: what the Clerk actually points to
- electionresults.macombgov.org: DNS resolves, but TLS ends in EOF (https) and plain http is closed by the remote end. Not reachable from the sandbox. Not linked from the Clerk's current elections page. A search index shows /m42 titled "Macomb County, Michigan Election Results" (Feb 2024), so it may be a retired host. Platform, endpoints, columns: UNKNOWN.
- Clerk elections page https://www.macombgov.org/departments/clerk-register-deeds/elections, under "November 3, 2026 Election: POLLS OPEN 7 A.M. - 8 P.M.", links:
  - "Unofficial Detailed Election Results" -> Clarity ENR https://results.enr.clarityelections.com/MI/Macomb/127293/ . Every request from the sandbox returned HTTP 202 with an empty body (bot challenge), so endpoints could not be tested. Standard Clarity endpoints (current_ver.txt, {ver}/json/en/summary.json, reports/*.zip) are UNVERIFIED for this event.
  - "Unofficial Summary Election Results" -> https://macombgovdocs.org/clerk/pdfs/elect-2026-11-03-unofficial-summary-results.pdf (3 pages, modified 2026-10-27). Currently a blank template. See section 4.
- Also: Track Your Absentee Ballot / sample ballot via Michigan.gov/vote; Public Accuracy Test list https://macombgovdocs.org/clerk/pdfs/elect-2026-11-03-Public-Accuracy-Test-List .
- Mode columns TOTAL / AVCB / Election Day / Early Voting are confirmed in the post-election Summary Results Report (section 2), not in the live feed. Precincts Reporting / Complete / Partially Reported appear there too (rows, one count per mode).
- Legacy static site (2022 and earlier): https://macombgovdocs.org/clerk/electionresults/2022/November22/index.html with results.html, numbered contest pages (4.html to 26.html), precincts.html (ED/AV first-report times, % in), voterturnout.html. Footer states Macomb-only results. 2024/May24 exists; 2024 Nov, 2025 Nov and 2026 Nov folders were not found.
- Recommended fallback: manual paste of Clarity page numbers (UNOFFICIAL, timestamped) plus the summary PDF.

## 2. Past elections database (pastelections.macombgov.org)
Platform: Civera ElectionStats (Next.js), branded "Macomb County Elections Database / Ballot Verifier". The old URL scheme (/contests/view/7785, /contests/get_source_documentation/11822/1) now returns 404; the database was re-ID'd.
- GraphQL POST /api/graphql_pr (introspection off). Page numbers start at 1. Variable shape: {"global":{"events":[88]} or {"years":{"from":2022,"to":2026}}, "ballotQuestions":{"text":"","types":[],"number":"","divisions":[]}, "contests":{"candidates":[],"divisions":[],"offices":[]}, "specialElectionsOnly":false, "voterStats":false, "stages":[]}.
- Events: 88 = 2024 Nov 5 General (165 contests); 8 = 2022 Nov 8 General (139); 87 = 2024 Aug primary; 93 = 2026 Aug 4 primary. No 2026 Nov event yet.
- Contest page /contest/<id>; precinct CSV /api/download_contest/<id>_table.csv?split_party=false. With &vote_channels=all each candidate gets three columns (one per vote channel; a label row precedes). Default CSV has total only. CSV rows: blank row, label row, "County,Macomb" (or "State Legislature District,58"), then "Precinct,<Jurisdiction>, Precinct <n>". Columns: candidates..., Write-In, Total Votes Cast, Overvotes/Undervotes, Total Ballots Cast.
- Source PDFs (2024 general): file 3931 Summary Results (44 pages, 200 KB) and file 3934 Precinct Results (2,914 pages, 11 MB). Raw: https://macombmi.elstats2.civera.com/eng/files/serve/<id>; viewer: /document/<id>?page=<n>.
- 2024 contest ids: Sheriff 11957 (summary page 8; precinct PDF page 4 for the first precinct); HD-58 11815 (summary page 3; precinct PDF from page 844); President 11808; U.S. Senator 12337; Straight Party 12336.
- 2022 general: no source PDF; contest pages link to the legacy static site. Contest ids: County Executive 665, HD-58 685, Governor 760, Straight Party 740. 2022 summary PDF at macombgovdocs elect-2022-11-08-* gives 404.
- Official summary PDFs on macombgovdocs: /clerk/pdfs/elect-<YYYY>-<MM>-<DD>-{unofficial|official}-summary-results.pdf (2024-11-05 official exists, modified 2024-11-20).

### PDF layout (Summary Results Report)
- Page header lines: "Summary Results Report", "November 2024", "Macomb County". Page 1 opens a Statistics block with column header "TOTAL AVCB Election Day Early Voting" (header wraps to two lines: "Election / Day" and "Early / Voting"). Statistics rows: Election Day Precincts Reporting "309 of 310", Precincts Complete, Precincts Partially Reported, Absentee/Early Precincts Reporting, Registered Voters - Total, Ballots Cast - Total (4 numbers), Ballots Cast - Blank, Voter Turnout - Total.
- Each contest: title line (office + jurisdiction), "Vote For N", the column header line, then candidate rows "<PARTY> <Name> <TOTAL> <AVCB> <ED> <EARLY>" (party codes DEM REP LIB UST GRN NLP NPA WCP; some rows lack a party, e.g. "Write-In Totals"), then "Total Votes Cast", "Overvotes", "Undervotes", "Contest Totals". Numbers have thousands commas. Multi-seat contests say "Vote For 2".
- Precinct report: same blocks repeated per precinct, preceded by the precinct name line, footer "Precinct Summary - <date time> Page x of 2914", and a Statistics block without the Precincts Reporting rows. Page header text on the 2024 file reads "11 2022 General Electio" (source typo).
- Parser tip: split on the column-header line, regex candidate rows with `^(?:([A-Z]{3}) )?(.+?) ([\d,]+) ([\d,]+) ([\d,]+) ([\d,]+)$`; handle name wraps.

## 3. Michigan SOS
- Michigan Voting Dashboard https://www.michigan.gov/sos/elections/election-results-and-data/voter-participation-dashboard : two Power BI Gov embeds (app.powerbigov.us). SOS release of 2026-10-13 says it is updated daily until the Monday before Election Day. Early-vote layer only (turnout).
- SOS release https://www.michigan.gov/sos/resources/news/2026/10/13/three-weeks-before-election-day-6-percent-of-voters-have-already-cast-their-ballot (HTML).
- Results: https://www.michigan.gov/sos/elections/election-results-and-data/candidate-listings-and-election-results-by-county links Macomb to the Clerk page and says election-night results are unofficial until certified. mielections.us gave SSL errors from the sandbox; the /election/results/<YYYY>GEN_CENR.html pattern comes from a search snippet only (UNVERIFIED). MVIC votehistory (https://mvic.sos.state.mi.us/votehistory/Index?type=C&electionDate=11-5-2024) returns 403 to scripts.

## 4. 2026 ballot (Clerk's official list, "Last Updated 9/03/2026 8:15 a.m.", https://macombgovdocs.org/clerk/pdfs/elect-2026-11-03-Official-Candidate-List-printable.pdf), cross-checked against the 2026-10-27 results template
Tier 1 names, all VERIFIED: HD-58 Katrina Manetta (D) v Ron Robinson (R, incumbent; won 2024); SD-24 Edlira Sako (D) v Douglas Chester Wozniak (R); MI-10 Christina Bertrand Hines (D) v Michael Bouchard (R); Governor Jocelyn Benson / Winnie Brinks (D) v John James / Jay DeBoyer (R); U.S. Senate Abdul El-Sayed (D) v Mike Rogers (R). Minor-party candidates are in the JSON.
- State Senate in Macomb: 9, 10, 11, 12, 24, 25. Multi-county (per template): 9, 10, 12, 25. Macomb only: 11, 24.
- State House in Macomb: 11, 12, 13, 14, 57, 58, 59, 60, 61, 62, 63, 65, 66 (no 64). Multi-county: 11, 12, 14, 57, 63, 65, 66. Macomb only: 13, 58-62.
- Clerk marks multi-county districts but does not name the other counties; leave other_counties unnamed rather than guessing.
- County Executive: Hackel (D) v Moore (R). County Commission: only District 1 partial term (LaBuhn D v Goike R).
- Statewide proposals: 2026-1 (convene a constitutional convention) and 2026-2 (initiated law on utility/contractor contributions and political-communication disclosure). Countywide: Veterans' millage, Public Transportation millage, Zoological Authority millage. Local: see JSON `local_props`. Source https://macombgovdocs.org/clerk/pdfs/elect-2026-11-03-proposals.pdf .
- Pitfalls: the other file elect-2026-11-03-candidate-list.pdf (UNOFFICIAL, May 29) is pre-primary and lists primary fields (El-Sayed, McMorrow, Stevens). Third-party aggregators (Ballot Brief) were stale or wrong on several districts, e.g. SD-24 geography.

## 5. HD-58 geography
31 precincts in the 2024 contest CSV: Sterling Heights 17 (18, 19, 20, 21, 22, 23, 25, 26, 27, 31, 32, 33, 34, 36, 39, 40, 42), Warren 8 (38, 39, 42, 48, 49, 50, 51, 52), Shelby Twp 5 (4, 6, 9, 10, 21), Utica 1 (precinct 1). "Motown Sound" name not confirmed.

## 6. Election-night plan
- The unofficial summary PDF is overwritten in place: poll Last-Modified/ETag every 5 minutes, archive every fetch with sha256 and timestamp, label UNOFFICIAL. Clarity: test endpoints in a real browser first (sandbox gets 202); if blocked, manual paste.
- On the first populated version, verify columns (the template has no totals, so mode splits are unknown) before building the parser.
- After election night, expect a new event in the Elections Database (not before certification; Aug 2026 primary is already loaded as event 93, so lag is weeks). Use CSV with vote_channels=all for the mode split.
- Respect rate limits: <=1 request/min per host; attribute to Macomb County Clerk; use neutral anomaly wording ("data changed - confirm with the Clerk").
