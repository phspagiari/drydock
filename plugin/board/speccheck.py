#!/usr/bin/env python3
"""Lint a spec's body: the criteria a spec gates on must mean what they say.

    python3 <PLUGIN_HOME>/board/speccheck.py <SPEC.md> [<SPEC.md>...]

Prints one line per violation::

    <path>:<line>: <RULE-ID> <row-or-block id>: <what is wrong>

Exit 0 when every file passes, 1 when any rule fires, 2 on a usage error, an
unreadable path, or a file that is neither a spec (no ``## Acceptance
criteria`` table) nor a plan (no ``## Tasks`` table) -- so a mistyped path
cannot read as clean. Warnings go to stderr and never change the exit code.

Rules, by id. Hard rules take no waiver; the rest are silenced by an
annotation in the comment block directly beneath the Acceptance table::

    <!-- speccheck-ok: <row-id> <RULE-ID> — <reason> -->

``R1-command-is-a-command`` (hard)
    Every Acceptance row's Command cell holds at least one code span.
``R2-pre-pr-runnable``
    No Command or Pass-condition cell presupposes a pull request, a merge, a
    deploy or a human (``R2_TOKENS``, minus the local git forms in
    ``R2_EXCLUDE``).
``R3-verbatim-no-run-claims``
    Text inside a ``verbatim:<name>`` fenced block does not count the run
    producing it or claim that run is exhausted.
``R4-verbatim-block-delimited`` (hard)
    A requirement saying *verbatim* (outside code spans and comments) names
    a ``verbatim:<name>`` block that exists.
``R5-artifact-read-is-scoped``
    A Command naming ``READY.md``, ``RUN.md``, ``DELIVERABLE.md``,
    ``QUESTION.md`` or ``REVIEW*.md`` reads a region, not the whole file:
    a range (``R5_SCOPES``), not a single-pattern filter.
``R6-extraction-asserted``
    A Command that extracts a region asserts its line count, or the row
    names another row that does.
``R7-verbatim-claim-is-tested``
    Some Acceptance row names each ``verbatim:<name>`` block.
``R8-stale-waiver`` (hard)
    A waiver names an existing row (or block, requirement or ``L<line>``),
    an existing rule, and a rule that is not hard.
``R9-marker-token-not-reproduced``
    The clarification token appears only inside real markers, as
    ``queue_rules.find_markers`` finds them, or in comments.
``R10-absence-has-control``
    A Pass condition asserting absence also asserts a positive control.
``R11-state-predicates-declared`` (hard)
    ``## Constraints & blast radius`` carries a non-empty **State
    predicates** label. A spec created before ``R11_SINCE``, or with no
    parseable ``created:``, gets a stderr warning instead.

Rows of the ``## Ship criteria`` table are exempt from every row rule: that
table holds what only the ship step can evaluate.

A plan -- a file whose ``## Tasks`` table header is ``| # | Task | Files |
Verify | After |`` -- gets ``R1`` on its Verify column and nothing else.

This module lints spec bodies only. Whether a spec is dispatchable
(frontmatter, clarification markers) is ``queue_rules.py``'s question.

Standard library only, like the rest of ``board/``.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import NamedTuple

import queue_rules

# --------------------------------------------------------------------------
# rules
# --------------------------------------------------------------------------

#: Every rule id, keyed by its short form. Waivers may use either form.
RULES = {
    "R1": "R1-command-is-a-command",
    "R2": "R2-pre-pr-runnable",
    "R3": "R3-verbatim-no-run-claims",
    "R4": "R4-verbatim-block-delimited",
    "R5": "R5-artifact-read-is-scoped",
    "R6": "R6-extraction-asserted",
    "R7": "R7-verbatim-claim-is-tested",
    "R8": "R8-stale-waiver",
    "R9": "R9-marker-token-not-reproduced",
    "R10": "R10-absence-has-control",
    "R11": "R11-state-predicates-declared",
}

#: Rules no waiver can silence: a waiver naming one is itself an ``R8``.
HARD_RULES = frozenset({"R1", "R4", "R8", "R11"})

#: What a criterion runnable before any pull request exists must not mention.
#: Bare ``CI``, ``ship`` and ``review`` are deliberately absent: criteria
#: legitimately name CI's pinned tool versions, the ship-criteria table and
#: review files, and none of those presupposes a pull request.
#: The bare abbreviation is matched upper-case only, so the ``-pr`` tail of a
#: branch or item slug is not read as a pull request.
R2_TOKENS = (
    ("a pull request", re.compile(r"(?i:\bpull[ -]requests?\b|\bgh\s+pr\b)"
                                  r"|\bPRs?\b")),
    ("a merge", re.compile(r"\bmerg(?:e|es|ed|ing)\b", re.I)),
    ("a deploy", re.compile(r"\bdeploy(?:s|ed|ing|ment|ments)?\b", re.I)),
    ("a human", re.compile(r"\bhumans?\b|\bmanual(?:ly)?\b|\bsign[- ]?off\b"
                           r"|\bapprov(?:e|es|ed|al)\b", re.I)),
)

#: Local forms that name a merge or a pull request without presupposing one:
#: git verbs, and the READY.md section holding the prepared text a criterion
#: may extract before any pull request exists. Removed from a cell before
#: ``R2_TOKENS`` scans it, longest first.
R2_EXCLUDE = ("git merge-base", "merge-base", "git merge", "--no-merges",
              "Prepared PR text")


class Violation(NamedTuple):
    path: str
    line: int
    rule: str      # short id, e.g. "R1"
    ident: str     # the row id or block name the rule fired on
    message: str

    def render(self) -> str:
        return f"{self.path}:{self.line}: {RULES[self.rule]} {self.ident}: {self.message}"


# --------------------------------------------------------------------------
# parsing
# --------------------------------------------------------------------------

#: A fence opener or closer: up to three spaces, then three or more of one char.
FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")

#: A cell boundary: a pipe no backslash escapes.
CELL_SPLIT_RE = re.compile(r"(?<!\\)\|")

#: A table's delimiter row.
TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$")


def code_spans(text: str) -> list[tuple[int, int, str]]:
    """``(start, end, content)`` of every inline code span in ``text``.

    A backtick run with no closing run of the same length is literal.
    """
    spans = []
    i, n = 0, len(text)
    while i < n:
        if text[i] != "`":
            i += 1
            continue
        run = n - i - len(text[i:].lstrip("`"))
        m = re.compile(rf"(?<!`){'`' * run}(?!`)").search(text, i + run)
        if m:
            spans.append((i, m.end(), text[i + run:m.start()]))
            i = m.end()
        else:
            i += run
    return spans


def _mask_line(line: str, in_comment: bool, spans: bool) -> tuple[str, bool]:
    """``line`` with HTML comments (and, if ``spans``, code spans) blanked.

    Same length as ``line``. ``in_comment`` says whether a comment opened on
    an earlier line is still open; the second value, whether one is after.
    """
    out = list(line)
    i, n = 0, len(line)
    while i < n:
        if in_comment:
            close = line.find("-->", i)
            end = n if close < 0 else close + 3
            out[i:end] = " " * (end - i)
            i, in_comment = end, close < 0
        elif line.startswith("<!--", i):
            in_comment = True
            out[i:i + 4] = "    "
            i += 4
        elif spans and line[i] == "`":
            found = code_spans(line[i:])
            if found and found[0][0] == 0:
                end = i + found[0][1]
                out[i:end] = " " * (end - i)
                i = end
            else:
                i += n - i - len(line[i:].lstrip("`"))
        else:
            i += 1
    return "".join(out), in_comment


@dataclass
class Row:
    line: int                 # 1-based
    ident: str                # the first cell, e.g. "AC-3"
    cells: dict[str, str]     # header name -> cell text, ``\\|`` unescaped


@dataclass
class Table:
    path: str
    line: int                 # the header row, 1-based
    header: list[str]
    rows: list[Row]
    end: int                  # the line after the last row, 1-based
    command_col: str = "Command"


@dataclass
class Doc:
    path: str
    text: str
    lines: list[str] = field(default_factory=list)
    #: fences, comments and code spans blanked
    masked: list[str] = field(default_factory=list)
    #: comments blanked, everything else raw
    uncommented: list[str] = field(default_factory=list)
    #: ``(title, heading line, end line exclusive)`` for every ``## `` heading
    sections: list[tuple[str, int, int]] = field(default_factory=list)
    #: ``verbatim:<name>`` fenced blocks: name -> (opener line, body lines)
    blocks: dict[str, tuple[int, list[str]]] = field(default_factory=dict)


def parse(path: str, text: str) -> Doc:
    """Split ``text`` into masked views, sections and ``verbatim:`` blocks."""
    doc = Doc(path, text)
    # split("\n"), not splitlines(): line numbers must agree with grep -n.
    doc.lines = text.split("\n")
    fence, block = "", None
    in_comment = False
    for lineno, line in enumerate(doc.lines, 1):
        if fence:
            m = FENCE_RE.match(line)
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence) \
                    and not line[m.end():].strip():
                fence, block = "", None
            elif block is not None:
                doc.blocks[block][1].append(line)
            doc.masked.append(" " * len(line))
            doc.uncommented.append(line)
            continue
        if not in_comment:
            m = FENCE_RE.match(line)
            info = line[m.end():].strip() if m else ""
            # A backtick fence's info string may not contain a backtick.
            if m and not (m.group(1)[0] == "`" and "`" in info):
                fence = m.group(1)
                vm = re.match(r"verbatim:([\w.-]+)", info)
                if vm:
                    block = vm.group(1)
                    doc.blocks[block] = (lineno, [])
                doc.masked.append(" " * len(line))
                doc.uncommented.append(line)
                continue
        uncommented, _ = _mask_line(line, in_comment, spans=False)
        masked, in_comment = _mask_line(line, in_comment, spans=True)
        doc.uncommented.append(uncommented)
        doc.masked.append(masked)
    heads = [(i + 1, m[3:].strip()) for i, m in enumerate(doc.masked)
             if m.startswith("## ")]
    for k, (lineno, title) in enumerate(heads):
        end = heads[k + 1][0] if k + 1 < len(heads) else len(doc.lines) + 1
        doc.sections.append((title, lineno, end))
    return doc


def section(doc: Doc, prefix: str) -> tuple[int, int] | None:
    """``(heading line, end line exclusive)`` of the first section so titled."""
    for title, start, end in doc.sections:
        if title.lower().startswith(prefix.lower()):
            return start, end
    return None


def split_cells(line: str) -> list[str]:
    """A table line's cells, split on unescaped pipes, ``\\|`` kept as ``|``."""
    body = line.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    return [c.strip().replace("\\|", "|") for c in CELL_SPLIT_RE.split(body)]


