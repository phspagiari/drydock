"""Tests for the queue predicates the contracts gate on.

    python3 -m unittest discover board/tests

The token is assembled at runtime, so this file never matches a plain
substring search for it either.
"""

import contextlib
import io
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import queue_rules  # noqa: E402
import server  # noqa: E402

TOKEN = "NEEDS" + " " + "CLARIFICATION"
SCRIPT = Path(queue_rules.__file__).resolve()


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def run(*argv: str) -> tuple[int, str, str]:
    """``queue_rules.main`` in-process: (exit code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = queue_rules.main(list(argv))
        except SystemExit as exc:  # argparse usage errors
            rc = exc.code
    return rc, out.getvalue(), err.getvalue()


class QueueTestCase(unittest.TestCase):
    """A fresh STATE_HOME per test; ``spec()`` drops an inbox SPEC.md."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = (Path(self._tmp.name) / "state").resolve()
        (self.root / "specs" / "inbox").mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def spec(self, item_id: str, text: str) -> Path:
        return write(self.root / "specs/inbox" / item_id / "SPEC.md", text)

    def shipped(self, state: str, item_id: str) -> None:
        write(self.root / state / item_id / "SPEC.md", "track: code\n")

    def eligible(self) -> list[str]:
        rc, out, err = run("eligible", "--root", str(self.root))
        self.assertEqual((rc, err), (0, ""))
        return out.splitlines()


class TestUnmetDeps(QueueTestCase):
    BLOCK = ("```yaml\ntrack: code\n"
             "depends_on:\n"
             "  - alpha-1   # delivered\n"
             "  - beta-2\n"
             "  - gamma-3\n"
             "budget:\n  max_agents: 1\n```\n")

    def test_block_list_three_ids_two_unmet_is_waiting_on_both(self):
        # The one-line grep read zero ids from this shape and called it eligible.
        self.shipped("deliverables", "alpha-1")
        self.spec("delta-4", self.BLOCK)
        self.assertEqual(queue_rules.deps_of(self.BLOCK), ["alpha-1", "beta-2", "gamma-3"])
        self.assertEqual(queue_rules.unmet_deps(self.root, self.BLOCK), ["beta-2", "gamma-3"])
        self.assertEqual(self.eligible(), ["WAITING\tdelta-4\tbeta-2,gamma-3"])

    def test_dep_in_deliverables_is_met(self):
        self.shipped("deliverables", "alpha-1")
        self.spec("beta-2", "depends_on: [alpha-1]\n")
        self.assertEqual(self.eligible(), ["ELIGIBLE\tbeta-2"])

    def test_dep_in_archive_is_met(self):
        self.shipped("archive", "alpha-1")
        self.spec("beta-2", "depends_on:\n  - alpha-1\n")
        self.assertEqual(self.eligible(), ["ELIGIBLE\tbeta-2"])

    def test_same_named_plain_file_is_not_met(self):
        write(self.root / "deliverables" / "alpha-1", "not a directory\n")
        write(self.root / "archive" / "alpha-1", "not a directory\n")
        self.spec("beta-2", "depends_on: [alpha-1]\n")
        self.assertEqual(self.eligible(), ["WAITING\tbeta-2\talpha-1"])

    def test_dep_still_in_the_queue_is_not_met(self):
        write(self.root / "specs/blocked/alpha-1/SPEC.md", "track: code\n")
        self.assertEqual(queue_rules.unmet_deps(self.root, "depends_on: [alpha-1]\n"),
                         ["alpha-1"])

    def test_no_depends_on_is_eligible(self):
        self.spec("alpha-1", "track: code\n\n# Spec: Nothing upstream\n")
        self.spec("beta-2", "depends_on: []\n")
        self.assertEqual(self.eligible(), ["ELIGIBLE\talpha-1", "ELIGIBLE\tbeta-2"])


