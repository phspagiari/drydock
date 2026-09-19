"""Tests for the PRIORS.md hot/cold splitter.

    python3 -m unittest discover board/tests

Every case runs against a throwaway STATE_HOME in a temporary directory. The
fixture is a miniature of the shape the live file grew into on its own: two
``## Target repo:`` sections, the two phase sections, and global sections
that must survive in the hot file.
"""

import contextlib
import io
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import split_priors  # noqa: E402

FIXTURE = """# PRIORS — distilled lessons from past runs

Read by every executor (before work) and every reviewer (while grounding).

<!-- retro-cursor: a2e1cc8 -->

## Target repo: ~/code/ledger-api

- **Pristine `main` is not green**, periodically and by a new mechanism
  each time. *(2026-06-02-inventory-test)*

## Target repo: ~/p/example-repo

- **A public repo is not consent to publish; redact before shipping.**
  *(2026-06-20-chain-branch-pr)*

## Spec-writing

- Phase numbering in a proposal is narrative, not a dependency graph.
  *(phases 0 / 1.5 parallel-run question)*

## PR prose is where the defects are

- **The prepared PR body outruns the diff as a defect surface.**
  *(2026-06-14-toolchain-repair, REVIEW-r1)*

## Escalating

- **Read the open PRs before proposing to touch another team's files.**
  *(2026-06-02-inventory-test, QUESTION-run4-resolved)*

## The machine drydock runs on

- **Clamshell sleep kills long agent sessions.**
  *(2026-06-20-chain-branch-pr, QUESTION-r5-resolved)*
"""


def nonblank(text: str) -> int:
    return sum(1 for line in text.splitlines() if line.strip())


class TestClassify(unittest.TestCase):
    def test_target_repo_becomes_a_repo_file(self):
        self.assertEqual(split_priors.classify("## Target repo: ~/code/ledger-api"),
                         "priors/ledger-api.md")

    def test_target_repo_tolerates_backticks_and_trailing_slash(self):
        self.assertEqual(split_priors.classify("## Target repo: `~/code/ledger-api/`"),
                         "priors/ledger-api.md")

    def test_phase_headings_match_on_their_prefix(self):
        self.assertEqual(split_priors.classify("## Spec-writing"),
                         "priors/_spec-writing.md")
        self.assertEqual(split_priors.classify("## PR prose is where the defects are"),
                         "priors/_pr-prose.md")
        self.assertEqual(split_priors.classify("## Review findings that repeat"),
                         "priors/_review.md")

    def test_unrecognised_heading_stays_hot(self):
        self.assertIsNone(split_priors.classify("## Escalating"))
        self.assertIsNone(split_priors.classify("## The machine drydock runs on"))

    def test_target_repo_with_no_derivable_slug_raises(self):
        with self.assertRaises(split_priors.SplitError):
            split_priors.classify("## Target repo: /")


class TestSplitText(unittest.TestCase):
    def test_sections_land_in_their_files(self):
        hot, cold = split_priors.split_text(FIXTURE)
        self.assertEqual(
            sorted(cold),
            ["priors/_pr-prose.md", "priors/_spec-writing.md",
             "priors/example-repo.md", "priors/ledger-api.md"])
        self.assertIn("## Target repo: ~/code/ledger-api", cold["priors/ledger-api.md"])
        self.assertIn("## Target repo: ~/p/example-repo", cold["priors/example-repo.md"])
        hot_text = "\n".join(hot)
        self.assertIn("<!-- retro-cursor: a2e1cc8 -->", hot_text)
        self.assertIn("## Escalating", hot_text)
        self.assertIn("## The machine drydock runs on", hot_text)
        self.assertNotIn("## Target repo:", hot_text)
        self.assertNotIn("## Spec-writing", hot_text)
        self.assertNotIn("## PR prose", hot_text)

    def test_headings_inside_a_fence_are_not_sections(self):
        text = "# Priors\n\n```markdown\n## Target repo: ~/code/ledger-api\n```\n"
        hot, cold = split_priors.split_text(text)
        self.assertEqual(cold, {})
        self.assertIn("## Target repo: ~/code/ledger-api", hot)

    def test_two_sections_for_one_repo_merge_into_one_file(self):
        text = ("# Priors\n\n## Target repo: ~/code/ledger-api\n\n- first\n\n"
                "## Escalating\n\n- global\n\n## Target repo: ~/code/ledger-api\n\n- second\n")
        _, cold = split_priors.split_text(text)
        body = "\n".join(cold["priors/ledger-api.md"])
        self.assertIn("- first", body)
        self.assertIn("- second", body)