def tables_in(doc: Doc, start: int, end: int, command_col: str = "Command") -> list[Table]:
    """Every pipe table between two 1-based lines, fenced ones excluded."""
    found = []
    i = start
    while i < end - 1:
        line, nxt = doc.lines[i - 1], doc.lines[i]
        if doc.masked[i - 1].strip().startswith("|") and TABLE_SEP_RE.match(nxt):
            header = split_cells(line)
            rows = []
            j = i + 2
            while j < end and doc.masked[j - 1].strip().startswith("|"):
                cells = split_cells(doc.lines[j - 1])
                rows.append(Row(j, cells[0] if cells else "",
                                dict(zip(header, cells, strict=False))))
                j += 1
            found.append(Table(doc.path, i, header, rows, j, command_col))
            i = j
        else:
            i += 1
    return found


def acceptance_table(doc: Doc) -> Table | None:
    """The first table under ``## Acceptance criteria`` with a Command column."""
    sec = section(doc, "Acceptance criteria")
    if sec is None:
        return None
    for table in tables_in(doc, *sec):
        if "Command" in table.header:
            return table
    return None


# --------------------------------------------------------------------------
# row rules
# --------------------------------------------------------------------------

def r1_command_is_a_command(table: Table) -> list[Violation]:
    """Every row's command cell carries at least one code span."""
    return [Violation(table.path, row.line, "R1", row.ident,
                      f"the {table.command_col} cell holds no code span, so it is "
                      "prose, not a command")
            for row in table.rows
            if not code_spans(row.cells.get(table.command_col, ""))]