class TestEligibleCli(QueueTestCase):
    def test_ids_in_lexicographic_order(self):
        for item_id in ["zeta-9", "alpha-1", "mu-5", "alpha-10"]:
            self.spec(item_id, "track: code\n")
        self.assertEqual([line.split("\t")[1] for line in self.eligible()],
                         ["alpha-1", "alpha-10", "mu-5", "zeta-9"])

    def test_hidden_and_spec_less_dirs_skipped(self):
        self.spec("alpha-1", "track: code\n")
        self.spec(".hidden-2", "track: code\n")
        (self.root / "specs/inbox/no-spec-3").mkdir()
        write(self.root / "specs/inbox/no-spec-3/QUESTION.md", "why\n")
        write(self.root / "specs/inbox/loose-file.md", "not an item\n")
        self.assertEqual(self.eligible(), ["ELIGIBLE\talpha-1"])

    def test_empty_inbox_prints_nothing(self):
        self.assertEqual(self.eligible(), [])

    def test_exit_2_on_missing_root(self):
        rc, out, err = run("eligible", "--root", str(self.root / "nowhere"))
        self.assertEqual((rc, out), (2, ""))
        self.assertIn("not a directory", err)

    def test_exit_2_on_root_without_inbox(self):
        (self.root / "specs" / "inbox").rmdir()
        rc, out, err = run("eligible", "--root", str(self.root))
        self.assertEqual((rc, out), (2, ""))
        self.assertIn("specs/inbox", err)

    def test_script_defaults_root_to_state_home_env(self):
        # Runs the file as the loop does, so the lazy server import is exercised.
        self.spec("alpha-1", "depends_on: [beta-2]\n")
        env = dict(os.environ, DRYDOCK_STATE_HOME=str(self.root))
        done = subprocess.run([sys.executable, str(SCRIPT), "eligible"],
                              capture_output=True, text=True, env=env, check=False)
        self.assertEqual((done.returncode, done.stdout, done.stderr),
                         (0, "WAITING\talpha-1\tbeta-2\n", ""))

    def test_board_gist_and_eligible_agree(self):
        self.shipped("deliverables", "dep-done")
        self.shipped("archive", "dep-old")
        self.spec("alpha-1", "depends_on: [dep-done, dep-old]\n")
        self.spec("beta-2", "depends_on:\n  - dep-done\n  - never-a\n  - never-b\n")
        self.spec("gamma-3", "depends_on: [never-c]  # upstream\n")
        board = {}
        for row in server.scan(self.root)["inbox"]:
            gist = row["gist"]
            board[row["id"]] = (gist.removeprefix("waiting on: ").split(", ")
                                if gist.startswith("waiting on: ") else [])
        cli = {}
        for line in self.eligible():
            parts = line.split("\t")
            cli[parts[1]] = parts[2].split(",") if parts[0] == "WAITING" else []
        self.assertEqual(board, cli)
        self.assertEqual(cli["beta-2"], ["never-a", "never-b"])


def too_many_digits(case: unittest.TestCase) -> int:
    """One digit past ``int()``'s string limit; skips where there is no limit."""
    limit = getattr(sys, "get_int_max_str_digits", lambda: 0)()
    if not limit:
        case.skipTest("this interpreter has no int-from-string digit limit")
    return limit + 1


class SlotsTestCase(QueueTestCase):
    """``specs/active/`` exists; ``active(n)`` drops n item dirs, ``config()`` the file."""

    def setUp(self):
        super().setUp()
        (self.root / "specs" / "active").mkdir()

    def active(self, n: int) -> None:
        for i in range(1, n + 1):
            (self.root / "specs/active" / f"item-{i}").mkdir()

    def config(self, text: str) -> None:
        write(self.root / "config", text)

    def slots(self) -> tuple[int, str, str]:
        return run("slots", "--root", str(self.root))


