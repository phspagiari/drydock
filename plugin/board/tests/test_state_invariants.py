"""The copied-review invariant: ``state_errors()``, its gist and ``check``.

    python3 -m unittest discover board/tests

Archiving a review round is a rename. A ``REVIEW.md`` byte-identical to one
of its own ``REVIEW-r<N>.md`` archives means the archive was made with a copy
and the stale file still reads as the current round. Every positive case here
has a twin one byte away that must stay clean, so a check that flags
everything fails as surely as one that flags nothing.
"""

import io
import subprocess
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import server  # noqa: E402

SERVER = Path(server.__file__).resolve()


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def review(round_: int, verdict: str = "fix", note: str = "") -> str:
    return f"verdict: {verdict}\nround: {round_}\nfindings: 1\n\n{note}\n"


class StateErrorsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.item = Path(self._tmp.name) / "item"
        self.item.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def test_identical_review_and_archive_is_one_error(self):
        write(self.item / "REVIEW-r1.md", review(1))
        write(self.item / "REVIEW.md", review(1))
        errors = server.state_errors(self.item)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("REVIEW.md is a copy of REVIEW-r1.md", errors[0])
        self.assertIn("the archive was a copy, not a rename", errors[0])

    def test_one_byte_apart_is_clean(self):
        # Non-vacuity twin of the case above.
        write(self.item / "REVIEW-r1.md", review(1))
        write(self.item / "REVIEW.md", review(1) + " ")
        self.assertEqual(server.state_errors(self.item), [])

    def test_batch_reset_rounds_name_the_copied_archive(self):
        # Round numbers restart per comment batch: seven archives carry
        # rounds 1,2,3,1,2,1,2. The copy is of the seventh.
        for n, round_ in enumerate((1, 2, 3, 1, 2, 1, 2), start=1):
            write(self.item / f"REVIEW-r{n}.md", review(round_, note=f"archive {n}"))
        write(self.item / "REVIEW.md", review(2, note="archive 7"))
        errors = server.state_errors(self.item)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("REVIEW-r7.md", errors[0])

    def test_round_value_is_not_read(self):
        # A fresh REVIEW.md at round 1 beside archives that already reached
        # round 3 is a new comment batch, not malformed state.
        for n, round_ in enumerate((1, 2, 3, 1, 2, 1, 2), start=1):
            write(self.item / f"REVIEW-r{n}.md", review(round_, note=f"archive {n}"))
        write(self.item / "REVIEW.md", review(1, note="a new batch"))
        self.assertEqual(server.state_errors(self.item), [])

    def test_unnumbered_archive_names_are_ignored(self):
        body = review(2, note="partial")
        write(self.item / "REVIEW-partial-crash2.md", body)
        write(self.item / "REVIEW-rX.md", body)
        write(self.item / "REVIEW.md", body)
        self.assertEqual(server.state_errors(self.item), [])

    def test_plan_review_copy_is_one_error(self):
        write(self.item / "PLAN-REVIEW-r1.md", "verdict: flag\nfindings: 2\n")
        write(self.item / "PLAN-REVIEW.md", "verdict: flag\nfindings: 2\n")
        errors = server.state_errors(self.item)
        self.assertEqual(len(errors), 1, errors)
        self.assertIn("PLAN-REVIEW.md is a copy of PLAN-REVIEW-r1.md", errors[0])

    def test_no_current_file_is_clean(self):
        write(self.item / "REVIEW-r1.md", review(1))
        write(self.item / "REVIEW-r2.md", review(1))
        self.assertEqual(server.state_errors(self.item), [])


class GistOrderTest(unittest.TestCase):
    """chain error > state error > blocker / waiting."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def card(self, state: str, item_id: str, spec: str, copied: bool,
             question: str = "") -> dict:
        item = server.state_dir(self.root, state) / item_id
        write(item / "SPEC.md", spec)
        if question:
            write(item / "QUESTION.md", question)
        write(item / "REVIEW-r1.md", review(1))
        write(item / "REVIEW.md", review(1) if copied else review(2))
        return server.scan_item(self.root, item, state)

    def test_chain_error_outranks_state_error(self):
        card = self.card("inbox", "chained", "track: code\nbranch: main\n", True)
        self.assertTrue(card["gist"].startswith("chain error: "), card["gist"])
        self.assertEqual(len(card["state_errors"]), 1)

    def test_state_error_outranks_the_blocker(self):
        card = self.card("blocked", "blocked", "track: code\n", True,
                         question="blocker: the human must pick\n")
        self.assertTrue(card["gist"].startswith("state error: "), card["gist"])
        self.assertIn("REVIEW-r1.md", card["gist"])

    def test_state_error_outranks_waiting(self):
        card = self.card("inbox", "waiting", "track: code\ndepends_on: [never-shipped]\n",
                         True)
        self.assertTrue(card["gist"].startswith("state error: "), card["gist"])

    def test_clean_item_keeps_its_blocker_and_waiting_gists(self):
        blocked = self.card("blocked", "blocked", "track: code\n", False,
                            question="blocker: the human must pick\n")
        self.assertEqual(blocked["gist"], "the human must pick")
        self.assertEqual(blocked["state_errors"], [])
        waiting = self.card("inbox", "waiting", "track: code\ndepends_on: [never-shipped]\n",
                            False)
        self.assertEqual(waiting["gist"], "waiting on: never-shipped")


class CheckCommandTest(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def run_check(self, root: Path) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = server.main(["check", "--root", str(root)])
        return code, out.getvalue(), err.getvalue()

    def test_dirty_root_exits_1_and_names_state_and_id(self):
        write(self.root / "archive/old-item/REVIEW-r1.md", review(1))
        write(self.root / "archive/old-item/REVIEW.md", review(1))
        write(self.root / "specs/active/live-item/REVIEW.md", review(1))
        code, out, _ = self.run_check(self.root)
        self.assertEqual(code, 1)
        self.assertEqual(out.splitlines(), [
            "archive/old-item: REVIEW.md is a copy of REVIEW-r1.md; "
            "the archive was a copy, not a rename",
        ])

    def test_every_state_is_scanned(self):
        for state in server.STATES:
            item = server.state_dir(self.root, state) / f"{state}-item"
            write(item / "REVIEW-r1.md", review(1))
            write(item / "REVIEW.md", review(1))
        code, out, _ = self.run_check(self.root)
        self.assertEqual(code, 1)
        self.assertEqual(sorted(line.split(":")[0] for line in out.splitlines()),
                         sorted(f"{s}/{s}-item" for s in server.STATES))

    def test_clean_root_exits_0_silently(self):
        write(self.root / "specs/active/live-item/REVIEW-r1.md", review(1))
        write(self.root / "specs/active/live-item/REVIEW.md", review(2))
        self.assertEqual(self.run_check(self.root), (0, "", ""))

    def test_missing_root_exits_2(self):
        code, out, err = self.run_check(self.root / "absent")
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("no such directory", err)

    def test_script_entry_point_carries_the_exit_code(self):
        write(self.root / "archive/old-item/REVIEW-r1.md", review(1))
        write(self.root / "archive/old-item/REVIEW.md", review(1))
        proc = subprocess.run([sys.executable, str(SERVER), "check",
                               "--root", str(self.root)],
                              capture_output=True, text=True, check=False)
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertIn("archive/old-item: REVIEW.md is a copy of REVIEW-r1.md",
                      proc.stdout)


if __name__ == "__main__":
    unittest.main()