def r2_pre_pr_runnable(table: Table) -> list[Violation]:
    """No command or pass cell presupposes a pull request, merge, deploy or human."""
    out = []
    for row in table.rows:
        for col in (table.command_col, "Pass condition"):
            text = row.cells.get(col, "")
            for form in R2_EXCLUDE:
                text = re.sub(re.escape(form), " ", text, flags=re.I)
            for what, token in R2_TOKENS:
                m = token.search(text)
                if m:
                    out.append(Violation(
                        table.path, row.line, "R2", row.ident,
                        f"the {col} cell says {m.group(0)!r}, which presupposes "
                        f"{what}; the executor stops before one exists -- move "
                        "the row to Ship criteria"))
    return out


#: The drydock artifacts a criterion's own report may be written into. Review
#: files are ``REVIEW.md`` and ``REVIEW-<suffix>.md``; the ``REVIEWER.md``
#: contract is a repo source, not a report.
R5_ARTIFACT_RE = re.compile(
    r"\b(?:READY|RUN|DELIVERABLE|QUESTION)\.md\b|\bREVIEW(?:-[\w.-]+)?\.md\b")

_ADDR = r"(?:\d+|\$|/(?:[^/\\]|\\.)*/)"

#: Constructs that read a region instead of a whole file, and their output
#: redirected into a file is the extract a later grep reads:
#:
#: - a ``sed -n`` script opening with an address pair (``'/a/,/b/p'``,
#:   ``'1,20p'``, ``'/a/,$p'``);
#: - an ``awk`` program holding two addresses joined by a comma
#:   (``'/a/,/b/'``), a flag or counter an action sets and a later pattern
#:   tests (``'/a/{f=1} f'``, ``'/^```/{n++; next} n==1'``), or an ``NR``
#:   comparison (``'NR>3'``);
#: - the named-section extractor.
#:
#: A single-pattern filter (``sed -n '/x/p'``, ``awk '/x/'``) visits every
#: line of the file -- it is ``grep`` spelled differently -- so it is no
#: scope.
R5_SCOPES = (
    re.compile(rf"\bsed\s+(?:-[a-zA-Z]+\s+)*?-[a-zA-Z]*n[a-zA-Z]*\s+"
               rf"(?:-[a-zA-Z]+\s+)*['\"]?\s*{_ADDR}\s*,\s*(?:{_ADDR}|[+~]\d+)"),
    re.compile(r"\bawk\b[^'\"]*(['\"])(?:(?!\1).)*?"
               r"(?:/(?:[^/\\]|\\.)*/\s*,\s*/(?:[^/\\]|\\.)*/"
               r"|\{[^}]*\b([A-Za-z_]\w*)\s*(?:=\s*\d+|\+\+)[^}]*\}"
               r"(?:(?!\1).)*?(?<![\w$])\2\s*(?:&&|\|\||[<>!=]=|[<>]|\{|\1)"
               r"|\bNR\s*(?:[<>]=?|[!=]=)\s*\d|\d\s*(?:[<>]=?|[!=]=)\s*NR\b)"),
    re.compile(r"\bpr_text\.py\s+extract\b"),
)