class TestMaxConcurrent(unittest.TestCase):
    """The cap is the ``max_concurrent:`` line, default 2, fail closed."""

    def test_missing_file_means_2(self):
        self.assertEqual(queue_rules.max_concurrent(None), 2)

    def test_missing_key_means_2(self):
        self.assertEqual(queue_rules.max_concurrent("namespace: t\npermission_mode: x\n"), 2)

    def test_value_with_inline_comment_and_whitespace(self):
        text = "namespace: t\nmax_concurrent:   10   # set by hand\n"
        self.assertEqual(queue_rules.max_concurrent(text), 10)

    def test_no_upper_bound(self):
        self.assertEqual(queue_rules.max_concurrent("max_concurrent: 250\n"), 250)

    def test_invalid_values_fail_closed(self):
        for value in ("0", "-1", "ten", "007", "1.5", "+3", "10 10", "'3'", "\"3\""):
            with self.subTest(value=value), self.assertRaises(queue_rules.SlotsError):
                queue_rules.max_concurrent(f"max_concurrent: {value}\n")

    def test_empty_value_does_not_fall_through_to_the_default(self):
        # field() needs a non-empty value, so it reads these as "absent" -> 2.
        for line in ("max_concurrent:", "max_concurrent:   ", "max_concurrent:  # later"):
            with self.subTest(line=line):
                self.assertEqual(queue_rules.field(line + "\n", "max_concurrent")
                                 .split("#")[0].strip(), "")
                with self.assertRaises(queue_rules.SlotsError):
                    queue_rules.max_concurrent("namespace: t\n" + line + "\n")

    def test_empty_value_as_the_last_line_without_newline(self):
        with self.assertRaises(queue_rules.SlotsError):
            queue_rules.max_concurrent("namespace: t\nmax_concurrent:")

    def test_two_lines_fail_closed_even_when_equal(self):
        for text in ("max_concurrent: 3\nmax_concurrent: 4\n",
                     "max_concurrent: 3\nnamespace: t\nmax_concurrent: 3\n"):
            with self.subTest(text=text), self.assertRaises(queue_rules.SlotsError):
                queue_rules.max_concurrent(text)

    def test_other_keys_and_comments_are_not_the_key(self):
        text = ("# max_concurrent: 9\nmy_max_concurrent: 8\nmax_concurrent_x: 7\n"
                "max_concurrent: 4\n")
        self.assertEqual(queue_rules.max_concurrent(text), 4)


class TestSlotsCli(SlotsTestCase):
    """``<free>\\t<cap>\\t<active>``, exit 0; exit 2 and no stdout otherwise."""

    def test_counts_dirs_only_and_skips_hidden(self):
        self.active(9)
        (self.root / "specs/active/.hidden").mkdir()
        write(self.root / "specs/active/loose-file", "not an item\n")
        self.config("namespace: t\nmax_concurrent: 10   # note\n")
        self.assertEqual(self.slots(), (0, "1\t10\t9\n", ""))

    def test_default_cap_without_config(self):
        self.active(1)
        self.assertEqual(self.slots(), (0, "1\t2\t1\n", ""))

    def test_free_never_negative(self):
        self.active(3)
        self.config("namespace: t\n")
        self.assertEqual(self.slots(), (0, "0\t2\t3\n", ""))

    def test_at_the_cap_nothing_is_free(self):
        self.active(10)
        self.config("max_concurrent: 10\n")
        self.assertEqual(self.slots(), (0, "0\t10\t10\n", ""))

    def test_empty_active_dir(self):
        self.config("max_concurrent: 5\n")
        self.assertEqual(self.slots(), (0, "5\t5\t0\n", ""))

    def test_invalid_config_exits_2_with_nothing_on_stdout(self):
        self.active(1)
        for text in ("max_concurrent: 0\n", "max_concurrent: -1\n", "max_concurrent: ten\n",
                     "max_concurrent: \n", "max_concurrent: 3\nmax_concurrent: 4\n"):
            with self.subTest(text=text):
                self.config(text)
                rc, out, err = self.slots()
                self.assertEqual((rc, out), (2, ""))
                self.assertIn("max_concurrent", err)

    def test_value_too_long_to_parse_exits_2(self):
        # Matches the pattern, but int() refuses strings past the interpreter's
        # digit limit; that must be a refusal, not a traceback and exit 1.
        # Run as the loop does, so an escaped exception shows as exit 1, not an ERROR.
        self.active(1)
        self.config(f"max_concurrent: {'9' * too_many_digits(self)}\n")
        done = subprocess.run([sys.executable, str(SCRIPT), "slots", "--root", str(self.root)],
                              capture_output=True, text=True, check=False)
        self.assertEqual((done.returncode, done.stdout), (2, ""), done.stderr[-300:])
        self.assertIn("too long", done.stderr)
        self.assertNotIn("Traceback", done.stderr)

    def test_config_that_is_a_directory_exits_2(self):
        (self.root / "config").mkdir()
        rc, out, err = self.slots()
        self.assertEqual((rc, out), (2, ""))
        self.assertIn("config", err)

    def test_exit_2_on_missing_root(self):
        rc, out, err = run("slots", "--root", str(self.root / "nowhere"))
        self.assertEqual((rc, out), (2, ""))
        self.assertIn("not a directory", err)

    def test_exit_2_on_root_without_active(self):
        (self.root / "specs" / "active").rmdir()
        rc, out, err = self.slots()
        self.assertEqual((rc, out), (2, ""))
        self.assertIn("specs/active", err)

    def test_exit_2_when_active_is_a_file(self):
        (self.root / "specs" / "active").rmdir()
        write(self.root / "specs" / "active", "not a directory\n")
        rc, out, err = self.slots()
        self.assertEqual((rc, out), (2, ""))
        self.assertIn("specs/active", err)

    def test_script_defaults_root_to_state_home_env(self):
        self.active(2)
        self.config("max_concurrent: 3\n")
        env = dict(os.environ, DRYDOCK_STATE_HOME=str(self.root))
        done = subprocess.run([sys.executable, str(SCRIPT), "slots"],
                              capture_output=True, text=True, env=env, check=False)
        self.assertEqual((done.returncode, done.stdout, done.stderr), (0, "1\t3\t2\n", ""))


