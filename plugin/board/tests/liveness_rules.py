"""The liveness, stall and base rules the contracts state, as pure functions.

Not a second orchestrator: the orchestrator is an agent reading
``contracts/ORCHESTRATOR.md`` and ``contracts/DISPATCH.md``. These functions
pin what that prose says over *sampled* inputs — a stamp, two samples of
RUN.md and of the session transcript, two samples of the worktree — so the
decision tables can be tested. No process is ever an input: nothing records a
pid, and the session process's CPU advances while it waits inside a tool.
``test_contract_liveness`` is what keeps the prose and the numbers here from
drifting apart.

The stamp is read with ``server.field`` — the parser the board already uses
for every ``key: value`` line — over the header region DISPATCH step 8
defines (the lines before the first ``## `` heading of any kind). The stamp
has no heading, so it is read whole. No second grammar.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import server  # noqa: E402

#: ORCHESTRATOR "Liveness, then budget": silence longer than this is suspect.
STALL_THRESHOLD = timedelta(minutes=10)
#: ... and a suspect is sampled twice, at least this far apart.
CORROBORATION_GAP = timedelta(seconds=30)
#: ORCHESTRATOR ready-to-review bullet: READY.md + clean tree + still HEAD.
READY_WINDOW = timedelta(minutes=5)

STAMP = ".progress"
TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
HEADING_RE = re.compile(r"^## ", re.M)
HOLD_RE = re.compile(r"^(\d+)m$")

LIVE, SUSPECT, STALLED, NOT_RUNNING = "live", "suspect", "stalled", "not-running"
#: The transcript could not be sampled: not evidence, so never a stall.
INDETERMINATE = "indeterminate"

#: Where Claude Code keeps a session's transcripts, one directory per cwd.
PROJECTS = Path.home() / ".claude" / "projects"
SLUG_RE = re.compile(r"[/.]")


def transcript_dir(worktree: str, projects: Path = PROJECTS) -> Path:
    """``<projects>/<worktree-slug>``: the absolute path, ``/`` and ``.`` → ``-``."""
    return projects / SLUG_RE.sub("-", worktree)


def newest_transcript(directory: Path) -> tuple[float, int] | None:
    """(mtime, size) of the newest ``*.jsonl`` at any depth, or None when unsampleable.

    Recursive, because the session transcript includes its subagents': their
    turns land in ``<session-id>/subagents/agent-*.jsonl`` and the parent file
    stays flat while the session waits on one. The newest file, not a named
    one: no session id is needed, executor and reviewer never share a worktree
    at once, and a finished transcript is flat.
    """
    try:
        stats = [f.stat() for f in directory.rglob("*.jsonl")]
    except OSError:
        return None
    if not stats:
        return None
    newest = max(stats, key=lambda st: st.st_mtime)
    return newest.st_mtime, newest.st_size


def sampler_output(returncode: int, stdout: str) -> tuple[float, int] | None:
    """A shell sampler's ``<mtime> <size>`` line, or None when empty or failed.

    Empty or failed output is "could not sample", never a value: two empty
    reads compared as equal would read as a flat transcript.
    """
    fields = stdout.split()
    if returncode != 0 or len(fields) != 2:
        return None
    try:
        return float(fields[0]), int(fields[1])
    except ValueError:
        return None


def question_open(text: str) -> bool:
    """An open escalation: the last ``## `` heading is not a ``## Resolution``.

    ``/drydock:spec unblock`` appends ``## Resolution (YYYY-MM-DD)`` as the
    last section, so a resolved QUESTION.md carried in as history is closed.
    """
    headings = [line for line in text.splitlines() if line.startswith("## ")]
    return not headings or not headings[-1].startswith("## Resolution")


def header(text: str) -> str:
    """The ``key: value`` region: everything before the first ``## `` heading."""
    return HEADING_RE.split(text, maxsplit=1)[0]


