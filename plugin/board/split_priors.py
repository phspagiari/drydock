#!/usr/bin/env python3
"""Split a monolithic drydock PRIORS.md into the hot/cold layout.

    python3 -m plugin.board.split_priors <PRIORS.md> <out-dir>

``<out-dir>`` is a STATE_HOME. The hot file is rewritten at
``<out-dir>/PRIORS.md`` and the cold files land in ``<out-dir>/priors/``:

    priors/<slug>.md        one per ``## Target repo: <path>`` section
    priors/_spec-writing.md ``## Spec-writing``
    priors/_pr-prose.md     ``## PR prose …``
    priors/_review.md       any ``## Review …``

Everything else — the preamble, the ``retro-cursor`` line, and any section
that classifies as none of the above — stays hot. Sections move whole, with
their heading, so no line is lost and no line is invented: the non-blank
line count of the input equals the non-blank line count of everything
written.

Running this on an already-split tree is a no-op: a hot file with no cold
sections left in it writes nothing at all.

Standard library only, like the rest of ``board/``.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

#: ``## Target repo: <path>`` — the path may be wrapped in backticks.
TARGET_REPO_RE = re.compile(r"^##\s+Target\s+repo\s*:\s*(.+?)\s*$", re.IGNORECASE)

#: Topic headings that belong to a phase rather than to a repo. Matched as
#: prefixes because the live headings carry a tail ("## PR prose is where the
#: defects are"); the phase is decided by how the heading starts.
PHASE_HEADINGS = (
    ("## Spec-writing", "_spec-writing.md"),
    ("## PR prose", "_pr-prose.md"),
    ("## Review", "_review.md"),
)

COLD_DIR = "priors"
HOT_FILE = "PRIORS.md"

FENCE_RE = re.compile(r"^\s*(```|~~~)")


class SplitError(Exception):
    """A heading the splitter refuses to guess a bucket for."""


def slug_for(target_repo: str) -> str:
    """Basename of a ``target_repo`` path, as the cold file's stem.

    ``~/code/ledger-api`` → ``ledger-api``. Two repos with the same basename
    collide into one file; that is a known and accepted limitation of the
    layout, called out in ``contracts/PRIORS.seed.md``.
    """
    cleaned = target_repo.strip().strip("`").strip().rstrip("/")
    name = Path(cleaned).name
    if not name or name in (".", ".."):
        raise SplitError(f"cannot derive a cold-file slug from: {target_repo!r}")
    return name


def classify(heading: str) -> str | None:
    """Cold file (relative to ``out-dir``) for a ``## `` heading, else None.

    None means the section stays in the hot file — the deliberate default, so
    an unrecognised heading is never silently filed under a bucket it does
    not belong to.
    """
    match = TARGET_REPO_RE.match(heading)
    if match:
        return f"{COLD_DIR}/{slug_for(match.group(1))}.md"
    lowered = heading.lower()
    for prefix, filename in PHASE_HEADINGS:
        if lowered.startswith(prefix.lower()):
            return f"{COLD_DIR}/{filename}"
    return None


def split_text(text: str) -> tuple[list[str], dict[str, list[str]]]:
    """Split priors markdown into ``(hot_lines, {relative_path: lines})``.

    Sections are ``## `` headings at the start of a line and outside a fenced
    code block. Every line of the input lands in exactly one bucket.
    """
    hot: list[str] = []
    cold: dict[str, list[str]] = {}
    current = hot
    fence: str | None = None

    for line in text.splitlines():
        opener = FENCE_RE.match(line)
        if fence is not None:
            if opener and opener.group(1) == fence:
                fence = None
            current.append(line)
            continue
        if opener:
            fence = opener.group(1)
            current.append(line)
            continue
        if line.startswith("## "):
            destination = classify(line)
            current = hot if destination is None else cold.setdefault(destination, [])
        current.append(line)

    return hot, cold


def _render(lines: list[str]) -> str:
    """Join lines back into a file body with exactly one trailing newline."""
    while lines and not lines[-1].strip():
        lines = lines[:-1]
    return "\n".join(lines) + "\n" if lines else ""


def split_file(src: Path, out_dir: Path) -> list[Path]:
    """Split ``src`` into ``out_dir``. Returns the files written, hot first.

    Nothing is written when the source has no cold sections — that is the
    already-split tree, and rewriting it would be churn at best. An existing
    cold file is appended to rather than replaced: priors are knowledge, and
    a migration that overwrites them is a migration that loses them.

    **The hot file is written last, after every cold file has landed.** Until
    that final write the source still holds every line, so a failure anywhere
    in the cold stage leaves the user's only copy of their priors intact. The
    reverse order — the order this was first written in — truncates
    ``PRIORS.md`` to the unclassified remainder before the cold sections
    exist anywhere on disk, and ``<STATE_HOME>`` is unbacked-up by design.
    Cold bodies are rendered (and existing ones read) before any write for
    the same reason: read errors happen while nothing has changed yet.
    """
    hot, cold = split_text(src.read_text(encoding="utf-8"))
    if not cold:
        return []

    bodies: list[tuple[Path, str]] = []
    for relative, lines in sorted(cold.items()):
        path = out_dir / relative
        body = _render(lines)
        if path.exists():
            existing = path.read_text(encoding="utf-8").rstrip("\n")
            body = f"{existing}\n\n{body}" if existing else body
        bodies.append((path, body))

    (out_dir / COLD_DIR).mkdir(parents=True, exist_ok=True)
    for path, body in bodies:
        path.write_text(body, encoding="utf-8")
    (out_dir / HOT_FILE).write_text(_render(hot), encoding="utf-8")

    return [out_dir / HOT_FILE, *(path for path, _ in bodies)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="split_priors",
        description="split a monolithic drydock PRIORS.md into hot + cold files")
    parser.add_argument("source", type=Path, help="the PRIORS.md to split")
    parser.add_argument("out_dir", type=Path, metavar="out-dir",
                        help="STATE_HOME to write PRIORS.md and priors/ into")
    args = parser.parse_args(argv)

    if not args.source.is_file():
        print(f"split_priors: no such file: {args.source}", file=sys.stderr)
        return 2
    if not args.out_dir.is_dir():
        print(f"split_priors: no such directory: {args.out_dir}", file=sys.stderr)
        return 2

    try:
        written = split_file(args.source, args.out_dir)
    except SplitError as exc:
        print(f"split_priors: {exc}", file=sys.stderr)
        return 1

    if not written:
        print(f"split_priors: nothing to split in {args.source} (already split)")
        return 0
    for path in written:
        print(f"split_priors: wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
