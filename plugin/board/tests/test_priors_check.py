"""Tests for the prior-record parser and the per-repo code cursor.

    python3 -m unittest discover plugin/board/tests

Parsing runs on in-memory text; the cursor cases run against a throwaway git
repository with two commits, so ``HEAD`` really moves between them. The
round-trip case pushes full-format records through ``split_priors`` and
checks that nothing about them changed on the way.
"""

import contextlib
import io
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import priors_check  # noqa: E402
import split_priors  # noqa: E402

FULL = """## Target repo: ~/code/ledger-api

- **[ledger-api/git-fetch]** `git fetch origin main:main` is refused while
  the primary worktree has main checked out.
  - scope: `~/code/ledger-api`
  - derived_from: `2026-06-02-inventory-test`
  - depends_on: primary worktree keeps main checked out; `.git/HEAD`,
    `.git/worktrees/**`; the branch is `main`
  - asserted: 2026-06-02
"""

LEGACY = """## Target repo: ~/code/ledger-api

- **Pristine `main` is not green**, periodically and by a new mechanism
  each time. *(2026-06-02-inventory-test)*
"""

ENV = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, env=ENV,
                          capture_output=True, text=True).stdout.strip()


def run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = priors_check.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class TestRecordFormat(unittest.TestCase):
    def test_full_format_record(self):
        [record] = priors_check.parse_text(FULL, Path("priors/ledger-api.md"))
        self.assertEqual(record["key"], "ledger-api/git-fetch")
        self.assertEqual(record["statement"], "`git fetch origin main:main` is refused "
                         "while the primary worktree has main checked out.")
        self.assertEqual(record["scope"], "~/code/ledger-api")
        self.assertEqual(record["derived_from"], "2026-06-02-inventory-test")
        self.assertEqual(record["asserted"], "2026-06-02")
        self.assertEqual(record["depends_on"],
                         "primary worktree keeps main checked out; `.git/HEAD`, "
                         "`.git/worktrees/**`; the branch is `main`")
        self.assertFalse(record["legacy"])
        self.assertEqual(record["missing"], [])
        self.assertEqual(record["line"], 3)

    def test_globs_are_backticked_tokens_with_path_characters(self):
        [record] = priors_check.parse_text(FULL, Path("priors/ledger-api.md"))
        self.assertEqual(record["globs"], [".git/HEAD", ".git/worktrees/**"])
        self.assertEqual(priors_check.globs("`.git/worktrees/**`"), [".git/worktrees/**"])
        self.assertEqual(priors_check.globs("`main`"), [])
        self.assertEqual(priors_check.globs("`*.bazel` and `a?c` and `go.mod`"),
                         ["*.bazel", "a?c", "go.mod"])
        self.assertEqual(priors_check.globs("no backticks, path/like text"), [])

    def test_legacy_bullet_scope_comes_from_the_filename(self):
        text = "- **Pristine `main` is not green.** *(2026-06-02-inventory-test)*\n"
        [record] = priors_check.parse_text(text, Path("priors/ledger-api.md"))
        self.assertTrue(record["legacy"])
        self.assertEqual(record["depends_on"], "unknown")
        self.assertEqual(record["globs"], [])
        self.assertEqual(record["asserted"], "unknown")
        self.assertEqual(record["derived_from"], "unknown")
        self.assertEqual(record["scope"], "ledger-api")
        self.assertEqual(record["key"], "ledger-api/L1")
        self.assertEqual(record["missing"], list(priors_check.FIELDS))

    def test_hot_and_phase_files_are_global(self):
        text = "## Escalating\n\n- **Read the open PRs first.**\n"
        for name in ("PRIORS.md", "_pr-prose.md", "_review.md"):
            [record] = priors_check.parse_text(text, Path(name))
            self.assertEqual(record["scope"], "global", name)

    def test_a_target_repo_heading_names_the_scope_of_legacy_bullets(self):
        # The monolithic pre-split PRIORS.md: the heading, not the filename,
        # is what knows the repo.
        text = LEGACY + "\n## Escalating\n\n- **Global lesson.**\n"
        repo, other = priors_check.parse_text(text, Path("PRIORS.md"))
        self.assertEqual(repo["scope"], "~/code/ledger-api")
        self.assertEqual(repo["statement"], "**Pristine `main` is not green**, "
                         "periodically and by a new mechanism each time. "
                         "*(2026-06-02-inventory-test)*")
        self.assertEqual(other["scope"], "global")

    def test_a_partial_record_names_what_it_lacks(self):
        text = "- **[x/y]** Claim.\n  - depends_on: `src/**`\n"
        [record] = priors_check.parse_text(text, Path("x.md"))
        self.assertFalse(record["legacy"])
        self.assertEqual(record["missing"], ["scope", "derived_from", "asserted"])
        self.assertEqual(record["scope"], "x")
        self.assertEqual(record["asserted"], "unknown")
        self.assertEqual(record["globs"], ["src/**"])

    def test_depends_on_unknown_stays_legal_in_full_format(self):
        text = FULL.replace("  - depends_on: primary worktree keeps main checked out; "
                            "`.git/HEAD`,\n    `.git/worktrees/**`; the branch is `main`\n",
                            "  - depends_on: unknown\n")
        [record] = priors_check.parse_text(text, Path("ledger-api.md"))
        self.assertEqual(record["depends_on"], "unknown")
        self.assertEqual(record["globs"], [])
        self.assertEqual(record["missing"], [])

    def test_body_after_the_fields_is_not_a_field(self):
        text = FULL + "  **Second instance.** More text `not/a/field`.\n"
        [record] = priors_check.parse_text(text, Path("ledger-api.md"))
        self.assertEqual(record["globs"], [".git/HEAD", ".git/worktrees/**"])
        self.assertEqual(record["asserted"], "2026-06-02")

    def test_bullets_inside_a_fence_are_not_priors(self):
        text = "# Example\n\n```markdown\n" + FULL + "```\n\n- **Real one.**\n"
        records = priors_check.parse_text(text, Path("example.md"))
        self.assertEqual([r["statement"] for r in records], ["**Real one.**"])

    def test_paragraphs_and_comments_end_a_record(self):
        text = "- **One.**\n<!-- retro-cursor: a2e1cc8 -->\n  indented stray\n- **Two.**\n"
        one, two = priors_check.parse_text(text, Path("PRIORS.md"))
        self.assertEqual(one["statement"], "**One.**")
        self.assertEqual(two["key"], "PRIORS/L4")

    def test_a_repeated_field_is_refused(self):
        text = "- **[x/y]** Claim.\n  - asserted: 2026-06-02\n  - asserted: 2026-06-03\n"
        with self.assertRaises(priors_check.PriorsError):
            priors_check.parse_text(text, Path("x.md"))

    def test_parse_subcommand_prints_json_lines(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger-api.md"
            path.write_text(FULL + "\n" + LEGACY.split("\n", 2)[2], encoding="utf-8")
            code, out, _ = run("parse", str(path))
        self.assertEqual(code, 0)
        records = [json.loads(line) for line in out.splitlines()]
        self.assertEqual([r["key"] for r in records], ["ledger-api/git-fetch", "ledger-api/L11"])
        self.assertEqual([r["legacy"] for r in records], [False, True])

    def test_parse_of_a_missing_file_exits_2(self):
        code, _, err = run("parse", "/nonexistent/priors.md")
        self.assertEqual(code, 2)
        self.assertIn("no such file", err)


class TestCursor(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.repo = root / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        for n in (1, 2):
            (self.repo / "f.txt").write_text(f"{n}\n")
            git(self.repo, "add", "f.txt")
            git(self.repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid",
                "commit", "-q", "-m", f"c{n}")
        self.first = git(self.repo, "rev-parse", "HEAD~1")
        self.head = git(self.repo, "rev-parse", "HEAD")
        self.priors = root / "ledger-api.md"
        self.priors.write_text(FULL + "\n" + LEGACY.split("\n", 2)[2], encoding="utf-8")

    def stale(self) -> tuple[int, list[str]]:
        code, out, _ = run("stale", "--repo", str(self.repo), "--priors", str(self.priors))
        return code, out.splitlines()

    def set_cursor(self, line: str) -> None:
        text = self.priors.read_text(encoding="utf-8")
        head, rest = text.split("\n", 1)
        self.priors.write_text(f"{head}\n\n{line}\n{rest}", encoding="utf-8")

    def test_no_cursor_prints_nocursor(self):
        self.assertEqual(self.stale(), (0, ["NOCURSOR"]))

    def test_a_missing_priors_file_is_nocursor(self):
        self.priors.unlink()
        self.assertEqual(self.stale(), (0, ["NOCURSOR"]))

    def test_moved_repo_prints_one_stale_line_per_prior(self):
        self.set_cursor(f"<!-- code-cursor: {self.first} -->")
        self.assertEqual(self.stale(), (0, [
            "STALE ledger-api/git-fetch 2026-06-02 primary worktree keeps main checked "
            "out; `.git/HEAD`, `.git/worktrees/**`; the branch is `main`",
            "STALE ledger-api/L13 unknown unknown",
        ]))

    def test_cursor_at_head_prints_nothing(self):
        self.set_cursor(f"<!-- code-cursor: {self.head} -->")
        self.assertEqual(self.stale(), (0, []))

    def test_bare_cursor_line_parses_too(self):
        self.set_cursor(f"code-cursor: {self.head}")
        self.assertEqual(self.stale(), (0, []))

    def test_comparison_is_exact_not_by_prefix(self):
        self.set_cursor(f"<!-- code-cursor: {self.head[:12]} -->")
        code, lines = self.stale()
        self.assertEqual(code, 0)
        self.assertEqual(len(lines), 2)

    def test_advance_then_stale_prints_nothing(self):
        self.set_cursor(f"<!-- code-cursor: {self.first} -->")
        code, out, _ = run("advance", "--repo", str(self.repo), "--priors", str(self.priors))
        self.assertEqual((code, out), (0, f"code-cursor: {self.head}\n"))
        self.assertEqual(self.stale(), (0, []))
        text = self.priors.read_text(encoding="utf-8")
        self.assertEqual(text.count("code-cursor:"), 1)
        self.assertNotIn(self.first, text)

    def test_advance_without_a_cursor_writes_it_under_the_heading(self):
        before = self.priors.read_text(encoding="utf-8")
        self.assertEqual(run("advance", "--repo", str(self.repo),
                             "--priors", str(self.priors))[0], 0)
        lines = self.priors.read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[:4], ["## Target repo: ~/code/ledger-api", "",
                                     f"<!-- code-cursor: {self.head} -->", ""])
        self.assertEqual(lines[4:], before.splitlines()[2:])
        self.assertEqual(self.stale(), (0, []))
        self.assertEqual(sorted(p.name for p in self.priors.parent.iterdir()),
                         ["ledger-api.md", "repo"])

    def test_advance_on_a_file_with_no_heading_writes_the_top_line(self):
        self.priors.write_text("- **[a/b]** Claim.\n", encoding="utf-8")
        run("advance", "--repo", str(self.repo), "--priors", str(self.priors))
        self.assertEqual(self.priors.read_text(encoding="utf-8"),
                         f"<!-- code-cursor: {self.head} -->\n\n- **[a/b]** Claim.\n")

    def test_advance_never_creates_a_priors_file(self):
        self.priors.unlink()
        code, _, err = run("advance", "--repo", str(self.repo), "--priors", str(self.priors))
        self.assertEqual(code, 2)
        self.assertFalse(self.priors.exists())
        self.assertIn("no such priors file", err)

    def test_two_cursor_lines_are_refused_and_nothing_is_written(self):
        self.set_cursor(f"<!-- code-cursor: {self.first} -->\n<!-- code-cursor: {self.head} -->")
        before = self.priors.read_text(encoding="utf-8")
        self.assertEqual(self.stale()[0], 2)
        code, _, err = run("advance", "--repo", str(self.repo), "--priors", str(self.priors))
        self.assertEqual(code, 2)
        self.assertIn("2 code-cursor lines", err)
        self.assertEqual(self.priors.read_text(encoding="utf-8"), before)

    def test_a_cursor_inside_a_fence_is_not_the_cursor(self):
        self.set_cursor(f"```text\n<!-- code-cursor: {self.head} -->\n```")
        self.assertEqual(self.stale(), (0, ["NOCURSOR"]))

    def test_a_repo_that_is_not_git_exits_2(self):
        self.set_cursor(f"<!-- code-cursor: {self.head} -->")
        code, _, err = run("stale", "--repo", str(self.priors.parent / "nope"),
                           "--priors", str(self.priors))
        self.assertEqual(code, 2)
        self.assertIn("rev-parse HEAD failed", err)


class TestSplitRoundTrip(unittest.TestCase):
    """split → parse → split must not lose or reorder a record's sub-bullets."""

    MONOLITH = ("# PRIORS\n\n<!-- retro-cursor: a2e1cc8 -->\n\n"
                + FULL.replace("## Target repo: ~/code/ledger-api\n",
                               "## Target repo: ~/code/ledger-api\n\n"
                               "<!-- code-cursor: " + "a" * 40 + " -->\n")
                + "\n- **[ledger-api/second]** Another claim.\n"
                  "  - scope: `~/code/ledger-api`\n  - derived_from: `x`\n"
                  "  - depends_on: `BUILD.bazel`\n  - asserted: 2026-06-03\n"
                + "\n## Escalating\n\n- **Global lesson.**\n")

    @staticmethod
    def semantic(records):
        # A legacy key is positional (``<stem>/L<line>``), so a split moves
        # it by design; a full-format key is written, and must not move.
        return [{k: v for k, v in r.items()
                 if k not in ("file", "line") and not (k == "key" and r["legacy"])}
                for r in records]

    @staticmethod
    def field_lines(text):
        return [line for line in text.splitlines() if priors_check.FIELD_RE.match(line)]

    def test_round_trip(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "PRIORS.md"
            source.write_text(self.MONOLITH, encoding="utf-8")
            before = priors_check.parse_file(source)

            split_priors.split_file(source, root)
            cold = root / "priors/ledger-api.md"
            hot_records = priors_check.parse_file(source)
            cold_records = priors_check.parse_file(cold)
            cold_text = cold.read_text(encoding="utf-8")

            self.assertEqual(self.semantic(cold_records + hot_records), self.semantic(before))
            self.assertEqual(self.field_lines(cold_text), self.field_lines(self.MONOLITH))
            self.assertEqual(priors_check.read_cursor(cold), "a" * 40)
            self.assertIsNone(priors_check.read_cursor(source))

            hot_before = source.read_text(encoding="utf-8")
            self.assertEqual(split_priors.split_file(source, root), [])
            self.assertEqual(source.read_text(encoding="utf-8"), hot_before)
            self.assertEqual(cold.read_text(encoding="utf-8"), cold_text)


if __name__ == "__main__":
    unittest.main()
