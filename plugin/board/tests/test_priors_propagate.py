"""Tests for propagation's mechanical stages in ``priors_check.py``.

    python3 -m unittest discover plugin/board/tests

Three stages, three classes: the ``candidates`` pre-filter over a diff's
file list, ``retract`` applying one file's verdicts, and ``advance
--if-ancestor`` refusing to move the cursor anywhere but forward along its
own history. The ancestor cases run against a throwaway repo with a real
side branch, because "not an ancestor" has two shapes -- behind, and
elsewhere -- and both must skip.
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

# Four priors, one per pre-filter outcome. Line numbers matter: the legacy
# prior's key is positional (``ledger-api/L21``).
PRIORS = """## Target repo: ~/code/ledger-api

- **[ledger-api/hit]** Migrations must be reversible.
  - scope: `~/code/ledger-api`
  - derived_from: `2026-06-02-inventory-test`
  - depends_on: the migration runner in `db/**/migrate_*.sql`
  - asserted: 2026-06-02

- **[ledger-api/miss]** The web bundle is built by the CI job only.
  - scope: `~/code/ledger-api`
  - derived_from: `2026-06-03-bundle`
  - depends_on: `web/package.json`, `.github/workflows/web.yml`
  - asserted: 2026-06-03

- **[ledger-api/no-globs]** The team reviews on Tuesdays.
  - scope: `~/code/ledger-api`
  - derived_from: `2026-06-04-review-day`
  - depends_on: the team's review rota, which no path records
  - asserted: 2026-06-04

- **Pristine `main` is not green**, periodically and by a new mechanism
  each time. *(2026-06-02-inventory-test)*
