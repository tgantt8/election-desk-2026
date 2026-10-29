# POLLS source recon - 2026-10-29

## Read this first: nothing was verified by fetch
Every WebFetch call (api.votehub.com, votehub.com, scsr.siena.edu, pollresults.org) failed with `getaddrinfo ENOTFOUND`. The session's network allowlist excludes those hosts, so I stopped fetching, as the error instructed. Bash has only github.com, and the two third-party VoteHub client PRs I tried (mihir-patel-05/2026Midterms #104, awall451/kalseer #37) returned 403 and I did not attach them.

All 16 entries in polls.json are therefore `status: UNVERIFIED`, `verified_at: null`, `fetch_result: DNS_BLOCKED`. They were built from WebSearch snippets, which are summarized and may be wrong. No endpoint, parameter or field name below is confirmed against a live response.

To unblock: allow `api.votehub.com`, `votehub.com`, `sri.siena.edu`, `scri.siena.edu`, `www.natesilver.net`, `ddhq.io`, `polling-api-docs.decisiondeskhq.com`, `www.realclearpolling.com`, `fiftyplusone.news`, then rerun. Or run these in a GitHub Actions job (unrestricted egress) and commit the raw responses as fixtures.

## Per source

### 1. VoteHub Polling API (beta) - polls.votehub_api
- Seen via search: docs at https://votehub.com/polls/api/; base https://api.votehub.com. Endpoints reported: `/polls`, `/polls/{poll_id}`, `/pollsters`, `/subjects`, `/poll-types`. A third-party client uses `/poll-types` then `/polls?poll_type=`. Filters reported: end-date cutoff, minimum sample size, population (`rv`/`lv`/`a`). I could not confirm `limit`, race/state or date parameter names.
- License reported: CC BY 4.0, beta. A third-party mirror (Firecrawl) shows an `attribution` object in responses (license name, license URL, credit text asking users to credit VoteHub and cite each poll's original source URL, provider URL). Official-page wording not seen. Store the object verbatim.
- Auth: none reported. Rate limit: not published (a third-party client self-limits to 1 req/s and retries on 5xx/429).
- Field names reported (no numbers): `id, poll_type, subject, seat_name, pollster, sponsors, population, sample_size, answers[{choice, pct}], partisan, internal, attribution{...}`. Unconfirmed: field dates, mode, original URL fields.
- Sample shape (names only):
```
{ "id":"S", "poll_type":"S", "subject":"S|null", "seat_name":"S|null", "pollster":"S",
  "sponsors":[...], "population":"a|lv|rv", "sample_size":N, "partisan":"S|null", "internal":B,
  "answers":[{"choice":"S","pct":N}], ...dates/url fields UNCONFIRMED..., "attribution":{...} }
```
- Gotcha: `partisan` and `internal` flags must travel with the record. VoteHub also publishes averages and Pollster Scorecards; those are judgment outputs and must not enter the polls layer.

### 2. NYT/Siena (nytimes.com) - polls.nyt_siena_nytimes
Public articles carry toplines, methodology and an interactive crosstab page. HTML only, paywall/login possible. Rule: toplines and crosstab basics with a link; never scrape behind login. Do not poll nytimes.com; detect releases through Siena's pages and enter NYT links by hand. Terms not read.

### 3. Siena Research Institute - polls.siena_sri
- The live host in the search index is **sri.siena.edu** (older **scri.siena.edu**). I saw no result for **scsr.siena.edu**; treat that as a likely wrong domain.
- WordPress-style site: category/tag pages (`/category/political/`, `/tag/new-york-times/`, `/tag/crosstabs`), posts titled "Crosstabs for ...", and crosstab PDFs under `/wp-content/uploads/YYYY/MM/` (example pattern: `SNY0925-Crosstabs.pdf`). PDF header lists sample (e.g. "N registered voters") and margin of error; tables by party, gender, ideology, region, age, religion, income. Federal NYT/Siena releases link out to the Times.
- The index showed a Siena NY statewide release Aug 12 2026 and a NYT/Siena national RV survey May 18 2026; it showed no October 2026 NYT/Siena release (index may be stale).
- Try `/feed/` RSS before scraping HTML (unverified).

### 4. PollResults.org - polls.pollresults_org
No search evidence that the site or an API exists. Do not build against it. Ask for the exact URL.

### 5. Call the Map - polls.callthemap
No search results for a product by that name. JSON URLs cannot be guessed. Ask for the exact URL(s); unlicensed hotlinking of another site's frontend JSON is not an API.

### 6. On Point Politics - polls.onpoint_politics
No search results. Unknown URL/format. If found, link-only (averages = derived).

### 7. Others
- 538/ABC: **shut down 2025-03-05** by ABC/Disney; public polling databases went offline (Nieman Lab, FlowingData, Wikipedia via search). The NYT started its own tracker (Mar 2025, Trump approval first). GitHub `fivethirtyeight/data` and mirrors (Rearc, datahub; one generic-ballot mirror last updated 2026-03-12) are legacy/unofficial. Not a 2026 source.
- RealClearPolling: public averages for generic ballot (and per search, 2026 races). Link only.
- Decision Desk HQ: public methodology at ddhq.io/polls/methodology and votes-docs.decisiondeskhq.com/polling-methodology; a polling API with `/reference/polls` and `/reference/averages` at polling-api-docs.decisiondeskhq.com, which the FAQ describes as documentation provided to clients. Treat as licensed/gated; link public pages only.
- Silver Bulletin: generic ballot average, approval, models, pollster ratings; Substack with paid content. Link only; freshness uncertain (search showed Jul 31 and Sep 8 updates).
- Cook Political Report: ratings layer, not polls; label+date+link only. No public polling average found.
- Extra find: Fifty Plus One (fiftyplusone.news) polls pages and tiered API/downloads (crosstabs premium). Link only unless licensed.

### 8. Pollster grades
- Silver Bulletin ratings: letter grades plus Predictive Plus-Minus and mean-reverted bias for 500+ pollsters; updated Jan 2026 and after 2025 elections; 2025 archive page frozen at 2025-02-17. Datawrapper table `datawrapper.dwcdn.net/GiFps/3` surfaced in search. Reuse terms unread.
- VoteHub Pollster Scorecards: page at votehub.com/polls/pollster-scorecards/ exists; contents and terms unread.
- 538 legacy: frozen at shutdown.
- Storage rule: `{pollster, grade, assigner, ratings_version_or_date, source_url, retrieved_at}`. Never a bare grade on the poll record. Grades are judgment, not evidence.

## Recommended dedupe key
`sha1(norm(pollster) | field_start | field_end | population | race_id | sponsor_norm)` where
- `norm(pollster)` is lowercase with punctuation removed and an alias table (e.g. "NYT/Siena", "Siena College/NYT" -> one id);
- `population` is one of `lv|rv|a`; a poll reporting several populations is several rows (one per population);
- `race_id` is a canonical id (e.g. `generic-ballot`, `approval-president`, `senate-MI-2026`);
- a poll from two sources (VoteHub and Siena) is one row with `sources[]` and `urls[]`, not two.
Rows are append-only: a changed topline on an existing key is a new snapshot row with `supersedes`, never an update.

## Fetch plan for GitHub Actions poller (Python requests)
1. Schedule: cron every 30 min (`*/30`) from now to Nov 3, cutting to 60 min off-peak 01:00-06:00 ET; add `concurrency: group: polls-poller, cancel-in-progress: false`. Note scheduled workflows can run late and are disabled after 60 days of repo inactivity.
2. Only machine-readable, licensed source in the first build: VoteHub. Others are link registry entries and a Siena RSS/listing check.
3. Per source: one `requests.Session`, `User-Agent: ElectionDesk2026-poller (contact: <email>)`, timeout 20s, 3 retries with backoff on 5xx/429, honor `Retry-After`, per-source minimum gap (VoteHub 1 req/min; Siena 1 req/10 min) enforced with a stored `last_fetch_at`.
4. Store raw response bytes plus `fetched_at` (UTC ISO), URL, HTTP status, sha256; skip commit if the sha256 matches the prior snapshot. Write to `data/polls/raw/<source>/<ts>.json` (append-only); normalized rows to `data/polls/normalized.ndjson`.
5. Validate against a JSON schema before normalizing; if keys are unexpected, fail the job loudly (no silent default) and store the raw file anyway.
6. Attach `attribution` (VoteHub: CC BY 4.0 credit text and original poll URL) to every row; every number carries `source`, `retrieved_at`, and the polls layer never writes to ratings/early_vote/results/calls/scenarios.
7. Siena: poll the category feed/listing for new post URLs only; on a new URL, open a human-review issue instead of auto-parsing the PDF.
8. Publish nothing without the page-level label: poll numbers are measurements, not calls.

## Terms blockers
- None found for VoteHub on the evidence available (CC BY 4.0) but this is unverified and the official attribution wording was not read.
- DDHQ API: client-gated. Treat as blocked unless licensed.
- NYT: site terms (not read) likely bar automated access; use link + manual toplines.
- Silver Bulletin / RCP / Fifty Plus One / Cook: link only; paid or login content must not be scraped.
- PollResults.org, Call the Map, On Point Politics: not identifiable, so no terms to assess.
