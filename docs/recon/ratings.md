# Ratings / forecast sources - recon notes (2026-10-29)

## READ FIRST: verification status
No source is VERIFIED by fetch. WebFetch failed with DNS errors (ENOTFOUND) for www.cookpolitical.com
and centerforpolitics.org, which are outside the session network allowlist (Bash reaches github.com only,
and GitHub search is repo-scoped). Following the tool's guidance, no more hosts were tried.
Everything below comes from WebSearch snippets (dated 2026-10-29) or prior knowledge, tagged per entry
in `ratings.json` (`basis`). Every entry is `status: UNVERIFIED`, `verified_at: null`.
Add these hosts to the allowlist and rerun the fetch pass before writing any parser:
www.cookpolitical.com, centerforpolitics.org, insideelections.com, votehub.com, api.votehub.com,
callthemap.com, natesilver.net, racetothewh.com, decisiondeskhq.com, en.wikipedia.org, 270towin.com.

## Page structures (what was observed vs. assumed)
Observed (search snippets only):
- Cook has print-friendly ratings pages: `/print/ratings/races/{senate,house,governor}`. Snippets show a
  single page-level date ("August 20, 2026" Senate; "August 27, 2026" Governor) and race names grouped under
  category headings (Solid list with incumbent/open annotations, e.g. "ID (Risch)", "KY (open)"). The
  print variant is the likeliest parse target: no JS, flat headings and lists. Unconfirmed: whether Lean and
  Toss Up groups are also un-gated.
- Cook also shows chamber tallies on the House page (e.g. July 16: Solid D181/R180; Likely+Lean D19/R20;
  Toss-up or worse D11/R16). Useful as a checksum against the parsed race list.
- Cook rating-change articles appear as paginated listings (`/analysis/{senate,house,governors}/...-overview?page=N`,
  `/taxonomy/term/NN`) with headline + date + author; bodies mostly members-only. No standalone public
  "ratings changes" table was found.
- Inside Elections has per-label index URLs: `insideelections.com/ie-rating/lean-republican/?cycle=2026`,
  `new.insideelections.com/ie-rating/tilt-democrat/`. If those list races publicly they are the parse target;
  detailed ratings and reports are subscriber-only.
- Sabato: category page `centerforpolitics.org/crystalball/category/2026-senate` exists; House/Governor
  analogues are pattern guesses.
- 270toWin per-rater pages carry "As of <date>" stamps (often weeks stale). Cross-check only.

Assumed (prior knowledge, not confirmed): Crystal Ball is free to read; Drupal/WordPress markup; Wikipedia titles.

## Label vocabularies (raw, store verbatim) and common 7-point scale
Common scale: -3 Solid/Safe D, -2 Likely D, -1 Lean D, 0 Toss-up, +1 Lean R, +2 Likely R, +3 Solid/Safe R.
Store `label_raw` (verbatim), `label_scale` (-3..+3), `label_lossy` (bool). The scale is for display and
diffing only and sits in the ratings layer. It is never a probability.

| Rater | Raw labels | 7-pt mapping | Notes |
|---|---|---|---|
| Cook Political Report | Solid D/R, Likely D/R, Lean D/R, Toss Up | direct (Cook itself uses a 7-point scale) | "Toss Up" has no D/R suffix |
| Sabato's Crystal Ball | Safe D/R, Likely D/R, Leans D/R, Toss-up | Safe=Solid; Leans=Lean | "Leans Democratic" in prose |
| Inside Elections | Solid, Likely, Lean, Tilt D/R, Toss-up (Battleground in some years) | Tilt maps to +/-1 with label_lossy=true | 9-point; keep Tilt in label_raw |
| Race to the WH, Split Ticket, others | mixed (Safe/Likely/Lean/Tilt/Toss-up) | same rule as above | confirm per site |
| VoteHub, Call the Map, Silver Bulletin, DDHQ, Economist | probabilities | NO label scale. Store as `model_probability` with the "model outputs" tag | do not convert to a rating label |

## Terms concerns
1. Cook's Terms & Conditions page was not read (the search did not surface it). The only Cook terms seen
   were for the 2022 PVI dataset: internal use only, revocable license, attribution requested. The ratings
   may be governed by a broader copyright/T&C. Reproducing up to 435 district labels publicly could
   exceed what a "label + date + link" practice implies. Get written permission, or start with Senate and
   Governor plus Michigan House seats and link out for the rest.
2. Inside Elections: paywalled. Only store labels if they are reachable with no login. Otherwise link-only.
3. Date semantics: a Cook page date means the page was last updated, not when that race's rating was set.
   Show "Rating: Cook Political Report, [page date]" and do not claim per-race change dates unless a
   rating-changes article supplies one.
4. VoteHub "Complete" forecast ingests expert ratings and markets, so it is not independent of Cook/Sabato/IE.
5. DDHQ also runs results and calls. Keep its forecast in ratings/model outputs only.
6. Wikipedia and 270toWin are secondary: cross-check only, never `rater=Wikipedia-aggregated`.
7. Do not scrape anything behind a login. A 401/403/redirect to a login page means STOP and log link-only.

## Secondary datapoints seen (NOT data - do not store)
Cook moved 18 House races toward Democrats on Oct 9 and about 19 on Oct 23, 2026 (via Karmactive and
Rio Times). Sabato shifted five Senate ratings on Oct 14. Silver Bulletin FLIPR updated Oct 22. DDHQ
updated its Senate forecast Oct 26. These dates say the final-week cadence is real, so poll more often.

## Recommended GitHub Actions poller plan
- Cron: `17 * * * *` (hourly, off the hour) through Oct 27. From Oct 28 to Nov 3 use `*/30`. Add
  `workflow_dispatch`. Hit only one URL per rater per run, with `If-None-Match`/`If-Modified-Since`
  and a User-Agent naming the project plus a contact email.
- Order per run: fetch -> save raw HTML (hash + fetched_at) to an append-only snapshots path -> parse ->
  validate -> write a new snapshot row only if the label set differs from the last one.
- Parse targets, in order: Cook `/print/ratings/races/{senate,house,governor}` (validate parsed counts against
  the page's tallies); IE category pages (only if public); Sabato category pages (articles' tables,
  low-frequency, daily). Fallback if parsing fails or the layout changes: link-only row, `status: parse_failed`,
  alert, no guessing.
- Each row: race, rater, label_raw, label_scale, label_lossy, page_date, fetched_at, url, snapshot_sha256,
  source_id. A change in page_date with no label change is still recorded. A label disappearing is an
  anomaly, flagged in neutral language ("label no longer present on page").
- Hard stops: robots.txt disallow for the path (robots.txt of every host unread so far; must be checked),
  HTTP 401/403, login redirect, Cloudflare challenge, rate-limit 429 (back off 24h).
- Daily: refresh `rating-changes` listing headlines only (for dating changes). Model outputs
  (VoteHub, Silver Bulletin, DDHQ, Economist, Call the Map): hourly only after an endpoint is confirmed; until
  then link-only cards.
- Michigan focus: Senate (open seat), Governor (open), MI House districts.
