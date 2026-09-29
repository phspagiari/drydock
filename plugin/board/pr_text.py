#!/usr/bin/env python3
"""A READY.md's prepared pull-request text, extracted, digested and verified.

    python3 <PLUGIN_HOME>/board/pr_text.py extract <READY.md> --title-out F --body-out F
    python3 <PLUGIN_HOME>/board/pr_text.py base <READY.md>
    gh pr view <url> --json title,body | python3 <PLUGIN_HOME>/board/pr_text.py digest
    gh pr view <url> --json title,body \\
        | python3 <PLUGIN_HOME>/board/pr_text.py verify <title-file> <body-file>

The prepared text lives in one section of READY.md::

    ## Prepared PR text

    pr_text_base: <64 lowercase hex>      (only when the PR already exists)

    ### Title

    ````
    <one line>
    ````

    ### Body

    ````
    <the whole body, verbatim>
    ````

Four backticks because a body carries three-backtick fences and ``##``
headings of its own. Headings and fences are recognised only outside fences:
a ``## `` line inside the body fence does not end the section, and a
``### Title`` inside some other fence is not the title. The section ends at
the next ``# `` or ``## `` heading outside a fence.

``extract`` writes the title as its one line plus a newline and the body as
the fence content verbatim plus a newline. Exit 0; exit 2 with one stderr line
naming the first rule broken, checked in this order: the section, ``### Title``,
``### Body``, the title's fence (exactly one, opened with exactly four
backticks, closed), the body's fence (same), an empty title, a title of more
than one line.

``base`` prints the ``pr_text_base:`` value -- one line, inside the section,
outside any fence, before ``### Title``. Exit 2 when it is absent, repeated,
misplaced or not 64 lowercase hex digits.

``digest`` reads ``gh pr view --json title,body`` JSON on stdin (other keys
ignored) and prints the sha256 hex of ``N(title) + "\\n\\x00\\n" + N(body)``,
UTF-8, where ``N`` turns CRLF into LF and strips trailing newlines: GitHub
appends a newline to a body, and a web edit may store CRLF. Exit 2 on bad JSON
or a missing or non-string ``title``/``body``.

``verify`` compares the same JSON with a title file and a body file under
``N``: exit 0 when both match, exit 1 with a unified diff on stderr when
either differs, exit 2 when a file is unreadable or the JSON is bad.

Usage errors exit 2. Standard library only.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import sys

SECTION = "## Prepared PR text"
TITLE = "### Title"
BODY = "### Body"
BASE_RE = re.compile(r"^pr_text_base:[ \t]*(\S*)[ \t]*$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
FENCE_OPEN_RE = re.compile(r"^ {0,3}(`{3,})[^`]*$")


class PrTextError(Exception):
    """A READY.md whose prepared text breaks a shape rule; str() names the rule."""


def normalise(text: str) -> str:
    """``N``: CRLF to LF, trailing newlines stripped."""
    return text.replace("\r\n", "\n").rstrip("\n")


# --------------------------------------------------------------------------
# fence-aware scanning
# --------------------------------------------------------------------------

def scan(lines: list[str]) -> list[tuple[bool, int, int]]:
    """Per line: (outside a fence, opener length if it opens one, 1 if it closes one).

    An opener is a run of three or more backticks (up to three spaces of
    indent, no backtick after it); it closes on a bare run of backticks at
    least as long. A fence left open runs to the end of the file.
    """
    out = []
    open_len = 0
    for line in lines:
        if open_len:
            bare = line.strip()
            closes = bool(bare) and set(bare) == {"`"} and len(bare) >= open_len \
                and len(line) - len(line.lstrip(" ")) <= 3
            out.append((False, 0, 1 if closes else 0))
            if closes:
                open_len = 0
            continue
        m = FENCE_OPEN_RE.match(line)
        if m:
            open_len = len(m.group(1))
            out.append((True, open_len, 0))
        else:
            out.append((True, 0, 0))
    return out


def section_bounds(lines: list[str], marks) -> tuple[int, int]:
    """[start, end) of the prepared-text section; raises when it is missing."""
    start = None
    for i, line in enumerate(lines):
        outside = marks[i][0]
        if not outside:
            continue
        if start is None:
            if line.rstrip() == SECTION:
                start = i
        elif line.startswith("# ") or line.startswith("## "):
            return start, i
    if start is None:
        raise PrTextError(f"{SECTION} missing")
    return start, len(lines)


def heading_at(lines, marks, start, end, heading) -> int | None:
    for i in range(start, end):
        if marks[i][0] and lines[i].rstrip() == heading:
            return i
    return None


def subsection_end(lines, marks, start, end) -> int:
    for i in range(start + 1, end):
        if marks[i][0] and re.match(r"^#{1,3} ", lines[i]):
            return i
    return end


def one_fence(lines, marks, start, end, heading) -> list[str]:
    """The content of the one four-backtick fence in [start, end), closed there too."""
    fences = []  # (opener index, opener length, close index or None)
    i = start
    while i < end:
        outside, opener, _ = marks[i]
        if outside and opener:
            close = None
            for j in range(i + 1, end):
                if marks[j][2]:
                    close = j
                    break
            fences.append((i, opener, close))
            if close is None:
                break
            i = close + 1
            continue
        i += 1
    if len(fences) != 1:
        raise PrTextError(f"{heading}: {len(fences)} fences, need exactly 1")
    first, opener, close = fences[0]
    if opener != 4:
        raise PrTextError(f"{heading}: fence opens with {opener} backticks, need 4")
    if close is None:
        raise PrTextError(f"{heading}: fence not closed")
    return lines[first + 1:close]


def split_lines(text: str) -> list[str]:
    return text.replace("\r\n", "\n").split("\n")


def extract_text(text: str) -> tuple[str, str]:
    """(title, body) from READY.md text; raises :class:`PrTextError`."""
    lines = split_lines(text)
    marks = scan(lines)
    start, end = section_bounds(lines, marks)
    t = heading_at(lines, marks, start + 1, end, TITLE)
    if t is None:
        raise PrTextError(f"{TITLE} missing")
    b = heading_at(lines, marks, start + 1, end, BODY)
    if b is None:
        raise PrTextError(f"{BODY} missing")
    title_lines = one_fence(lines, marks, t + 1,
                            subsection_end(lines, marks, t, end), TITLE)
    body_lines = one_fence(lines, marks, b + 1,
                           subsection_end(lines, marks, b, end), BODY)
    if not any(line.strip() for line in title_lines):
        raise PrTextError("title is empty")
    if len(title_lines) != 1:
        raise PrTextError(f"title spans {len(title_lines)} lines, need 1")
    return title_lines[0].strip(), "\n".join(body_lines)


def base_of(text: str) -> str:
    """The ``pr_text_base`` digest; raises :class:`PrTextError`."""
    lines = split_lines(text)
    marks = scan(lines)
    start, end = section_bounds(lines, marks)
    t = heading_at(lines, marks, start + 1, end, TITLE)
    found = [(i, m.group(1)) for i in range(start + 1, end)
             if marks[i][0] and (m := BASE_RE.match(lines[i]))]
    if not found:
        raise PrTextError("pr_text_base missing")
    if len(found) > 1:
        raise PrTextError(f"pr_text_base appears {len(found)} times, need 1")
    i, value = found[0]
    if t is not None and i > t:
        raise PrTextError(f"pr_text_base must precede {TITLE}")
    if not HEX64_RE.match(value):
        raise PrTextError("pr_text_base is not 64 lowercase hex digits")
    return value


def live_text(raw: str) -> tuple[str, str]:
    """(title, body) from ``gh pr view --json title,body`` output."""
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise PrTextError(f"stdin is not JSON: {exc}") from None
    if not isinstance(data, dict):
        raise PrTextError("stdin JSON is not an object")
    for key in ("title", "body"):
        if not isinstance(data.get(key), str):
            raise PrTextError(f"stdin JSON has no string {key!r}")
    return data["title"], data["body"]


def digest(title: str, body: str) -> str:
    joined = normalise(title) + "\n\x00\n" + normalise(body)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def differences(want_title: str, want_body: str,
                live_title: str, live_body: str) -> list[str]:
    """Unified-diff lines, empty when both match under ``N``."""
    out: list[str] = []
    for name, want, live in (("title", want_title, live_title),
                             ("body", want_body, live_body)):
        a, b = normalise(want), normalise(live)
        if a != b:
            out.extend(difflib.unified_diff(
                a.split("\n"), b.split("\n"),
                f"{name} (prepared)", f"{name} (pull request)", lineterm=""))
    return out


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def fail(msg: str) -> int:
    print(f"pr_text: {msg}", file=sys.stderr)
    return 2


def read(path: str) -> str:
    """The file as stored: CRLF is left for ``split_lines``/``normalise``."""
    try:
        with open(path, encoding="utf-8", newline="") as f:
            return f.read()
    except OSError as exc:
        raise PrTextError(f"cannot read {path}: {exc.strerror or exc}") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pr_text", description="a READY.md's prepared pull-request text")
    commands = parser.add_subparsers(dest="command", required=True)
    ext = commands.add_parser("extract", help="write the title and body to files")
    ext.add_argument("ready", metavar="READY.md")
    ext.add_argument("--title-out", required=True, metavar="F")
    ext.add_argument("--body-out", required=True, metavar="F")
    base = commands.add_parser("base", help="print the pr_text_base digest")
    base.add_argument("ready", metavar="READY.md")
    commands.add_parser("digest", help="digest of gh pr view JSON on stdin")
    ver = commands.add_parser("verify", help="compare gh pr view JSON on stdin")
    ver.add_argument("title_file", metavar="TITLE")
    ver.add_argument("body_file", metavar="BODY")
    args = parser.parse_args(argv)

    try:
        if args.command == "extract":
            title, body = extract_text(read(args.ready))
            try:
                with open(args.title_out, "w", encoding="utf-8", newline="") as f:
                    f.write(title + "\n")
                with open(args.body_out, "w", encoding="utf-8", newline="") as f:
                    f.write(body + "\n")
            except OSError as exc:
                return fail(f"cannot write: {exc.strerror or exc}")
            return 0
        if args.command == "base":
            print(base_of(read(args.ready)))
            return 0
        if args.command == "digest":
            print(digest(*live_text(sys.stdin.read())))
            return 0
        want_title, want_body = read(args.title_file), read(args.body_file)
        diff = differences(want_title, want_body, *live_text(sys.stdin.read()))
    except PrTextError as exc:
        return fail(str(exc))
    if diff:
        print("\n".join(diff), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
