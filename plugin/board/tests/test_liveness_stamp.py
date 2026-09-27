"""The progress stamp and the liveness decision table (DISPATCH step 7, ORCHESTRATOR).

    python3 -m unittest discover plugin/board/tests

A stale stamp is corroborated by one measurement only: growth of RUN.md and of
the session transcript (the newest ``*.jsonl`` at any depth under the
worktree's slug directory in ``~/.claude/projects``, subagent transcripts
included) across two reads at least 30 seconds apart. Process CPU is not an
input: nothing records a pid, and the session process's CPU advances while it
waits inside a tool. The real sessions below are re-expressed in that
measurement, each with its source.
"""

import dataclasses
import inspect
import os
import shutil
import sys
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import liveness_rules as rules  # noqa: E402
from liveness_rules import INDETERMINATE, LIVE, NOT_RUNNING, STALLED, SUSPECT, Sample  # noqa: E402

UTC = timezone.utc
NOW = datetime(2026, 9, 25, 14, 0, tzinfo=UTC)
#: A sampled transcript: (mtime, size) of the newest *.jsonl.
TR = (1_790_000_000.0, 4096)


def ago(minutes: float) -> datetime:
    return NOW - timedelta(minutes=minutes)


def stamp(minutes_ago: float, **fields: str) -> str:
    lines = [f"last_progress: {ago(minutes_ago).strftime(rules.TS_FORMAT)}"]
    return "\n".join(lines + [f"{k}: {v}" for k, v in fields.items()]) + "\n"


def flat(**kw) -> tuple[Sample, Sample]:
    """Two samples 30s apart where nothing moves."""
    first = Sample(at=NOW, **kw)
    return first, Sample(at=NOW + timedelta(seconds=30), **kw)


