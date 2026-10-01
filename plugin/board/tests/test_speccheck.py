"""Tests for the spec-body lint.

    python3 -m unittest discover board/tests

Each test's first docstring line names the full rule id it pins, so the
verbose run lists every rule. The clarification token is assembled at
runtime, so this file never matches a plain substring search for it.
"""

import contextlib
import io
import sys
import unittest
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import queue_rules  # noqa: E402
import speccheck  # noqa: E402

TOKEN = "NEEDS" + " " + "CLARIFICATION"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "speccheck"

HEADER = ("| # | Check | Command | Pass condition |\n"
          "|---|-------|---------|----------------|\n")


def spec(rows: str = "| AC-1 | Tests | `make test` | exit 0 |\n", *,
         after_table: str = "", requirements: str = "- **FR-001**: It works.\n",
         constraints: str = "- **State predicates**: none.\n",
         created: str = "2030-01-01", tail: str = "") -> str:
    """A spec with every rule satisfied unless an argument breaks one."""
    return (f"# Spec: fixture\n\n```yaml\nid: x\ncreated: {created}\n```\n\n"
            f"## Constraints & blast radius\n\n- **May touch**: `src/`\n"
            f"{constraints}\n## Requirements\n\n{requirements}\n"
            f"## Acceptance criteria (executable)\n\n{HEADER}{rows}"
            f"{after_table}\n{tail}")


def row(ident: str, command: str, passes: str = "exit 0", check: str = "c") -> str:
    return f"| {ident} | {check} | {command} | {passes} |\n"


def lint(text: str) -> tuple[list[speccheck.Violation], list[str]]:
    return speccheck.check("s.md", text)


def rules(text: str) -> list[str]:
    return [v.rule for v in lint(text)[0]]


def run(*argv: str) -> tuple[int, str, str]:
    """``speccheck.main`` in-process: (exit code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            rc = speccheck.main(list(argv))
        except SystemExit as exc:  # argparse usage errors
            rc = exc.code
    return rc, out.getvalue(), err.getvalue()


class Baseline(unittest.TestCase):
    def test_the_baseline_spec_is_clean(self):
        """Every rule: the helper's default spec passes, so each test isolates one rule."""
        self.assertEqual(lint(spec()), ([], []))


class R1(unittest.TestCase):
    def test_R1_command_is_a_command_fires_on_prose(self):
        """R1-command-is-a-command: a Command cell with no code span fires."""
        found = lint(spec(row("AC-1", "all required checks")))[0]
        self.assertEqual([(v.rule, v.ident) for v in found], [("R1", "AC-1")])
        self.assertIn("R1-command-is-a-command AC-1:", found[0].render())

    def test_R1_command_is_a_command_accepts_a_code_span(self):
        """R1-command-is-a-command: one code span anywhere in the cell is enough."""
        self.assertEqual(rules(spec(row("AC-1", "run `make test` twice"))), [])

    def test_R1_command_is_a_command_keeps_escaped_pipes_in_the_cell(self):
        """R1-command-is-a-command: an escaped pipe does not split the Command cell."""
        text = spec(row("AC-1", r"`find . \| wc -l`", "count at least 1"))
        table = speccheck.acceptance_table(speccheck.parse("s.md", text))
        self.assertEqual(table.rows[0].cells["Command"], "`find . | wc -l`")
        self.assertEqual(rules(text), [])

    def test_R1_command_is_a_command_ignores_ship_rows(self):
        """R1-command-is-a-command: Ship criteria rows are prose by design."""
        ship = ("## Ship criteria (owned by the ship step — NOT the executor)\n\n"
                + HEADER + row("SC-1", "the checks on the pull request", "green"))
        self.assertEqual(rules(spec(tail=ship)), [])