"""

DIFF = ["db/schema/2026/migrate_0042.sql", "README.md"]

ENV = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, env=ENV,
                          capture_output=True, text=True).stdout.strip()


def run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = priors_check.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class FileCase(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.priors = self.root / "ledger-api.md"
        self.priors.write_text(PRIORS, encoding="utf-8")

    def keys(self) -> list[str]:
        return [r["key"] for r in priors_check.parse_file(self.priors)]


class TestCandidates(FileCase):
    def candidates(self, paths: list[str]) -> tuple[int, list[dict], str]:
        listing = self.root / "diff-files.txt"
        listing.write_text("".join(f"{p}\n" for p in paths), encoding="utf-8")
        code, out, err = run("candidates", "--priors", str(self.priors),
                             "--diff-files", str(listing))
        return code, [json.loads(line) for line in out.splitlines()], err

    def test_four_priors_one_diff(self):
        self.assertEqual(self.keys(), ["ledger-api/hit", "ledger-api/miss",
                                       "ledger-api/no-globs", "ledger-api/L21"])
        code, found, _ = self.candidates(DIFF)
        self.assertEqual(code, 0)
        self.assertEqual({c["key"]: c["matched_globs"] for c in found}, {
            "ledger-api/hit": ["db/**/migrate_*.sql"],
            "ledger-api/no-globs": [],
            "ledger-api/L21": [],
        })
        self.assertNotIn("ledger-api/miss", [c["key"] for c in found])
        by_key = {c["key"]: c for c in found}
        self.assertEqual(by_key["ledger-api/L21"]["depends_on"], "unknown")
        self.assertEqual(by_key["ledger-api/no-globs"]["depends_on"],
                         "the team's review rota, which no path records")
        self.assertEqual(sorted(found[0]), ["depends_on", "key", "matched_globs"])

    def test_the_glob_less_priors_survive_an_empty_diff(self):
        _, found, _ = self.candidates([])
        self.assertEqual([c["key"] for c in found],
                         ["ledger-api/no-globs", "ledger-api/L21"])

    def test_double_star_is_zero_or_more_segments(self):
        hits = priors_check.glob_hits
        self.assertTrue(hits("db/**/migrate_*.sql", "db/migrate_1.sql"))
        self.assertTrue(hits("db/**/migrate_*.sql", "db/a/migrate_1.sql"))
        self.assertTrue(hits("db/**/migrate_*.sql", "db/a/b/c/migrate_1.sql"))
        self.assertTrue(hits("**/BUILD.bazel", "BUILD.bazel"))
        self.assertTrue(hits("**/BUILD.bazel", "go/svc/BUILD.bazel"))
        self.assertTrue(hits(".git/worktrees/**", ".git/worktrees/x/HEAD"))

    def test_single_star_stays_inside_one_segment(self):
        hits = priors_check.glob_hits
        self.assertFalse(hits("db/*/migrate_*.sql", "db/a/b/migrate_1.sql"))
        self.assertFalse(hits("*.bazel", "go/svc/BUILD.bazel"))
        self.assertTrue(hits("*.bazel", "MODULE.bazel"))
        self.assertFalse(hits("db/**/migrate_*.sql", "web/db/migrate_1.sql"))
        self.assertFalse(hits("Web/package.json", "web/package.json"))

    def test_an_ancestor_directory_match_counts(self):
        hits = priors_check.glob_hits
        self.assertTrue(hits("plugin/board", "plugin/board/priors_check.py"))
        self.assertTrue(hits("plugin/*", "plugin/board/tests/test_x.py"))
        self.assertTrue(hits("./plugin/board/", "plugin/board/x.py"))
        self.assertFalse(hits("plugin/board/priors_check.py", "plugin/board"))
        self.assertFalse(hits("", "anything"))

    def test_a_non_path_token_with_a_dot_makes_a_prior_excludable(self):
        # The globs() docstring's warning, pinned: `v2.1.6` reads as a glob,
        # so this prior is dropped from a diff it cannot match.
        self.priors.write_text(PRIORS.replace(
            "the team's review rota, which no path records",
            "the linter stays at `v2.1.6`"), encoding="utf-8")
        _, found, _ = self.candidates(DIFF)
        self.assertNotIn("ledger-api/no-globs", [c["key"] for c in found])

    def test_missing_inputs_exit_2(self):
        listing = self.root / "diff-files.txt"
        listing.write_text("README.md\n", encoding="utf-8")
        code, _, err = run("candidates", "--priors", str(self.root / "nope.md"),
                           "--diff-files", str(listing))
        self.assertEqual(code, 2)
        self.assertIn("no such priors file", err)
        code, _, err = run("candidates", "--priors", str(self.priors),
                           "--diff-files", str(self.root / "nope.txt"))
        self.assertEqual(code, 2)
        self.assertIn("no such file", err)


class TestRetract(FileCase):
    SHA = "c23bcbd5a310d41cbda6681fbad371a41a00d682"
    LEGACY = ("## Target repo: ~/code/ledger-api\n\n"
              "- **One.** first legacy.\n\n"
              "- **Two.** second legacy.\n\n"
              "- **Three.** third legacy,\n  wrapped.\n\n"
              "- **[ledger-api/rec]** A record.\n"
              "  - scope: `~/code/ledger-api`\n  - derived_from: `x`\n"
              "  - depends_on: `src/**`\n  - asserted: 2026-06-05\n")

    def retract(self, *argv: str) -> tuple[int, str, str]:
        return run("retract", "--priors", str(self.priors), *argv)

    def blocks(self, text: str) -> dict[str, str]:
        """Each prior's exact text, keyed by its key in ``text``."""
        lines = text.splitlines()
        return {r["key"]: "\n".join(lines[r["line"] - 1:end])
                for r, end in priors_check._parse(text, self.priors)}

    def test_mark_adds_stale_to_the_named_prior_only(self):
        before = self.blocks(PRIORS)
        code, out, _ = self.retract("--sha", self.SHA, "--mark", "ledger-api/hit")
        self.assertEqual((code, out), (0, f"stale ledger-api/hit {self.SHA}\n"))
        text = self.priors.read_text(encoding="utf-8")
        self.assertEqual(text, PRIORS.replace(
            "  - asserted: 2026-06-02\n",
            f"  - asserted: 2026-06-02\n  - stale: {self.SHA}\n"))
        after = self.blocks(text)
        for key in ("ledger-api/miss", "ledger-api/no-globs"):
            self.assertEqual(after[key], before[key])
        self.assertEqual(after["ledger-api/L22"], before["ledger-api/L21"])
        [hit] = [r for r in priors_check.parse_file(self.priors) if r["key"] == "ledger-api/hit"]
        self.assertEqual(hit["stale"], self.SHA)
        self.assertEqual(hit["missing"], [])

    def test_a_second_mark_overwrites_the_sha(self):
        self.retract("--sha", "a" * 40, "--mark", "ledger-api/hit")
        once = self.priors.read_text(encoding="utf-8")
        self.retract("--sha", self.SHA, "--mark", "ledger-api/hit")
        text = self.priors.read_text(encoding="utf-8")
        self.assertEqual(text.count("- stale:"), 1)
        self.assertEqual(text, once.replace("a" * 40, self.SHA))

    def test_remove_takes_only_the_named_prior(self):
        before = self.blocks(PRIORS)
        code, out, _ = self.retract("ledger-api/miss")
        self.assertEqual((code, out), (0, "retract ledger-api/miss\n"))
        text = self.priors.read_text(encoding="utf-8")
        self.assertEqual(text, PRIORS.replace(before["ledger-api/miss"] + "\n\n", ""))
        self.assertNotIn("\n\n\n", text)
        self.assertEqual(self.keys(), ["ledger-api/hit", "ledger-api/no-globs",
                                       "ledger-api/L15"])

    def test_removing_the_last_prior_leaves_no_trailing_blank(self):
        self.retract("ledger-api/L21")
        text = self.priors.read_text(encoding="utf-8")
        self.assertTrue(text.endswith("  - asserted: 2026-06-04\n"), repr(text[-40:]))

    def test_all_verdicts_in_one_call_hit_the_right_priors(self):
        # Three legacy priors; removing the first shifts the others' keys,
        # so resolving every key against one parse is what keeps the call
        # from hitting a neighbour.
        self.priors.write_text(self.LEGACY, encoding="utf-8")
        self.assertEqual(self.keys(), ["ledger-api/L3", "ledger-api/L5",
                                       "ledger-api/L7", "ledger-api/rec"])
        code, out, _ = self.retract("--sha", self.SHA, "--mark", "ledger-api/L7",
                                    "--mark", "ledger-api/rec", "ledger-api/L3")
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), [
            "retract ledger-api/L3", f"stale ledger-api/L7 {self.SHA}",
            f"stale ledger-api/rec {self.SHA}"])
        records = priors_check.parse_file(self.priors)
        self.assertEqual([r["statement"] for r in records], [
            "**Two.** second legacy.", "**Three.** third legacy, wrapped.", "A record."])
        self.assertEqual([r["stale"] for r in records], [None, self.SHA, self.SHA])
        self.assertEqual([r["legacy"] for r in records], [True, True, False])

    def test_a_removal_above_a_mark_does_not_slide_it(self):
        # The quiet shape of the same defect: edited top-down, removing L3
        # first would slide the stale line onto "Three" instead of "Two".
        self.priors.write_text(self.LEGACY, encoding="utf-8")
        self.assertEqual(self.retract("--sha", self.SHA, "--mark", "ledger-api/L5",
                                      "ledger-api/L3")[0], 0)
        records = priors_check.parse_file(self.priors)
        self.assertEqual([(r["statement"], r["stale"]) for r in records], [
            ("**Two.** second legacy.", self.SHA),
            ("**Three.** third legacy, wrapped.", None),
            ("A record.", None)])

    def test_two_calls_would_have_hit_the_wrong_prior(self):
        # Why the contract says one call per file: after a removal, the old
        # key of the prior below names a different prior, or none.
        self.retract("ledger-api/miss")
        code, _, err = self.retract("ledger-api/L21")
        self.assertEqual(code, 2)
        self.assertIn("no prior with key 'ledger-api/L21'", err)

    def test_parse_keeps_stale_out_of_the_statement(self):
        text = ("- **Pristine `main` is not green**, periodically\n"
                "  and by a new mechanism.\n"
                f"  - stale: {self.SHA}\n")
        [record] = priors_check.parse_text(text, Path("ledger-api.md"))
        self.assertEqual(record["statement"],
                         "**Pristine `main` is not green**, periodically and by a new mechanism.")
        self.assertEqual(record["stale"], self.SHA)
        self.assertTrue(record["legacy"])
        self.assertEqual(record["depends_on"], "unknown")
        self.assertEqual(record["missing"], list(priors_check.FIELDS))

    def test_refusals_write_nothing(self):
        cases = [
            (("ledger-api/nope",), "no prior with key"),
            (("--sha", self.SHA, "--mark", "ledger-api/hit", "ledger-api/hit"),
             "named more than once"),
            (("--mark", "ledger-api/hit"), "--mark needs --sha"),
            (("--sha", "not-a-sha", "--mark", "ledger-api/hit"), "--mark needs --sha"),
            ((), "name at least one key"),
        ]
        for argv, message in cases:
            with self.subTest(argv=argv):
                code, _, err = self.retract(*argv)
                self.assertEqual(code, 2)
                self.assertIn(message, err)
                self.assertEqual(self.priors.read_text(encoding="utf-8"), PRIORS)

    def test_a_shared_key_is_refused(self):
        self.priors.write_text(PRIORS + PRIORS.split("\n\n")[1] + "\n", encoding="utf-8")
        before = self.priors.read_text(encoding="utf-8")
        code, _, err = self.retract("ledger-api/hit")
        self.assertEqual(code, 2)
        self.assertIn("2 priors share key 'ledger-api/hit'", err)
        self.assertEqual(self.priors.read_text(encoding="utf-8"), before)


