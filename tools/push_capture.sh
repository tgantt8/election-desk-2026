#!/usr/bin/env bash
# Ingest one or more browser captures (tools/browser/*.js output files) on top of the CURRENT main and push.
#
# The election-night loop commits to main every few minutes and regenerates every derived file (data/*/site.json,
# docs/data/*, scenarios). Rebasing a sandbox commit onto that would conflict on those files and on the append-only
# logs, so this script never rebases: it resets to origin/main, re-applies the captures (append-only records + snapshot),
# rebuilds the site data exactly as the loop does, runs the hygiene check, commits and pushes. On a push race it starts
# over from the new main. Captures are idempotent through the per-source state file ({ver, zip sha256}).
#
# usage: tools/push_capture.sh <source_id>[@<county>]=<capture file> ...   (e.g. enr_oakland_clarity@Oakland=/path/desk_oakland_123.json)
set -euo pipefail
cd "$(dirname "$0")/.."
[ $# -ge 1 ] || { echo "usage: $0 source_id=capture_file ..."; exit 2; }
git config user.name  >/dev/null 2>&1 || git config user.name "election-desk-capture"
git config user.email >/dev/null 2>&1 || git config user.email "info@ganttformichigan.com"
for attempt in 1 2 3 4 5; do
  git fetch -q origin main
  git checkout -q -B capture-work origin/main
  n=0
  for arg in "$@"; do
    sid="${arg%%=*}"; f="${arg#*=}"; county=""
    case "$sid" in *@*) county="${sid#*@}"; sid="${sid%%@*}";; esac
    if [ -n "$county" ]; then python3 tools/ingest_clarity_bundle.py --source-id "$sid" --county "$county" --bundle "$f" && n=$((n+1))
    else python3 tools/ingest_clarity_bundle.py --source-id "$sid" --bundle "$f" && n=$((n+1)); fi
  done
  python3 tools/run_anomalies.py || true
  python3 tools/build_polls_site.py >/dev/null && python3 tools/build_results_site.py && python3 tools/simulate.py >/dev/null && python3 tools/build_site_data.py >/dev/null
  python3 tools/hygiene_check.py --all
  git add data docs/data
  if git diff --cached --quiet; then echo "nothing new to push (captures unchanged)"; exit 0; fi
  git commit -q -m "browser capture: $* $(date -u +%FT%TZ)

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01WsshaGzKN6LCbQEoYDsJnQ"
  if git push -q origin capture-work:main; then echo "pushed $(git rev-parse --short HEAD) ($n captures)"; exit 0; fi
  echo "push raced with the loop (attempt $attempt); re-applying on the new main"; sleep 3
done
echo "gave up after 5 attempts"; exit 1
