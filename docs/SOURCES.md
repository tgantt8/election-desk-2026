# Election Desk 2026 - source registry

Generated 2026-10-29T17:07:05Z from the five recon files (polls, ratings, early_vote, national_enr, macomb). Machine file: `sources.json`. All data is UNOFFICIAL until certified; every number the desk shows carries source + timestamp. Nothing voter-file-derived or voter-level is ingested (VAN firewall); layers never cross-write.

## Counts

| layer | total | VERIFIED | VERIFIED_PARTIAL | UNVERIFIED | LINK_ONLY | EXCLUDED |
|---|---|---|---|---|---|---|
| polls | 12 | 0 | 1 | 0 | 7 | 4 |
| ratings | 17 | 0 | 0 | 13 | 3 | 1 |
| early_vote | 24 | 7 | 0 | 7 | 2 | 8 |
| results | 60 | 3 | 26 | 30 | 0 | 1 |
| calls | 11 | 0 | 0 | 0 | 10 | 1 |
| **all** | **124** | **10** | **27** | **50** | **22** | **15** |

## Conventions

- `status`: VERIFIED = fetched and read 2026-10-29; VERIFIED_PARTIAL = a page, file or API answer was fetched but election-night/endpoint behavior is untested; UNVERIFIED = blocked, unreachable or search-only; LINK_ONLY = policy says link, no ingest; EXCLUDED = not found, unlicensed, voter-level or voter-file-derived.
- `machine_readable`: `true` only where a machine payload was actually read; `"unverified"` where recon expects one but did not read it; `false` otherwise.
- `expected_cadence_min` is the pre-election success cadence; for manual, link-only and gated entries it is the intended check interval (1440 = daily) and 0 means never polled (EXCLUDED). `election_night_cadence_min` is null wherever no automated poller exists.
- `poller` values come from the fixed list; `manual` also stands for "automatable but no poller family defined yet" (flagged under Verification gaps). `last_success_at` is null and `last_error` empty until a poller runs.

## Polls (12)

| id | name | status | poller | cadence | terms / decision |
|---|---|---|---|---|---|
| `polls_votehub_api` | VoteHub Polling API (beta) | VERIFIED_PARTIAL | votehub_polls | 30 min | CC BY 4.0 (docs: 'This API is licensed under Creative Commons Attribution 4.0 International'). Attribution: credit VoteHub ... |
| `polls_nyt_siena` | NYT/Siena College polls (nytimes.com) | LINK_ONLY | link_only | 1440 min | Link only. Toplines and crosstab basics entered by hand with link and timestamp; do not copy article analysis text; never scrape behind ... |
| `polls_siena_sri` | Siena Research Institute release pages (sri.siena.edu) | LINK_ONLY | link_only | 1440 min | Link only. Treat as copyrighted: topline and crosstab basics with link, no wholesale PDF mirroring. Terms not located. Attribute 'Siena ... |
| `polls_rcp` | RealClearPolling averages | LINK_ONLY | link_only | 1440 min | Link only (published averages shown beside ours, attributed to RealClearPolling). No scraping; terms not read. Averages are derived output, ... |
| `polls_silver_bulletin` | Silver Bulletin polling averages (Nate Silver) | LINK_ONLY | link_only | 1440 min | Link only. Substack terms apply; some content paid; do not copy analysis text; do not use Datawrapper chart CSVs (terms unread). Attribute ... |
| `polls_ddhq` | Decision Desk HQ polling averages (public pages) | LINK_ONLY | link_only | 1440 min | Public pages: link only. DDHQ polling API (polling-api-docs.decisiondeskhq.com: /reference/polls, /reference/averages) is a gated client ... |
| `polls_nyt_tracker` | NYT polling averages / tracker | LINK_ONLY | link_only | 1440 min | Link only. Derived averages; never copy. Terms not read. |
| `polls_fiftyplusone` | Fifty Plus One polls and averages | LINK_ONLY | link_only | 1440 min | Link only unless licensed. Tiered downloads/API (standard: horse race + approval; premium: crosstabs) are gated products. Attribute 'Fifty ... |
| `polls_538_legacy` | 538 / ABC News poll data (shut down 2025-03-05) | EXCLUDED | none | not polled | Not a 2026 source. ABC shut 538 on 2025-03-05; public polling databases went offline. GitHub fivethirtyeight/data and mirrors are frozen, ... |
| `polls_pollresults_org` | PollResults.org | EXCLUDED | none | not polled | No terms assessable: site and any API not found in search. Do not build against it. **DECISION:** PollResults.org: provide the exact URL if this source was intended; otherwise it stays dropped. |
| `polls_callthemap` | Call the Map (polling data) | EXCLUDED | none | not polled | No terms assessable. JSON URLs cannot be guessed; hotlinking another site's front-end JSON is not an API. **DECISION:** Call the Map: provide the exact URL(s) if this source was intended; otherwise it stays dropped. |
| `polls_onpoint_politics` | On Point Politics polling averages | EXCLUDED | none | not polled | Unknown publisher and methodology. If ever used: link only, averages are derived output and never enter the polls layer. **DECISION:** On Point Politics: provide the exact polling-average URL if this source was intended; otherwise it stays dropped. |

## Ratings (17)