class TestAdvanceIfAncestor(unittest.TestCase):
    """main: A → B → C; side branch S off A."""

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.repo = root / "repo"
        git(root, "init", "-q", "-b", "main", str(self.repo))
        self.a = self.commit("A")
        self.b = self.commit("B")
        self.c = self.commit("C")
        git(self.repo, "checkout", "-q", "-b", "side", self.a)
        self.s = self.commit("S")
        git(self.repo, "checkout", "-q", "main")
        self.priors = root / "ledger-api.md"

    def commit(self, name: str) -> str:
        (self.repo / "f.txt").write_text(f"{name}\n")
        git(self.repo, "add", "f.txt")
        git(self.repo, "-c", "user.name=t", "-c", "user.email=t@example.invalid",
            "commit", "-q", "-m", name)
        return git(self.repo, "rev-parse", "HEAD")

    def with_cursor(self, sha: str | None) -> None:
        cursor = f"<!-- code-cursor: {sha} -->\n\n" if sha else ""
        self.priors.write_text(f"## Target repo: ~/code/ledger-api\n\n{cursor}"
                               "- **A prior.**\n", encoding="utf-8")

    def advance(self, to: str) -> tuple[int, str]:
        code, out, _ = run("advance", "--if-ancestor", "--repo", str(self.repo),
                           "--priors", str(self.priors), "--ref", to)
        return code, out

    def test_forward_moves(self):
        self.with_cursor(self.a)
        self.assertEqual(self.advance(self.c), (0, f"code-cursor: {self.c}\n"))
        self.assertEqual(priors_check.read_cursor(self.priors), self.c)

    def test_backwards_is_skipped(self):
        self.with_cursor(self.c)
        before = self.priors.read_text(encoding="utf-8")
        code, out = self.advance(self.b)
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("skip: "), out)
        self.assertEqual(len(out.splitlines()), 1)
        self.assertEqual(self.priors.read_text(encoding="utf-8"), before)

    def test_a_side_branch_cursor_is_skipped(self):
        self.with_cursor(self.s)
        before = self.priors.read_text(encoding="utf-8")
        code, out = self.advance(self.c)
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("skip: "), out)
        self.assertIn(self.s, out)
        self.assertEqual(self.priors.read_text(encoding="utf-8"), before)

    def test_no_cursor_is_set(self):
        self.with_cursor(None)
        self.assertEqual(self.advance(self.b), (0, f"code-cursor: {self.b}\n"))
        self.assertEqual(priors_check.read_cursor(self.priors), self.b)

    def test_a_cursor_git_does_not_know_is_skipped(self):
        self.with_cursor("0" * 40)
        before = self.priors.read_text(encoding="utf-8")
        code, out = self.advance(self.c)
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("skip: "), out)
        self.assertEqual(self.priors.read_text(encoding="utf-8"), before)

    def test_same_sha_is_a_no_op_advance(self):
        self.with_cursor(self.c)
        before = self.priors.read_text(encoding="utf-8")
        self.assertEqual(self.advance(self.c), (0, f"code-cursor: {self.c}\n"))
        self.assertEqual(self.priors.read_text(encoding="utf-8"), before)

    def test_without_the_flag_advance_still_goes_anywhere(self):
        # The guard is opt-in: the retro's plain advance is unchanged.
        self.with_cursor(self.c)
        code, out, _ = run("advance", "--repo", str(self.repo),
                           "--priors", str(self.priors), "--ref", self.b)
        self.assertEqual((code, out), (0, f"code-cursor: {self.b}\n"))


if __name__ == "__main__":
    unittest.main()
