#!/usr/bin/env python3
"""Public-repo hygiene check.

Fails (exit 1) when a staged/committed file path or its content matches a
private-layer pattern or a credential pattern. Used as a pre-commit hook and in CI.

Usage:
  python3 tools/hygiene_check.py            # check files staged for commit
  python3 tools/hygiene_check.py --all      # check every tracked file
  python3 tools/hygiene_check.py PATH ...   # check specific files
"""
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Paths that belong to the private layer. Matched against the repo-relative path (lowercase).
FORBIDDEN_PATH_PATTERNS = [
    r"(^|/)private(/|$)",
    r"(^|/)overlay(/|$)",
    r"field_aggregate",
    r"hd[-_]?58[-_]?goal",
    r"vote[-_]?goal",
    r"projection[-_]?internal",
    r"internal[-_]?projection",
    r"scenarios?[-_]?private",
    r"voter[-_]?file",
    r"\.van$",
    r"(^|/)\.env(\.|$)",
    r"\.(pem|key|p12|pfx)$",
    r"(^|/)(secrets?|credentials?|token)[^/]*\.json$",
]

# Content patterns: credentials and private-layer markers.
FORBIDDEN_CONTENT_PATTERNS = [
    (r"ghp_[A-Za-z0-9]{36}", "GitHub personal access token"),
    (r"github_pat_[A-Za-z0-9_]{60,}", "GitHub fine-grained token"),
    (r"gh[ousr]_[A-Za-z0-9]{36}", "GitHub app/oauth token"),
    (r"AKIA[0-9A-Z]{16}", "AWS access key id"),
    (r"AIza[0-9A-Za-z_\-]{35}", "Google API key"),
    (r"sk-[A-Za-z0-9]{20,}", "secret key (sk-)"),
    (r"xox[baprs]-[A-Za-z0-9-]{10,}", "Slack token"),
    (r"-----BEGIN [A-Z ]*PRIVATE KEY-----", "private key block"),
    (r"(?i)\b(api[_-]?key|secret|token|password)\b\s*[:=]\s*['\"][A-Za-z0-9/+_\-]{16,}['\"]", "hard-coded credential"),
    (r"(?i)\bvan[_ -]?id\b", "VAN identifier"),
    (r"(?i)\bfield_aggregates?\b", "field aggregates marker"),
    (r"(?i)\bhd-?58 (vote )?goal\b", "HD-58 vote goal marker"),
    (r"(?i)internal estimate .{0,40}do not share", "internal-projection marker in data"),
]

# Only data-ish files get the contact-data sweep (code and docs legitimately mention the project contact).
CONTACT_SWEEP_EXT = {".json", ".jsonl", ".csv", ".tsv", ".txt"}
CONTACT_PATTERNS = [
    (r"\(?\b[2-9]\d{2}\)?[-. ]\d{3}[-. ]\d{4}\b", "phone number"),
    (r"\b[A-Za-z0-9._%+-]+@(?!ganttformichigan\.com)[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "email address"),
]

ALLOWLIST_FILES = {"tools/hygiene_check.py", "PRIVATE_LAYER.md", "tests/test_hygiene.py", ".gitignore"}
BINARY_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".gz", ".zip", ".woff", ".woff2", ".ico"}


def git_files(staged_only=True):
    cmd = ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"] if staged_only else ["git", "ls-files"]
    out = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [p for p in out.splitlines() if p.strip()]


def check_path(rel):
    low = rel.lower()
    return [f"forbidden path pattern /{pat}/" for pat in FORBIDDEN_PATH_PATTERNS if re.search(pat, low)]


def check_content(rel):
    problems = []
    ext = os.path.splitext(rel)[1].lower()
    if ext in BINARY_EXT:
        return problems
    full = os.path.join(ROOT, rel)
    try:
        with open(full, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except (OSError, IsADirectoryError):
        return problems
    for pat, label in FORBIDDEN_CONTENT_PATTERNS:
        m = re.search(pat, text)
        if m:
            line = text.count("\n", 0, m.start()) + 1
            problems.append(f"{label} at line {line}")
    if ext in CONTACT_SWEEP_EXT:
        for pat, label in CONTACT_PATTERNS:
            m = re.search(pat, text)
            if m:
                line = text.count("\n", 0, m.start()) + 1
                problems.append(f"possible {label} at line {line} (no personal contact data in data files)")
    return problems


def main(argv):
    if argv and argv[0] == "--all":
        files = git_files(staged_only=False)
    elif argv:
        files = [os.path.relpath(os.path.abspath(a), ROOT) for a in argv]
    else:
        files = git_files(staged_only=True)
    failures = []
    for rel in files:
        rel = rel.replace(os.sep, "/")
        if rel in ALLOWLIST_FILES:
            continue
        for p in check_path(rel):
            failures.append((rel, p))
        for p in check_content(rel):
            failures.append((rel, p))
    if failures:
        print("HYGIENE CHECK FAILED — this is a PUBLIC repository.")
        for rel, p in failures:
            print(f"  {rel}: {p}")
        print("See PRIVATE_LAYER.md. Fix the file; do not weaken the check.")
        return 1
    print(f"hygiene ok ({len(files)} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