class R2(unittest.TestCase):
    def test_R2_pre_pr_runnable_fires_on_each_token_class(self):
        """R2-pre-pr-runnable: pull request, merge, deploy and human forms fire."""
        for command, passes in [("`gh pr view 3`", "exit 0"),
                                ("`make check`", "green on the pull request"),
                                ("`make check`", "all checks on the PR pass"),
                                ("`git log`", "the branch is merged"),
                                ("`make deploy`", "exit 0"),
                                ("`make check`", "a human approves the output"),
                                ("`make check`", "manually confirmed")]:
            with self.subTest(command=command, passes=passes):
                self.assertEqual(rules(spec(row("AC-1", command, passes))), ["R2"])

    def test_R2_pre_pr_runnable_exclusions_are_local_forms(self):
        """R2-pre-pr-runnable: every R2_EXCLUDE form passes, merge-base and --no-merges included."""
        self.assertIn("git merge-base", speccheck.R2_EXCLUDE)
        self.assertIn("--no-merges", speccheck.R2_EXCLUDE)
        for form in speccheck.R2_EXCLUDE:
            with self.subTest(form=form):
                self.assertEqual(rules(spec(row("AC-1", f"`x {form} y`"))), [])

    def test_R2_pre_pr_runnable_exclusion_does_not_hide_a_real_token(self):
        """R2-pre-pr-runnable: an excluded form beside a real token still fires."""
        self.assertEqual(rules(spec(row("AC-1", "`git merge-base a b; gh pr view`"))),
                         ["R2"])

    def test_R2_pre_pr_runnable_ignores_a_pr_slug_tail(self):
        """R2-pre-pr-runnable: the lower-case -pr tail of a slug is not a pull request."""
        text = spec(row("AC-1", "`cat notes/2026-01-01-retry-upload-pr.md`",
                        "count at least 1"))
        self.assertEqual(rules(text), [])

    def test_R2_pre_pr_runnable_does_not_scan_ci_ship_or_review(self):
        """R2-pre-pr-runnable: bare CI, ship and review are not tokens."""
        text = spec(row("AC-1", "`uvx ruff check`", "CI's pinned version; Ship "
                        "criteria untouched; review file absent is fine at least once"))
        self.assertEqual(rules(text), [])


VERBATIM_REQ = "- **FR-001**: The body opens with `verbatim:summary`.\n"


def verbatim_spec(block: str, *, passes: str = "names summary") -> str:
    fenced = f"```verbatim:summary\n{block}\n```\n"
    return spec(row("AC-1", "`make body`", passes),
                requirements=VERBATIM_REQ + "\n" + fenced)


class R3(unittest.TestCase):
    def test_R3_verbatim_no_run_claims_fires_on_a_count(self):
        """R3-verbatim-no-run-claims: a numeral or number word before a run noun fires."""
        for text in ("Touches 3 files.", "Addresses two findings.", "One commit."):
            with self.subTest(text=text):
                self.assertEqual(rules(verbatim_spec(text)), ["R3"])

    def test_R3_verbatim_no_run_claims_fires_on_each_exhaustive_word(self):
        """R3-verbatim-no-run-claims: every R3_EXHAUSTIVE phrase fires."""
        for word in speccheck.R3_EXHAUSTIVE:
            with self.subTest(word=word):
                self.assertEqual(rules(verbatim_spec(f"This is {word} change.")), ["R3"])

    def test_R3_verbatim_no_run_claims_scans_only_blocks(self):
        """R3-verbatim-no-run-claims: the same words outside a block do not fire."""
        text = spec(requirements="- **FR-001**: Touches only 3 files.\n")
        self.assertEqual(rules(text), [])


class R4(unittest.TestCase):
    def test_R4_verbatim_block_delimited_fires_without_a_block(self):
        """R4-verbatim-block-delimited: the word with no named block fires."""
        found = lint(spec(requirements="- **FR-002**: Paste this verbatim:\n"
                                       "  \"Adds retries.\"\n"))[0]
        self.assertEqual([(v.rule, v.ident) for v in found], [("R4", "FR-002")])

    def test_R4_verbatim_block_delimited_fires_on_a_missing_block(self):
        """R4-verbatim-block-delimited: naming a block that does not exist fires."""
        text = spec(requirements="- **FR-001**: Verbatim, `verbatim:nowhere`.\n")
        self.assertEqual(rules(text), ["R4"])

    def test_R4_verbatim_block_delimited_passes_with_a_named_block(self):
        """R4-verbatim-block-delimited: naming an existing block passes."""
        self.assertEqual(rules(verbatim_spec("Adds retries.")), [])

    def test_R4_verbatim_block_delimited_masks_code_spans_and_comments(self):
        """R4-verbatim-block-delimited: the word in a code span or comment is discussion."""
        text = spec(requirements="- **FR-001**: Discusses `verbatim` text "
                                 "<!-- verbatim -->.\n")
        self.assertEqual(rules(text), [])

    def test_R4_verbatim_block_delimited_is_hard(self):
        """R4-verbatim-block-delimited: a waiver cannot silence it."""
        text = spec(requirements="- **FR-001**: Paste it verbatim.\n",
                    after_table="\n<!-- speccheck-ok: FR-001 R4 — no -->\n")
        self.assertEqual(sorted(rules(text)), ["R4", "R8"])