#: A boundary assertion: the extract's line count.
R6_ASSERT_RE = re.compile(r"\bwc\s+-l\b")


def r5_artifact_read_is_scoped(table: Table) -> list[Violation]:
    """A command naming a drydock artifact reads a region of it, not the file."""
    out = []
    for row in table.rows:
        cmd = row.cells.get(table.command_col, "")
        m = R5_ARTIFACT_RE.search(cmd)
        if m and not any(scope.search(cmd) for scope in R5_SCOPES):
            out.append(Violation(
                table.path, row.line, "R5", row.ident,
                f"reads {m.group(0)} whole; the criterion's own report lands in "
                "that file, so scope the read to the region under test"))
    return out


def r6_extraction_asserted(table: Table) -> list[Violation]:
    """A row that extracts a region asserts its boundaries or names who does."""
    out = []
    for row in table.rows:
        cmd = row.cells.get(table.command_col, "")
        if not any(scope.search(cmd) for scope in R5_SCOPES):
            continue
        both = cmd + " " + row.cells.get("Pass condition", "")
        others = set(re.findall(r"\bAC-\d+\b", both)) - {row.ident}
        if not R6_ASSERT_RE.search(cmd) and not others:
            out.append(Violation(
                table.path, row.line, "R6", row.ident,
                "extracts a region without asserting its boundaries (wc -l) or "
                "naming the row that does, so a runaway extract reads as clean"))
    return out


