#!/usr/bin/env python3
"""Parse prior records, flag the ones whose repo has moved past its cursor,
and apply what a landed diff says about them.

    python3 <PLUGIN_HOME>/board/priors_check.py parse <file>
    python3 <PLUGIN_HOME>/board/priors_check.py stale --repo <path> --priors <file> [--ref <ref>]
    python3 <PLUGIN_HOME>/board/priors_check.py advance --repo <path> --priors <file> [--ref <ref>]
                                                        [--if-ancestor]
    python3 <PLUGIN_HOME>/board/priors_check.py candidates --priors <file> --diff-files <list>
    python3 <PLUGIN_HOME>/board/priors_check.py retract --priors <file> [--sha <sha>]
                                                        [--mark <key>]... [<key>]...

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
stay legal; nothing here rewrites them into records.

Either shape may also carry one ``- stale: <sha>`` sub-bullet, the merge
commit of a landed diff that made the prior doubtful. It is not one of the
four fields -- it neither makes a legacy bullet a record nor counts as
missing -- and it parses into the record's ``stale`` value, never into the
statement.

A priors file may carry one ``<!-- code-cursor: <full sha> -->`` line (the
bare ``code-cursor: <sha>`` form parses too): the target-repo commit its
priors were last validated against. In a cold repo file it sits directly
under the ``## Target repo:`` heading, so ``split_priors.py`` moves it with
the section. ``stale`` compares it to the repo's cursor ref by exact string --
"moved" means "differs", deliberately, not an ancestry test -- and
``advance`` is the only thing besides the retro that writes it -- the
propagation step writes it through ``advance --if-ancestor``, which never
moves it backwards or off mainline's line of descent.

The cursor ref is the repo's mainline, ``origin/<default>``, resolved through
``refs/remotes/origin/HEAD``. It is never the checkout's ``HEAD``: the human's
checkout may be parked on any branch, and the cursor exists to notice
mainline moving under a prior. ``--ref`` overrides it (tests, and repos with
no ``origin/HEAD``). This never fetches; callers fetch first.

``candidates`` is propagation's mechanical pre-filter over a diff's file
list: it can narrow the priors an agent must judge, never drop one with no
globs. ``retract`` applies the agent's verdicts -- ``--mark`` adds the
``stale:`` sub-bullet, a bare key removes the prior -- all of one file's in
one call, because removing a prior moves every legacy key below it. Nothing
else here deletes a prior. Standard library only, like the rest of
``board/``.
"""

from __future__ import annotations

import argparse
import fnmatch
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
STALE = "stale"
FIELD_RE = re.compile(r"^([ \t]+)[-*+][ \t]+(" + "|".join((*FIELDS, STALE))
                      + r")[ \t]*:[ \t]*(.*)$")
SHA_RE = re.compile(r"^[0-9a-f]{7,64}$")
CURSOR_RE = re.compile(r"^(?:<!--[ \t]*)?code-cursor:[ \t]*([0-9a-f]{7,64})[ \t]*(?:-->)?[ \t]*$")
TICKED_RE = re.compile(r"`([^`\n]+)`")
GLOB_CHARS = frozenset("*?/.")


class PriorsError(Exception):
    """A priors file this checker refuses to guess about."""


def globs(depends_on: str) -> list[str]:
    """Backticked tokens in ``depends_on`` that read as path globs.

    Heuristic on purpose: a token with ``*``, ``?``, ``/`` or ``.`` counts.
    A false positive is not harmless: it makes the prior glob-bearing, and
    ``candidates`` then drops it from a diff that touches no path it names --
    where a prior with no globs at all would always have been judged.
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
        "stale": _unticked(_join(fields[STALE])) if STALE in fields else None,
    }


def parse_text(text: str, path: Path) -> list[dict]:
    """Every prior record in ``text``, in file order.

    Headings, paragraphs and comments at column 0 are not priors and end the
    record before them; fenced blocks are skipped whole. ``path`` names the
    file for keys and for scope inference.
    """
    return [record for record, _ in _parse(text, path)]


def _parse(text: str, path: Path) -> list[tuple[dict, int]]:
    """``parse_text``'s records, each with the 1-based line it ends on."""
    records: list[tuple[dict, int]] = []
    current: dict | None = None
    field: str | None = None
    field_indent = 0
    inferred = _file_scope(path)
    fence: str | None = None

    def close() -> None:
        nonlocal current, field
        if current is not None:
            records.append((_finish(current, path), current["last"]))
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
                current = {"line": number, "last": number, "first": bullet.group(1),
                           "statement": [], "fields": {}, "inferred": inferred}
            continue
        if current is None:
            continue
        current["last"] = number
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


MAINLINE = "refs/remotes/origin/HEAD"


