#!/usr/bin/env python3
"""Parse prior records and flag the ones whose repo has moved past its cursor.

    python3 <PLUGIN_HOME>/board/priors_check.py parse <file>
    python3 <PLUGIN_HOME>/board/priors_check.py stale --repo <path> --priors <file>
    python3 <PLUGIN_HOME>/board/priors_check.py advance --repo <path> --priors <file>

A prior is a top-level bullet. The full record format is::

    - **[<slug>/<key>]** <statement>
      - scope: <target repo path, or global>
      - derived_from: <item id>
      - depends_on: <free text; backticked tokens may be path globs>
      - asserted: <ISO date>

A bullet carrying none of the four sub-bullets is a **legacy** prior: it
parses with ``depends_on: unknown``, its scope inferred from where it lives,
and ``<file stem>/L<line>`` as its key -- positional, so it moves when the
file is edited or split; only a full-format key is stable. Legacy bullets
stay legal; nothing here rewrites them.

A priors file may carry one ``<!-- code-cursor: <full sha> -->`` line (the
bare ``code-cursor: <sha>`` form parses too): the target-repo commit its
priors were last validated against. In a cold repo file it sits directly
under the ``## Target repo:`` heading, so ``split_priors.py`` moves it with
the section. ``stale`` compares it to the repo's ``HEAD`` by exact string --
"moved" means "differs", deliberately, not an ancestry test -- and
``advance`` is the only thing besides the retro that writes it.

This flags; it never deletes a prior. Standard library only, like the rest of
``board/``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

try:
    from . import split_priors
except ImportError:  # run as a script, or imported with board/ on sys.path
    import split_priors

FIELDS = ("scope", "derived_from", "depends_on", "asserted")
UNKNOWN = "unknown"

BULLET_RE = re.compile(r"^[-*+][ \t]+(.*)$")
FULL_RE = re.compile(r"^\*\*\[([^\]\s/]+/[^\]\s]+)\]\*\*[ \t]*(.*)$")
FIELD_RE = re.compile(r"^([ \t]+)[-*+][ \t]+(" + "|".join(FIELDS) + r")[ \t]*:[ \t]*(.*)$")
CURSOR_RE = re.compile(r"^(?:<!--[ \t]*)?code-cursor:[ \t]*([0-9a-f]{7,64})[ \t]*(?:-->)?[ \t]*$")
TICKED_RE = re.compile(r"`([^`\n]+)`")
GLOB_CHARS = frozenset("*?/.")


class PriorsError(Exception):
    """A priors file this checker refuses to guess about."""


def globs(depends_on: str) -> list[str]:
    """Backticked tokens in ``depends_on`` that read as path globs.

    Heuristic on purpose: a token with ``*``, ``?``, ``/`` or ``.`` counts.
    A false positive only widens a later pre-filter's candidate set.
    """
    return [tok for tok in TICKED_RE.findall(depends_on) if GLOB_CHARS & set(tok)]


def _unticked(value: str) -> str:
    """``\\`~/p/repo\\``` → ``~/p/repo``; anything else unchanged."""
    match = re.fullmatch(r"`([^`]*)`", value)
    return match.group(1).strip() if match else value


def _file_scope(path: Path) -> str:
    """Scope implied by a file's name alone: hot and phase files are global."""
    if path.name == split_priors.HOT_FILE or path.name.startswith("_"):
        return "global"
    return path.stem


def _join(parts: list[str]) -> str:
    return " ".join(" ".join(parts).split())


def _finish(raw: dict, path: Path) -> dict:
    fields = raw["fields"]
    present = [name for name in FIELDS if name in fields]
    head = FULL_RE.match(raw["first"])
    key = head.group(1) if head else f"{path.stem}/L{raw['line']}"
    statement = [head.group(2) if head else raw["first"], *raw["statement"]]
    scope = _unticked(_join(fields["scope"])) if "scope" in fields else raw["inferred"]
    depends_on = _join(fields.get("depends_on", [])) or UNKNOWN
    return {
        "file": str(path),
        "line": raw["line"],
        "key": key,
        "statement": _join(statement),
        "scope": scope,
        "derived_from": _unticked(_join(fields.get("derived_from", []))) or UNKNOWN,
        "depends_on": depends_on,
        "globs": globs(depends_on),
        "asserted": _unticked(_join(fields.get("asserted", []))) or UNKNOWN,
        "legacy": not present,
        "missing": [name for name in FIELDS if name not in fields],
    }