class TestBoardSlots(SlotsTestCase):
    """The board's ``active <n>/<cap>`` comes from the same function."""

    def test_board_and_cli_agree(self):
        self.active(4)
        (self.root / "specs/active/.hidden").mkdir()
        self.config("max_concurrent: 6  # note\n")
        _, out, _ = self.slots()
        free, cap, active = (int(v) for v in out.split("\t"))
        self.assertEqual(server.scan(self.root)["slots"],
                         {"free": free, "cap": cap, "active": active})
        self.assertEqual((free, cap, active), (2, 6, 4))

    def test_board_survives_an_invalid_config(self):
        self.config("max_concurrent: 0\n")
        state = server.scan(self.root)["slots"]
        self.assertEqual(set(state), {"error"})
        self.assertIn("max_concurrent", state["error"])

    def test_board_survives_a_value_too_long_to_parse(self):
        self.config(f"max_concurrent: {'9' * too_many_digits(self)}\n")
        try:
            state = server.scan(self.root)["slots"]
        except Exception as exc:  # the defect: scan() itself raising
            self.fail(f"scan() raised {type(exc).__name__}: {str(exc)[:120]}")
        self.assertEqual(set(state), {"error"})
        self.assertIn("too long", state["error"])

    def test_board_survives_a_missing_active_dir(self):
        (self.root / "specs" / "active").rmdir()
        self.assertIn("specs/active", server.scan(self.root)["slots"]["error"])


class TestServerReexports(unittest.TestCase):
    def test_board_uses_the_same_objects(self):
        for name in ("field", "deps_of", "_chain_field", "chain_errors",
                     "DEFAULT_BRANCHES", "unmet_deps", "slots", "SlotsError"):
            with self.subTest(name=name):
                self.assertIs(getattr(server, name), getattr(queue_rules, name))