#: Pass-condition phrasings that assert absence. A code span that is exactly
#: ``0`` is one too, unless it is an exit code (``R10_EXIT_WORDS``).
R10_ABSENCE = (
    re.compile(r"\bprints? nothing\b", re.I),
    re.compile(r"\bno output\b", re.I),
    re.compile(r"\breturns? nothing\b", re.I),
    re.compile(r"(?<!non-)\bempty\b", re.I),
    re.compile(r"\bdiff=0\b"),
)

#: A positive control in the same cell: one thing that must match.
R10_CONTROL = (
    re.compile(r"\bat least\b", re.I),
    re.compile(r"(?:≥|>=)\s*1\b"),
    re.compile(r"\bnon-empty\b", re.I),
    re.compile(r"\bpositive control\b", re.I),
)

#: The word immediately before a ``0`` span that makes it an exit code.
R10_EXIT_WORDS = ("exit", "exits")


def absence_claims(cell: str) -> list[str]:
    """The absence assertions in a pass-condition cell, as written."""
    found = [m.group(0) for rx in R10_ABSENCE for m in rx.finditer(cell)]
    for start, end, content in code_spans(cell):
        if content.strip() != "0":
            continue
        before = re.search(r"(\w+)\s*$", cell[:start])
        if before and before.group(1).lower() in R10_EXIT_WORDS:
            continue
        found.append(cell[start:end])
    return found


def r10_absence_has_control(table: Table) -> list[Violation]:
    """A pass condition asserting absence also asserts a positive control."""
    out = []
    for row in table.rows:
        cell = row.cells.get("Pass condition", "")
        claims = absence_claims(cell)
        if claims and not any(rx.search(cell) for rx in R10_CONTROL):
            out.append(Violation(
                table.path, row.line, "R10", row.ident,
                f"passes on {claims[0]!r} with no positive control in the same "
                "cell, so a broken matcher reads as a clean result"))
    return out


# --------------------------------------------------------------------------
# verbatim rules
# --------------------------------------------------------------------------

#: What a frozen text must not count: the run that produces it.
R3_RUN_NOUNS = ("commit", "finding", "round", "file", "site", "line")

#: Number words that quantify a run noun as well as a numeral does.
R3_NUMBER_WORDS = ("one", "two", "three", "four", "five", "six", "seven", "eight",
                   "nine", "ten", "eleven", "twelve", "twenty", "dozen", "hundred")

#: Claims that the run producing a frozen text is exhausted.
R3_EXHAUSTIVE = ("only", "never", "no other", "the last")

R3_COUNT_RE = re.compile(
    rf"\b(?:\d+|{'|'.join(R3_NUMBER_WORDS)})\s+(?:{'|'.join(R3_RUN_NOUNS)})(?:e?s)?\b",
    re.I)
R3_EXHAUSTIVE_RE = re.compile(rf"\b(?:{'|'.join(R3_EXHAUSTIVE)})\b", re.I)

VERBATIM_WORD_RE = re.compile(r"\bverbatim\b", re.I)
VERBATIM_NAME_RE = re.compile(r"verbatim:([\w.-]+)")
BULLET_RE = re.compile(r"^[-*+] ")