class R5(unittest.TestCase):
    def test_R5_artifact_read_is_scoped_fires_on_a_whole_file_read(self):
        """R5-artifact-read-is-scoped: each artifact read whole fires."""
        for name in ("READY.md", "RUN.md", "DELIVERABLE.md", "QUESTION.md",
                     "REVIEW.md", "REVIEW-r2.md"):
            with self.subTest(name=name):
                text = spec(row("AC-1", f"`grep -c x {name}`", "count at least 1"))
                self.assertEqual(rules(text), ["R5"])

    def test_R5_artifact_read_is_scoped_accepts_each_scope(self):
        """R5-artifact-read-is-scoped: every R5_SCOPES construct passes."""
        for command in ("`sed -n '/^## A/,/^## B/p' READY.md > e.txt; wc -l < e.txt`",
                        "`sed -n '/^## Log/,$p' RUN.md > e.txt; wc -l < e.txt`",
                        "`sed -n 5,20p RUN.md > e.txt; wc -l < e.txt`",
                        "`sed -nE -e '/^## A/,+3p' RUN.md > e.txt; wc -l < e.txt`",
                        "`awk '/^## A/{f=1} f' RUN.md > e.txt; wc -l < e.txt`",
                        "`awk '/^## A/,/^## B/' RUN.md > e.txt; wc -l < e.txt`",
                        "`awk '/^## A/{f=1} /^## B/{f=0} !f' RUN.md > e.txt; wc -l < e.txt`",
                        "`awk '/^~~~/{n++; next} n==1' READY.md > e.txt; wc -l < e.txt`",
                        "`awk 'NR>3' RUN.md > e.txt; wc -l < e.txt`",
                        "`pr_text.py extract READY.md > e.txt; wc -l < e.txt`"):
            with self.subTest(command=command):
                self.assertEqual(rules(spec(row("AC-1", command, "count at least 1"))),
                                 [])
        self.assertEqual(len(speccheck.R5_SCOPES), 3)

    def test_R5_artifact_read_is_scoped_fires_on_a_single_pattern_filter(self):
        """R5-artifact-read-is-scoped: a sed -n or awk filter reads the whole file, so it fires."""
        for command in ("`awk '/retry budget/' READY.md \\| wc -l`",
                        "`sed -n '/retry budget/p' READY.md \\| wc -l`",
                        "`sed -n 's/^x \\(.*\\)/\\1/p' READY.md \\| wc -l`",
                        "`awk '{print $1,$2}' READY.md \\| wc -l`",
                        "`awk '/x/{c++} END{print c}' READY.md`"):
            with self.subTest(command=command):
                self.assertEqual(rules(spec(row("AC-1", command, "count at least 1"))),
                                 ["R5"])

    def test_R5_artifact_read_is_scoped_ignores_other_markdown(self):
        """R5-artifact-read-is-scoped: README, SPEC and the REVIEWER contract are not artifacts."""
        self.assertEqual(rules(spec(row("AC-1", "`grep -c x README.md SPEC.md REVIEWER.md`",
                                        "count at least 1"))), [])


class R6(unittest.TestCase):
    EXTRACT = "`sed -n '/^## Log/,$p' RUN.md > e.txt; grep -c done e.txt`"

    def test_R6_extraction_asserted_fires_without_a_line_count(self):
        """R6-extraction-asserted: an extract with no wc -l and no delegate fires."""
        self.assertEqual(rules(spec(row("AC-1", self.EXTRACT, "count at least 1"))),
                         ["R6"])

    def test_R6_extraction_asserted_accepts_wc_l(self):
        """R6-extraction-asserted: a line count in the same row passes."""
        command = self.EXTRACT[:-1] + "; wc -l < e.txt`"
        self.assertEqual(rules(spec(row("AC-1", command, "count at least 1"))), [])

    def test_R6_extraction_asserted_accepts_a_delegate(self):
        """R6-extraction-asserted: naming another row that asserts the boundaries passes."""
        rows = (row("AC-1", "`true`") + row("AC-2", self.EXTRACT,
                                             "at least 1; boundaries are AC-1's"))
        self.assertEqual(rules(spec(rows)), [])