def ref_sha(repo: Path, ref: str | None = None) -> str:
    """Full sha of ``ref``, by default the repo's mainline ``origin/HEAD``."""
    target = ref or MAINLINE
    if target.startswith("-"):
        raise PriorsError(f"not a ref: {target!r}")
    done = subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", "--quiet",
                           f"{target}^{{commit}}"],
                          capture_output=True, text=True, check=False)
    if done.returncode == 0:
        return done.stdout.strip()
    if ref is None and subprocess.run(["git", "-C", str(repo), "rev-parse", "--git-dir"],
                                      capture_output=True, check=False).returncode == 0:
        raise PriorsError(f"{repo}: {MAINLINE} is not set, so origin's default branch "
                          f"is unknown; run 'git -C {repo} remote set-head origin -a' "
                          f"or pass --ref")
    raise PriorsError(f"{repo}: cannot resolve {target} to a commit: "
                      f"{done.stderr.strip() or 'not a git repository or no such ref'}")


def stale_lines(repo: Path, priors: Path, ref: str | None = None) -> list[str]:
    """``NOCURSOR``, nothing (cursor == ref), or one ``STALE`` line per prior.

    The file is parsed before the cursor is compared, so a malformed record
    fails the same way whether or not the repo moved.
    """
    if not priors.is_file():
        return ["NOCURSOR"]
    records = parse_file(priors)
    cursor = read_cursor(priors)
    if cursor is None:
        return ["NOCURSOR"]
    if cursor == ref_sha(repo, ref):
        return []
    return [f"STALE {r['key']} {r['asserted']} {r['depends_on']}" for r in records]


def _write(path: Path, lines: list[str]) -> None:
    """Write to a temporary name and rename, so a failure never tears ``path``."""
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def is_ancestor(repo: Path, old: str, new: str) -> bool | None:
    """Whether ``old`` is ``new`` or an ancestor of it; None if git cannot say."""
    done = subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor", old, new],
                          capture_output=True, check=False)
    return {0: True, 1: False}.get(done.returncode)


def advance(repo: Path, priors: Path, ref: str | None = None,
            if_ancestor: bool = False) -> str:
    """Set the file's ``code-cursor`` to the cursor ref's sha; returns the line to print.

    An existing cursor line is replaced in place. Otherwise the line goes
    directly under a leading ``## `` heading (inside the section, so a split
    carries it), or at the top of a file with none. Written to a temporary
    name and renamed, so a failure never leaves the file torn.

    With ``if_ancestor`` an existing cursor moves only when it is the new sha
    or an ancestor of it. Otherwise -- the new sha is behind the cursor, on
    another line of history, or unknown to the repo -- nothing is written and
    the returned line is a ``skip:`` reason, left for the retro. A file with
    no cursor yet takes the new sha either way.
    """
    if not priors.is_file():
        raise PriorsError(f"no such priors file: {priors}")
    parse_file(priors)  # a malformed record is refused, never stamped as validated
    sha = ref_sha(repo, ref)
    cursor = f"<!-- code-cursor: {sha} -->"
    text = priors.read_text(encoding="utf-8")
    lines = text.splitlines()
    old = read_cursor(priors)  # refuses a file with two cursors before anything is written
    if if_ancestor and old is not None and is_ancestor(repo, old, sha) is not True:
        return (f"skip: code-cursor {old} is not an ancestor of {sha}; "
                f"left unchanged for the retro")
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
    _write(priors, lines)
    return f"code-cursor: {sha}"


def _segments(value: str) -> list[str]:
    return [part for part in value.strip().split("/") if part not in ("", ".")]


def _glob_matches(pattern: list[str], path: list[str]) -> bool:
    """Whole-path match, one ``fnmatch`` per segment; ``**`` is zero or more."""
    if not pattern:
        return not path
    if pattern[0] == "**":
        return any(_glob_matches(pattern[1:], path[i:]) for i in range(len(path) + 1))
    return bool(path) and fnmatch.fnmatchcase(path[0], pattern[0]) \
        and _glob_matches(pattern[1:], path[1:])


def glob_hits(glob: str, path: str) -> bool:
    """Whether ``glob`` matches ``path`` or one of its ancestor directories.

    Both are repo-relative. The ancestor rule only widens: a prior that
    names ``plugin/board`` is touched by a diff to ``plugin/board/x.py``.
    """
    pattern, parts = _segments(glob), _segments(path)
    return bool(pattern) and any(_glob_matches(pattern, parts[:end])
                                 for end in range(1, len(parts) + 1))


def candidates(priors: Path, paths: list[str]) -> list[dict]:
    """The priors in ``priors`` a diff over ``paths`` may have touched.

    A prior is a candidate when one of its globs hits one of the paths, or
    when it has no globs at all -- legacy and ``depends_on: unknown`` priors
    included. The filter narrows what an agent must judge; it never decides
    that a prior with nothing to match on is safe.
    """
    if not priors.is_file():
        raise PriorsError(f"no such priors file: {priors}")
    found = []
    for record in parse_file(priors):
        matched = [g for g in record["globs"] if any(glob_hits(g, p) for p in paths)]
        if matched or not record["globs"]:
            found.append({"key": record["key"], "matched_globs": matched,
                          "depends_on": record["depends_on"]})
    return found


