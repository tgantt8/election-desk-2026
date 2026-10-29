# Enhanced Voting fixtures

Real payloads from the Enhanced Voting public results API, fetched with
`User-Agent: election-desk-2026/0.1 (public results desk; info@ganttformichigan.com)` from the Composio workbench
(the dev shell has no outbound network). All values are verbatim; files are compact UTF-8 JSON with no trailing newline,
so each file's sha256 is the sha256 of the payload (or of the re-serialized subset, see below).

| File | URL | fetched_at (UTC) | bytes | sha256 | Notes |
| --- | --- | --- | --- | --- | --- |
| `wa_election_20261103.json` | https://results.votewa.gov/results/public/api/elections/washington/20261103 | 2026-10-29T17:02:33Z | 6015 | 1eb72002c051a478f89b5af7d85f583ab11607e440dcc0b23b44affb6bdae9ec | Full, byte-identical to the response. |
| `wa_ballot_items_20261103_subset.json` | https://results.votewa.gov/results/public/api/elections/washington/20261103/ballot-items | 2026-10-29T17:02:33Z | 22337 | 1c110b212686cab9c15aeeed89e401823e878959c04f9a8b112c05e5ef7cc68f | SUBSET: 11 of 173 ballot items, verbatim items, original order, envelope kept (`totalRecordCount` still 173). |
| `ga_election_06162026GeneralPrimaryRunoff.json` | https://results.sos.ga.gov/results/public/api/elections/georgia/06162026GeneralPrimaryRunoff | 2026-10-29T17:04:10Z | 3225 | 123a82fbb947b8b6fd27500ef1a81577f7b2949758833745bd9a8e3c310ba84a | Full, byte-identical. `isOfficialResults: true`, `isPrimary: true`. |
| `ga_ballot_items_06162026GeneralPrimaryRunoff_first3.json` | https://results.sos.ga.gov/results/public/api/elections/georgia/06162026GeneralPrimaryRunoff/ballot-items | 2026-10-29T17:04:11Z | 7678 | 9d23f87d006af86a82c113dee935beb5c632023a2f534b0a8507b47262cc7433 | TRIMMED: first 3 of 27 items (US Senate - Rep, Governor - Rep, Lieutenant Governor - Rep), verbatim, envelope kept (`totalRecordCount` still 27). |

## Full WA ballot-items payload (not stored)

The complete response was 324,642 bytes, sha256 `88f35d7cca582f395f0bcd95ea4d402d1e26d147e51e6af62bd8bac6565dd21d`, 173 ballot items
(155 Candidate + 18 BallotMeasure), all zero votes. Only a transport limit (payloads reach this repo by pasting text out of the
workbench) is why the committed WA ballot fixture is a subset. Subset selection (all verbatim, none edited):
Initiative Measure IP26-645 and IL26-638; Congressional District 1, 2, 7, 9; Supreme Court Justice Position #01;
Legislative District 7 State Senator; Ferry/Pend Oreille/Stevens Superior Court Judge Position 2 (the one item with party "NO");
Southeast Electoral District Judge Position No. 5 (group "other"); Cheney School District Proposition No. 1 (levy measure, `referendum` text "School").
The subset was re-serialized with `json.dumps(separators=(",", ":"), ensure_ascii=False)`; the same call reproduces the complete WA
and GA responses byte-for-byte (checked), so the item text is identical to the wire format.

Because the subset/trim envelopes keep the original `totalRecordCount`, `run()` reports `parse_status: ok_partial` for them
(`totalRecordCount > len(data)`). That is expected for fixtures and is the real guard for a truncated live response.

## Other live hosts found while probing (election objects only; not stored)

| State | Host | Slug | Election id | Seen |
| --- | --- | --- | --- | --- |
| Utah | electionresults.utah.gov | utah | General11032026 | 64 ballot items, 93,746 bytes, zero votes, asOf 2026-10-21T18:48:33Z |
| Virginia | enr.elections.virginia.gov | virginia | 2026-November-General | 32 ballot items, 259,457 bytes, zero votes, asOf 2026-10-29T15:45:44Z |
| Georgia | results.sos.ga.gov | georgia | 06162026GeneralPrimaryRunoff | (host `results.enr.sos.ga.gov` does not resolve) |
| Washington | results.votewa.gov | washington | 20261103 | |