class R7(unittest.TestCase):
    def test_R7_verbatim_claim_is_tested_fires_when_no_row_names_the_block(self):
        """R7-verbatim-claim-is-tested: an unnamed block fires."""
        found = lint(verbatim_spec("Adds retries.", passes="exit 0"))[0]
        self.assertEqual([(v.rule, v.ident) for v in found], [("R7", "summary")])

    def test_R7_verbatim_claim_is_tested_passes_when_a_row_names_it(self):
        """R7-verbatim-claim-is-tested: the name in a Pass cell passes."""
        self.assertEqual(rules(verbatim_spec("Adds retries.")), [])


class R8(unittest.TestCase):
    PR_ROW = row("AC-1", "`gh pr view 3`")

    def waive(self, *comments: str) -> str:
        return spec(self.PR_ROW, after_table="".join(f"\n{c}\n" for c in comments))

    def test_R8_stale_waiver_short_and_full_ids_silence(self):
        """R8-stale-waiver: a valid waiver, short or full id, silences and is not stale."""
        for rule in ("R2", "R2-pre-pr-runnable"):
            with self.subTest(rule=rule):
                self.assertEqual(
                    rules(self.waive(f"<!-- speccheck-ok: AC-1 {rule} — why -->")), [])

    def test_R8_stale_waiver_fires_on_a_missing_row(self):
        """R8-stale-waiver: a waiver naming no row fires and silences nothing."""
        self.assertEqual(sorted(rules(self.waive(
            "<!-- speccheck-ok: AC-9 R2 — why -->"))), ["R2", "R8"])

    def test_R8_stale_waiver_fires_on_an_unknown_rule(self):
        """R8-stale-waiver: a waiver naming no rule fires."""
        self.assertIn("R8", rules(self.waive("<!-- speccheck-ok: AC-1 R99 — why -->")))

    def test_R8_stale_waiver_fires_on_a_hard_rule(self):
        """R8-stale-waiver: waiving R1, R4, R8 or R11 fires; hard rules take no annotation."""
        for rule in sorted(speccheck.HARD_RULES):
            with self.subTest(rule=rule):
                text = self.waive("<!-- speccheck-ok: AC-1 R2 — why -->",
                                  f"<!-- speccheck-ok: AC-1 {rule} — why -->")
                self.assertEqual(rules(text), ["R8"])

    def test_R8_stale_waiver_reads_multi_line_and_spaced_comments(self):
        """R8-stale-waiver: blank lines and multi-line comments stay in the block."""
        text = spec(self.PR_ROW + row("AC-2", "`deploy it`"),
                    after_table="\n<!-- speccheck-ok: AC-1 R2 — a reason that\n"
                                "     wraps -->\n\n<!-- a note -->\n"
                                "<!-- speccheck-ok: AC-2 R2 — why -->\n")
        self.assertEqual(rules(text), [])

    def test_R8_stale_waiver_ignores_annotations_outside_the_block(self):
        """R8-stale-waiver: an annotation after prose, or in a code span, is not a waiver."""
        text = spec(self.PR_ROW, after_table="\nProse, A --> B.\n"
                    "<!-- speccheck-ok: AC-1 R2 — too late -->\n"
                    "`<!-- speccheck-ok: AC-1 R2 — example -->`\n")
        self.assertEqual(rules(text), ["R2"])