| id | name | status | poller | cadence | terms / decision |
|---|---|---|---|---|---|
| `ratings_cook_senate` | Cook Political Report - Senate race ratings | UNVERIFIED | cook_ratings | 30 min | Label + date + link ONLY; never analysis text (desk rule). Attribute 'Rating: Cook Political Report, [page date]'. Page date means page ... **DECISION:** Cook written permission to display rating labels publicly (Senate/Governor), or fall back to link-only per race. |
| `ratings_cook_house` | Cook Political Report - House race ratings | UNVERIFIED | cook_ratings | 30 min | Label + date + link ONLY; never analysis text (desk rule). Attribute 'Rating: Cook Political Report, [page date]'. Page date means page ... **DECISION:** Cook written permission to display all 435 House labels, or show only Michigan districts and link out for the rest. |
| `ratings_cook_governor` | Cook Political Report - Governor race ratings | UNVERIFIED | cook_ratings | 30 min | Label + date + link ONLY; never analysis text (desk rule). Attribute 'Rating: Cook Political Report, [page date]'. Page date means page ... **DECISION:** Cook written permission to display rating labels publicly (Senate/Governor), or fall back to link-only per race. |
| `ratings_cook_rating_changes` | Cook Political Report - rating-change article listings | LINK_ONLY | link_only | 1440 min | Link only. Article headlines are Cook analysis text; bodies mostly members-only. No public ratings-changes table found. **DECISION:** Confirm whether Cook listing headline + date may be stored as a changelog hint (recommended: no, link only). |
| `ratings_sabato_senate` | Sabato's Crystal Ball - 2026 Senate ratings | UNVERIFIED | manual | 1440 min | Label + date + link only; no analysis text. UVA Center for Politics site terms not read. Attribute 'Sabato's Crystal Ball, [date]'. Never ... |
| `ratings_sabato_house` | Sabato's Crystal Ball - 2026 House ratings | UNVERIFIED | manual | 1440 min | Label + date + link only; no analysis text. UVA Center for Politics site terms not read. Attribute 'Sabato's Crystal Ball, [date]'. Never ... |
| `ratings_sabato_governor` | Sabato's Crystal Ball - 2026 Governor ratings | UNVERIFIED | manual | 1440 min | Label + date + link only; no analysis text. UVA Center for Politics site terms not read. Attribute 'Sabato's Crystal Ball, [date]'. Never ... |
| `ratings_insideelections` | Inside Elections (Nathan Gonzales) - 2026 ratings | UNVERIFIED | manual | 1440 min | Paywalled product. Store labels ONLY if reachable with no login; otherwise link only. Label + date + link; no analysis text; never bypass ... **DECISION:** Confirm Inside Elections labels are publicly reachable (no login) and get permission; otherwise link only. |
| `ratings_votehub_forecast` | VoteHub 2026 midterm forecast (model outputs) | UNVERIFIED | link_only | 1440 min | Model output, NOT a rating: store as model_probability with the 'model outputs' tag; never convert to a rating label. Terms not read. No ... |
| `ratings_silverbulletin_flipr` | Silver Bulletin FLIPR 2026 midterm forecast (model outputs) | UNVERIFIED | link_only | 1440 min | Model output, NOT a rating: store as model_probability with the 'model outputs' tag; never convert to a rating label. Terms not read. No ... |
| `ratings_ddhq_the_hill_forecast` | Decision Desk HQ / The Hill 2026 forecast (model outputs) | UNVERIFIED | link_only | 1440 min | Model output, NOT a rating: store as model_probability with the 'model outputs' tag; never convert to a rating label. Terms not read. No ... |
| `ratings_economist` | The Economist 2026 midterm forecast (model outputs) | UNVERIFIED | link_only | 1440 min | Model output, NOT a rating: store as model_probability with the 'model outputs' tag; never convert to a rating label. Terms not read. No ... |
| `ratings_racetothewh` | Race to the WH 2026 forecast (model outputs) | UNVERIFIED | link_only | 1440 min | Model output, NOT a rating: store as model_probability with the 'model outputs' tag; never convert to a rating label. Terms not read. No ... |
| `ratings_splitticket_argument` | Split Ticket / The Argument 2026 forecast (model outputs) | UNVERIFIED | link_only | 1440 min | Model output, NOT a rating: store as model_probability with the 'model outputs' tag; never convert to a rating label. Terms not read. No ... |
| `ratings_callthemap_forecast` | Call the Map 2026 forecast (model outputs) | EXCLUDED | none | not polled | Terms unknown. Would be labeled 'model outputs' if found. **DECISION:** Call the Map: provide the exact URL(s) if this source was intended; otherwise it stays dropped. |
| `ratings_270towin_crosscheck` | 270toWin consensus and per-rater pages (cross-check only) | LINK_ONLY | manual | 1440 min | Third-party aggregator: manual cross-check only. Never store as rater data. Pages carry 'As of <date>' stamps, often weeks stale. |
| `ratings_wikipedia_crosscheck` | Wikipedia 2026 election pages (cross-check only) | LINK_ONLY | manual | 1440 min | CC BY-SA. Secondary: cross-check only. NEVER store as rater=Wikipedia-aggregated. If scripted: <=1 req/s with descriptive User-Agent. |

## Early vote (24)