class TestFindMarkers(unittest.TestCase):
    def markers(self, *lines: str) -> list[tuple[int, str]]:
        return queue_rules.find_markers("\n".join(lines) + "\n")

    def test_bracketed_with_colon_and_body_is_a_marker(self):
        self.assertEqual(self.markers("# Spec", "", f"- [{TOKEN}: which store?]"),
                         [(3, "which store?")])

    def test_bare_bracketed_words_are_not_a_marker(self):
        self.assertEqual(self.markers(f"- Any unresolved [{TOKEN}] at execution time."), [])

    def test_bare_words_without_brackets_are_not_a_marker(self):
        self.assertEqual(self.markers(f"The {TOKEN} convention: {TOKEN}: x"), [])

    def test_empty_or_blank_body_is_not_a_marker(self):
        self.assertEqual(self.markers(f"[{TOKEN}:]", f"[{TOKEN}: ]", f"[{TOKEN}:\t ]"), [])

    def test_backticked_mention_is_not_a_marker(self):
        self.assertEqual(self.markers(f"- Any unresolved `[{TOKEN}]` at execution time.",
                                      f"- write `[{TOKEN}: …]` for a gap",
                                      f"- or ``[{TOKEN}: with ` inside]``"), [])

    def test_unclosed_backtick_is_literal(self):
        self.assertEqual(self.markers(f"a stray ` then [{TOKEN}: real]"), [(1, "real")])

    def test_real_marker_after_a_code_span_on_the_same_line(self):
        self.assertEqual(self.markers(f"see `[{TOKEN}: quoted]` and [{TOKEN}: real one]"),
                         [(1, "real one")])

    def test_two_markers_on_one_line(self):
        self.assertEqual(self.markers(f"[{TOKEN}: first] and [{TOKEN}: second]"),
                         [(1, "first"), (1, "second")])

    def test_single_line_comment_hides_a_marker(self):
        self.assertEqual(self.markers(f"<!-- [{TOKEN}: hidden] --> [{TOKEN}: shown]"),
                         [(1, "shown")])

    def test_multi_line_comment_hides_markers(self):
        self.assertEqual(self.markers("<!--",
                                      f"  Convention: [{TOKEN}: ...] markers flag gaps",
                                      "-->",
                                      f"[{TOKEN}: after the comment]"),
                         [(4, "after the comment")])

    def test_comment_closing_mid_line_resumes_matching(self):
        self.assertEqual(self.markers("<!-- opens",
                                      f"still [{TOKEN}: hidden] --> [{TOKEN}: shown]"),
                         [(2, "shown")])

    def test_backtick_fence_hides_markers(self):
        self.assertEqual(self.markers("```markdown", f"[{TOKEN}: in fence]", "```",
                                      f"[{TOKEN}: after fence]"),
                         [(4, "after fence")])

    def test_tilde_fence_and_longer_fence_hide_markers(self):
        self.assertEqual(self.markers("~~~", f"[{TOKEN}: tilde]", "~~~",
                                      "````", "```", f"[{TOKEN}: nested]", "```", "````",
                                      f"[{TOKEN}: out]"),
                         [(9, "out")])

    def test_fence_delimiter_inside_a_comment_opens_nothing(self):
        self.assertEqual(self.markers("<!--", "```", "-->", f"[{TOKEN}: visible]"),
                         [(4, "visible")])

    def test_marker_spanning_lines_is_not_a_marker(self):
        self.assertEqual(self.markers(f"[{TOKEN}: starts here", "and ends here]"), [])

    def test_line_numbers_count_blank_and_masked_lines(self):
        text = "\n".join(["a", "", "```", "x", "```", "<!--", "c", "-->", "",
                          f"[{TOKEN}: ten]", "", f"[{TOKEN}: twelve]"])
        self.assertEqual(queue_rules.find_markers(text), [(10, "ten"), (12, "twelve")])

    def test_shipped_template_header_comment_is_not_a_marker(self):
        template = Path(__file__).resolve().parents[2] / "templates/spec-template.md"
        lines = template.read_text().split("\n")
        header_end = lines.index("-->") + 1
        self.assertIn(TOKEN, "\n".join(lines[:header_end]))  # the header does mention it
        found = queue_rules.find_markers("\n".join(lines))
        self.assertTrue(all(line > header_end for line, _ in found), found)


class TestCheckCli(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_check_clean_file_exits_0(self):
        path = write(self.dir / "SPEC.md",
                     f"track: code\n\n- Any unresolved `[{TOKEN}]` at execution time.\n")
        self.assertEqual(run("check", str(path)), (0, "", ""))

    def test_check_marker_exits_1(self):
        path = write(self.dir / "SPEC.md", f"track: code\n\n- **FR-001**: [{TOKEN}: which?]\n")
        self.assertEqual(run("check", str(path)), (1, f"{path}:3: marker: which?\n", ""))

    def test_check_chain_error_exits_1(self):
        path = write(self.dir / "SPEC.md", "track: code\nbranch: main\n")
        rc, out, _ = run("check", str(path))
        self.assertEqual(rc, 1)
        self.assertTrue(out.startswith(f"{path}:0: chain: branch: is main"), out)

    def test_check_unreadable_path_exits_2(self):
        clean = write(self.dir / "SPEC.md", "track: code\n")
        rc, out, err = run("check", str(clean), str(self.dir / "missing.md"))
        self.assertEqual((rc, out), (2, ""))
        self.assertIn("missing.md", err)

    def test_check_unreadable_outranks_a_finding(self):
        marked = write(self.dir / "SPEC.md", f"[{TOKEN}: open]\n")
        rc, out, _ = run("check", str(self.dir), str(marked))
        self.assertEqual(rc, 2)
        self.assertEqual(out, f"{marked}:1: marker: open\n")

    def test_check_without_paths_is_a_usage_error(self):
        rc, _, err = run("check")
        self.assertEqual(rc, 2)
        self.assertIn("usage", err)


if __name__ == "__main__":
    unittest.main()
