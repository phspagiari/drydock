"""The contracts carry the every-session rules, once, and point at them.

    python3 -m unittest discover board/tests

DISPATCH.md holds one *Every session* section; the three executor prompts in
step 8, REVIEWER.md and ORCHESTRATOR.md's Hard limits point at it instead of
restating it. Every assertion here runs on a region extracted by content
anchors, never on a whole file, and every extraction must be non-empty -- a
grep over the wrong region, or over nothing, would otherwise pass.
"""

import re
import unittest
from pathlib import Path

CONTRACTS = Path(__file__).resolve().parent.parent.parent / "contracts"

SECTION = "## Every session — no prompts, verified effects"

#: The sentence each quoted executor prompt carries, whitespace collapsed.
POINTER = ("Before running any command, also read the `## Every session` "
           "section of `<PLUGIN_HOME>/contracts/DISPATCH.md`; it binds this "
           "session.")

#: The labels step 8's three quoted executor prompts follow.
PROMPT_LABELS = ("**8a — Plan.** Prompt:", "**8c — Implement.**",
                 "**Single-phase (old-shape")


def collapse(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def h2_section(text: str, heading_prefix: str) -> str:
    """From the H2 starting with ``heading_prefix`` to the next H2 or EOF."""
    m = re.search(rf"^{re.escape(heading_prefix)}.*?(?=^## |\Z)", text, re.M | re.S)
    return m.group(0) if m else ""


def last_h2(text: str) -> str:
    starts = [m.start() for m in re.finditer(r"^## ", text, re.M)]
    return text[starts[-1]:] if starts else ""


def step_8(text: str) -> str:
    """DISPATCH step 8, from its list item to step 9's."""
    m = re.search(r"^8\. .*?(?=^9\. )", text, re.M | re.S)
    return m.group(0) if m else ""


def quoted_prompts(step: str) -> list[str]:
    """Every ``*"…"*`` span in the step: a quoted prompt."""
    return re.findall(r'\*"(.*?)"\*', step, re.S)


def labelled_prompt(step: str, label: str) -> str:
    """The first quoted prompt after ``label``."""
    at = step.find(label)
    if at < 0:
        return ""
    found = quoted_prompts(step[at:])
    return found[0] if found else ""


def read(name: str) -> str:
    return (CONTRACTS / name).read_text()


class EverySessionSectionTest(unittest.TestCase):
    def setUp(self):
        self.section = h2_section(read("DISPATCH.md"), SECTION)
        self.assertTrue(self.section.strip(), "no Every session section extracted")
        self.flat = collapse(self.section)

    def test_it_sits_directly_above_preflight(self):
        text = read("DISPATCH.md")
        self.assertLess(text.index(SECTION), text.index("## Preflight (fail closed"))
        self.assertTrue(text.index(SECTION) + len(self.section)
                        == text.index("## Preflight (fail closed"))

    def test_non_interactive_forms(self):
        for needle in ("`rm -f`", "`cp -f`", "`mv -f`", "`git commit -m`",
                       "`git --no-pager`", "`| head`", "aliased"):
            self.assertIn(needle, self.flat, needle)

    def test_it_names_every_session_it_binds(self):
        for session in ("plan, implement and single-phase executors", "a relaunch",
                        "the comment-fix executor", "the diff reviewer",
                        "the plan gate", "the retro", "the orchestrator"):
            self.assertIn(session, self.flat, session)

    def test_a_reported_effect_is_a_verified_effect(self):
        self.assertIn("Exit 0 is not evidence.", self.flat)
        self.assertIn("reads EOF as \"no\", changes nothing and exits 0", self.flat)

    def test_state_home_changes_through_git_verbs(self):
        for needle in ("`git mv`", "`git rm`", "`--stat`", "that is a rename"):
            self.assertIn(needle, self.flat, needle)

    def test_the_nesting_clause(self):
        self.assertIn("assert the destination does not exist", self.flat)
        self.assertIn("`git mv` into an existing directory nests the source "
                      "inside it and exits 0", self.flat)


class ExecutorPromptPointerTest(unittest.TestCase):
    def setUp(self):
        self.step = step_8(read("DISPATCH.md"))
        self.assertTrue(self.step.strip(), "no step 8 extracted")

    def test_step_8_holds_exactly_three_quoted_prompts(self):
        # Positive control for the extraction below: if the prompt syntax
        # changes, this fails before the pointer check can pass vacuously.
        self.assertEqual(len(quoted_prompts(self.step)), 3)

    def test_each_executor_prompt_carries_the_pointer(self):
        for label in PROMPT_LABELS:
            prompt = labelled_prompt(self.step, label)
            self.assertTrue(prompt, f"no prompt after {label!r}")
            self.assertEqual(collapse(prompt).count(POINTER), 1, label)

    def test_the_three_prompts_are_three_different_prompts(self):
        prompts = {collapse(labelled_prompt(self.step, label))
                   for label in PROMPT_LABELS}
        self.assertEqual(len(prompts), 3)


class ReviewerTest(unittest.TestCase):
    def test_final_h2_binds_both_passes(self):
        section = last_h2(read("REVIEWER.md"))
        self.assertTrue(section.strip(), "no final H2 extracted")
        flat = collapse(section)
        self.assertIn("`## Every session`", flat)
        self.assertIn("the diff review and the plan gate", flat)
        self.assertIn("assert that your one output file exists", flat)

    def test_final_h2_follows_the_plan_gate(self):
        text = read("REVIEWER.md")
        self.assertLess(text.index("## Plan gate — DISPATCH step 8b"),
                        text.index(last_h2(text)))


class OrchestratorHardLimitsTest(unittest.TestCase):
    def setUp(self):
        self.limits = h2_section(read("ORCHESTRATOR.md"), "## Hard limits")
        self.assertTrue(self.limits.strip(), "no Hard limits extracted")
        self.flat = collapse(self.limits)

    def test_the_loop_is_a_session_and_runs_the_check(self):
        self.assertIn("`## Every session`", self.flat)
        self.assertIn("server.py check", self.flat)

    def test_finished_work_is_enumerated_and_every_recovery_checks_it(self):
        for needle in ("`READY.md`", "`QUESTION.md`", "`## Orchestrator —`",
                       "`--force`", "Needs input", "budget", "relaunch",
                       "rescue branch", "branch reset", "second-death block",
                       "worktree prune"):
            self.assertIn(needle, self.flat, needle)

    def test_the_open_question_test_is_cited_not_restated(self):
        self.assertIn("dispatch-failure bullet", self.flat)
        self.assertIn('"Executor died without moving state"', self.flat)
        self.assertNotIn("## Resolution", self.limits)

    def test_the_cited_bullet_exists_and_holds_the_test(self):
        # The citation is only worth something while its target says what
        # the Hard limits bullet relies on.
        text = read("ORCHESTRATOR.md")
        self.assertEqual(text.count("- Executor died without moving state"), 1)
        self.assertIn("**(i) An open `QUESTION.md`**", text)


if __name__ == "__main__":
    unittest.main()