def requirement_units(doc: Doc) -> list[tuple[int, int, str]]:
    """``(first line, end line exclusive, id)`` per requirement in ``## Requirements``.

    A requirement is a top-level bullet with everything nested under it, or
    a paragraph outside any bullet. Its id is the first ``FR-n`` it names,
    else ``L<first line>``.
    """
    sec = section(doc, "Requirements")
    if sec is None:
        return []
    units: list[list[int]] = []
    prev_blank = True
    for lineno in range(sec[0] + 1, sec[1]):
        line = doc.masked[lineno - 1]
        if not line.strip():
            prev_blank = True
            continue
        starts = BULLET_RE.match(line) or line.startswith("#") \
            or (prev_blank and not line[0].isspace())
        if starts or not units:
            units.append([lineno, lineno + 1])
        else:
            units[-1][1] = lineno + 1
        prev_blank = False
    out = []
    for start, end in units:
        fr = re.search(r"\bFR-\d+\b", "\n".join(doc.lines[start - 1:end - 1]))
        out.append((start, end, fr.group(0) if fr else f"L{start}"))
    return out


def r4_verbatim_block_delimited(doc: Doc) -> list[Violation]:
    """A requirement saying *verbatim* names a ``verbatim:<name>`` block that exists.

    Code spans and comments are masked first, so a requirement discussing the
    rule quotes the word in a code span.
    """
    out = []
    for start, end, ident in requirement_units(doc):
        hit = next((n for n in range(start, end)
                    if VERBATIM_WORD_RE.search(doc.masked[n - 1])), None)
        if hit is None:
            continue
        raw = "\n".join(doc.lines[start - 1:end - 1])
        if any(name in doc.blocks for name in VERBATIM_NAME_RE.findall(raw)):
            continue
        out.append(Violation(doc.path, hit, "R4", ident,
                             "says verbatim but names no verbatim:<name> fenced "
                             "block in this spec, so the frozen text has no "
                             "surface to check"))
    return out


def r3_verbatim_no_run_claims(doc: Doc) -> list[Violation]:
    """Inside ``verbatim:`` blocks: no tally of the run, no exhaustiveness claim."""
    out = []
    for name, (opener, body) in doc.blocks.items():
        for k, line in enumerate(body, 1):
            for m in list(R3_COUNT_RE.finditer(line)) + list(R3_EXHAUSTIVE_RE.finditer(line)):
                out.append(Violation(doc.path, opener + k, "R3", name,
                                     f"frozen text says {m.group(0)!r}, a claim "
                                     "about the run producing it that the run "
                                     "can falsify"))
    return out


def r7_verbatim_claim_is_tested(doc: Doc, table: Table) -> list[Violation]:
    """Some Acceptance row names each ``verbatim:`` block in its Check or Pass cell."""
    out = []
    for name, (opener, _) in doc.blocks.items():
        named = re.compile(rf"(?<![\w-]){re.escape(name)}(?![\w-])")
        if not any(named.search(row.cells.get(col, ""))
                   for row in table.rows for col in ("Check", "Pass condition")):
            out.append(Violation(doc.path, opener, "R7", name,
                                 "no Acceptance row names this block in its "
                                 "Check or Pass condition, so nothing proves "
                                 "the frozen text is true"))
    return out


# --------------------------------------------------------------------------
# marker token
# --------------------------------------------------------------------------

def marker_token() -> str:
    """The clarification token, read off ``queue_rules.MARKER_RE``.

    The pattern opens ``\\[``, spells the token up to its colon, and writes
    the space as ``[ ]``; undoing that is all it takes, so this module never
    spells the token and never defines a second marker matcher.
    """
    pattern = queue_rules.MARKER_RE.pattern
    if pattern.startswith("\\["):
        pattern = pattern[2:]
    return pattern.split(":", 1)[0].replace("[ ]", " ")


def r9_marker_token_not_reproduced(doc: Doc, table: Table) -> list[Violation]:
    """The token appears only inside real markers (or in comments).

    Per line: the token's occurrences outside HTML comments, minus the real
    markers ``queue_rules.find_markers`` reports there. A remainder is a
    mention that a whole-file count of the token would read as a marker.
    """
    token = marker_token()
    real: dict[int, int] = {}
    for lineno, _ in queue_rules.find_markers(doc.text):
        real[lineno] = real.get(lineno, 0) + 1
    rows = {row.line: row.ident for row in table.rows}
    out = []
    for lineno, line in enumerate(doc.uncommented, 1):
        extra = line.count(token) - real.get(lineno, 0)
        if extra > 0:
            out.append(Violation(
                doc.path, lineno, "R9", rows.get(lineno, f"L{lineno}"),
                "reproduces the clarification token outside a real marker; "
                "describe the marker (bracketed, a colon, a body) instead"))
    return out


