# What never goes in this repository

This repository is **public**. Everything committed here — code, workflow files,
data snapshots, commit messages, issue text — is world-readable, forever.

The following live **only** in the private overlay (a private claude.ai Artifact
with its own database) and must never be committed, pasted into an issue, or
written into a workflow log:

1. HD-58 vote goals (goal, cushion band, banked vs. needed, doors/contacts gap).
2. Internal election-night projections, intervals, "needs X% of remaining" lines.
3. Field aggregates (doors, contacts, shifts by zone).
4. Simulator scenarios that have not been approved for public view.
5. Any personal or contact data (names of voters or volunteers, phones, emails,
   addresses). Candidate names on the official ballot are fine.
6. Internal notes, strategy, campaign memos.
7. Anything derived from VAN or the voter file (MDP Voter File Access Agreement ¶5).
8. API keys and tokens of any kind. Those go in **repository Secrets**.

`tools/hygiene_check.py` runs as a pre-commit hook and in CI and fails on any
file path or content pattern that looks like one of the above. If it fires on a
false positive, fix the file name or content; do not weaken the check.

Model probabilities computed by the public simulator are labeled
"Internal estimate — not a call — do not share" in the UI and are never
written to the `results` or `calls` layers.
