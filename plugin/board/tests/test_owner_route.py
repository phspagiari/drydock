"""Tests for ``queue_rules.py route`` and the ``owner:`` findings of ``check``.

    python3 -m unittest discover plugin/board/tests

A spec may name the session that receives its notifications with an
``owner:`` line. Only the spec's frontmatter -- its first yaml fenced block --
can set it, so the fixtures under ``fixtures/route/`` are whole specs in the
template's shape, each carrying exactly the owner line its name says, and the
dangerous direction (an owner read from somewhere it must not be read) has a
fixture of its own: ``body-only.md`` and ``commented.md`` must route to the
human.
"""

import contextlib
import io
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import queue_rules  # noqa: E402

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures" / "route"
TEMPLATE = HERE.parents[1] / "templates" / "spec-template.md"
SCRIPT = Path(queue_rules.__file__).resolve()


def run(*argv: str) -> tuple[int, str, str]:
    """``queue_rules.main`` in-process: (exit code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = queue_rules.main(list(argv))
        except SystemExit as exc:  # argparse usage errors
            rc = exc.code
    return rc, out.getvalue(), err.getvalue()


def fixture(name: str) -> str:
    return str(FIXTURES / f"{name}.md")


def spec(*frontmatter: str, body: str = "## Context\n\nProse.\n") -> str:
    """A minimal spec: a title, one yaml block holding ``frontmatter``, a body."""
    block = "\n".join(("id: 2026-11-09-x", "track: code") + frontmatter)
    return f"# Spec: x\n\n```yaml\n{block}\n```\n\n{body}"


class TestFixturesAreWhatTheyClaim(unittest.TestCase):
    """The fixtures carry exactly the owner line their names promise."""

    EXPECTED = {
        "owner": ["owner: lead-a"],
        "none": [],
        "commented": ["# owner: lead-a"],
        "body-only": ["owner: lead-a"],
        "invalid": ["owner: lead a!"],
        "duplicate": ["owner: lead-a", "owner: lead-b"],
    }

    def test_each_fixture_holds_only_its_owner_lines(self):
        self.assertEqual(sorted(p.stem for p in FIXTURES.glob("*.md")),
                         sorted(self.EXPECTED))
        for name, lines in self.EXPECTED.items():
            with self.subTest(fixture=name):
                text = Path(fixture(name)).read_text()
                found = [line for line in text.splitlines() if "owner:" in line]
                self.assertEqual(found, lines)

    def test_body_only_owner_sits_in_the_body_under_context(self):
        lines = Path(fixture("body-only")).read_text().splitlines()
        at = lines.index("owner: lead-a")
        self.assertNotIn("owner: lead-a", queue_rules.frontmatter_lines("\n".join(lines)))
        headings = [line for line in lines[:at] if line.startswith("## ")]
        self.assertEqual(headings[-1], "## Context")

    def test_fixtures_are_otherwise_clean_specs(self):
        # No marker and no chain error, so a check finding is the owner's alone.
        for name in self.EXPECTED:
            with self.subTest(fixture=name):
                text = Path(fixture(name)).read_text()
                self.assertEqual(queue_rules.find_markers(text), [])
                self.assertEqual(queue_rules.chain_errors(text), [])
                self.assertTrue(queue_rules.frontmatter_lines(text))


class TestRouteFixtures(unittest.TestCase):
    def test_route_owner_fixture_prints_owner_tab_name(self):
        self.assertEqual(run("route", fixture("owner")), (0, "owner\tlead-a\n", ""))

    def test_route_none_fixture_is_human(self):
        self.assertEqual(run("route", fixture("none")), (0, "human\n", ""))

    def test_route_commented_fixture_is_human(self):
        self.assertEqual(run("route", fixture("commented")), (0, "human\n", ""))

    def test_route_body_only_fixture_is_human(self):
        self.assertEqual(run("route", fixture("body-only")), (0, "human\n", ""))

    def test_route_invalid_fixture_exits_2_with_nothing_on_stdout(self):
        rc, out, err = run("route", fixture("invalid"))
        self.assertEqual((rc, out), (2, ""))
        self.assertIn("owner:", err)
        self.assertIn("lead a!", err)

    def test_route_duplicate_fixture_exits_2_with_nothing_on_stdout(self):
        rc, out, err = run("route", fixture("duplicate"))
        self.assertEqual((rc, out), (2, ""))
        self.assertIn("owner:", err)
        self.assertIn("2 times", err)

    def test_route_shipped_template_is_human(self):
        # The template carries the field commented out; it must stay inert.
        self.assertIn("\n# owner:", TEMPLATE.read_text())
        self.assertEqual(run("route", str(TEMPLATE)), (0, "human\n", ""))

    def test_route_as_a_script_prints_the_exact_bytes(self):
        # The way the contracts run it: a real tab, one line, exit 0.
        done = subprocess.run([sys.executable, str(SCRIPT), "route", fixture("owner")],
                              capture_output=True, check=False)
        self.assertEqual((done.returncode, done.stdout, done.stderr),
                         (0, b"owner\tlead-a\n", b""))


class TestRouteCli(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def route(self, text: str) -> tuple[int, str, str]:
        path = self.dir / "SPEC.md"
        path.write_text(text)
        return run("route", str(path))

    def test_unreadable_path_exits_2(self):
        rc, out, err = run("route", str(self.dir / "missing.md"))
        self.assertEqual((rc, out), (2, ""))
        self.assertIn("missing.md", err)

    def test_directory_exits_2(self):
        rc, out, _ = run("route", str(self.dir))
        self.assertEqual((rc, out), (2, ""))

    def test_route_takes_exactly_one_path(self):
        for argv in (("route",), ("route", fixture("owner"), fixture("none"))):
            with self.subTest(argv=argv):
                rc, out, err = run(*argv)
                self.assertEqual((rc, out), (2, ""))
                self.assertIn("usage", err)

    def test_trailing_comment_is_not_part_of_the_name(self):
        self.assertEqual(self.route(spec("owner: lead-a   # who hears about this spec")),
                         (0, "owner\tlead-a\n", ""))

    def test_trailing_blanks_are_not_part_of_the_name(self):
        self.assertEqual(self.route(spec("owner:\tlead-a \t")), (0, "owner\tlead-a\n", ""))

    def test_name_alphabet_and_length(self):
        good = ["a", "lead-a", "conductor", "Lead_A.2", "9" * 64, "x" + "-" * 63]
        bad = ["lead a", "lead-a!", "-lead", "_lead", ".lead", "x" * 65, "lead/a", "'lead-a'"]
        for name in good:
            with self.subTest(good=name):
                self.assertEqual(self.route(spec(f"owner: {name}")), (0, f"owner\t{name}\n", ""))
        for name in bad:
            with self.subTest(bad=name):
                rc, out, _ = self.route(spec(f"owner: {name}"))
                self.assertEqual((rc, out), (2, ""))

    def test_no_yaml_block_is_human(self):
        self.assertEqual(self.route("# Spec\n\nowner: lead-a\n"), (0, "human\n", ""))

    def test_only_the_first_yaml_block_is_frontmatter(self):
        text = spec() + "\n```yaml\nowner: lead-b\n```\n"
        self.assertEqual(self.route(text), (0, "human\n", ""))

    def test_other_code_blocks_are_not_frontmatter(self):
        before = "# Spec\n\n```text\nowner: lead-b\n```\n\n"
        self.assertEqual(self.route(before + spec().split("\n", 2)[2]), (0, "human\n", ""))
        self.assertEqual(self.route(before + spec("owner: lead-a").split("\n", 2)[2]),
                         (0, "owner\tlead-a\n", ""))

    # A yaml block quoted in a comment or another fence is not a fenced block,
    # so it is never the frontmatter: the marker rule's fences and comments
    # decide that, not a line scan. Each shape is checked with a real
    # frontmatter after it that names lead-a, and with one that names nobody.
    QUOTED = "```yaml\nowner: ghost\n```\n"

    def assert_quote_is_skipped(self, before: str, after: str):
        self.assertEqual(self.route(f"# Spec: x\n\n{before}{self.QUOTED}{after}\n"
                                    "```yaml\nid: x\nowner: lead-a\n```\n"),
                         (0, "owner\tlead-a\n", ""))
        self.assertEqual(self.route(f"# Spec: x\n\n{before}{self.QUOTED}{after}\n"
                                    "```yaml\nid: x\n```\n"),
                         (0, "human\n", ""))

    def test_yaml_block_quoted_in_an_html_comment_is_not_frontmatter(self):
        self.assert_quote_is_skipped("<!--\n", "-->\n")

    def test_yaml_block_quoted_in_a_longer_backtick_fence_is_not_frontmatter(self):
        self.assert_quote_is_skipped("````text\n", "````\n")

    def test_yaml_block_quoted_in_a_tilde_fence_is_not_frontmatter(self):
        self.assert_quote_is_skipped("~~~text\n", "~~~\n")

    def test_frontmatter_closes_on_a_longer_backtick_fence(self):
        # A fence closes on a run of its own char at least as long as its opener.
        self.assertEqual(self.route("# Spec\n\n```yaml\nowner: lead-a\n````\n"),
                         (0, "owner\tlead-a\n", ""))
        self.assertEqual(self.route("# Spec\n\n```yaml\nid: x\n````\n\nowner: lead-b\n"),
                         (0, "human\n", ""))

    def test_frontmatter_does_not_close_on_a_tilde_fence(self):
        self.assertEqual(self.route("# Spec\n\n```yaml\nid: x\n~~~\nowner: lead-a\n```\n"),
                         (0, "owner\tlead-a\n", ""))

    def test_unclosed_yaml_block_is_no_frontmatter(self):
        # Reading to end of file would read the body as frontmatter.
        self.assertEqual(self.route("# Spec\n\n```yaml\ntrack: code\n\nowner: lead-a\n"),
                         (0, "human\n", ""))

    def test_indented_or_respaced_owner_is_not_an_owner_line(self):
        # FR-002's line pattern is anchored at column 0 with the colon on the key.
        for line in ("  owner: lead-a", "owner : lead-a", "owners: lead-a", "co_owner: lead-a"):
            with self.subTest(line=line):
                self.assertEqual(self.route(spec(line)), (0, "human\n", ""))

    def test_empty_owner_value_is_no_owner(self):
        for line in ("owner:", "owner:   "):
            with self.subTest(line=line):
                self.assertEqual(self.route(spec(line)), (0, "human\n", ""))

    def test_comment_alone_after_the_colon_is_invalid(self):
        # FR-002's pattern needs a non-blank value, so it captures the comment
        # itself, and a comment is not a session name: fail closed.
        rc, out, _ = self.route(spec("owner:  # nobody yet"))
        self.assertEqual((rc, out), (2, ""))

    def test_commented_line_beside_a_real_one_is_not_a_duplicate(self):
        self.assertEqual(self.route(spec("# owner: <session-name>", "owner: lead-a")),
                         (0, "owner\tlead-a\n", ""))

    def test_crlf_spec_routes_like_lf(self):
        text = spec("owner: lead-a").replace("\n", "\r\n")
        self.assertEqual(self.route(text), (0, "owner\tlead-a\n", ""))


class TestCheckOwner(unittest.TestCase):
    def test_check_reports_one_owner_line_per_invalid_file(self):
        rc, out, err = run("check", fixture("invalid"), fixture("duplicate"))
        self.assertEqual((rc, err), (1, ""))
        lines = out.splitlines()
        self.assertEqual(len(lines), 2, lines)
        self.assertTrue(lines[0].startswith(f"{fixture('invalid')}:0: owner: "), lines[0])
        self.assertTrue(lines[1].startswith(f"{fixture('duplicate')}:0: owner: "), lines[1])

    def test_check_is_silent_on_valid_and_absent_owners(self):
        names = ("owner", "none", "commented", "body-only")
        self.assertEqual(run("check", *[fixture(n) for n in names]), (0, "", ""))

    def test_check_owner_line_beside_a_marker_exits_1(self):
        token = "NEEDS" + " " + "CLARIFICATION"
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "SPEC.md"
            path.write_text(spec("owner: lead a!", body=f"- [{token}: which?]\n"))
            rc, out, _ = run("check", str(path))
        self.assertEqual(rc, 1)
        self.assertEqual([line.split(": ", 2)[1] for line in out.splitlines()],
                         ["marker", "owner"])

    def test_owner_errors_name_the_problem(self):
        self.assertEqual(queue_rules.owner_errors(spec("owner: lead-a")), [])
        self.assertEqual(queue_rules.owner_errors(spec()), [])
        (bad,) = queue_rules.owner_errors(spec("owner: lead a!"))
        self.assertIn("'lead a!'", bad)
        (dup,) = queue_rules.owner_errors(spec("owner: lead-a", "owner: lead-a"))
        self.assertIn("2 times", dup)


if __name__ == "__main__":
    unittest.main()