class R9(unittest.TestCase):
    def test_R9_marker_token_not_reproduced_imports_the_matcher(self):
        """R9-marker-token-not-reproduced: the derived token is one find_markers accepts."""
        token = speccheck.marker_token()
        self.assertEqual(token, TOKEN)
        self.assertEqual(queue_rules.find_markers(f"[{token}: x]"), [(1, "x")])
        source = Path(speccheck.__file__).read_text()
        self.assertNotIn(TOKEN, source)
        self.assertNotIn("MARKER_RE =", source)

    def test_R9_marker_token_not_reproduced_fires_outside_a_marker(self):
        """R9-marker-token-not-reproduced: the token in prose or a code span fires."""
        for line in (f"Any unresolved `[{TOKEN}]` blocks.", f"The {TOKEN} word."):
            with self.subTest(line=line):
                self.assertEqual(rules(spec(tail=line + "\n")), ["R9"])

    def test_R9_marker_token_not_reproduced_allows_markers_and_comments(self):
        """R9-marker-token-not-reproduced: a real marker or a comment mention passes."""
        text = spec(tail=f"- **FR-9**: [{TOKEN}: which one?]\n<!-- {TOKEN} -->\n")
        self.assertEqual(rules(text), [])

    def test_R9_marker_token_not_reproduced_counts_per_occurrence(self):
        """R9-marker-token-not-reproduced: a marker does not excuse a second mention."""
        text = spec(tail=f"[{TOKEN}: a] and `{TOKEN}`\n")
        self.assertEqual(rules(text), ["R9"])


class R10(unittest.TestCase):
    def test_R10_absence_has_control_fires_on_each_absence_token(self):
        """R10-absence-has-control: every absence phrasing without a control fires."""
        for passes in ("prints nothing", "no output", "returns nothing",
                       "output is empty", "`diff=0`", "count `0`"):
            with self.subTest(passes=passes):
                self.assertEqual(rules(spec(row("AC-1", "`x`", passes))), ["R10"])

    def test_R10_absence_has_control_accepts_each_control(self):
        """R10-absence-has-control: every R10_CONTROL phrasing silences."""
        for control in ("at least 1 hit", "≥ 1 hit", ">= 1 hit", "a non-empty file",
                        "a positive control matches"):
            with self.subTest(control=control):
                passes = f"prints nothing; {control}"
                self.assertEqual(rules(spec(row("AC-1", "`x`", passes))), [])

    def test_R10_absence_has_control_exit_code_exclusion(self):
        """R10-absence-has-control: `0` after exit/exits is an exit code; alone it is a count."""
        self.assertEqual(speccheck.R10_EXIT_WORDS, ("exit", "exits"))
        for passes in ("exits `0`", "Exit `0`", "the command exit `0`"):
            with self.subTest(passes=passes):
                self.assertEqual(rules(spec(row("AC-1", "`x`", passes))), [])
        for passes in ("`0`", "prints `0`", "exited `0`"):
            with self.subTest(passes=passes):
                self.assertEqual(rules(spec(row("AC-1", "`x`", passes))), ["R10"])

    def test_R10_absence_has_control_non_empty_is_not_absence(self):
        """R10-absence-has-control: non-empty alone asserts nothing absent."""
        self.assertEqual(rules(spec(row("AC-1", "`x`", "the file is non-empty"))), [])

    def test_R10_absence_has_control_ignores_ship_rows(self):
        """R10-absence-has-control: Ship criteria rows are exempt."""
        ship = ("## Ship criteria (owned by the ship step — NOT the executor)\n\n"
                + HEADER + row("SC-1", "`x`", "no output"))
        self.assertEqual(rules(spec(tail=ship)), [])


class R11(unittest.TestCase):
    NONE = "- **Must not touch**: the rest\n"

    def test_R11_state_predicates_declared_fires_from_r11_since(self):
        """R11-state-predicates-declared: missing on or after R11_SINCE is an error."""
        for day in (speccheck.R11_SINCE, speccheck.R11_SINCE + timedelta(days=1)):
            with self.subTest(day=day):
                found, warnings = lint(spec(constraints=self.NONE,
                                            created=day.isoformat()))
                self.assertEqual([v.rule for v in found], ["R11"])
                self.assertEqual(warnings, [])

    def test_R11_state_predicates_declared_warns_before_r11_since(self):
        """R11-state-predicates-declared: an older spec gets a warning, not an error."""
        day = speccheck.R11_SINCE - timedelta(days=1)
        found, warnings = lint(spec(constraints=self.NONE, created=day.isoformat()))
        self.assertEqual(found, [])
        self.assertEqual(len(warnings), 1)
        self.assertIn("R11-state-predicates-declared warning", warnings[0])

    def test_R11_state_predicates_declared_warns_when_created_is_unparseable(self):
        """R11-state-predicates-declared: no parseable created: is grandfathered too."""
        found, warnings = lint(spec(constraints=self.NONE, created="YYYY-MM-DD"))
        self.assertEqual((found, len(warnings)), ([], 1))

    def test_R11_state_predicates_declared_fires_on_an_empty_body(self):
        """R11-state-predicates-declared: the label with nothing after it fires."""
        text = spec(constraints="- **State predicates**:\n- **Must not touch**: x\n")
        self.assertEqual(rules(text), ["R11"])

    def test_R11_state_predicates_declared_accepts_a_body_below_the_label(self):
        """R11-state-predicates-declared: a label whose body is the bullets below passes."""
        text = spec(constraints="**State predicates**\n\n- `RUN.md` — written at "
                                "dispatch.\n")
        self.assertEqual(rules(text), [])

    def test_R11_state_predicates_declared_ignores_a_label_in_a_comment(self):
        """R11-state-predicates-declared: a commented-out label does not count."""
        text = spec(constraints="<!-- **State predicates**: none -->\n")
        self.assertEqual(rules(text), ["R11"])


