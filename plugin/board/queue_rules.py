#!/usr/bin/env python3
"""The queue predicates the contracts gate on, as one tested implementation.

    python3 <PLUGIN_HOME>/board/queue_rules.py eligible [--root <STATE_HOME>]
    python3 <PLUGIN_HOME>/board/queue_rules.py check <SPEC.md> [<SPEC.md>...]
    python3 <PLUGIN_HOME>/board/queue_rules.py route <SPEC.md>

``eligible`` prints one tab-separated line per ``specs/inbox/<id>/SPEC.md``,
ids in lexicographic order::

    ELIGIBLE<TAB><id>
    WAITING<TAB><id><TAB><unmet id>,<unmet id>...

A ``depends_on`` id is met when ``<root>/deliverables/<id>/`` or
``<root>/archive/<id>/`` is a directory -- the same test the board applies to
every inbox card. Exit 0; exit 2 when the root or its ``specs/inbox`` is not a
directory.

``check`` prints ``<path>:<line>: marker: <body>`` for every clarification
marker, ``<path>:0: chain: <message>`` for every broken ``branch:`` /
``pr_url:`` pair and ``<path>:0: owner: <message>`` for an invalid ``owner:``.
Exit 0 when no file has any of them, 1 when any does, 2 on an unreadable path
or a usage error.

``route`` prints the one line that says who hears about a spec's events::

    owner<TAB><session name>
    human

and exits 0. An invalid ``owner:`` exits 2 with nothing on stdout and the
reason on stderr, and so does an unreadable path. The owner is read only from
the spec's frontmatter -- its first ```` ```yaml ```` fenced block -- by
:func:`owner_values`; ``field()`` is not used for it, because ``field()``
reads a key anywhere in the file.

A marker is the bracketed form -- the two words, a colon, a body holding at
least one non-blank character, all on one line -- and only outside fenced
code blocks, HTML comments and inline code spans. The bare bracketed words, an
empty body, and any mention inside code or a comment are not markers, so a
spec that describes the convention does not block itself. ``MARKER_RE`` spells
the space as ``[ ]`` so this file never matches a plain substring search.

The board (``server.py``) imports the parsers from here; this module imports
``server`` only inside :func:`main`, for the STATE_HOME default.

Standard library only.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# --------------------------------------------------------------------------
# frontmatter
# --------------------------------------------------------------------------

def field(text: str, key: str) -> str:
    """Value of a yaml-ish ``key: value`` line, quotes stripped."""
    m = re.search(rf"^\s*{re.escape(key)}:\s*(.+?)\s*$", text, re.M)
    return m.group(1).strip("'\"") if m else ""


def deps_of(spec: str) -> list[str]:
    """``depends_on`` ids — inline ``[a, b]`` or YAML block list, comments stripped."""
    m = re.search(r"^depends_on:[ \t]*(\[[^\]\n]*\])?[ \t]*(?:#[^\n]*)?"
                  r"((?:\n[ \t]*-[ \t]*[^\n]+)*)", spec, re.M)
    if not m:
        return []
    ids = re.findall(r"[\w][\w.-]{3,}", (m.group(1) or "").split("#")[0])
    for line in (m.group(2) or "").splitlines():
        mm = re.search(r"-[ \t]*([\w][\w.-]{3,})", line.split("#")[0])
        if mm:
            ids.append(mm.group(1))
    return ids


def unmet_deps(root: Path, spec: str) -> list[str]:
    """``depends_on`` ids with no directory in ``deliverables/`` or ``archive/``.

    Order is the spec's. A plain file of the same name does not count: the
    ship and archive moves always leave a directory.
    """
    return [d for d in deps_of(spec)
            if not ((root / "deliverables" / d).is_dir()
                    or (root / "archive" / d).is_dir())]


#: Branch names a chained spec may never declare: basing on one is not chaining,
#: it is committing to the branch every other spec is cut from.
DEFAULT_BRANCHES = frozenset({"main", "master"})


def _chain_field(spec: str, key: str) -> str:
    """A chain field's value, trailing ``# comment`` dropped.

    Frontmatter lines carry one (see ``templates/spec-template.md``) and
    :func:`field` keeps whatever follows the colon, comment included.
    """
    return field(spec, key).split("#")[0].strip().strip("'\"")


def chain_errors(spec: str) -> list[str]:
    """Why this spec's ``branch:``/``pr_url:`` pair cannot be dispatched.

    One human-readable message per violated rule; empty when the chain is
    dispatchable. Neither field set is the default path and valid, and
    ``branch:`` alone is valid too — it chains onto an existing branch and
    still opens a new pull request at ship.
    """
    branch = _chain_field(spec, "branch")
    pr_url = _chain_field(spec, "pr_url")
    errors = []
    if pr_url and not branch:
        errors.append("pr_url: is set without branch: — a pull request cannot be "
                      "pushed to without naming the branch it tracks")
    if branch in DEFAULT_BRANCHES:
        errors.append(f"branch: is {branch} — that commits to the default branch "
                      "instead of chaining onto work in flight")
    return errors


# --------------------------------------------------------------------------
# owner
# --------------------------------------------------------------------------

#: The frontmatter block's opening fence: the template writes exactly this.
YAML_FENCE_RE = re.compile(r"^```yaml[ \t]*$")

#: An ``owner:`` line, a trailing ``# comment`` allowed and not captured.
OWNER_LINE_RE = re.compile(r"^owner:[ \t]*(\S.*?)[ \t]*(#.*)?$")

#: A session name as ``ListAgents`` prints it, minus every name with a space.
OWNER_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


def frontmatter_lines(spec: str) -> list[str]:
    """The lines inside the spec's first ```` ```yaml ```` fenced block.

    Fences and comments are the marker rule's (:func:`walk`), so a yaml
    block quoted inside an HTML comment or inside another fenced block is
    not a fenced block and is never the frontmatter. The block ends where
    :func:`walk` closes it. Empty when there is no such block, and when it
    is never closed: reading an unclosed block to the end of the file would
    read the body as frontmatter.
    """
    lines = spec.splitlines()
    start = None
    for index, kind, _ in walk(lines):
        if start is None:
            if kind == OPEN and YAML_FENCE_RE.match(lines[index]):
                start = index
        elif kind == CLOSE:
            return lines[start + 1:index]
    return []


def owner_values(spec: str) -> list[str]:
    """The value of every ``owner:`` line in the frontmatter, in order.

    A line starting with ``#`` is a comment -- the template ships the field
    commented out -- and never sets the owner. Nothing outside the first yaml
    block is read.
    """
    values = []
    for line in frontmatter_lines(spec):
        if line.startswith("#"):
            continue
        m = OWNER_LINE_RE.match(line)
        if m:
            values.append(m.group(1))
    return values


def owner_errors(spec: str) -> list[str]:
    """Why this spec's ``owner:`` cannot be routed to; empty when it can."""
    values = owner_values(spec)
    if len(values) > 1:
        return [f"set {len(values)} times in the frontmatter ("
                f"{', '.join(repr(v) for v in values)}) — name one session"]
    if values and not OWNER_NAME_RE.match(values[0]):
        return [f"{values[0]!r} is not a session name — letters, digits, '_', '.' "
                "and '-', at most 64, starting with a letter or digit"]
    return []


