"""Complete but wedged: review does not wait for the session (ORCHESTRATOR "Active").

    python3 -m unittest discover plugin/board/tests

The 2026-09-25 11:05 wedge happened after READY.md was written: the work was
finished on disk and the session was never coming back. The rule is READY.md
present, a clean tree and an unchanged HEAD across a 5-minute window → stop
the session and dispatch the reviewer, whatever the stamp says.

The same shape struck an escalation on 2026-09-25: QUESTION.md finished, then
a wedge while moving the item. An open QUESTION.md is the handler's first
arm, ahead of READY.md.
"""

import inspect
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import liveness_rules as rules  # noqa: E402
from liveness_rules import LIVE, STALLED, Sample  # noqa: E402

UTC = timezone.utc
T0 = datetime(2026, 9, 25, 11, 5, tzinfo=UTC)
CLEAN = ("", "")
#: Every action the stall handler takes when arm (i) does not fire.
ORDINARY = {"rescue-and-relaunch", "dispatch-failure", "leave-to-ready-review",
            "block-with-question", "wait", "budget-exceeded"}
OPEN = "# QUESTION — x\n\n## Q1 — a decision\n\nWhich one?\n"
RESOLVED = OPEN + "\n## Resolution (2026-09-27)\n\nOption 1.\n"


def heads(sha0: str, sha1: str, minutes: float = 5) -> tuple:
    return (T0, sha0), (T0 + timedelta(minutes=minutes), sha1)


class ReadyWedgedTest(unittest.TestCase):
    def test_ready_clean_and_still_dispatches_review(self):
        self.assertEqual(rules.ready_action(True, True, heads("abc", "abc"), CLEAN),
                         "stop-session-and-review")

    def test_regardless_of_stamp_age_and_of_the_stall_handler(self):
        # The routing reads no stamp and no stall verdict: nothing about
        # liveness is an input, so neither a fresh stamp nor a stall handler
        # that has not run yet can hold review up.
        params = set(inspect.signature(rules.ready_action).parameters)
        self.assertEqual(params, {"ready_present", "session_live", "heads", "porcelain",
                                  "question_open"})
        # ... while the stall branch, for the same item, stands aside.
        for state in (LIVE, STALLED):
            self.assertNotEqual(rules.stall_action(state, False, True, False, 0),
                                "rescue-and-relaunch")

    def test_head_moving_inside_the_window_waits(self):
        self.assertEqual(rules.ready_action(True, True, heads("abc", "def"), CLEAN), "wait")

    def test_dirty_tree_waits(self):
        dirty = ("", " M plugin/contracts/DISPATCH.md\n")
        self.assertEqual(rules.ready_action(True, True, heads("abc", "abc"), dirty), "wait")

    def test_window_shorter_than_five_minutes_waits(self):
        # 3 minutes is the longest quiet pause seen in a healthy executor.
        self.assertEqual(rules.ready_action(True, True, heads("abc", "abc", 3), CLEAN), "wait")

    def test_window_sits_between_healthy_pause_and_stall_threshold(self):
        self.assertLess(timedelta(minutes=3), rules.READY_WINDOW)
        self.assertLess(rules.READY_WINDOW, rules.STALL_THRESHOLD)

    def test_no_ready_md_waits(self):
        self.assertEqual(rules.ready_action(False, True, heads("abc", "abc"), CLEAN), "wait")

    def test_exited_session_is_reviewed_as_before(self):
        self.assertEqual(rules.ready_action(True, False, heads("abc", "def", 0), ("", "?? x")),
                         "review")

    def test_stall_handler_never_rescues_resets_or_relaunches_a_ready_item(self):
        # The reset guard ("every commit was made by this run and
        # none is on any remote") is satisfied by a finished, unpushed run, so
        # a READY check placed after the rescue would strip the finished
        # commit. READY.md is checked first and covers the whole handler.
        rescue = {"rescue-and-relaunch", "dispatch-failure"}
        for over_budget in (False, True):
            for used in (0, 1):
                clean = rules.stall_action(STALLED, over_budget, True, False, used)
                dirty = rules.stall_action(STALLED, over_budget, True, True, used)
                self.assertEqual(clean, "leave-to-ready-review")
                self.assertEqual(dirty, "block-with-question")
                self.assertNotIn(clean, rescue)
                self.assertNotIn(dirty, rescue)

    def test_ready_clean_stalled_item_reaches_review(self):
        # The stall handler stands aside and the ready path, which reads no
        # stall verdict, dispatches the reviewer.
        self.assertEqual(rules.stall_action(STALLED, False, True, False, 0),
                         "leave-to-ready-review")
        self.assertEqual(rules.ready_action(True, True, heads("abc", "abc"), CLEAN),
                         "stop-session-and-review")