class TestSplitFile(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.source = self.root / "PRIORS.md"
        self.source.write_text(FIXTURE, encoding="utf-8")

    def written_files(self):
        return sorted(p.name for p in (self.root / "priors").iterdir())

    def test_writes_the_hot_file_and_four_cold_files(self):
        split_priors.split_file(self.source, self.root)
        self.assertEqual(
            self.written_files(),
            ["_pr-prose.md", "_spec-writing.md", "example-repo.md", "ledger-api.md"])
        hot = (self.root / "PRIORS.md").read_text(encoding="utf-8")
        self.assertIn("<!-- retro-cursor: a2e1cc8 -->", hot)
        self.assertIn("## Escalating", hot)
        self.assertIn("## The machine drydock runs on", hot)
        for absent in ("## Target repo:", "## Spec-writing", "## PR prose"):
            self.assertNotIn(absent, hot)

    def test_no_line_is_lost(self):
        split_priors.split_file(self.source, self.root)
        out = nonblank((self.root / "PRIORS.md").read_text(encoding="utf-8"))
        for path in (self.root / "priors").iterdir():
            out += nonblank(path.read_text(encoding="utf-8"))
        self.assertEqual(nonblank(FIXTURE), out)

    def test_second_run_is_a_no_op(self):
        split_priors.split_file(self.source, self.root)
        before = {p: p.read_text(encoding="utf-8")
                  for p in [self.root / "PRIORS.md", *(self.root / "priors").iterdir()]}
        self.assertEqual(split_priors.split_file(self.source, self.root), [])
        after = {p: p.read_text(encoding="utf-8")
                 for p in [self.root / "PRIORS.md", *(self.root / "priors").iterdir()]}
        self.assertEqual(before, after)

    def test_a_failing_cold_write_leaves_the_hot_file_intact(self):
        """The source is the user's only copy until the cold files land.

        ``priors`` present as a regular file makes the cold stage fail. The
        hot file is written last precisely so that this leaves the source
        untouched instead of truncated to the unclassified remainder.
        """
        (self.root / "priors").write_text("not a directory\n", encoding="utf-8")
        before = self.source.read_bytes()
        with self.assertRaises(OSError):
            split_priors.split_file(self.source, self.root)
        self.assertEqual(self.source.read_bytes(), before)

    def test_main_leaves_the_hot_file_untouched_when_the_split_fails(self):
        """Same guarantee through the CLI the installer actually runs."""
        (self.root / "priors").write_text("not a directory\n", encoding="utf-8")
        before = self.source.read_bytes()
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()), \
                self.assertRaises(OSError):
            split_priors.main([str(self.source), str(self.root)])
        self.assertEqual(self.source.read_bytes(), before)

    def test_an_existing_cold_file_is_appended_to_not_replaced(self):
        (self.root / "priors").mkdir()
        (self.root / "priors" / "ledger-api.md").write_text(
            "## Target repo: ~/code/ledger-api\n\n- an earlier prior\n", encoding="utf-8")
        split_priors.split_file(self.source, self.root)
        body = (self.root / "priors" / "ledger-api.md").read_text(encoding="utf-8")
        self.assertIn("- an earlier prior", body)
        self.assertIn("Pristine `main` is not green", body)


class TestMain(unittest.TestCase):
    """``main`` is quiet under test: its reporting goes to the installer."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def run_main(self, argv: list[str]) -> int:
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()):
            return split_priors.main(argv)

    def test_exit_zero_and_files_written(self):
        source = self.root / "PRIORS.md"
        source.write_text(FIXTURE, encoding="utf-8")
        self.assertEqual(self.run_main([str(source), str(self.root)]), 0)
        self.assertTrue((self.root / "priors" / "ledger-api.md").is_file())

    def test_missing_source_exits_two(self):
        self.assertEqual(
            self.run_main([str(self.root / "nope.md"), str(self.root)]), 2)

    def test_missing_out_dir_exits_two(self):
        source = self.root / "PRIORS.md"
        source.write_text(FIXTURE, encoding="utf-8")
        self.assertEqual(
            self.run_main([str(source), str(self.root / "nope")]), 2)

    def test_unclassifiable_target_repo_exits_one(self):
        source = self.root / "PRIORS.md"
        source.write_text("# Priors\n\n## Target repo: /\n\n- a prior\n", encoding="utf-8")
        self.assertEqual(self.run_main([str(source), str(self.root)]), 1)


if __name__ == "__main__":
    unittest.main()
