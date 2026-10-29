# Fixtures

Public source documents used as parser test fixtures. Each entry lists its source URL and fetch time; `SHA256SUMS` carries the hashes.

- `macomb_2024_general_summary_elstats.pdf` — source: <https://macombmi.elstats2.civera.com/eng/files/serve/3931>  
  fetched 2026-10-29 via workbench; 200801 bytes; server Last-Modified: n/a
- `macomb_2024_general_official_summary.pdf` — source: <https://macombgovdocs.org/clerk/pdfs/elect-2024-11-05-official-summary-results.pdf>  
  fetched 2026-10-29 via workbench; 209531 bytes; server Last-Modified: Wed, 20 Nov 2024 16:37:30 GMT
- `macomb_2026_general_unofficial_summary_template.pdf` — source: <https://macombgovdocs.org/clerk/pdfs/elect-2026-11-03-unofficial-summary-results.pdf>  
  fetched 2026-10-29 via workbench; 142083 bytes; server Last-Modified: Tue, 27 Oct 2026 18:29:02 GMT
- `macomb_2024_sheriff_precincts.csv` — source: <https://pastelections.macombgov.org/api/download_contest/11957_table.csv?split_party=false&vote_channels=all>  
  fetched 2026-10-29 via workbench; 32237 bytes; server Last-Modified: n/a
- `macomb_2024_hd58_precincts.csv` — source: <https://pastelections.macombgov.org/api/download_contest/11815_table.csv?split_party=false&vote_channels=all>  
  fetched 2026-10-29 via workbench; 3901 bytes; server Last-Modified: n/a
- `macomb_2026_official_candidate_list.pdf` — source: <https://macombgovdocs.org/clerk/pdfs/elect-2026-11-03-Official-Candidate-List-printable.pdf>  
  fetched 2026-10-29 via workbench; 190054 bytes; server Last-Modified: Fri, 18 Sep 2026 14:45:40 GMT

Notes: the 2026 unofficial summary PDF is a blank template as of Oct 27 2026 and is expected to be overwritten in place on election night; the poller archives every distinct hash. CSVs come from the Clerk's Past Elections database (Civera ElectionStats) with `vote_channels=all`, one column per vote mode.