class OpenQuestionTest(unittest.TestCase):
    """Arm (i): an open QUESTION.md in active/<id>/ is a finished escalation."""

    def test_open_means_the_last_heading_is_not_a_resolution(self):
        self.assertTrue(rules.question_open(OPEN))
        self.assertFalse(rules.question_open(RESOLVED))
        self.assertTrue(rules.question_open("# QUESTION\n\nno sections at all\n"))
        # a later round's question after a resolution is open again
        self.assertTrue(rules.question_open(RESOLVED + "\n## R2-1 — another\n"))
        # a heading merely mentioning a resolution is not one
        self.assertTrue(rules.question_open(OPEN + "\n## Proposed Resolution\n"))

    def test_open_question_completes_the_move_and_never_rescues(self):
        for ready in (False, True):
            for over_budget in (False, True):
                for used in (0, 1):
                    clean = rules.stall_action(STALLED, over_budget, ready, False, used,
                                               question_open=True)
                    dirty = rules.stall_action(STALLED, over_budget, ready, True, used,
                                               question_open=True)
                    self.assertEqual(clean, "complete-move-to-blocked")
                    self.assertEqual(dirty, "complete-move-to-blocked-noting-dirty")
                    self.assertNotIn(clean, ORDINARY)
                    self.assertNotIn(dirty, ORDINARY)

    def test_a_resolved_question_falls_through_to_ordinary_stall_handling(self):
        closed = rules.question_open(RESOLVED)
        self.assertEqual(rules.stall_action(STALLED, False, False, False, 0, closed),
                         "rescue-and-relaunch")
        self.assertEqual(rules.stall_action(STALLED, False, True, False, 0, closed),
                         "leave-to-ready-review")

    def test_ready_with_an_open_question_is_not_reviewed(self):
        self.assertEqual(rules.ready_action(True, True, heads("abc", "abc"), CLEAN,
                                            question_open=True), "block")
        self.assertEqual(rules.ready_action(True, False, heads("abc", "abc"), CLEAN,
                                            question_open=True), "block")
        self.assertEqual(rules.ready_action(True, True, heads("abc", "abc"), CLEAN,
                                            question_open=False), "stop-session-and-review")

    def test_chained_pr_stays_draft_is_stalled_then_moved_not_rescued(self):
        # SOURCED: executor session 799976b0, 2026-09-25, from its transcript
        # and the orchestrator's note in its RUN.md. QUESTION.md written
        # 22:24:28Z; the next call, the Bash move to blocked/, wedged on a
        # prompt; the transcript's last timestamped record is 22:24:34.688Z;
        # RUN.md last written 22:25Z; no .progress (dispatched before it
        # existed), no READY.md, tree clean, one unpushed commit. Transcript
        # size is [UNSOURCED] and inert: only its being flat is used.
        run_mtime = datetime(2026, 9, 25, 22, 25, tzinfo=UTC)
        last = datetime(2026, 9, 25, 22, 24, 34, 688000, tzinfo=UTC).timestamp()
        tick = datetime(2026, 9, 25, 22, 36, tzinfo=UTC)
        tr = (last, 1)  # [UNSOURCED] size
        samples = (Sample(at=tick, run_size=1, run_mtime=run_mtime, transcript=tr),
                   Sample(at=tick + timedelta(seconds=35), run_size=1, run_mtime=run_mtime,
                          transcript=tr))
        state = rules.liveness(tick, None, run_mtime, True, samples)
        self.assertEqual(state, STALLED)
        # 22:34Z is inside the 10-minute threshold: not yet suspect.
        self.assertEqual(rules.liveness(datetime(2026, 9, 25, 22, 34, tzinfo=UTC), None,
                                        run_mtime, True), LIVE)
        action = rules.stall_action(state, over_budget=False, ready_present=False,
                                    tree_dirty=False, relaunches_used=0,
                                    question_open=rules.question_open(OPEN))
        self.assertEqual(action, "complete-move-to-blocked")
        # Non-vacuity: without arm (i) the same item is rescued and reset.
        self.assertEqual(rules.stall_action(state, False, False, False, 0),
                         "rescue-and-relaunch")


if __name__ == "__main__":
    unittest.main()