| id | name | status | poller | cadence | terms / decision |
|---|---|---|---|---|---|
| `ev_nc_daily_absentee_pdf` | NC State Board of Elections - Daily Absentee Stats Report (2026 General) | VERIFIED | pdf_hash | 1440 min | State public record. Attribute 'North Carolina State Board of Elections' and the report's own 'data updated' timestamp (footer: 'Published ... |
| `ev_nc_absentee_counts_csv` | NCSBE absentee counts (aggregate CSV, 2026 General) | VERIFIED | nc_s3 | 1440 min | Public record. Attribute 'North Carolina State Board of Elections' with Last-Modified. Fetch ONLY the aggregate files ... |
| `ev_nc_absentee_voter_files` | NCSBE voter-level absentee files (absentee_*.zip, absentee_county_*.zip, spoiled/outstanding zips) | EXCLUDED | none | not polled | EXCLUDED by VAN firewall: voter-level records. Never fetched, even to aggregate. The nc_s3 poller must allow-list aggregate files only. **DECISION:** Confirm VAN-firewall rule: voter-level absentee files (NC, GA, ME) are never downloaded, even to aggregate ... |
| `ev_fl_publicstats` | Florida Division of Elections - County Vote-by-Mail and Early Voting Reports (PublicStats) | VERIFIED | manual | 360 min | State public record. Attribute 'Florida Department of State, Division of Elections' with the page's 'Compiled' timestamp (source_as_of). ... |
| `ev_mi_sos_dashboard` | Michigan Voting Dashboard (Dept. of State, Bureau of Elections) | VERIFIED | manual | 720 min | State of Michigan page. Attribute 'Michigan Department of State, Bureau of Elections, Michigan Voting Dashboard' with capture time. Counts ... **DECISION:** Who captures the dashboard 2x/day, or ask [contact address on source site] for a data feed? (recommended: manual capture now, ... |
| `ev_mi_sos_news_releases` | Michigan Dept. of State news releases (early / absentee return tables) | VERIFIED | manual | 60 min | State publication. Attribute 'Michigan Department of State news release, <date>' (releases state a 7 a.m. as-of time). Statewide aggregates ... |
| `ev_mi_sos_2022_baseline_xlsx` | Michigan Dept. of State 2022 general mail-ballot stats by jurisdiction (same-point baseline snapshots) | VERIFIED | manual | not polled | State publication. Attribute 'Michigan Department of State news release' + date. Aggregates only. NOTE: actual files are XLSX (not in the ... |
| `ev_ufl_election_lab` | University of Florida Election Lab - 2026 Early Voting (Michael McDonald) | VERIFIED | none | 30 min | CC BY-NC-ND 4.0: reasonable attribution mandatory ('University of Florida Election Lab' / Michael McDonald, plus the row's last_update); no ... **DECISION:** UF CC BY-NC-ND license ruling: is a campaign policy-shop dashboard 'non-commercial', and is normalizing a derivative? ... |
| `ev_votehub_cdn_tracker` | VoteHub 2026 Midterm Early Vote Tracker (static JSON on cdn.votehub.com, built with L2) | LINK_ONLY | link_only | 1440 min | LINK ONLY. votehub.com/terms (updated 2025-12-05) is a website-use license that bars redistribution, commercial exploitation and derivative ... **DECISION:** Ask VoteHub for written permission to read cdn.votehub.com/early-vote-tracker/*.json (aggregate counts only), or stay ... |
| `ev_nbc_early_vote` | NBC News - Tracking the 2026 Early Vote | LINK_ONLY | link_only | 1440 min | Link only. Copyrighted; link + attribution. Footnote: national total aggregates 'daily state totals sourced from TargetSmart and state ... |
| `ev_targetearly` | TargetSmart TargetEarly (2026) | EXCLUDED | none | not polled | EXCLUDED: client-only (MyTargetSmart 'Request Access'), voter-file-derived (VAN firewall). TargetSmart all rights reserved. |
| `ev_ddhq_newsnation` | Decision Desk HQ / NewsNation early-voting pages | EXCLUDED | none | not polled | Commercial vendor; its data API is a paid product. Link only if a general-election page appears. |
| `ev_onpoint_tracker` | OnPoint Politics 2026 Early Vote Tracker | EXCLUDED | none | not polled | Do not use: unknown publisher, no methodology seen. |
| `ev_pollcheck_tracker` | PollCheck (UK) US midterms early-voting page | EXCLUDED | none | not polled | Do not use: secondary re-publisher of state numbers. |
| `ev_ga_data_hub` | Georgia SOS Election Data Hub - unofficial turnout (absentee, early, total) | UNVERIFIED | link_only | 1440 min | State public record; attribute the agency and the source's own timestamp. Who voted, not how they voted: aggregate turnout counts only; any ... |
| `ev_ga_voter_absentee_file` | Georgia voter-level absentee file (mvp.sos.ga.gov) | EXCLUDED | none | not polled | EXCLUDED by VAN firewall: voter-level absentee file. Never fetched, even to aggregate. **DECISION:** Confirm VAN-firewall rule: voter-level absentee files (NC, GA, ME) are never downloaded, even to aggregate ... |
| `ev_me_absentee_voter_file` | Maine SOS Statewide Absentee Voter Data File | EXCLUDED | none | not polled | EXCLUDED by VAN firewall: record-level (voter-level) file; free per state law but never fetched, even to aggregate. Use the UF ME row as a ... **DECISION:** Confirm VAN-firewall rule: voter-level absentee files (NC, GA, ME) are never downloaded, even to aggregate ... |
| `ev_nh_sos_voter_lookup` | New Hampshire SOS absentee voter lookup (per-voter) | EXCLUDED | none | not polled | EXCLUDED: interactive per-voter lookup (voter-level, personal data). No aggregate page found. |
| `ev_oh_sos_dashboard` | Ohio SOS - Data Analytics and Archives dashboard and county absentee reports | UNVERIFIED | link_only | 1440 min | State public record; attribute the agency and the source's own timestamp. Who voted, not how they voted: aggregate turnout counts only; any ... |
| `ev_tx_sos_ivis_evr` | Texas SOS Early Voting Results (IVIS EVR) | UNVERIFIED | manual | 1440 min | State public record; attribute the agency and the source's own timestamp. Who voted, not how they voted: aggregate turnout counts only; any ... |
| `ev_ia_sos_absentee` | Iowa SOS - Absentee ballot statistics | UNVERIFIED | link_only | 1440 min | State public record; attribute the agency and the source's own timestamp. Who voted, not how they voted: aggregate turnout counts only; any ... |
| `ev_ak_doe` | Alaska Division of Elections - absentee / early-vote reports | UNVERIFIED | link_only | 1440 min | State public record; attribute the agency and the source's own timestamp. Who voted, not how they voted: aggregate turnout counts only; any ... |
| `ev_ne_sos` | Nebraska SOS - Elections Division (early voting) | UNVERIFIED | link_only | 1440 min | State public record; attribute the agency and the source's own timestamp. Who voted, not how they voted: aggregate turnout counts only; any ... |
| `ev_mn_sos_absentee` | Minnesota SOS - Absentee Data (ballots sent / accepted) | UNVERIFIED | link_only | 1440 min | State public record; attribute the agency and the source's own timestamp. Who voted, not how they voted: aggregate turnout counts only; any ... |

## Results (national ENR + Macomb) (60)

| id | name | status | poller | cadence | terms / decision |
|---|---|---|---|---|---|
| `enr_ga_ev` | Georgia - election-night results | VERIFIED_PARTIAL | enhanced_voting | 60 min (night 2 min) | Public record of Georgia Secretary of State; attribute 'Georgia Secretary of State, unofficial results, as of <asOf>' (store publisher ... |
| `enr_nc_dashboard` | North Carolina - state results dashboard (NC SBE) | VERIFIED_PARTIAL | link_only | 1440 min | Public record of North Carolina State Board of Elections; attribute 'North Carolina State Board of Elections, unofficial results, as of ... |
| `enr_mi_sos` | Michigan - county results links (Michigan SOS) | VERIFIED_PARTIAL | link_only | 1440 min | Public record of Michigan Department of State and county clerks; attribute 'Michigan Department of State and county clerks, unofficial ... |
| `enr_me_sos` | Maine - election-night results | UNVERIFIED | manual | 1440 min | Public record of Maine Department of the Secretary of State; attribute 'Maine Department of the Secretary of State, unofficial results, as ... |
| `enr_oh_sos` | Ohio - election-night results | UNVERIFIED | manual | 1440 min | Public record of Ohio Secretary of State; attribute 'Ohio Secretary of State, unofficial results, as of <timestamp>'. UNOFFICIAL until ... |
| `enr_tx_sos` | Texas - election-night results | VERIFIED_PARTIAL | manual | 1440 min | Public record of Texas Secretary of State; attribute 'Texas Secretary of State, unofficial results, as of <timestamp>'. UNOFFICIAL until ... |
| `enr_ia_clarity` | Iowa - election-night results | UNVERIFIED | clarity | 60 min (night 3 min) | Public record of Iowa Secretary of State; attribute 'Iowa Secretary of State, unofficial results, as of <timestamp>'. UNOFFICIAL until ... |
| `enr_ak_sos` | Alaska - election-night results | UNVERIFIED | manual | 1440 min | Public record of Alaska Division of Elections; attribute 'Alaska Division of Elections, unofficial results, as of <timestamp>'. UNOFFICIAL ... |
| `enr_ne_sos` | Nebraska - election-night results | VERIFIED_PARTIAL | manual | 1440 min | Public record of Nebraska Secretary of State; attribute 'Nebraska Secretary of State, unofficial results, as of <timestamp>'. UNOFFICIAL ... |
| `enr_nh_sos` | New Hampshire - election-night results | UNVERIFIED | manual | 1440 min | Public record of New Hampshire Secretary of State; attribute 'New Hampshire Secretary of State, unofficial results, as of <timestamp>'. ... |
| `enr_mn_sos` | Minnesota - election-night results | UNVERIFIED | manual | 1440 min | Public record of Minnesota Secretary of State; attribute 'Minnesota Secretary of State, unofficial results, as of <timestamp>'. UNOFFICIAL ... |
| `enr_fl_sos` | Florida - election-night results | VERIFIED_PARTIAL | manual | 1440 min | Public record of Florida Division of Elections; attribute 'Florida Division of Elections, unofficial results, as of <timestamp>'. ... |
| `enr_ks_sos` | Kansas - election-night results | UNVERIFIED | manual | 1440 min | Public record of Kansas Secretary of State; attribute 'Kansas Secretary of State, unofficial results, as of <timestamp>'. UNOFFICIAL until ... |
| `enr_ky_sos` | Kentucky - election-night results | UNVERIFIED | manual | 1440 min | Public record of Kentucky State Board of Elections; attribute 'Kentucky State Board of Elections, unofficial results, as of <timestamp>'. ... |
| `enr_sc_clarity` | South Carolina - election-night results | UNVERIFIED | clarity | 60 min (night 3 min) | Public record of South Carolina Election Commission; attribute 'South Carolina Election Commission, unofficial results, as of <timestamp>'. ... |
| `enr_ok_sos` | Oklahoma - election-night results | VERIFIED_PARTIAL | manual | 1440 min | Public record of Oklahoma State Election Board; attribute 'Oklahoma State Election Board, unofficial results, as of <timestamp>'. ... |
| `enr_la_sos` | Louisiana - election-night results | VERIFIED_PARTIAL | manual | 1440 min | Public record of Louisiana Secretary of State; attribute 'Louisiana Secretary of State, unofficial results, as of <timestamp>'. UNOFFICIAL ... |
| `enr_al_sos` | Alabama - election-night results | UNVERIFIED | manual | 1440 min | Public record of Alabama Secretary of State; attribute 'Alabama Secretary of State, unofficial results, as of <timestamp>'. UNOFFICIAL ... |
| `enr_ar_sos` | Arkansas - election-night results | UNVERIFIED | manual | 1440 min | Public record of Arkansas Secretary of State; attribute 'Arkansas Secretary of State, unofficial results, as of <timestamp>'. UNOFFICIAL ... |
| `enr_co_clarity` | Colorado - election-night results | UNVERIFIED | clarity | 60 min (night 3 min) | Public record of Colorado Secretary of State; attribute 'Colorado Secretary of State, unofficial results, as of <timestamp>'. UNOFFICIAL ... |
| `enr_de_sos` | Delaware - election-night results | UNVERIFIED | manual | 1440 min | Public record of Delaware Department of Elections; attribute 'Delaware Department of Elections, unofficial results, as of <timestamp>'. ... |
| `enr_id_ev` | Idaho - election-night results | VERIFIED_PARTIAL | enhanced_voting | 60 min (night 2 min) | Public record of Idaho Secretary of State; attribute 'Idaho Secretary of State, unofficial results, as of <asOf>' (store publisher ... |
| `enr_il_sos` | Illinois - election-night results | UNVERIFIED | manual | 1440 min | Public record of Illinois State Board of Elections; attribute 'Illinois State Board of Elections, unofficial results, as of <timestamp>'. ... |
| `enr_ma_sos` | Massachusetts - election-night results | VERIFIED_PARTIAL | manual | 1440 min | Public record of Massachusetts Secretary of the Commonwealth; attribute 'Massachusetts Secretary of the Commonwealth, unofficial results, ... |
| `enr_ms_sos` | Mississippi - election-night results | UNVERIFIED | manual | 1440 min | Public record of Mississippi Secretary of State; attribute 'Mississippi Secretary of State, unofficial results, as of <timestamp>'. ... |
| `enr_mt_sos` | Montana - election-night results | UNVERIFIED | manual | 1440 min | Public record of Montana Secretary of State; attribute 'Montana Secretary of State, unofficial results, as of <timestamp>'. UNOFFICIAL ... |
| `enr_nj_sos` | New Jersey - election-night results | UNVERIFIED | manual | 1440 min | Public record of New Jersey Division of Elections; attribute 'New Jersey Division of Elections, unofficial results, as of <timestamp>'. ... |
| `enr_nm_sos` | New Mexico - election-night results | VERIFIED_PARTIAL | manual | 1440 min | Public record of New Mexico Secretary of State; attribute 'New Mexico Secretary of State, unofficial results, as of <timestamp>'. ... |
| `enr_or_sos` | Oregon - election-night results | UNVERIFIED | manual | 1440 min | Public record of Oregon Secretary of State; attribute 'Oregon Secretary of State, unofficial results, as of <timestamp>'. UNOFFICIAL until ... |
| `enr_ri_sos` | Rhode Island - election-night results | UNVERIFIED | manual | 1440 min | Public record of Rhode Island Board of Elections; attribute 'Rhode Island Board of Elections, unofficial results, as of <timestamp>'. ... |
| `enr_sd_sos` | South Dakota - election-night results | VERIFIED_PARTIAL | manual | 1440 min | Public record of South Dakota Secretary of State; attribute 'South Dakota Secretary of State, unofficial results, as of <timestamp>'. ... |
| `enr_tn_sos` | Tennessee - election-night results | UNVERIFIED | manual | 1440 min | Public record of Tennessee Secretary of State; attribute 'Tennessee Secretary of State, unofficial results, as of <timestamp>'. UNOFFICIAL ... |
| `enr_va_ev` | Virginia - election-night results | VERIFIED_PARTIAL | enhanced_voting | 60 min (night 2 min) | Public record of Virginia Department of Elections; attribute 'Virginia Department of Elections, unofficial results, as of <asOf>' (store ... |
| `enr_wv_sos` | West Virginia - election-night results | UNVERIFIED | manual | 1440 min | Public record of West Virginia Secretary of State; attribute 'West Virginia Secretary of State, unofficial results, as of <timestamp>'. ... |
| `enr_wy_sos` | Wyoming - election-night results | UNVERIFIED | manual | 1440 min | Public record of Wyoming Secretary of State; attribute 'Wyoming Secretary of State, unofficial results, as of <timestamp>'. UNOFFICIAL ... |
| `enr_az_sos` | Arizona - election-night results | UNVERIFIED | manual | 1440 min | Public record of Arizona Secretary of State; attribute 'Arizona Secretary of State, unofficial results, as of <timestamp>'. UNOFFICIAL ... |
| `enr_ca_sos` | California - election-night results | UNVERIFIED | manual | 1440 min | Public record of California Secretary of State; attribute 'California Secretary of State, unofficial results, as of <timestamp>'. ... |
| `enr_ct_sos` | Connecticut - election-night results | VERIFIED_PARTIAL | manual | 1440 min | Public record of Connecticut Secretary of the State; attribute 'Connecticut Secretary of the State, unofficial results, as of <timestamp>'. ... |
| `enr_dc_sos` | District of Columbia - election-night results | VERIFIED_PARTIAL | manual | 1440 min | Public record of DC Board of Elections; attribute 'DC Board of Elections, unofficial results, as of <timestamp>'. UNOFFICIAL until ... |
| `enr_hi_sos` | Hawaii - election-night results | UNVERIFIED | manual | 1440 min | Public record of Hawaii Office of Elections; attribute 'Hawaii Office of Elections, unofficial results, as of <timestamp>'. UNOFFICIAL ... |
| `enr_in_sos` | Indiana - election-night results | VERIFIED_PARTIAL | manual | 1440 min | Public record of Indiana Secretary of State; attribute 'Indiana Secretary of State, unofficial results, as of <timestamp>'. UNOFFICIAL ... |
| `enr_md_sos` | Maryland - election-night results | VERIFIED_PARTIAL | manual | 1440 min | Public record of Maryland State Board of Elections; attribute 'Maryland State Board of Elections, unofficial results, as of <timestamp>'. ... |
| `enr_mo_sos` | Missouri - election-night results | UNVERIFIED | manual | 1440 min | Public record of Missouri Secretary of State; attribute 'Missouri Secretary of State, unofficial results, as of <timestamp>'. UNOFFICIAL ... |
| `enr_nv_sos` | Nevada - election-night results | UNVERIFIED | manual | 1440 min | Public record of Nevada Secretary of State; attribute 'Nevada Secretary of State, unofficial results, as of <timestamp>'. UNOFFICIAL until ... |
| `enr_ny_sos` | New York - election-night results | UNVERIFIED | manual | 1440 min | Public record of New York State Board of Elections; attribute 'New York State Board of Elections, unofficial results, as of <timestamp>'. ... |
| `enr_nd_sos` | North Dakota - election-night results | VERIFIED_PARTIAL | manual | 1440 min | Public record of North Dakota Secretary of State; attribute 'North Dakota Secretary of State, unofficial results, as of <timestamp>'. ... |
| `enr_pa_sos` | Pennsylvania - election-night results | VERIFIED_PARTIAL | manual | 1440 min | Public record of Pennsylvania Department of State; attribute 'Pennsylvania Department of State, unofficial results, as of <timestamp>'. ... |
| `enr_ut_ev` | Utah - election-night results | VERIFIED_PARTIAL | enhanced_voting | 60 min (night 2 min) | Public record of Utah Lieutenant Governor's Office; attribute 'Utah Lieutenant Governor's Office, unofficial results, as of <asOf>' (store ... |
| `enr_vt_sos` | Vermont - election-night results | VERIFIED_PARTIAL | manual | 1440 min | Public record of Vermont Secretary of State; attribute 'Vermont Secretary of State, unofficial results, as of <timestamp>'. UNOFFICIAL ... |
| `enr_wa_ev` | Washington - election-night results | VERIFIED_PARTIAL | enhanced_voting | 60 min (night 2 min) | Public record of Washington Secretary of State; attribute 'Washington Secretary of State, unofficial results, as of <asOf>' (store ... |
| `enr_wi_sos` | Wisconsin - election-night results | UNVERIFIED | manual | 1440 min | Public record of Wisconsin Elections Commission (counties report); attribute 'Wisconsin Elections Commission (counties report), unofficial ... |
| `enr_nc_s3_results` | North Carolina SBE ENR bulk results (S3: results_pct_20261103.zip) | VERIFIED_PARTIAL | nc_s3 | 60 min (night 2 min) | Public record of the North Carolina State Board of Elections; attribute 'NC State Board of Elections, unofficial results, Last-Modified ... |
| `enr_mi_cenr_mielections` | Michigan statewide County Election Night Reporting (mielections.us CENR) | UNVERIFIED | link_only | 1440 min | Statewide totals appear only after all counties report; unofficial until certified by county/state boards of canvassers. Attribute ... |
| `macomb_clarity_enr` | Macomb 'Unofficial Detailed Election Results' (Clarity ENR) | VERIFIED_PARTIAL | clarity | 1440 min (night 3 min) | Attribute 'Macomb County Clerk/Register of Deeds, unofficial results, as of <timestamp>'. UNOFFICIAL until certified. Macomb-only totals ... |
| `macomb_clerk_unofficial_summary_pdf` | Macomb Clerk election-night UNOFFICIAL summary results (3-page PDF) | VERIFIED_PARTIAL | pdf_hash | 1440 min (night 5 min) | Attribute 'Macomb County Clerk/Register of Deeds, unofficial results, as of <timestamp>' (Last-Modified). UNOFFICIAL until certified. ... |
| `macomb_past_elections_db` | Macomb County Elections Database / Ballot Verifier (pastelections.macombgov.org, Civera ElectionStats) | VERIFIED | manual | 1440 min | Attribute 'Macomb County Clerk/Register of Deeds'. Terms unread. Baseline/archive only (elections added weeks after certification). OUT OF ... |
| `macomb_legacy_static_html` | Macomb Clerk legacy static election-results site (macombgovdocs.org) | VERIFIED_PARTIAL | none | 1440 min | Attribute 'Macomb County Clerk/Register of Deeds'. Footer: this website reports Macomb County results only. Terms unread. HTML tables only ... |
| `macomb_candidate_list_pdf` | Macomb Clerk OFFICIAL candidate list, Nov 3 2026 (PDF) | VERIFIED | pdf_hash | 1440 min | Public record. Store names and party only; DO NOT store candidate addresses or contact data. Header 'Last Updated 9/03/2026 8:15 a.m.'; ... |
| `macomb_clerk_elections_page` | Macomb Clerk - Elections page (links to Clarity ENR and unofficial summary PDF) | VERIFIED | manual | 1440 min | Attribute 'Macomb County Clerk/Register of Deeds'. Do NOT follow or store the per-voter 'Track Your Absent Voter Ballot' link (voter-level, ... |
| `macomb_electionresults_host` | electionresults.macombgov.org (legacy live-results host) | EXCLUDED | none | not polled | No terms assessable: host not serving to the probe. |

## Calls (11)

| id | name | status | poller | cadence | terms / decision |
|---|---|---|---|---|---|
| `calls_ap_results_hub` | AP 2026 midterm results hub (apnews.com) | LINK_ONLY | manual | 1440 min | Calls enter the calls layer by MANUAL ENTRY only: one append-only row per outlet call (outlet, basis, called_for, called_at_et as ... |
| `calls_ap_elections_api` | AP Elections API (licensed data feed) | EXCLUDED | none | not polled | Licensed product: not scraped, not used without a contract; if licensed later, ingest as basis=AP API under the contract's terms. **DECISION:** License the AP Elections API (or DDHQ API) for post-Nov 3 use? (recommended: not before Nov 3; manual entry for now) |
| `calls_npr` | NPR election results (AP calls republished) | LINK_ONLY | manual | 1440 min | Calls enter the calls layer by MANUAL ENTRY only: one append-only row per outlet call (outlet, basis, called_for, called_at_et as ... |
| `calls_pbs` | PBS NewsHour election results (AP calls republished) | LINK_ONLY | manual | 1440 min | Calls enter the calls layer by MANUAL ENTRY only: one append-only row per outlet call (outlet, basis, called_for, called_at_et as ... |
| `calls_mi_local_ap_members` | Michigan local AP-member newsrooms (Detroit Free Press, MLive, Detroit News, Bridge Michigan, Michigan Public, WXYZ/WDIV/WOOD) | LINK_ONLY | manual | 1440 min | Calls enter the calls layer by MANUAL ENTRY only: one append-only row per outlet call (outlet, basis, called_for, called_at_et as ... |
| `calls_nbc` | NBC News / MSNBC decision desk (Edison data) | LINK_ONLY | manual | 1440 min | Calls enter the calls layer by MANUAL ENTRY only: one append-only row per outlet call (outlet, basis, called_for, called_at_et as ... |
| `calls_cbs` | CBS News decision desk (Edison data) | LINK_ONLY | manual | 1440 min | Calls enter the calls layer by MANUAL ENTRY only: one append-only row per outlet call (outlet, basis, called_for, called_at_et as ... |
| `calls_abc` | ABC News decision desk (Edison data) | LINK_ONLY | manual | 1440 min | Calls enter the calls layer by MANUAL ENTRY only: one append-only row per outlet call (outlet, basis, called_for, called_at_et as ... |
| `calls_cnn` | CNN decision desk (Edison data) | LINK_ONLY | manual | 1440 min | Calls enter the calls layer by MANUAL ENTRY only: one append-only row per outlet call (outlet, basis, called_for, called_at_et as ... |
| `calls_fox` | Fox News Decision Desk (AP-independent) | LINK_ONLY | manual | 1440 min | Calls enter the calls layer by MANUAL ENTRY only: one append-only row per outlet call (outlet, basis, called_for, called_at_et as ... |
| `calls_ddhq_hill_newsnation` | Decision Desk HQ calls (also on The Hill and NewsNation) | LINK_ONLY | manual | 1440 min | Calls enter the calls layer by MANUAL ENTRY only: one append-only row per outlet call (outlet, basis, called_for, called_at_et as ... |

## Decisions needed from Tabu

1. PollResults.org: provide the exact URL if this source was intended; otherwise it stays dropped.  
   Sources: `polls_pollresults_org`
2. Call the Map: provide the exact URL(s) if this source was intended; otherwise it stays dropped.  
   Sources: `polls_callthemap`, `ratings_callthemap_forecast`
3. On Point Politics: provide the exact polling-average URL if this source was intended; otherwise it stays dropped.  
   Sources: `polls_onpoint_politics`
4. Cook written permission to display rating labels publicly (Senate/Governor), or fall back to link-only per race.  
   Sources: `ratings_cook_senate`, `ratings_cook_governor`
5. Cook written permission to display all 435 House labels, or show only Michigan districts and link out for the rest.  
   Sources: `ratings_cook_house`
6. Confirm whether Cook listing headline + date may be stored as a changelog hint (recommended: no, link only).  
   Sources: `ratings_cook_rating_changes`
7. Confirm Inside Elections labels are publicly reachable (no login) and get permission; otherwise link only.  
   Sources: `ratings_insideelections`
8. Confirm VAN-firewall rule: voter-level absentee files (NC, GA, ME) are never downloaded, even to aggregate (recommended: yes).  
   Sources: `ev_nc_absentee_voter_files`, `ev_ga_voter_absentee_file`, `ev_me_absentee_voter_file`
9. Who captures the dashboard 2x/day, or ask [contact address on source site] for a data feed? (recommended: manual capture now, request feed)  
   Sources: `ev_mi_sos_dashboard`
10. UF CC BY-NC-ND license ruling: is a campaign policy-shop dashboard 'non-commercial', and is normalizing a derivative? Contact [contact address on source site] (recommended: ask in writing; link only until answered).  
   Sources: `ev_ufl_election_lab`
11. Ask VoteHub for written permission to read cdn.votehub.com/early-vote-tracker/*.json (aggregate counts only), or stay link-only (recommended: link only).  
   Sources: `ev_votehub_cdn_tracker`
12. License the AP Elections API (or DDHQ API) for post-Nov 3 use? (recommended: not before Nov 3; manual entry for now)  
   Sources: `calls_ap_elections_api`

## Verification gaps

Every UNVERIFIED entry, with the reason:

**Ratings** (13)

- `ratings_cook_senate`: Not fetched (recon WebFetch DNS-blocked; page structure from search snippets). Parse target is the print variant /print/ratings/races/<chamber> (page-level date, grouped lists); validate parsed counts against the page's chamber tallies. robots.txt unread. ...
- `ratings_cook_house`: Not fetched (recon WebFetch DNS-blocked; page structure from search snippets). Parse target is the print variant /print/ratings/races/<chamber> (page-level date, grouped lists); validate parsed counts against the page's chamber tallies. robots.txt unread. ...
- `ratings_cook_governor`: Not fetched (recon WebFetch DNS-blocked; page structure from search snippets). Parse target is the print variant /print/ratings/races/<chamber> (page-level date, grouped lists); validate parsed counts against the page's chamber tallies. robots.txt unread. ...
- `ratings_sabato_senate`: Not fetched (DNS-blocked). Senate category URL seen in search; Free-to-read assumed, not confirmed. No poller family defined for Sabato, so entries are manual (low-frequency, daily).
- `ratings_sabato_house`: Not fetched (DNS-blocked). Senate category URL seen in search; House/Governor URLs are pattern guesses. Free-to-read assumed, not confirmed. No poller family defined for Sabato, so entries are manual (low-frequency, daily).
- `ratings_sabato_governor`: Not fetched (DNS-blocked). Senate category URL seen in search; House/Governor URLs are pattern guesses. Free-to-read assumed, not confirmed. No poller family defined for Sabato, so entries are manual (low-frequency, daily).
- `ratings_insideelections`: Not fetched. Unknown whether per-label category pages list races publicly; Tilt labels map lossy to the 7-point scale (keep label_raw).
- `ratings_votehub_forecast`: Not fetched. No documented data endpoint found; link card only until an endpoint is confirmed (then hourly).
- `ratings_silverbulletin_flipr`: Not fetched. No documented data endpoint found; link card only until an endpoint is confirmed (then hourly).
- `ratings_ddhq_the_hill_forecast`: Not fetched. No documented data endpoint found; link card only until an endpoint is confirmed (then hourly).
- `ratings_economist`: Not fetched. No documented data endpoint found; link card only until an endpoint is confirmed (then hourly).
- `ratings_racetothewh`: Not fetched. No documented data endpoint found; link card only until an endpoint is confirmed (then hourly).
- `ratings_splitticket_argument`: Not fetched. No documented data endpoint found; link card only until an endpoint is confirmed (then hourly).

**Early vote** (7)

- `ev_ga_data_hub`: Cloudflare 403 challenge on sos.ga.gov and mvp.sos.ga.gov from the workbench; not readable programmatically. Recon URL differed slightly (election-data-hub-turnout vs -unofficial-turnout); the UF-cited path is used. Consume via UF GA_county.csv only if UF ...
- `ev_oh_sos_dashboard`: 403 (WAF / 'Website Maintenance' interstitial) from the workbench; named as OH source by UF. Ohio's new receipt-by-Election-Day rule limits comparability to 2022.
- `ev_tx_sos_ivis_evr`: SPA shell 200 (18 KB, 'Early Voting Results'); underlying JSON API not inspected; sos.texas.gov returns 403 (WAF). Needs a networked-browser pass.
- `ev_ia_sos_absentee`: Cloudflare 403 challenge; Vivid JSON URLs not located (need a browser to find). UF IA row is the practical secondary.
- `ev_ak_doe`: TLS certificate verification failed from the workbench; exact report page unknown; UF AK row has no party columns.
- `ev_ne_sos`: No public SOS early-vote page located; UF NE row says 'Data file provided by Nebraska Secretary of State' (not a public URL). Not fetched.
- `ev_mn_sos_absentee`: Page 200 but Radware bot CAPTCHA served; format unconfirmed; UF MN row last updated 10/23. Not readable programmatically.

**Results (national ENR + Macomb)** (30)

- `enr_me_sos`: Static pages; the old results path redirects to /sos/elections-voting/election-results-data (200); no live feed identified; RCV tabulation days later; media rely on AP.
- `enr_oh_sos`: liveresults.ohiosos.gov and ohiosos.gov returned 403 'Website Maintenance'; unofficial results said (search) to be at VoteOhio.gov, not corroborated. URL is that unconfirmed pointer.
- `enr_ia_clarity`: electionresults.iowa.gov returned HTTP 202 empty body (WAF challenge); Clarity-style path inferred only.
- `enr_ak_sos`: elections.alaska.gov did not connect from the probe; path pattern from memory only. Polls close 00:00 ET Nov 4. URL is a state elections landing page / pattern, not a recon-verified results host.
- `enr_nh_sos`: sos.nh.gov returned 403 Access Denied to the probe; no feed identified; media rely on AP. URL is a state elections landing page / pattern, not a recon-verified results host.
- `enr_mn_sos`: electionresults.sos.mn.gov / sos.mn.gov served a Radware captcha; CSV download links unverified.
- `enr_ks_sos`: sos.ks.gov election-results page 200; live ENR host not identified.
- `enr_ky_sos`: elect.ky.gov reachable; results host not identified (results.sos.ky.gov and electionresults.ky.gov did not connect).
- `enr_sc_clarity`: enr-scvotes.org returned HTTP 202 empty body (WAF challenge); Clarity path inferred.
- `enr_al_sos`: Host and vendor not identified; alabamavotes.gov did not connect. URL is a state elections landing page / pattern, not a recon-verified results host.
- `enr_ar_sos`: results.arkansas.gov did not connect; results.enr.clarityelections.com/AR/ returned 202 (WAF); vendor not confirmed, so manual. URL is a state elections landing page / pattern, not a recon-verified results host.
- `enr_co_clarity`: Clarity host returns 202 empty body (AWS WAF) to plain clients from the probe; JSON not fetchable. All-mail. URL is a state elections landing page / pattern, not a recon-verified results host.
- `enr_de_sos`: results.elections.delaware.gov did not connect; elections.delaware.gov reachable; vendor unverified.
- `enr_il_sos`: Host not identified. Cook County reports separately (Chicago BOE + suburban Cook clerk). URL is a state elections landing page / pattern, not a recon-verified results host.
- `enr_ms_sos`: Host and vendor not identified; not fetched. URL is a state elections landing page / pattern, not a recon-verified results host.
- `enr_mt_sos`: sosmt.gov returned 403 Cloudflare challenge. URL is a state elections landing page / pattern, not a recon-verified results host.
- `enr_nj_sos`: County clerks report first; vendor unverified. URL is a state elections landing page / pattern, not a recon-verified results host.
- `enr_or_sos`: All-mail; counts continue for days; CSV export expected, unverified. URL is a state elections landing page / pattern, not a recon-verified results host.
- `enr_ri_sos`: Static HTML expected; not fetched. URL is a state elections landing page / pattern, not a recon-verified results host.
- `enr_tn_sos`: Host and vendor not identified; not fetched. URL is a state elections landing page / pattern, not a recon-verified results host.
- `enr_wv_sos`: Host and vendor not identified; not fetched. URL is a state elections landing page / pattern, not a recon-verified results host.
- `enr_wy_sos`: ElectionStats-style archive suspected; host not identified; not fetched. URL is a state elections landing page / pattern, not a recon-verified results host.
- `enr_az_sos`: results.arizona.vote returned 403 Cloudflare challenge.
- `enr_ca_sos`: State ENR believed JSON-backed but unverified; county feeds vary; very slow count (weeks); SOS posts unprocessed-ballot counts. URL is a state elections landing page / pattern, not a recon-verified results host.
- `enr_hi_sos`: Printouts / ENR; polls close 7 pm HST (00:00 ET Nov 4); vendor unverified. URL is a state elections landing page / pattern, not a recon-verified results host.
- `enr_mo_sos`: enrpages.sos.mo.gov did not connect; s1.sos.mo.gov/elections/results/ reachable (200).
- `enr_nv_sos`: Vendor unverified; mail ballots accepted for days after. URL is a state elections landing page / pattern, not a recon-verified results host.
- `enr_ny_sos`: nyenr.elections.ny.gov returned 403 Cloudflare challenge.
- `enr_wi_sos`: elections.wi.gov 403 Cloudflare; WEC runs no statewide ENR - counties report; media rely on AP.
- `enr_mi_cenr_mielections`: mielections.us timed out / SSL errors from the probe; CENR page pattern comes from a search snippet and a 2016 link on the SOS page. Historical state results at mvic.sos.state.mi.us/votehistory return 403 to scripts.

Cross-cutting gaps (not tied to one UNVERIFIED row):

- No Clarity endpoint (CO, IA, SC, Macomb) has been read: every request from the recon sandbox got HTTP 202 with an empty body (WAF challenge). Test current_ver.txt and json/en/summary.json from the production network before Nov 3; if challenged, use the manual path (no evasion).
- TX, NE, NM, SD, ND and PA expose JSON services but no poller in the fixed list covers them (TX 2026 election not yet configured; NE-family method list and PA route names unconfirmed). They are `manual` until a poller family is defined.
- FL PublicStats, MI news releases and Sabato/Inside Elections pages are automatable but have no poller family in the list; they are `manual`.
- Michigan per-county ENR sources are not yet in the registry: 13 Enhanced Voting counties already have Nov 3 entries (Clare, Delta, Gratiot, Ingham, Isabella, Lake, Midland, Newaygo, Osceola, Saginaw, Shiawassee, St. Joseph, Van Buren), Cass and Leelanau do not yet, Clarity counties are WAF-blocked, and Wayne/Washtenaw/Ottawa/Kalamazoo were not identified. Only Macomb has entries.
- State landing-page URLs for AL, AK, AR, CA, CO, CT, HI, IL, MS, MT, NH, NJ, NV, OH, OR, RI, TN, WV, WY are general-knowledge pages or patterns, not recon-verified results hosts; confirm before use.
- Cook terms and robots.txt were never read, and no ratings page (Cook, Sabato, Inside Elections, forecasts) has been fetched; parse targets come from search snippets.
- polls_votehub_api: only /polls and /polls/{poll_id} are confirmed live; field names, date/limit parameters and the exact attribution object were not read in a response by the polls recon.
- Pollster-grade sources (Silver Bulletin ratings, VoteHub Pollster Scorecards, 538 legacy) were in the polls recon but are not registered here: grades are judgment outputs and do not belong in the polls layer.
- Poll-close times in the national ENR recon follow a Wikipedia table plus timezone arithmetic and are unverified against state pages (MA snippet said 19:30 vs the standard 20:00).