def route_line(spec: str) -> str:
    """``owner\\t<name>`` or ``human``; raises ``ValueError`` on an invalid owner."""
    errors = owner_errors(spec)
    if errors:
        raise ValueError(errors[0])
    values = owner_values(spec)
    return f"owner\t{values[0]}" if values else "human"


# --------------------------------------------------------------------------
# clarification markers
# --------------------------------------------------------------------------

#: The body's required non-blank character is ``[^\]\s]``, not ``\S``: ``\S``
#: also matches ``]`` and would merge two markers on one line into one.
MARKER_RE = re.compile(r"\[NEEDS[ ]CLARIFICATION:([^\]\n]*[^\]\s][^\]\n]*)\]")

#: A fence opener or closer: up to three spaces, then three or more of one char.
FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")


def _mask_line(line: str, in_comment: bool) -> tuple[str, bool]:
    """``line`` with comment and code-span characters blanked, same length.

    ``in_comment`` says whether an HTML comment opened on an earlier line is
    still open; the second value says whether one is open after this line.
    A backtick run with no closing run of the same length is literal.
    """
    out = list(line)
    i, n = 0, len(line)

    def blank(start: int, end: int) -> None:
        for k in range(start, end):
            out[k] = " "

    while i < n:
        if in_comment:
            close = line.find("-->", i)
            end = n if close < 0 else close + 3
            blank(i, end)
            i, in_comment = end, close < 0
        elif line.startswith("<!--", i):
            in_comment = True
            blank(i, i + 4)
            i += 4
        elif line[i] == "`":
            run = n - i - len(line[i:].lstrip("`"))
            m = re.compile(rf"(?<!`){'`' * run}(?!`)").search(line, i + run)
            if m:
                blank(i, m.end())
                i = m.end()
            else:
                i += run
        else:
            i += 1
    return "".join(out), in_comment


#: What :func:`walk` says a line is.
OPEN, INSIDE, CLOSE, TEXT = "open", "inside", "close", "text"