def parse_ts(value: str) -> datetime | None:
    try:
        return datetime.strptime(value, TS_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


@dataclass(frozen=True)
class Stamp:
    last_progress: datetime
    hold: timedelta | None
    step: str
    note: str


def read_stamp(text: str) -> Stamp | None:
    """The stamp, or None when ``last_progress:`` is missing or malformed.

    A malformed timestamp is rejected, never read as fresh: the caller falls
    back to RUN.md's mtime, as ORCHESTRATOR says for an unparseable stamp.
    """
    head = header(text)
    last = parse_ts(server.field(head, "last_progress"))
    if last is None:
        return None
    m = HOLD_RE.match(server.field(head, "hold"))
    hold = timedelta(minutes=int(m.group(1))) if m else None
    return Stamp(last, hold, server.field(head, "step"), server.field(head, "note"))


def write_stamp(item_dir: Path, last_progress: datetime, **fields: str) -> None:
    """Write-then-rename: ``.progress.tmp`` in the same directory, then replace."""
    lines = [f"last_progress: {last_progress.strftime(TS_FORMAT)}"]
    lines += [f"{key}: {value}" for key, value in fields.items()]
    tmp = item_dir / (STAMP + ".tmp")
    tmp.write_text("\n".join(lines) + "\n")
    os.replace(tmp, item_dir / STAMP)


@dataclass(frozen=True)
class Sample:
    """One read of an item at an instant. None means "not there to read"."""
    at: datetime
    run_size: int | None = None
    run_mtime: datetime | None = None
    transcript: tuple[float, int] | None = None  # newest_transcript(); None = unsampleable
    status: str = ""  # the session's status string: recorded, never consulted


def liveness(now: datetime, stamp_text: str | None, run_mtime: datetime | None,
             executor_expected: bool,
             samples: tuple[Sample, Sample] | None = None) -> str:
    """ORCHESTRATOR "Liveness, then budget", step by step.

    ``executor_expected`` is plan-phase's predicate — the states its
    dead-executor check is scoped to — passed in, never enumerated here.
    """
    if not executor_expected:
        return NOT_RUNNING
    stamp = read_stamp(stamp_text) if stamp_text is not None else None
    if stamp:
        last, window = stamp.last_progress, max(STALL_THRESHOLD, stamp.hold or STALL_THRESHOLD)
    else:
        last, window = run_mtime, STALL_THRESHOLD
    if last is not None and now - last <= window:
        return LIVE
    if samples is None:
        return SUSPECT  # never stopped on age alone: go and sample
    first, second = samples
    if second.at - first.at < CORROBORATION_GAP:
        raise ValueError("the two samples must be at least 30 seconds apart")
    grew = first.run_size is not None and second.run_size is not None and (
        (first.run_size, first.run_mtime) != (second.run_size, second.run_mtime))
    if first.transcript is None or second.transcript is None:
        # Cannot be sampled is not evidence. Dead or alive is ListAgents' call.
        return LIVE if grew else INDETERMINATE
    talked = first.transcript != second.transcript
    return LIVE if grew or talked else STALLED


def stall_action(state: str, over_budget: bool, ready_present: bool,
                 tree_dirty: bool, relaunches_used: int,
                 question_open: bool = False) -> str:
    """What the Active section does with a liveness verdict.

    Finished work is excluded first and the exclusion covers the whole stall
    handler — stop, rescue, reset, relaunch — because the reset guard is
    satisfied by a finished, unpushed run and would strip its commit. Arm (i),
    an open QUESTION.md, wins over arm (ii), READY.md.
    """
    if state == STALLED:
        if question_open:
            # the executor finished an escalation and wedged handing it off
            return ("complete-move-to-blocked-noting-dirty" if tree_dirty
                    else "complete-move-to-blocked")
        if ready_present:
            # clean: the ready-to-review bullet owns it; dirty: a human decides
            return "block-with-question" if tree_dirty else "leave-to-ready-review"
        return "rescue-and-relaunch" if relaunches_used == 0 else "dispatch-failure"
    if state in (LIVE, INDETERMINATE) and over_budget:
        # indeterminate reaches here only alive: a dead session is a death
        return "budget-exceeded"
    return "wait"


def ready_action(ready_present: bool, session_live: bool,
                 heads: tuple[tuple[datetime, str], tuple[datetime, str]],
                 porcelain: tuple[str, str], question_open: bool = False) -> str:
    """ORCHESTRATOR ready-to-review bullet. Takes no stamp: its age is irrelevant."""
    if not ready_present:
        return "wait"
    if question_open:
        return "block"  # the escalation wins: no reviewer
    if not session_live:
        return "review"
    (t0, head0), (t1, head1) = heads
    if t1 - t0 < READY_WINDOW or head0 != head1 or any(p.strip() for p in porcelain):
        return "wait"  # still writing: the liveness check has it
    return "stop-session-and-review"


def base_check(preflight_sha: str, head: str, remote: str, revalidated: bool) -> str:
    """DISPATCH step 7: the worktree, and the remote as it is at cut time
    (``git ls-remote``), must both still be where step 5 validated.

    After ``revalidate`` a spec without ``branch:`` re-points its fresh branch
    at the new ``preflight_sha`` before this is asked again; a chained branch
    is never re-pointed.
    """
    if head == preflight_sha and remote == preflight_sha:
        return "proceed"
    return "escalate" if revalidated else "revalidate"