# --------------------------------------------------------------------------
# state predicates
# --------------------------------------------------------------------------

#: The day ``R11`` became a rule. A spec ``created:`` on or after it fails R11;
#: an older one, or one with no parseable ``created:``, gets a warning.
R11_SINCE = date(2026, 9, 29)

STATE_LABEL_RE = re.compile(r"\*\*State predicates\*\*", re.I)

#: A line that opens the next labelled item, ending the label's body.
NEXT_LABEL_RE = re.compile(r"^\s*(?:[-*+]\s+)?\*\*|^#")


def created_of(doc: Doc) -> date | None:
    """The frontmatter ``created:`` date, or ``None`` when it does not parse."""
    value = queue_rules.field(doc.text, "created").split("#")[0].strip()
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def state_predicates_missing(doc: Doc) -> tuple[int, str] | None:
    """``(line, why)`` when Constraints carries no labelled, non-empty body."""
    sec = section(doc, "Constraints")
    if sec is None:
        return 1, "the spec has no ## Constraints & blast radius section"
    start, end = sec
    for lineno in range(start + 1, end):
        m = STATE_LABEL_RE.search(doc.masked[lineno - 1])
        if not m:
            continue
        body = [doc.uncommented[lineno - 1][m.end():]]
        for k in range(lineno + 1, end):
            if NEXT_LABEL_RE.match(doc.masked[k - 1]):
                break
            body.append(doc.uncommented[k - 1])
        if re.search(r"\w", " ".join(body)):
            return None
        return lineno, "the State predicates label has an empty body"
    return start, ("Constraints carries no **State predicates** label naming "
                   "who writes each disk or git state the spec branches on "
                   "(write none if nothing does)")


def r11_state_predicates_declared(doc: Doc) -> tuple[list[Violation], list[str]]:
    """``(violations, warnings)``: hard from ``R11_SINCE``, a warning before it."""
    missing = state_predicates_missing(doc)
    if missing is None:
        return [], []
    line, why = missing
    created = created_of(doc)
    if created is not None and created >= R11_SINCE:
        return [Violation(doc.path, line, "R11", "Constraints", why)], []
    when = (f"created: {created.isoformat()} is before {R11_SINCE.isoformat()}"
            if created else "no parseable created:")
    return [], [f"{doc.path}:{line}: {RULES['R11']} warning: {why} ({when}, "
                "so not blocking)"]


# --------------------------------------------------------------------------
# waivers
# --------------------------------------------------------------------------

#: ``<!-- speccheck-ok: <row-id> <RULE-ID> — <reason> -->``
WAIVER_RE = re.compile(r"^<!--\s*speccheck-ok:\s*(\S+)\s+(\S+)")


class Waiver(NamedTuple):
    line: int
    ident: str
    rule: str      # as written: short or full id


def rule_of(token: str) -> str | None:
    """The short id a waiver's rule token names, or ``None``."""
    if token in RULES:
        return token
    for short, full in RULES.items():
        if token == full:
            return short
    return None


def waivers_beneath(doc: Doc, table: Table) -> list[Waiver]:
    """The annotations in the comment block directly beneath ``table``.

    Blank lines may precede and separate the comments; a comment may span
    several lines. The first line that is neither blank nor part of a comment
    ends the block, so an annotation anywhere else -- a syntax example in a
    code span, say -- is not a waiver.
    """
    found = []
    i = table.end
    while i <= len(doc.lines):
        line = doc.lines[i - 1].strip()
        if not line:
            i += 1
            continue
        if not line.startswith("<!--"):
            break
        start, parts = i, []
        while i <= len(doc.lines):
            parts.append(doc.lines[i - 1].strip())
            i += 1
            if "-->" in parts[-1]:
                break
        m = WAIVER_RE.match(" ".join(parts))
        if m:
            found.append(Waiver(start, m.group(1), m.group(2)))
    return found