class StampFileTest(unittest.TestCase):
    def test_parses_with_the_shared_field_parser_in_any_order(self):
        text = "note: bazel test //...\nhold: 45m\nstep: 9\nlast_progress: 2026-09-25T13:41:07Z\n"
        s = rules.read_stamp(text)
        self.assertEqual(s.last_progress, datetime(2026, 9, 25, 13, 41, 7, tzinfo=UTC))
        self.assertEqual(s.hold, timedelta(minutes=45))
        self.assertEqual((s.step, s.note), ("9", "bazel test //..."))

    def test_only_last_progress_is_required(self):
        s = rules.read_stamp("last_progress: 2026-09-25T13:41:07Z\n")
        self.assertEqual((s.hold, s.step, s.note), (None, "", ""))

    def test_header_ends_at_a_heading_of_any_name(self):
        # plan-phase's boundary: the first "## " heading, whatever it is called.
        run = ("# RUN — x\n\nbase_sha: abc\nphase: implement\n\n## Something else\n\n"
               "last_progress: 2026-09-25T13:41:07Z\n")
        self.assertEqual(rules.server.field(rules.header(run), "phase"), "implement")
        self.assertIsNone(rules.read_stamp(run), "a key under a heading is not header")
        head_first = "last_progress: 2026-09-25T13:41:07Z\n## Log\n- line\n"
        self.assertIsNotNone(rules.read_stamp(head_first))

    def test_malformed_timestamp_is_rejected_not_read_as_fresh(self):
        for bad in ("last_progress: now\n", "last_progress: 2026-09-25 13:41\n",
                    "last_progress: 2026-13-45T99:00:00Z\n", "last_progress:\n", ""):
            self.assertIsNone(rules.read_stamp(bad), bad)
        # ... and a rejected stamp falls back to RUN.md's mtime, it does not
        # count as live on its own.
        self.assertEqual(rules.liveness(NOW, "last_progress: now\n", ago(30), True,
                                        flat(transcript=TR)),
                         STALLED)

    def test_write_is_write_then_rename(self):
        with TemporaryDirectory() as tmp:
            item = Path(tmp)
            rules.write_stamp(item, ago(5), step="7")
            seen = []
            real_replace = rules.os.replace

            def spy(src, dst):
                # At the instant of the rename: the target still holds the old
                # stamp whole, and the new one is complete under its tmp name.
                seen.append((Path(dst).read_text(), Path(src).read_text()))
                real_replace(src, dst)

            with mock.patch.object(rules.os, "replace", spy):
                rules.write_stamp(item, ago(1), step="9")
            self.assertEqual(len(seen), 1, "the stamp was not renamed into place")
            old, new = seen[0]
            self.assertEqual(rules.read_stamp(old).step, "7")
            self.assertEqual(rules.read_stamp(new).step, "9")
            self.assertEqual(rules.read_stamp((item / ".progress").read_text()).step, "9")
            self.assertFalse((item / ".progress.tmp").exists())

    def test_interleaved_reader_never_sees_a_partial_stamp(self):
        with TemporaryDirectory() as tmp:
            item = Path(tmp)
            rules.write_stamp(item, ago(0), step="0", note="x" * 4000)
            stop, bad = threading.Event(), []

            def reader():
                while not stop.is_set():
                    if rules.read_stamp((item / ".progress").read_text()) is None:
                        bad.append(1)

            t = threading.Thread(target=reader)
            t.start()
            for i in range(300):
                rules.write_stamp(item, ago(0), step=str(i), note="x" * 4000)
            stop.set()
            t.join()
            self.assertEqual(bad, [])

    def test_stamp_moves_with_the_item_directory(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            active = root / "specs/active/item"
            active.mkdir(parents=True)
            (active / "RUN.md").write_text("# RUN\n\nbase_sha: abc\n\n## Log\n")
            rules.write_stamp(active, ago(3), step="9")
            blocked = root / "specs/blocked/item"
            blocked.parent.mkdir(parents=True)
            shutil.move(str(active), str(blocked))
            self.assertEqual(rules.read_stamp((blocked / ".progress").read_text()).step, "9")


class LivenessTableTest(unittest.TestCase):
    """The decision table ORCHESTRATOR's "Liveness, then budget" bullet states."""

    def test_the_rule_takes_no_process_input(self):
        # Process CPU was the first corroborator tried; nothing records a pid,
        # so the model must not be able to express one.
        fields = {f.name for f in dataclasses.fields(Sample)}
        self.assertEqual(fields, {"at", "run_size", "run_mtime", "transcript", "status"})
        self.assertNotIn("cpu", " ".join(inspect.signature(rules.liveness).parameters))

    def test_fresh_stamp_is_live(self):
        self.assertEqual(rules.liveness(NOW, stamp(2), None, True), LIVE)

    def test_stale_stamp_alone_never_condemns(self):
        self.assertEqual(rules.liveness(NOW, stamp(30), None, True), SUSPECT)

    def test_stale_stamp_with_run_md_growing_is_live(self):
        first = Sample(at=NOW, run_size=100, run_mtime=ago(30), transcript=TR)
        second = Sample(at=NOW + timedelta(seconds=30), run_size=180,
                        run_mtime=NOW + timedelta(seconds=20), transcript=TR)
        self.assertEqual(rules.liveness(NOW, stamp(30), ago(30), True, (first, second)), LIVE)

    def test_stale_stamp_with_transcript_growing_is_live(self):
        first = Sample(at=NOW, run_size=100, run_mtime=ago(30), transcript=TR)
        second = Sample(at=NOW + timedelta(seconds=30), run_size=100, run_mtime=ago(30),
                        transcript=(TR[0] + 25, TR[1] + 4096))
        self.assertEqual(rules.liveness(NOW, stamp(30), ago(30), True, (first, second)), LIVE)

    def test_stale_stamp_within_its_hold_is_live(self):
        self.assertEqual(rules.liveness(NOW, stamp(30, hold="45m"), None, True), LIVE)
        # hold covers only its own window, not beyond it.
        self.assertEqual(rules.liveness(NOW, stamp(50, hold="45m"), None, True), SUSPECT)

    def test_stale_stamp_both_flat_is_stalled(self):
        samples = flat(run_size=100, run_mtime=ago(30), transcript=TR)
        self.assertEqual(rules.liveness(NOW, stamp(30), ago(30), True, samples), STALLED)

    def test_no_stamp_falls_back_to_run_md_mtime(self):
        self.assertEqual(rules.liveness(NOW, None, ago(2), True), LIVE)
        self.assertEqual(rules.liveness(NOW, None, ago(12), True), SUSPECT)

    def test_unsampleable_transcript_is_indeterminate_never_stalled(self):
        for first_tr, second_tr in ((None, None), (TR, None), (None, TR)):
            samples = (Sample(at=NOW, run_size=100, run_mtime=ago(30), transcript=first_tr),
                       Sample(at=NOW + timedelta(seconds=30), run_size=100,
                              run_mtime=ago(30), transcript=second_tr))
            state = rules.liveness(NOW, stamp(30), ago(30), True, samples)
            self.assertEqual(state, INDETERMINATE)
            # never a stall: no rescue, no relaunch; the budget still binds
            self.assertEqual(rules.stall_action(state, False, False, False, 0), "wait")
            self.assertEqual(rules.stall_action(state, True, False, False, 0),
                             "budget-exceeded")
        # no signal of any kind is the same: indeterminate, not a stall
        self.assertEqual(rules.liveness(NOW, None, None, True, flat()), INDETERMINATE)

    def test_samples_closer_than_30_seconds_are_refused(self):
        a = Sample(at=NOW, transcript=TR)
        b = Sample(at=NOW + timedelta(seconds=10), transcript=TR)
        with self.assertRaises(ValueError):
            rules.liveness(NOW, stamp(30), None, True, (a, b))

    def test_outside_the_executor_running_states_is_never_stalled(self):
        # The predicate is plan-phase's; this test passes its answer in and
        # names none of its states.
        for text, mtime in ((stamp(600), ago(600)), (None, None)):
            self.assertEqual(rules.liveness(NOW, text, mtime, False, flat(transcript=TR)),
                             NOT_RUNNING)


class TranscriptTest(unittest.TestCase):
    """Locating and sampling the transcript: no pid, no session id."""

    def test_slug_of_a_real_shaped_path(self):
        self.assertEqual(
            rules.transcript_dir("/Users/x/p/drydock-wt/2026-09-25-a.b", Path("/p")),
            Path("/p/-Users-x-p-drydock-wt-2026-09-25-a-b"))

    def test_newest_jsonl_wins_and_other_files_are_ignored(self):
        with TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "old.jsonl").write_text("x" * 10)
            (d / "new.jsonl").write_text("y" * 20)
            (d / "notes.txt").write_text("z" * 99)
            os.utime(d / "old.jsonl", (1000, 1000))
            os.utime(d / "new.jsonl", (2000, 2000))
            os.utime(d / "notes.txt", (3000, 3000))
            self.assertEqual(rules.newest_transcript(d), (2000, 20))

    def test_missing_dir_or_no_jsonl_is_unsampleable(self):
        with TemporaryDirectory() as tmp:
            d = Path(tmp)
            self.assertIsNone(rules.newest_transcript(d / "absent"))
            self.assertIsNone(rules.newest_transcript(d))
            (d / "x.txt").write_text("")
            self.assertIsNone(rules.newest_transcript(d))

    def test_subagent_transcript_growing_under_a_flat_parent_is_live(self):
        # A session waiting on a subagent: its own file is flat while
        # <sid>/subagents/agent-a.jsonl takes the turns.
        with TemporaryDirectory() as tmp:
            d = Path(tmp)
            parent, sub = d / "sid.jsonl", d / "sid" / "subagents" / "agent-a.jsonl"
            sub.parent.mkdir(parents=True)
            parent.write_text('{"p":1}\n')
            sub.write_text('{"a":1}\n')
            os.utime(parent, (1000, 1000))
            os.utime(sub, (1010, 1010))
            before = rules.newest_transcript(d)
            with sub.open("a") as fh:
                fh.write('{"a":2}\n')
            os.utime(sub, (1040, 1040))
            after = rules.newest_transcript(d)
            self.assertEqual(parent.stat().st_mtime, 1000, "the parent stayed flat")
            samples = (Sample(at=NOW, run_size=100, run_mtime=ago(30), transcript=before),
                       Sample(at=NOW + timedelta(seconds=30), run_size=100,
                              run_mtime=ago(30), transcript=after))
            self.assertEqual(rules.liveness(NOW, stamp(30), ago(30), True, samples), LIVE)
            # ... and the same layout with both files flat is a stall.
            still = rules.newest_transcript(d)
            self.assertEqual(rules.liveness(NOW, stamp(30), ago(30), True,
                                            flat(run_size=100, run_mtime=ago(30),
                                                 transcript=still)),
                             STALLED)

    def test_only_a_subagent_transcript_is_still_sampleable(self):
        with TemporaryDirectory() as tmp:
            sub = Path(tmp) / "sid" / "subagents" / "agent-a.jsonl"
            sub.parent.mkdir(parents=True)
            sub.write_text("x" * 7)
            os.utime(sub, (1500, 1500))
            self.assertEqual(rules.newest_transcript(Path(tmp)), (1500, 7))

    def test_empty_or_failed_sampler_output_is_unsampleable_never_equal(self):
        for returncode, stdout in ((0, ""), (0, "\n"), (1, ""), (1, "1500.0 7\n"),
                                   (0, "garbage"), (0, "1500.0 seven\n")):
            self.assertIsNone(rules.sampler_output(returncode, stdout), (returncode, stdout))
        self.assertEqual(rules.sampler_output(0, "1500.5 7\n"), (1500.5, 7))
        # Both reads empty: not an equal, therefore flat, pair.
        empty = rules.sampler_output(0, "")
        samples = flat(run_size=100, run_mtime=ago(30), transcript=empty)
        self.assertEqual(rules.liveness(NOW, stamp(30), ago(30), True, samples),
                         INDETERMINATE)

    def test_an_append_is_seen_across_two_samples(self):
        with TemporaryDirectory() as tmp:
            f = Path(tmp) / "s.jsonl"
            f.write_text('{"a":1}\n')
            os.utime(f, (1000, 1000))
            before = rules.newest_transcript(Path(tmp))
            with f.open("a") as fh:
                fh.write('{"b":2}\n')
            os.utime(f, (1030, 1030))
            self.assertNotEqual(before, rules.newest_transcript(Path(tmp)))