def walk(lines: list[str]):
    """``(index, kind, masked)`` for every line: the one fence and comment rule.

    ``kind`` is ``OPEN`` for a fence opener, ``INSIDE`` for a line within a
    fenced block, ``CLOSE`` for the line that closes one, and ``TEXT`` for
    everything else. A fence is backtick or tilde, opened outside an HTML
    comment and closed by a run of the same char at least as long with
    nothing after it. ``masked`` is a ``TEXT`` line with comment and
    code-span characters blanked (:func:`_mask_line`), and ``""`` otherwise.
    Both the marker rule and the frontmatter rule read the file through this.
    """
    fence = ""
    in_comment = False
    for index, line in enumerate(lines):
        if fence:
            m = FENCE_RE.match(line)
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence) \
                    and not line[m.end():].strip():
                fence = ""
                yield index, CLOSE, ""
            else:
                yield index, INSIDE, ""
            continue
        if not in_comment:
            m = FENCE_RE.match(line)
            # A backtick fence's info string may not contain a backtick.
            if m and not (m.group(1)[0] == "`" and "`" in line[m.end():]):
                fence = m.group(1)
                yield index, OPEN, ""
                continue
        masked, in_comment = _mask_line(line, in_comment)
        yield index, TEXT, masked


def find_markers(text: str) -> list[tuple[int, str]]:
    """``(1-based line, body)`` for every clarification marker in ``text``.

    Fenced blocks, HTML comments (multi-line too) and inline code spans are
    blanked first (:func:`walk`), with line numbers preserved. The body is
    read from the original line, stripped.
    """
    found: list[tuple[int, str]] = []
    # split("\n"), not splitlines(): line numbers must agree with grep -n.
    lines = text.split("\n")
    for index, kind, masked in walk(lines):
        if kind == TEXT:
            line = lines[index]
            for m in MARKER_RE.finditer(masked):
                found.append((index + 1, line[m.start(1):m.end(1)].strip()))
    return found


# --------------------------------------------------------------------------
# cli
# --------------------------------------------------------------------------

def eligible_lines(root: Path) -> list[str]:
    """One ``ELIGIBLE``/``WAITING`` line per inbox spec, ids sorted."""
    inbox = root / "specs" / "inbox"
    lines = []
    for item in sorted(inbox.iterdir(), key=lambda p: p.name):
        spec = item / "SPEC.md"
        if not item.is_dir() or item.name.startswith(".") or not spec.is_file():
            continue
        unmet = unmet_deps(root, spec.read_text(errors="replace"))
        lines.append(f"WAITING\t{item.name}\t{','.join(unmet)}" if unmet
                     else f"ELIGIBLE\t{item.name}")
    return lines


def check_lines(path: str, text: str) -> list[str]:
    """The ``marker:``, ``chain:`` and ``owner:`` findings for one file."""
    return ([f"{path}:{line}: marker: {body}" for line, body in find_markers(text)]
            + [f"{path}:0: chain: {msg}" for msg in chain_errors(text)]
            + [f"{path}:0: owner: {msg}" for msg in owner_errors(text)])


def read_spec(path: str) -> str | None:
    """The file's text, or None after saying on stderr why it is unreadable."""
    try:
        return Path(path).read_text(errors="replace")
    except OSError as exc:
        print(f"queue_rules: cannot read {path}: {exc.strerror or exc}", file=sys.stderr)
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="queue_rules", description="the queue predicates the contracts gate on")
    commands = parser.add_subparsers(dest="command", required=True)
    elig = commands.add_parser("eligible", help="which inbox specs have every dependency met")
    elig.add_argument("--root", type=Path, default=None,
                      help="drydock STATE_HOME (default: $DRYDOCK_STATE_HOME or ~/.drydock)")
    check = commands.add_parser("check",
                                help="clarification markers, chain errors and invalid owners")
    check.add_argument("paths", nargs="+", metavar="SPEC.md")
    route = commands.add_parser("route", help="who hears about this spec: its owner or the human")
    route.add_argument("path", metavar="SPEC.md")
    args = parser.parse_args(argv)

    if args.command == "route":
        text = read_spec(args.path)
        if text is None:
            return 2
        try:
            line = route_line(text)
        except ValueError as exc:
            print(f"queue_rules: {args.path}: owner: {exc}", file=sys.stderr)
            return 2
        print(line)
        return 0

    if args.command == "eligible":
        if args.root is None:
            import server  # only for the default; server imports this module
            args.root = server.default_root()
        inbox = args.root / "specs" / "inbox"
        if not inbox.is_dir():
            print(f"queue_rules: not a directory: {inbox}", file=sys.stderr)
            return 2
        for line in eligible_lines(args.root):
            print(line)
        return 0

    rc = 0
    for path in args.paths:
        text = read_spec(path)
        if text is None:
            rc = 2
            continue
        found = check_lines(path, text)
        for line in found:
            print(line)
        if found and rc == 0:
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