class PlanMode(unittest.TestCase):
    PLAN = ("# Plan: x\n\n## Tasks\n\n| # | Task | Files | Verify | After |\n"
            "|---|---|---|---|---|\n")

    def test_R1_command_is_a_command_applies_to_a_plan_verify_column(self):
        """R1-command-is-a-command: a plan's prose Verify cell fires, by row id."""
        text = self.PLAN + "| T1 | FR-001 | `a` | looks right | — |\n"
        found = lint(text)[0]
        self.assertEqual([(v.rule, v.ident) for v in found], [("R1", "T1")])
        self.assertIn("Verify cell", found[0].message)

    def test_plan_mode_runs_only_R1(self):
        """R1-command-is-a-command: the spec-only rules (R2-R11) do not run on a plan."""
        text = self.PLAN + "| T1 | FR-001 | `a` | `gh pr view 1` — prints nothing | — |\n"
        self.assertEqual(lint(text), ([], []))


class Cli(unittest.TestCase):
    def test_cli_exit_codes_and_output_shape(self):
        """R1-command-is-a-command: exit 1 with one path:line: RULE-ID id: line per violation."""
        with TemporaryDirectory() as tmp:
            bad = Path(tmp, "bad.md")
            bad.write_text(spec(row("AC-1", "prose")))
            good = Path(tmp, "good.md")
            good.write_text(spec())
            self.assertEqual(run(str(good)), (0, "", ""))
            rc, out, _ = run(str(good), str(bad))
            self.assertEqual(rc, 1)
            self.assertRegex(out, rf"^{bad}:\d+: R1-command-is-a-command AC-1: ")
            self.assertEqual(len(out.splitlines()), 1)

    def test_cli_exit_2_on_unreadable_or_not_a_spec(self):
        """A missing file, or one with no Acceptance or Tasks table, exits 2, never 0."""
        with TemporaryDirectory() as tmp:
            prose = Path(tmp, "prose.md")
            prose.write_text("# Notes\n\nNothing to check.\n")
            for path in (str(Path(tmp, "missing.md")), str(prose)):
                with self.subTest(path=path):
                    rc, out, err = run(path)
                    self.assertEqual((rc, out), (2, ""))
                    self.assertIn("speccheck:", err)


class Fixtures(unittest.TestCase):
    def test_every_must_fail_fixture_exits_1_and_every_rule_is_covered(self):
        """R1…R11: every must-fail fixture exits 1; together they fire every rule id."""
        files = sorted((FIXTURES / "must-fail").glob("*.md"))
        self.assertGreaterEqual(len(files), len(speccheck.RULES))
        fired = set()
        for path in files:
            with self.subTest(fixture=path.name):
                rc, out, _ = run(str(path))
                self.assertEqual(rc, 1, out)
                fired |= {line.split(": ")[1].split()[0] for line in out.splitlines()}
        self.assertEqual(fired, set(speccheck.RULES.values()))

    def test_every_must_pass_fixture_exits_0(self):
        """R11-state-predicates-declared: must-pass fixtures, the grandfathered one warning."""
        files = sorted((FIXTURES / "must-pass").glob("*.md"))
        self.assertGreaterEqual(len(files), 3)
        for path in files:
            with self.subTest(fixture=path.name):
                rc, out, err = run(str(path))
                self.assertEqual((rc, out), (0, ""))
                if "grandfathered" in path.name:
                    self.assertIn("R11-state-predicates-declared warning", err)


if __name__ == "__main__":
    unittest.main()
