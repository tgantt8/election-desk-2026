#!/usr/bin/env python3
"""Macomb County Clerk "compact summary" PDF parser (Macomb-only totals).

The Clerk overwrites https://macombgovdocs.org/clerk/pdfs/elect-2026-11-03-unofficial-summary-results.pdf in place on
election night.  The layout is a 3-4 page, three-column "results only" sheet (not the 44-page Civera "Summary Results
Report").  Candidate lines read "Name PARTY votes"; contests are black bars with white text; sub-headers (district,
township / city / school-district name, office) are bold or italic lines in between.

Design notes
------------
* Words come from pdfplumber ``extract_words`` (with font name, size and fill colour).  Linear ``extract_text`` is never
  used, because the three columns interleave.
* Column split (per page), see :func:`find_column_boundaries`:
    1. The "body" is everything at or below the first white-on-black bar; the title block above it feeds the header.
    2. Left edges are the x0 peaks (1 pt bins) of regular-weight alphabetic "line-start" words: first word in its row,
       or preceded by a gap > 3.5 pt (party codes and Yes/No excluded).  A peak needs >= 2 words and >= 5% of the
       tallest peak; peaks must be >= 100 pt apart (strongest first).
    3. The boundary in front of column k is ``max(prev_col_max_x1 + 1, left_k - 8)`` capped at ``left_k - 0.5``, where
       ``prev_col_max_x1`` is the right-most x1 of regular words with x1 <= ``left_k``.  A word belongs to the column
       whose boundary is the last one <= its x0.  Zero or one peak means a single column (the proposals page).
* Lines are rebuilt per column by clustering ``top`` (tolerance 2.0 pt, anchored on the first word of the line).
* Votes that are blank in the source stay ``None`` (never 0).  If every candidate in the file is blank the status is
  ``template_blank``.
* Tie-out (the Clerk prints no per-contest totals on this sheet): turnout % must equal number voted / eligible voters
  to the printed 0.1 point, and no contest may carry more votes than number voted x votes-per-voter.  Any violation
  raises :class:`CompactTieOutError`.  The cross-document tie-out against the 44-page report lives in the tests.
* Nothing here writes to any data layer; the output is a plain dict for the ``results`` layer's staging step, which
  stamps source + timestamp and the UNOFFICIAL flag.  No personal data, no network.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import Counter

PARTIES = {"DEM", "REP", "LIB", "UST", "GRN", "NLP", "NPA", "WC", "WCP"}
NUM_RE = re.compile(r"^\d[\d,]*$")
WORD_NUMS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}

# Section bars: regex -> normalised section name.
SECTION_PATTERNS = [
    (re.compile(r"^PARTISAN(?: SECTION)?$"), "PARTISAN"),
    (re.compile(r"^NONPARTISAN(?: SECTION)?$"), "NONPARTISAN"),
    (re.compile(r"^JUDICIAL(?: OFFICES| SECTION)?$"), "JUDICIAL"),
    (re.compile(r"^TOWNSHIPS?(?: OFFICES)?$"), "TOWNSHIPS"),
    (re.compile(r"^CIT(?:Y|IES)(?: OFFICES)?$"), "CITIES"),
    (re.compile(r"^VILLAGES?(?: OFFICES)?$"), "VILLAGES"),
    (re.compile(r"^BOARDS? OF EDUCATION$"), "BOARDS OF EDUCATION"),
    (re.compile(r"^LIBRARY BOARDS?(?: MEMBERS?)?$"), "LIBRARY BOARDS"),
    (re.compile(r"^PROPOSALS?$"), "PROPOSALS"),
]
# Sections whose non-bar bold/italic lines are jurisdiction names (township, city, village, school district).
LOCAL_SECTIONS = {"TOWNSHIPS", "CITIES", "VILLAGES", "BOARDS OF EDUCATION", "LIBRARY BOARDS"}
# 2024 prints judicial and college bars without a section bar; infer the section from the bar text.
INFERRED_SECTIONS = [
    (re.compile(r"^(?:JUSTICE|JUDGE|PROBATE|CIRCUIT COURT|COURT OF APPEALS)\b|\bCOURT\b"), "JUDICIAL"),
    (re.compile(r"\bCOLLEGE\b"), "NONPARTISAN"),
]
DISTRICT_RE = re.compile(r"^(\d+(?:st|nd|rd|th)\s+District)\s*(\(.*\))?$")
DESCRIPTOR_RE = re.compile(
    r"^(?:(?:Non-)?Incumbent Position|New Judgeship|Partial Term|Unexpired Term|Full Term|"
    r"(?:One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten|\d+)[ -](?:\d+-Year|Partial))", re.I)
OFFICE_RE = re.compile(
    r"^(?:(?:Village|City|Township|Charter Township)\s+)?(?:Supervisor|Clerk|Treasurer|Trustee|Mayor|"
    r"(?:City )?Council(?: Member)?|President|Commissioner|Assessor|Board Member|Library Board Member|Constable)\b", re.I)
CONTD_RE = re.compile(r"\s*\((?:cont'?d\.?|continued)\)\s*$", re.I)
VOTE_FOR_RE = re.compile(r"\((\d+)\)|\((\d+)\s+Partial|\b(One|Two|Three|Four|Five|Six|Seven|Eight|Nine|Ten)\b(?=\s+(?:\d+-Year|Partial))", re.I)
WRITE_IN_RE = re.compile(r"\s*\(W\.?\s?I\.?\)\s*", re.I)
MONTH_RE = re.compile(r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}\b", re.I)


class CompactParseError(Exception):
    """The compact PDF could not be parsed into a trustworthy structure."""


class CompactTieOutError(CompactParseError):
    """Printed header totals and parsed values disagree (the tie-out rule: fail, never patch)."""


# --------------------------------------------------------------------------------------------------------------------
# word / line primitives
# --------------------------------------------------------------------------------------------------------------------
def _is_white(word):
    """True when the word's fill colour is white (text printed on a black contest bar)."""
    c = word.get("non_stroking_color")
    if c is None:
        return False
    vals = c if isinstance(c, (list, tuple)) else (c,)
    return len(vals) > 0 and all(isinstance(v, (int, float)) and v >= 0.99 for v in vals)