class RealSessionsTest(unittest.TestCase):
    """Real sessions, each re-expressed in the one measurement the rule uses.

    Source per fixture is in its comment. A value nobody recorded is marked
    [UNSOURCED] and the fixture asserts the mechanism, not a number.
    """

    def test_ef671360_blocked_in_one_tool_call_is_stalled(self):
        # SOURCED: review session ef671360, 2026-09-25. Its transcript has no
        # record between 17:11:33.018Z and 17:13:33.376Z (120 s) while it sat
        # inside one Bash call, read from the transcript's own timestamps.
        # 883524 bytes is the file's size summed through the 17:11:33.018Z
        # record, not its size today. RUN.md's size is inert (equal in both).
        t0 = datetime(2026, 9, 25, 17, 11, 33, 18000, tzinfo=UTC).timestamp()
        at = datetime(2026, 9, 25, 17, 12, 0, tzinfo=UTC)
        samples = (Sample(at=at, run_size=500, run_mtime=ago(30), transcript=(t0, 883_524)),
                   Sample(at=at + timedelta(seconds=90), run_size=500, run_mtime=ago(30),
                          transcript=(t0, 883_524)))
        self.assertEqual(rules.liveness(NOW, stamp(30), ago(30), True, samples), STALLED)
        # Non-vacuity: the same samples with the transcript advancing are live.
        # 885203 bytes: the size through its next record, at 17:13:33.376Z.
        t1 = datetime(2026, 9, 25, 17, 13, 33, 376000, tzinfo=UTC).timestamp()
        moved = (samples[0], dataclasses.replace(samples[1], transcript=(t1, 885_203)))
        self.assertEqual(rules.liveness(NOW, stamp(30), ago(30), True, moved), LIVE)

    def test_1100_healthy_build_is_live_on_stamp_age_alone(self):
        # SOURCED: 11:00, no RUN.md growth for 3 minutes. Live because 3 < 10
        # minutes: no corroboration is consulted, so none is supplied. Its
        # transcript was never sampled — [UNSOURCED], and not used.
        self.assertEqual(rules.liveness(NOW, None, ago(3), True), LIVE)
        self.assertEqual(rules.stall_action(LIVE, False, False, False, 0), "wait")

    def test_1105_closed_pipe_is_stalled_long_before_the_budget(self):
        # 11:05: 16 minutes without a write, 18 minutes into a 3h budget, the
        # session blocked on a closed pipe. Its transcript was never sampled —
        # [UNSOURCED]. Asserted from the mechanism ef671360 measured: a
        # session blocked inside a tool does not write its transcript.
        tr = (ago(16).timestamp(), 1)  # [UNSOURCED] placeholder: flat, not recorded
        samples = flat(run_size=500, run_mtime=ago(16), transcript=tr)
        state = rules.liveness(NOW, None, ago(16), True, samples)
        self.assertEqual(state, STALLED)
        self.assertEqual(rules.stall_action(state, over_budget=False, ready_present=False,
                                            tree_dirty=False, relaunches_used=0),
                         "rescue-and-relaunch")

    def test_status_string_is_not_evidence(self):
        # 11:00 and 11:05 both showed "shell". Relabelling changes nothing.
        wedged = flat(run_size=500, run_mtime=ago(16), transcript=TR)
        for status in ("shell", "waiting", "blocked", "running"):
            relabel = tuple(Sample(s.at, s.run_size, s.run_mtime, s.transcript, status)
                            for s in wedged)
            self.assertEqual(rules.liveness(NOW, None, ago(16), True, relabel), STALLED)
        self.assertEqual(rules.liveness(NOW, None, ago(3), True), LIVE)

    def test_host_sleep_over_budget_is_a_stall_not_a_budget_failure(self):
        # 2026-09-18: 67 minutes silent, 3h50m elapsed on a 2h budget. The
        # transcript across a sleep resume was never sampled — [UNSOURCED];
        # a frozen session writes nothing, so it is flat by mechanism.
        samples = flat(run_size=900, run_mtime=ago(67), transcript=(ago(67).timestamp(), 1))
        state = rules.liveness(NOW, None, ago(67), True, samples)
        self.assertEqual(state, STALLED)
        self.assertEqual(rules.stall_action(state, over_budget=True, ready_present=False,
                                            tree_dirty=False, relaunches_used=0),
                         "rescue-and-relaunch")

    def test_live_and_over_budget_is_still_over_budget(self):
        self.assertEqual(rules.stall_action(LIVE, True, False, False, 0), "budget-exceeded")

    def test_second_stall_is_a_dispatch_failure(self):
        self.assertEqual(rules.stall_action(STALLED, False, False, False, 1),
                         "dispatch-failure")


if __name__ == "__main__":
    unittest.main()