def parse_text(text: str, path: Path) -> list[dict]:
    """Every prior record in ``text``, in file order.

    Headings, paragraphs and comments at column 0 are not priors and end the
    record before them; fenced blocks are skipped whole. ``path`` names the
    file for keys and for scope inference.
    """
    records: list[dict] = []
    current: dict | None = None
    field: str | None = None
    field_indent = 0
    inferred = _file_scope(path)
    fence: str | None = None

    def close() -> None:
        nonlocal current, field
        if current is not None:
            records.append(_finish(current, path))
        current, field = None, None

    for number, line in enumerate(text.splitlines(), start=1):
        opener = split_priors.FENCE_RE.match(line)
        if fence is not None:
            if opener and opener.group(1) == fence:
                fence = None
            continue
        if opener:
            close()
            fence = opener.group(1)
            continue
        if not line.strip():
            continue
        if not line[0].isspace():
            close()
            if line.startswith("## "):
                target = split_priors.TARGET_REPO_RE.match(line)
                inferred = target.group(1).strip("`").strip() if target else _file_scope(path)
            bullet = BULLET_RE.match(line)
            if bullet:
                current = {"line": number, "first": bullet.group(1), "statement": [],
                           "fields": {}, "inferred": inferred}
            continue
        if current is None:
            continue
        sub = FIELD_RE.match(line)
        if sub:
            field, field_indent = sub.group(2), len(sub.group(1))
            if field in current["fields"]:
                raise PriorsError(f"{path}:{number}: second {field}: in the prior "
                                  f"at line {current['line']}")
            current["fields"][field] = [sub.group(3)]
        elif field is not None and len(line) - len(line.lstrip()) > field_indent:
            current["fields"][field].append(line.strip())
        elif not current["fields"]:
            current["statement"].append(line.strip())
        else:
            field = None  # body text after the fields: part of the prior, not a field
    close()
    return records


def parse_file(path: Path) -> list[dict]:
    return parse_text(path.read_text(encoding="utf-8"), path)


def _cursor_lines(lines: list[str]) -> list[tuple[int, str]]:
    found, fence = [], None
    for index, line in enumerate(lines):
        opener = split_priors.FENCE_RE.match(line)
        if fence is not None:
            if opener and opener.group(1) == fence:
                fence = None
            continue
        if opener:
            fence = opener.group(1)
            continue
        match = CURSOR_RE.match(line)
        if match:
            found.append((index, match.group(1)))
    return found


def read_cursor(path: Path) -> str | None:
    """The file's ``code-cursor`` sha; None when the file or the line is absent."""
    if not path.is_file():
        return None
    found = _cursor_lines(path.read_text(encoding="utf-8").splitlines())
    if len(found) > 1:
        rows = ", ".join(str(index + 1) for index, _ in found)
        raise PriorsError(f"{path}: {len(found)} code-cursor lines (lines {rows}); keep one")
    return found[0][1] if found else None


def head_sha(repo: Path) -> str:
    done = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise PriorsError(f"git rev-parse HEAD failed in {repo}: {done.stderr.strip()}")
    return done.stdout.strip()


def stale_lines(repo: Path, priors: Path) -> list[str]:
    """``NOCURSOR``, nothing (cursor == HEAD), or one ``STALE`` line per prior."""
    cursor = read_cursor(priors)
    if cursor is None:
        return ["NOCURSOR"]
    if cursor == head_sha(repo):
        return []
    return [f"STALE {r['key']} {r['asserted']} {r['depends_on']}" for r in parse_file(priors)]


def advance(repo: Path, priors: Path) -> str:
    """Set the file's ``code-cursor`` to the repo's HEAD; returns the sha.

    An existing cursor line is replaced in place. Otherwise the line goes
    directly under a leading ``## `` heading (inside the section, so a split
    carries it), or at the top of a file with none. Written to a temporary
    name and renamed, so a failure never leaves the file torn.
    """
    if not priors.is_file():
        raise PriorsError(f"no such priors file: {priors}")
    sha = head_sha(repo)
    cursor = f"<!-- code-cursor: {sha} -->"
    text = priors.read_text(encoding="utf-8")
    lines = text.splitlines()
    read_cursor(priors)  # refuses a file with two cursors before anything is written
    found = _cursor_lines(lines)
    if found:
        lines[found[0][0]] = cursor
    else:
        first = next((i for i, line in enumerate(lines) if line.strip()), None)
        if first is not None and lines[first].startswith("## "):
            rest = lines[first + 1:]
            lines = [*lines[:first + 1], "", cursor, *([] if rest[:1] == [""] else [""]), *rest]
        else:
            lines = [cursor, "", *lines]
    temporary = priors.with_name(f".{priors.name}.tmp")
    temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(temporary, priors)
    return sha


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="priors_check", description="parse priors and flag stale ones")
    commands = parser.add_subparsers(dest="command", required=True)
    parse_cmd = commands.add_parser("parse", help="print prior records as JSON lines")
    parse_cmd.add_argument("file", type=Path)
    for name, text in (("stale", "list priors whose repo moved past the cursor"),
                       ("advance", "set code-cursor to the repo's HEAD")):
        cmd = commands.add_parser(name, help=text)
        cmd.add_argument("--repo", type=Path, required=True)
        cmd.add_argument("--priors", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        if args.command == "parse":
            if not args.file.is_file():
                raise PriorsError(f"no such file: {args.file}")
            for record in parse_file(args.file):
                print(json.dumps(record, ensure_ascii=False))
        elif args.command == "stale":
            for line in stale_lines(args.repo, args.priors):
                print(line)
        else:
            print(f"code-cursor: {advance(args.repo, args.priors)}")
    except PriorsError as exc:
        print(f"priors_check: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