def _font_flags(word):
    """Return (bold, italic) for a word from its font name; 'Black' counts as bold."""
    name = (word.get("fontname") or "").lower()
    return ("bold" in name or "black" in name), ("italic" in name or "oblique" in name)


def _is_regular(word):
    """True for regular-weight, upright text (candidate names, party codes, votes, Yes/No)."""
    bold, italic = _font_flags(word)
    return not bold and not italic


def group_lines(words, tol=2.0):
    """Group words into lines by ``top`` (tolerance ``tol`` from the line's first word); words sorted left to right."""
    lines = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if lines and abs(w["top"] - lines[-1][0]["top"]) <= tol:
            lines[-1].append(w)
        else:
            lines.append([w])
    return [sorted(ln, key=lambda w: w["x0"]) for ln in lines]


def _text(words):
    """Join word texts with single spaces."""
    return " ".join(w["text"] for w in words).strip()


def find_column_boundaries(words):
    """Return (left_edges, boundaries) for the columns of one page's body words.

    Left edges are x0 peaks of regular-weight alphabetic words (name starts).  ``boundaries`` has one x per column after
    the first; a word with x0 >= boundaries[i] belongs to column i+1.  No peak or one peak -> ([...], []) (one column).
    """
    reg = [w for w in words if _is_regular(w) and w["text"][:1].isalpha() and w["text"] not in PARTIES
           and w["text"].lower() not in ("yes", "no")]
    rows = group_lines(words)
    starts = []
    for row in rows:
        for i, w in enumerate(row):
            if w in reg and (i == 0 or w["x0"] - row[i - 1]["x1"] > 3.5):
                starts.append(w)
    bins = Counter(int(w["x0"]) for w in starts)
    if not bins:
        return [], []
    top = max(bins.values())
    cands = sorted(((c, b) for b, c in bins.items() if c >= 2 and c >= 0.05 * top), reverse=True)
    peaks = []
    for _, b in cands:
        if all(abs(b - p) >= 100 for p in peaks):
            peaks.append(b)
    peaks.sort()
    lefts = []
    for p in peaks:
        xs = sorted(w["x0"] for w in starts if int(w["x0"]) == p)
        lefts.append(xs[len(xs) // 2])
    boundaries = []
    for left in lefts[1:]:
        prev = [w["x1"] for w in words if _is_regular(w) and w["x1"] <= left + 0.5]
        prev_x1 = max(prev) if prev else left - 8
        boundaries.append(min(max(prev_x1 + 1.0, left - 8.0), left - 0.5))
    return lefts, boundaries


def split_columns(words):
    """Split body words into per-column word lists (left to right) using :func:`find_column_boundaries`."""
    _, bounds = find_column_boundaries(words)
    cols = [[] for _ in range(len(bounds) + 1)]
    for w in words:
        cols[sum(1 for b in bounds if w["x0"] >= b)].append(w)
    return [c for c in cols if c]


def page_words(page):
    """Words of a page with ``fontname``, ``size`` and ``non_stroking_color`` taken from the word's most common char.

    ``extract_words(extra_attrs=...)`` would split a word whenever a glyph has a different subset-font or fill tuple
    ("Am y"), so the attributes are read from the chars of an ordinary word instead.
    """
    out = []
    for w in page.extract_words(keep_blank_chars=False, return_chars=True):
        chars = w.pop("chars")
        w["fontname"] = Counter(c.get("fontname") for c in chars).most_common(1)[0][0]
        w["size"] = Counter(round(c.get("size") or 0, 1) for c in chars).most_common(1)[0][0]
        w["non_stroking_color"] = Counter(
            tuple(c["non_stroking_color"]) if isinstance(c.get("non_stroking_color"), (list, tuple)) else c.get("non_stroking_color")
            for c in chars).most_common(1)[0][0]
        out.append(w)
    return out


def page_lines(page):
    """Return (header_words, columns) for a pdfplumber page: header words above the first bar; columns -> lines."""
    words = page_words(page)
    white_tops = [w["top"] for w in words if _is_white(w)]
    body_top = (min(white_tops) - 1.0) if white_tops else 0.0
    head = [w for w in words if w["top"] < body_top]
    body = [w for w in words if w["top"] >= body_top]
    columns = []
    for col in split_columns(body):
        lines = [ln for ln in group_lines(col) if not re.match(r"^Page \d+ of \d+$", _text(ln))]
        columns.append(lines)
    return head, columns


# --------------------------------------------------------------------------------------------------------------------
# header block
# --------------------------------------------------------------------------------------------------------------------
def parse_header(head_words, warnings):
    """Parse the title block: election label, eligible/registered voters, number voted, turnout, official flag."""
    rows = [_text(ln) for ln in group_lines(head_words, tol=2.0)]
    blob = "\n".join(rows)
    flat = " ".join(rows)

    def grab(pattern):
        m = re.search(pattern, flat, re.I)
        return m.group(1) if m else None

    label = None
    for r in rows:
        m = re.search(r"((?:[A-Z][A-Z ]+ - )?" + MONTH_RE.pattern + r"(?: Election)?)", r, re.I)
        if m:
            label = m.group(1).strip()
            break
    if label is None:
        warnings.append("header: election label not found")

    def to_int(s):
        return int(s.replace(",", "")) if s else None

    lab_found = {k: bool(re.search(p, flat, re.I)) for k, p in
                 (("eligible", r"(?:ELIGIBLE|REGISTERED) VOTERS:"), ("voted", r"(?:NUMBER|TOTAL) VOTED:"), ("turnout", r"TURNOUT:"))}
    for k, found in lab_found.items():
        if not found:
            warnings.append(f"header: {k} label not found")
    eligible = to_int(grab(r"(?:ELIGIBLE|REGISTERED) VOTERS:\s*(\d[\d,]*)"))
    voted = to_int(grab(r"(?:NUMBER|TOTAL) VOTED:\s*(\d[\d,]*)"))
    t = grab(r"TURNOUT:\s*(\d+(?:\.\d+)?)\s*%")
    turnout = float(t) if t else None

    if re.search(r"\bUNOFFICIAL\b", blob, re.I):
        flag = "UNOFFICIAL"
    elif re.search(r"\bOFFICIAL\b", blob, re.I):
        flag = "OFFICIAL"
    else:
        flag, _ = None, warnings.append("header: official/unofficial flag not found")
    macomb_only = bool(re.search(r"Macomb\s+County\s+results\s+only", flat, re.I))
    if not macomb_only:
        warnings.append("header: 'Macomb County results only' notice not found")
    if eligible is not None and voted is not None and turnout is not None and eligible > 0:
        if round(100.0 * voted / eligible, 1) != round(turnout, 1):
            raise CompactTieOutError(
                f"header turnout {turnout}% != number voted {voted} / eligible {eligible} = {100.0 * voted / eligible:.2f}%")
    return {"election_label": label, "eligible_voters": eligible, "number_voted": voted, "turnout_pct": turnout,
            "official_flag": flag, "macomb_only": True if macomb_only else False}


# --------------------------------------------------------------------------------------------------------------------
# contest state machine
# --------------------------------------------------------------------------------------------------------------------
def _section_of(text):
    """Map a bar's text to a normalised section name, or None if the bar is a contest."""
    for rx, name in SECTION_PATTERNS:
        if rx.match(text):
            return name
    return None


def _vote_for(*texts):
    """Votes-per-voter from the first text carrying '(2)', '(2 Partial Terms ...)' or 'Three 4-Year Terms'."""
    for t in texts:
        if not t:
            continue
        m = VOTE_FOR_RE.search(t)
        if m:
            return int(m.group(1) or m.group(2) or WORD_NUMS[m.group(3).lower()])
    return None


class _State:
    """Running context while walking lines in reading order (page, column, top to bottom)."""

    def __init__(self):
        self.section, self.section_inferred = "PARTISAN", True
        self.reset_below_section()
        self.contests = []
        self.current = None
        self.keys = Counter()

    def reset_below_section(self):
        """Clear everything below the section level (bar title, district, jurisdiction, office, descriptor)."""
        self.bar = None
        self.bar_is_bar = False
        self.district = self.jurisdiction = self.office = self.descriptor = None
        self.multi = False
        self.multi_note = None
        self.current = None

    def reset_below_bar(self):
        """Clear district, jurisdiction, office and descriptor (a new contest bar or title)."""
        self.district = self.jurisdiction = self.office = self.descriptor = None
        self.multi = False
        self.multi_note = None
        self.current = None

    def new_contest(self, proposal=False):
        """Open a contest from the current context and return it (``proposal``: Yes/No contest, title filled later)."""
        if self.office:
            title = self.office
            if self.district:
                title = f"{title} - {self.district}"
        elif self.bar:
            title = self.bar + (f" - {self.district}" if self.district else "")
        elif proposal:
            title = ""
        else:
            title = self.jurisdiction or ""
        vf = _vote_for(self.office, self.bar, self.descriptor, self.jurisdiction)
        jur = self.jurisdiction or (self.bar if (self.office and self.bar and self.bar_is_bar) else None)
        if not self.office and not self.bar and not proposal:
            jur = None  # library-board style: the place name is the title
        c = {"title": title, "section": self.section, "jurisdiction": jur, "multi_county": self.multi,
             "candidates": [], "kind": "candidate", "office": self.office or (self.bar if not self.office else None), "district": self.district,
             "descriptor": self.descriptor, "vote_for": vf if vf is not None else 1, "vote_for_inferred": vf is None,
             "multi_county_note": self.multi_note, "section_inferred": self.section_inferred}
        key = " | ".join(x for x in (self.section, jur, title, self.descriptor, self.multi_note) if x)
        self.keys[key] += 1
        c["key"] = key if self.keys[key] == 1 else f"{key} #{self.keys[key]}"
        self.contests.append(c)
        self.current = c
        return c


def _apply_multi(state, text):
    """Record a '(Multi-County)' / 'Multi-County (LAPEER)' marker found in header text."""
    if re.search(r"multi-?county", text, re.I):
        state.multi = True
        m = re.search(r"multi-?county\s*\(([^)]*)\)", text, re.I)
        state.multi_note = m.group(1).strip() if m else None


def _header_line(state, text, bar, italic, bold, size):
    """Update the context for one non-candidate line; ``bar`` = white-on-black."""
    t = text.strip()
    t_clean = CONTD_RE.sub("", t).strip()
    cont = t_clean != t
    if bar:
        sec = _section_of(t_clean)
        if sec:
            if sec != state.section or state.section_inferred:
                state.section, state.section_inferred = sec, False
                state.reset_below_section()
            elif not cont and state.bar is not None:
                pass
            return
        if cont and t_clean == state.bar:
            return
        for rx, name in INFERRED_SECTIONS:
            if rx.search(t_clean) and state.section not in (name,):
                if state.section in ("PARTISAN", "TOWNSHIPS", "CITIES", "VILLAGES", "BOARDS OF EDUCATION", "LIBRARY BOARDS", "NONPARTISAN"):
                    state.section, state.section_inferred = name, True
                break
        state.bar, state.bar_is_bar = t_clean, True
        state.reset_below_bar()
        _apply_multi(state, t_clean)
        return
    if italic and not bold:
        if size < 7.6:
            if state.current and state.current["candidates"]:
                state.current["candidates"][-1]["note"] = t_clean
            return
        state.descriptor = t_clean
        state.current = None
        return
    m = DISTRICT_RE.match(t_clean)
    if m:
        rest = m.group(2) or ""
        if cont and state.district == m.group(1):
            return
        state.district, state.descriptor = m.group(1), None
        state.office = None
        state.multi, state.multi_note = False, None
        _apply_multi(state, rest)
        left = re.sub(r"multi-?county", "", rest, flags=re.I).strip("() ")
        if left:
            state.descriptor = left
        state.current = None
        return
    if re.search(r"multi-?county", t_clean, re.I) and len(t_clean) < 40:
        _apply_multi(state, t_clean)
        state.current = None
        return
    if OFFICE_RE.match(t_clean):
        if cont and state.office == t_clean:
            return
        state.office, state.descriptor = t_clean, None
        state.current = None
        return
    if DESCRIPTOR_RE.match(t_clean):
        state.descriptor = t_clean
        state.current = None
        return
    if state.section in LOCAL_SECTIONS or state.bar_is_bar:
        if cont and state.jurisdiction == t_clean:
            return
        state.jurisdiction = t_clean
        state.office = state.descriptor = state.district = None
        state.multi, state.multi_note = False, None
        state.current = None
        return
    state.bar, state.bar_is_bar = t_clean, False
    state.reset_below_bar()


def parse_candidate_line(words):
    """Parse a regular-weight line into (name, party, votes, write_in, clipped); votes None when blank.

    ``clipped`` is True when the source cell cut the name off at an opening parenthesis (the "(W.I.)" marker overlapped
    by the party box, so the text reads "Name (NPA"); the line is then read as a write-in.  Returns None if no name.
    """
    toks = [w["text"] for w in words]
    votes = None
    if toks and NUM_RE.match(toks[-1]):
        votes = int(toks[-1].replace(",", ""))
        toks = toks[:-1]
    party, clipped = None, False
    if toks and toks[-1] in PARTIES:
        party = toks[-1]
        toks = toks[:-1]
    elif toks:
        m = re.match(r"^\((" + "|".join(sorted(PARTIES)) + r")$", toks[-1])
        if m:
            party, clipped = m.group(1), True
            toks = toks[:-1]
    name = " ".join(toks).strip()
    if name.endswith("("):
        clipped = True
    write_in = bool(WRITE_IN_RE.search(name)) or clipped
    name = WRITE_IN_RE.sub(" ", name).rstrip(" (").strip()
    if not re.search(r"[A-Za-z]", name):
        return None
    return name, party, votes, write_in, clipped


def _proposal_line(state, words, pending):
    """Handle one line inside the PROPOSALS section.  ``pending`` is a list of title fragments (mutated)."""
    idx = next((i for i, w in enumerate(words) if w["text"].lower() in ("yes", "no") and _is_regular(w)), None)
    if idx is None:
        text = _text(words)
        bold, italic = _font_flags(words[0])
        if state.current is not None:
            state.current["title"] = (state.current["title"] + " " + text).strip()
        elif italic and not bold:
            pending.append(text)
        else:
            state.jurisdiction = text
            state.office = state.descriptor = None
            pending.clear()
        return
    frag = _text(words[:idx])
    rest = words[idx:]
    choice = rest[0]["text"].capitalize()
    votes = int(rest[-1]["text"].replace(",", "")) if len(rest) > 1 and NUM_RE.match(rest[-1]["text"]) else None
    if state.current is None:
        c = state.new_contest(proposal=True)
        c["office"] = None
        c["kind"] = "proposal"
    c = state.current
    parts = [p for p in pending + ([frag] if frag else []) if p]
    pending.clear()
    if parts:
        c["title"] = (c["title"] + " " + " ".join(parts)).strip()
    c["candidates"].append({"name": choice, "party": None, "votes": votes, "write_in": False})
    if choice == "No":
        state.current = None
        c["key"] = " | ".join(x for x in (c["section"], c["jurisdiction"], c["title"]) if x)


def parse_columns(columns_by_page, warnings):
    """Walk every page's columns in reading order and return the list of contest dicts."""
    st = _State()
    pending = []
    for pno, columns in columns_by_page:
        for cno, lines in enumerate(columns, 1):
            for ln in lines:
                text = _text(ln)
                first = ln[0]
                if _is_white(first):
                    _header_line(st, text, True, False, True, first["size"])
                    pending.clear()
                    continue
                if st.section == "PROPOSALS":
                    _proposal_line(st, ln, pending)
                    continue
                if _is_regular(first):
                    parsed = parse_candidate_line(ln)
                    if parsed is None:
                        warnings.append(f"p{pno} col{cno}: unparsed line {text!r}")
                        continue
                    if st.current is None:
                        st.new_contest()
                    name, party, votes, wi, clipped = parsed
                    cand = {"name": name, "party": party, "votes": votes, "write_in": wi}
                    if clipped:
                        cand["name_clipped"] = True
                        warnings.append(f"p{pno} col{cno}: candidate label clipped in source ({text!r}); read as write-in")
                    st.current["candidates"].append(cand)
                    continue
                bold, italic = _font_flags(first)
                _header_line(st, text, False, italic, bold, first["size"])
    for c in st.contests:
        if not c["candidates"]:
            warnings.append(f"contest without candidates: {c['key']}")
    return [c for c in st.contests if c["candidates"]]


def classify_and_check(header, contests, warnings):
    """Return ``"template_blank"`` or ``"ok"`` and apply the vote-bound tie-out.

    ``template_blank``: every candidate in every contest has blank votes (kept as ``None``, never 0).  Otherwise
    ``ok``, with a warning when some votes are blank.  When the header carries a number voted, no contest may hold more
    votes than number voted x votes-per-voter (:class:`CompactTieOutError`).
    """
    blank = [cd["votes"] is None for c in contests for cd in c["candidates"]]
    status = "template_blank" if blank and all(blank) else "ok"
    if status == "ok" and any(blank):
        n_bad = sum(1 for c in contests if all(cd["votes"] is None for cd in c["candidates"]))
        warnings.append(f"{sum(blank)} candidate(s) with blank votes ({n_bad} contest(s) entirely blank); left as null")
    nv = header.get("number_voted")
    if status == "ok" and nv is not None:
        for c in contests:
            total = sum(cd["votes"] for cd in c["candidates"] if cd["votes"] is not None)
            if total > nv * (c.get("vote_for") or 1):
                raise CompactTieOutError(f"{c['key']}: {total} votes exceed number voted {nv} x vote-for {c.get('vote_for') or 1}")
    return status


# --------------------------------------------------------------------------------------------------------------------
# public entry point
# --------------------------------------------------------------------------------------------------------------------
def parse_compact_pdf(path, fetched_at=None):
    """Parse a Macomb compact summary PDF.

    Returns ``{"header", "contests", "parse_status", "warnings", "pages", "source"}``.  ``parse_status`` is
    ``"template_blank"`` when every candidate's votes are blank (votes stay ``None``), else ``"ok"``.  Raises
    :class:`CompactParseError` for an unreadable layout and :class:`CompactTieOutError` when printed header totals or
    vote bounds disagree with the parsed numbers.  ``fetched_at`` is echoed into ``source`` (the poller owns timestamps).
    """
    import pdfplumber

    warnings = []
    columns_by_page = []
    header_words = []
    with open(path, "rb") as fh:
        raw = fh.read()
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            head, cols = page_lines(page)
            if i == 1:
                header_words = head
            columns_by_page.append((i, cols))
            if len(cols) > 3:
                warnings.append(f"p{i}: {len(cols)} columns detected (expected <= 3)")
        n_pages = len(pdf.pages)
    if not columns_by_page:
        raise CompactParseError("no pages")
    header = parse_header(header_words, warnings)
    contests = parse_columns(columns_by_page, warnings)
    if not contests:
        raise CompactParseError("no contests found: layout not recognised")
    status = classify_and_check(header, contests, warnings)
    return {"header": header, "contests": contests, "parse_status": status, "warnings": warnings, "pages": n_pages,
            "source": {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "fetched_at": fetched_at}}


def main(argv=None):
    """CLI: ``python3 macomb_compact_pdf.py file.pdf`` prints a JSON summary of the parse."""
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: macomb_compact_pdf.py <pdf>", file=sys.stderr)
        return 2
    r = parse_compact_pdf(argv[0])
    print(json.dumps(r, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


# ---------------------------------------------------------------------------
# Live adapter used by tools/poll_macomb_pdf.py: compact-sheet contests → results-layer records.
# ---------------------------------------------------------------------------
import os
import re as _re
import tempfile as _tempfile

_PARTY = {"DEM": "D", "REP": "R", "LIB": "L", "GRN": "G", "UST": "U", "NLP": "N", "WC": "W", "WCP": "W", "NPA": "I"}


def compact_contest_id(contest):
    """Map a compact-sheet contest to the desk's Macomb contest ids (data/contests/macomb_2026.json)."""
    t = (contest.get("title") or "").upper().strip()
    d = _re.search(r"(\d+)(?:ST|ND|RD|TH)? DISTRICT", t + " " + (contest.get("district") or "").upper())
    n = int(d.group(1)) if d else None
    if t.startswith("GOVERNOR"):
        return "macomb-gov"
    if t.startswith("U.S. SENATOR") or t.startswith("UNITED STATES SENATOR"):
        return "macomb-ussen"
    if t.startswith("SECRETARY OF STATE"):
        return "macomb-sos"
    if t.startswith("ATTORNEY GENERAL"):
        return "macomb-ag"
    if n is not None and ("REPRESENTATIVE IN CONGRESS" in t or t.startswith("U.S. REPRESENTATIVE") or "CONGRESS" in t):
        return f"macomb-mi{n:02d}"
    if n is not None and "STATE SENATOR" in t:
        return f"macomb-sd{n:02d}"
    if n is not None and "STATE REPRESENTATIVE" in t:
        return f"macomb-hd{n:02d}"
    if t.startswith("COUNTY EXECUTIVE"):
        return "macomb-countyexec"
    if t.startswith("COUNTY COMMISSIONER") and n is not None:
        return f"macomb-commission_d{n}"
    return "macomb-other:" + _re.sub(r"[^a-z0-9]+", "-", (contest.get("key") or t).lower()).strip("-")


def compact_to_records(parsed, source_id="macomb_clerk_unofficial_summary_pdf", snapshot_id=None, as_of=None):
    recs = []
    hdr = parsed.get("header", {})
    for c in parsed.get("contests", []):
        cid = compact_contest_id(c)
        for k in c.get("candidates", []):
            recs.append({"layer": "results", "contest_id": cid, "contest_name": c.get("title"), "section": c.get("section"), "jurisdiction": c.get("jurisdiction"),
                         "unit": "county", "mode": "TOTAL", "candidate": k.get("name"), "party": _PARTY.get(k.get("party"), k.get("party")), "party_raw": k.get("party"),
                         "votes": k.get("votes"), "write_in": bool(k.get("write_in")), "county_scope": "macomb_portion" if c.get("multi_county") else "macomb_only",
                         "official_flag": hdr.get("official_flag"), "number_voted": hdr.get("number_voted"), "source_id": source_id, "snapshot_id": snapshot_id, "as_of": as_of, "unofficial": True})
    return recs


def parse_compact_pdf_bytes(raw, fetched_at=None):
    """Entry point for the poller: returns {"parse_status", "records", "header", "warnings"}; records are empty for a blank template."""
    with _tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as fh:
        fh.write(raw)
        path = fh.name
    try:
        parsed = parse_compact_pdf(path, fetched_at=fetched_at)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
    recs = [] if parsed.get("parse_status") == "template_blank" else compact_to_records(parsed)
    return {"parse_status": parsed.get("parse_status"), "records": recs, "header": parsed.get("header"), "warnings": parsed.get("warnings", []), "contests": len(parsed.get("contests", []))}