def known_idents(doc: Doc, table: Table) -> set[str]:
    """Every id a waiver may name: rows, ``verbatim:`` blocks, FRs, ``L<n>``."""
    idents = {row.ident for row in table.rows} | set(doc.blocks)
    idents |= set(re.findall(r"\bFR-\d+\b", doc.text))
    idents |= {f"L{n}" for n in range(1, len(doc.lines) + 1)}
    return idents


def r8_stale_waiver(doc: Doc, table: Table, waivers: list[Waiver]) -> list[Violation]:
    """A waiver naming a missing id, an unknown rule, or a hard rule."""
    idents = known_idents(doc, table)
    out = []
    for w in waivers:
        rule = rule_of(w.rule)
        if rule is None:
            why = f"names no rule: {w.rule!r}"
        elif rule in HARD_RULES:
            why = f"names {RULES[rule]}, a hard rule no waiver can silence"
        elif w.ident not in idents:
            why = f"names {w.ident!r}, which is not a row, block or requirement here"
        else:
            continue
        out.append(Violation(doc.path, w.line, "R8", w.ident, f"the waiver {why}"))
    return out


def apply_waivers(found: list[Violation], waivers: list[Waiver]) -> list[Violation]:
    """``found`` minus every waivable violation a waiver names."""
    waived = {(w.ident, rule_of(w.rule)) for w in waivers}
    return [v for v in found
            if v.rule in HARD_RULES or (v.ident, v.rule) not in waived]


# --------------------------------------------------------------------------
# driver
# --------------------------------------------------------------------------

PLAN_HEADER = ["#", "Task", "Files", "Verify", "After"]


class NotASpec(Exception):
    """Neither an Acceptance criteria table nor a plan's Tasks table."""


def plan_table(doc: Doc) -> Table | None:
    """A plan's ``## Tasks`` table, recognised by its exact header."""
    sec = section(doc, "Tasks")
    if sec is None:
        return None
    for table in tables_in(doc, *sec, command_col="Verify"):
        if table.header == PLAN_HEADER:
            return table
    return None


def check(path: str, text: str) -> tuple[list[Violation], list[str]]:
    """``(violations, warnings)`` for one file; raises :class:`NotASpec`."""
    doc = parse(path, text)
    plan = plan_table(doc)
    if plan is not None:
        return r1_command_is_a_command(plan), []
    table = acceptance_table(doc)
    if table is None:
        raise NotASpec("no ## Acceptance criteria table with a Command column "
                       "and no plan ## Tasks table")
    waivers = waivers_beneath(doc, table)
    found = (r1_command_is_a_command(table) + r2_pre_pr_runnable(table)
             + r3_verbatim_no_run_claims(doc) + r4_verbatim_block_delimited(doc)
             + r5_artifact_read_is_scoped(table) + r6_extraction_asserted(table)
             + r7_verbatim_claim_is_tested(doc, table)
             + r9_marker_token_not_reproduced(doc, table)
             + r10_absence_has_control(table))
    found = apply_waivers(found, waivers) + r8_stale_waiver(doc, table, waivers)
    r11, warnings = r11_state_predicates_declared(doc)
    return sorted(found + r11, key=lambda v: (v.line, v.rule)), warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="speccheck", description="lint a spec's criteria and requirements")
    parser.add_argument("paths", nargs="+", metavar="SPEC.md")
    args = parser.parse_args(argv)

    rc = 0
    for path in args.paths:
        try:
            text = Path(path).read_text(errors="replace")
            found, warnings = check(path, text)
        except OSError as exc:
            print(f"speccheck: cannot read {path}: {exc.strerror or exc}",
                  file=sys.stderr)
            rc = 2
            continue
        except NotASpec as exc:
            print(f"speccheck: {path}: {exc}", file=sys.stderr)
            rc = 2
            continue
        for warning in warnings:
            print(warning, file=sys.stderr)
        for v in found:
            print(v.render())
        if found and rc == 0:
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
