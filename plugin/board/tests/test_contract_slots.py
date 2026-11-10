"""Tests that pin the concurrency cap's contract text to ``queue_rules.py slots``.

    python3 -m unittest discover plugin/board/tests

The cap is ``max_concurrent`` in ``<STATE_HOME>/config`` and is computed in one
place, ``queue_rules.slots``. Two prose gates apply it -- ORCHESTRATOR.md's
Inbox step and the dispatch skill's step 1 -- and both used to restate it as a
number, which is exactly the copy that drifts when the value moves into
config. These tests require each gate to run the CLI and to carry no number of
its own; the Hard limits line must name the key, not a count, and so must the
clause in DISPATCH.md step 7 that explains why chained specs collide. Extraction
is anchored on content and proves it found the region before judging it.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ORCHESTRATOR = ROOT / "plugin" / "contracts" / "ORCHESTRATOR.md"
DISPATCH_SKILL = ROOT / "plugin" / "skills" / "dispatch" / "SKILL.md"
DISPATCH = ROOT / "plugin" / "contracts" / "DISPATCH.md"

#: The runnable spelling, as every board script is spelled in the contracts.
SLOTS_CALL = r"python3 <plugin_home>/board/queue_rules\.py slots"

_NUM = r"(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)"
_ORD = r"(?:second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|eleventh)"

#: Ways a prose gate restates the cap as a count. Step citations ("DISPATCH
#: step 7") and ids are not counts of executions and do not match.
NUMERIC_CAP = [
    rf"\b(?:fewer|less|more) than {_NUM}\b",
    rf"\b(?:at most|up to|max(?:imum)?(?: of)?|cap(?: of)?) {_NUM}\b",
    rf"\b{_NUM}\+? (?:concurrent |active |parallel )?execution",
    rf"\b(?:a|the) {_ORD}\b",
]


class ExtractionError(AssertionError):
    """A content anchor matched nothing, or matched the wrong region."""


def normalise(text: str) -> str:
    """Drop Markdown emphasis and code ticks, fold whitespace, lower-case."""
    text = text.replace("**", "").replace("`", "")
    return re.sub(r"\s+", " ", text).strip().lower()


def numeric_caps(section: str) -> list[str]:
    text = normalise(section)
    return [m.group(0) for p in NUMERIC_CAP for m in re.finditer(p, text)]


def orchestrator_inbox(text: str) -> str:
    match = re.search(r"^1\. \*\*Inbox\*\*.*?(?=^2\. )", text, re.M | re.S)
    if not match or "ELIGIBLE" not in match.group(0):
        raise ExtractionError("no '1. **Inbox**' step holding the ELIGIBLE rule")
    return match.group(0)


def orchestrator_hard_limits(text: str) -> str:
    match = re.search(r"^## Hard limits\n(.*?)(?=^## )", text + "\n## ", re.M | re.S)
    if not match or "relaunch" not in match.group(1):
        raise ExtractionError("no '## Hard limits' section with the relaunch cap")
    return match.group(1)


def dispatch_step_1(text: str) -> str:
    procedure = re.search(r"^## Procedure\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    match = procedure and re.search(r"^1\. .*?(?=^2\. )", procedure.group(1), re.M | re.S)
    if not match:
        raise ExtractionError("no step 1 under '## Procedure'")
    return match.group(0)


def chained_spec_clause(text: str) -> str:
    """The sentence in DISPATCH.md step 7 saying how many executions run at once.

    Only that clause: the rest of its paragraph counts colliding specs ("Two
    specs", "the second git worktree add"), which is not the cap.
    """
    step = re.search(r"^7\. .*?(?=^8\. )", text, re.M | re.S)
    para = step and re.search(r"\*\*Two specs chaining onto the same `branch:`.*?"
                              r"Whoever writes the series owns it\.", step.group(0), re.S)
    clause = para and re.findall(r"the orchestrator runs[^.]*\.", normalise(para.group(0)))
    if not clause or len(clause) != 1:
        raise ExtractionError("no single 'the orchestrator runs …' clause in step 7's "
                              "chained-spec paragraph")
    return clause[0]


class TestGatesRunSlots(unittest.TestCase):
    def gates(self) -> dict[str, str]:
        return {
            "ORCHESTRATOR.md Inbox": orchestrator_inbox(ORCHESTRATOR.read_text()),
            "dispatch/SKILL.md step 1": dispatch_step_1(DISPATCH_SKILL.read_text()),
        }

    def test_every_gate_runs_queue_rules_slots(self):
        for name, section in self.gates().items():
            with self.subTest(gate=name):
                self.assertRegex(normalise(section), SLOTS_CALL)

    def test_no_gate_carries_a_numeric_cap(self):
        for name, section in self.gates().items():
            with self.subTest(gate=name):
                self.assertEqual(numeric_caps(section), [])

    def test_inbox_reruns_slots_after_each_dispatch_and_fails_closed(self):
        text = normalise(orchestrator_inbox(ORCHESTRATOR.read_text()))
        self.assertRegex(text, r"free > 0")
        self.assertRegex(text, r"re-run[^.]{0,80}after each dispatch")
        self.assertRegex(text, r"non-zero exit from slots")

    def test_hard_limits_name_the_key_not_a_count(self):
        text = normalise(orchestrator_hard_limits(ORCHESTRATOR.read_text()))
        self.assertIn("max_concurrent", text)
        self.assertIn("<state_home>/config", text)
        self.assertNotRegex(text, rf"max {_NUM} concurrent")

    def test_dispatch_chained_spec_clause_names_the_key_not_a_count(self):
        clause = chained_spec_clause(DISPATCH.read_text())
        self.assertIn("max_concurrent", clause)
        self.assertEqual(numeric_caps(clause), [])


class TestNumericCapDetector(unittest.TestCase):
    """The detector must see every shape the old prose used, and not step citations."""

    def test_old_phrasings_are_caught(self):
        for stale in ("while fewer than **2** executions are active",
                      "Max 2 concurrent executions",
                      "If 2+ executions are already active",
                      "get explicit go-ahead before adding a third",
                      "the orchestrator runs up to 2 executions at once",
                      "the hard cap of two concurrent executions"):
            with self.subTest(stale=stale):
                self.assertNotEqual(numeric_caps(stale), [])

    def test_step_citations_and_config_reads_are_not_caps(self):
        clean = ("per DISPATCH step 7, then the `<DISPATCH step-8 prompt>`; while "
                 "`python3 <PLUGIN_HOME>/board/queue_rules.py slots` reports free > 0 "
                 "(its second field is the cap)")
        self.assertEqual(numeric_caps(clean), [])

    def test_old_chained_spec_clause_is_caught(self):
        old = ("7. Worktree.\n   **Two specs chaining onto the same `branch:` cannot be "
               "dispatched\n   concurrently.** the second add dies — and the orchestrator "
               "runs up to 2 executions at once. Whoever writes the series owns it.\n8. Next.\n")
        clause = chained_spec_clause(old)
        self.assertNotIn("max_concurrent", clause)
        self.assertEqual(numeric_caps(clause), ["up to 2", "2 execution"])

    def test_extraction_fails_loudly_on_a_missing_anchor(self):
        with self.assertRaises(ExtractionError):
            orchestrator_inbox("# O\n\n1. **Outbox** — nothing\n2. **Active**\n")
        with self.assertRaises(ExtractionError):
            dispatch_step_1("## Argument\n\n1. x\n2. y\n")
        with self.assertRaises(ExtractionError):
            chained_spec_clause("7. Worktree, no chained-spec paragraph.\n8. Next.\n")


if __name__ == "__main__":
    unittest.main()