def retract(priors: Path, remove: list[str], mark: list[str],
            sha: str | None = None) -> list[str]:
    """Apply one file's verdicts at once; returns one line per change.

    Each key in ``mark`` gains a ``- stale: <sha>`` sub-bullet (an existing
    one is overwritten); each key in ``remove`` loses its whole record. Every
    key is resolved against a single parse and the edits run bottom-up, so a
    removal cannot shift a legacy ``<stem>/L<n>`` key the same call names
    further down. Any key that is unknown, ambiguous, or named twice refuses
    the whole call before anything is written.
    """
    if not priors.is_file():
        raise PriorsError(f"no such priors file: {priors}")
    if mark and (sha is None or not SHA_RE.match(sha)):
        raise PriorsError(f"--mark needs --sha <hex commit sha>, got {sha!r}")
    named = [*remove, *mark]
    twice = sorted({key for key in named if named.count(key) > 1})
    if twice:
        raise PriorsError(f"named more than once: {', '.join(twice)}")
    text = priors.read_text(encoding="utf-8")
    spans: dict[str, list[tuple[dict, int]]] = {}
    for record, end in _parse(text, priors):
        spans.setdefault(record["key"], []).append((record, end))
    for key in named:
        if key not in spans:
            raise PriorsError(f"{priors}: no prior with key {key!r}")
        if len(spans[key]) > 1:
            rows = ", ".join(str(r["line"]) for r, _ in spans[key])
            raise PriorsError(f"{priors}: {len(spans[key])} priors share key {key!r} "
                              f"(lines {rows})")
    lines = text.splitlines()
    report = []
    for key in sorted(named, key=lambda k: spans[k][0][0]["line"], reverse=True):
        record, end = spans[key][0]
        start = record["line"] - 1
        if key in mark:
            stale = f"  - {STALE}: {sha}"
            at = next((i for i in range(start + 1, end)
                       if (m := FIELD_RE.match(lines[i])) and m.group(2) == STALE), None)
            if at is None:
                lines.insert(end, stale)
            else:
                lines[at] = stale
            report.append(f"stale {key} {sha}")
        else:
            del lines[start:end]
            # Keep the file's spacing: one blank line where the prior was.
            if start < len(lines) and not lines[start].strip() \
                    and (start == 0 or not lines[start - 1].strip()):
                del lines[start]
            elif start == len(lines) and start > 0 and not lines[start - 1].strip():
                del lines[start - 1]
            report.append(f"retract {key}")
    _write(priors, lines)
    return report[::-1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="priors_check", description="parse priors and flag stale ones")
    commands = parser.add_subparsers(dest="command", required=True)
    parse_cmd = commands.add_parser("parse", help="print prior records as JSON lines")
    parse_cmd.add_argument("file", type=Path)
    for name, text in (("stale", "list priors whose repo moved past the cursor"),
                       ("advance", "set code-cursor to the repo's mainline")):
        cmd = commands.add_parser(name, help=text)
        cmd.add_argument("--repo", type=Path, required=True)
        cmd.add_argument("--priors", type=Path, required=True)
        cmd.add_argument("--ref", help="cursor ref (default: origin/HEAD, "
                                       "the repo's mainline)")
        if name == "advance":
            cmd.add_argument("--if-ancestor", action="store_true",
                             help="move an existing cursor only forward along its "
                                  "own history; otherwise print a skip: reason")
    cand_cmd = commands.add_parser("candidates", help="priors a diff's file list may touch")
    cand_cmd.add_argument("--priors", type=Path, required=True)
    cand_cmd.add_argument("--diff-files", type=Path, required=True,
                          help="file with one repo-relative path per line")
    retract_cmd = commands.add_parser("retract", help="apply one file's verdicts at once")
    retract_cmd.add_argument("--priors", type=Path, required=True)
    retract_cmd.add_argument("--sha", help="merge sha a --mark records")
    retract_cmd.add_argument("--mark", action="append", default=[], metavar="KEY",
                             help="flag this prior stale: <sha> (repeatable)")
    retract_cmd.add_argument("remove", nargs="*", metavar="KEY", help="remove this prior")
    args = parser.parse_args(argv)

    try:
        if args.command == "parse":
            if not args.file.is_file():
                raise PriorsError(f"no such file: {args.file}")
            for record in parse_file(args.file):
                print(json.dumps(record, ensure_ascii=False))
        elif args.command == "stale":
            for line in stale_lines(args.repo, args.priors, args.ref):
                print(line)
        elif args.command == "advance":
            print(advance(args.repo, args.priors, args.ref, args.if_ancestor))
        elif args.command == "candidates":
            if not args.diff_files.is_file():
                raise PriorsError(f"no such file: {args.diff_files}")
            paths = [line.strip() for line in
                     args.diff_files.read_text(encoding="utf-8").splitlines() if line.strip()]
            for found in candidates(args.priors, paths):
                print(json.dumps(found, ensure_ascii=False))
        else:
            if not args.remove and not args.mark:
                raise PriorsError("retract: name at least one key")
            for line in retract(args.priors, args.remove, args.mark, args.sha):
                print(line)
    except PriorsError as exc:
        print(f"priors_check: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
