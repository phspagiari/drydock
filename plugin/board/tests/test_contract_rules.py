"""Tests that pin the contracts to the board and to each other.

    python3 -m unittest discover plugin/board/tests

Two facts are stated in more than one place, and nothing else notices when
the copies drift apart: the diff-review verdict vocabulary (REVIEWER.md and
the board's badge whitelist in static/app.js) and the round-cap rules
(REVIEWER.md, DISPATCH.md step 12, ORCHESTRATOR.md, docs/ARCHITECTURE.md and
README.md). DISPATCH.md's step numbers and the citations of them are pinned
in test_contract_refs.py. Every extraction is anchored on content, never on
a line number, and proves it found something before anything is judged on
it — a check over an empty region passes vacuously, which is the failure
these tests exist to stop.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CONTRACTS = ROOT / "plugin" / "contracts"
APP_JS = ROOT / "plugin" / "board" / "static" / "app.js"


class ExtractionError(AssertionError):
    """A content anchor matched nothing, or matched the wrong region."""


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def normalise(text: str) -> str:
    """Drop Markdown emphasis and code ticks, fold whitespace, lower-case."""
    text = text.replace("**", "").replace("`", "")
    return re.sub(r"\s+", " ", text).strip().lower()


# --- region extractors ------------------------------------------------------

def h2_sections(text: str) -> list[tuple[str, str]]:
    """(heading line, section text up to the next H2) for every H2."""
    sections, heading, lines = [], None, []
    for line in text.splitlines():
        if line.startswith("## "):
            if heading is not None:
                sections.append((heading, "\n".join(lines)))
            heading, lines = line, [line]
        elif heading is not None:
            lines.append(line)
    if heading is not None:
        sections.append((heading, "\n".join(lines)))
    return sections


def h2_section(text: str, prefix: str) -> str:
    for heading, body in h2_sections(text):
        if heading.startswith(prefix):
            return body
    raise ExtractionError(f"no H2 section beginning {prefix!r}")


def diff_review_block(reviewer: str) -> str:
    """The YAML block of the DIFF-REVIEW verdict section.

    That section's H2 begins "## Verdict" and names REVIEW.md without a
    PLAN- prefix; a plan-gate verdict section is skipped wherever it sits.
    The block must carry a `round:` key, which only the diff-review block has.
    """
    for heading, body in h2_sections(reviewer):
        if (heading.startswith("## Verdict") and "REVIEW.md" in heading
                and "PLAN-REVIEW" not in heading):
            fence = re.search(r"^```yaml\n(.*?)^```", body, re.M | re.S)
            if not fence or not fence.group(1).strip():
                raise ExtractionError("diff-review verdict section has no yaml block")
            block = fence.group(1)
            if not re.search(r"^round:", block, re.M):
                raise ExtractionError("yaml block has no round: key — not the diff-review block")
            return block
    raise ExtractionError("no '## Verdict … REVIEW.md' section outside the plan gate")


def verdicts(block: str) -> list[str]:
    line = re.search(r"^verdict:(.*)$", block, re.M)
    values = [v.strip() for v in line.group(1).split("|")] if line else []
    if not values or not all(values):
        raise ExtractionError("no verdict: values in the block")
    return values


def verdict_classes(app_js: str) -> set[str]:
    body = re.search(r"const VERDICT_CLASS = \{(.*?)\};", app_js, re.S)
    keys = set(re.findall(r"""["']?([\w-]+)["']?\s*:""", body.group(1))) if body else set()
    if not keys:
        raise ExtractionError("no VERDICT_CLASS whitelist in app.js")
    return keys


def unrenderable(reviewer: str, app_js: str) -> list[str]:
    """Diff-review verdicts the board has no badge class for."""
    classes = verdict_classes(app_js)
    return [v for v in verdicts(diff_review_block(reviewer)) if v not in classes]


def numbered_item(text: str, n: int) -> str:
    """Top-level list item `n.` up to the next top-level item or heading."""
    match = re.search(rf"^{n}\. .*?(?=^\d+\. |^#)", text + "\n#", re.M | re.S)
    if not match:
        raise ExtractionError(f"no top-level item {n}.")
    return match.group(0)


def orchestrator_verdict_bullet(text: str) -> str:
    match = re.search(r"^   - `REVIEW\.md` verdict appeared.*?(?=^   - |^\d+\. )", text,
                      re.M | re.S)
    if not match:
        raise ExtractionError("no '`REVIEW.md` verdict appeared' bullet")
    return match.group(0)


def architecture_cap_paragraph(text: str) -> str:
    paragraphs = [p for p in re.split(r"\n\s*\n", text) if "round cap" in p.lower()]
    if len(paragraphs) != 1:
        raise ExtractionError(f"expected one round-cap paragraph, found {len(paragraphs)}")
    return paragraphs[0]


def readme_cap_bullet(text: str) -> str:
    match = re.search(r"^- \*\*Round cap.*?(?=^- \*\*|^\s*$)", text, re.M | re.S)
    if not match:
        raise ExtractionError("no '- **Round cap' bullet")
    return match.group(0)


# --- the rules --------------------------------------------------------------

# One entry per rule a section stating the cap must carry. Every pattern of a
# rule must match the section's normalised text.
CAP_RULES = {
    "cap is 2 fix rounds per run": [r"round cap:? 2 fix rounds per run"],
    "run scope": [r"run begins at dispatch from inbox/ and ends at ship or archive"],
    "re-queue starts a new run": [r"re-queue after a flag starts a new run",
                                  r"resets (round )?to 0"],
    "dispatch failure retries the round": [r"dispatch failure", r"byte-unchanged",
                                           r"same round retried"],
    "repair pass is not a fix round": [r"repair pass[^.;]{0,30} is not a fix round"],
    "at the cap": [r"cap_retire: true", r"judgement[^.;]{0,40}→ (the reviewer flags|flag)"],
}


def missing_rules(section: str) -> list[str]:
    text = normalise(section)
    return [name for name, patterns in CAP_RULES.items()
            if not all(re.search(p, text) for p in patterns)]


def doc_contradictions(section: str) -> list[str]:
    """What a prose restatement of the cap gets wrong or leaves out."""
    text = normalise(section)
    problems = []
    if re.search(r"flag.{0,20}regardless", text):
        problems.append("says the cap flags regardless")
    for word in ("judgement", "flag", "mechanical", "repair pass"):
        if word not in text:
            problems.append(f"does not mention {word!r}")
    return problems


# --- fixtures ---------------------------------------------------------------

DIFF_REVIEW = """## Verdict — write `REVIEW.md`

```yaml
verdict: {verdicts}
round: <N>
review: <M>
findings: <count>
```
"""

PLAN_GATE = """## Plan gate — write `PLAN-REVIEW.md`

```yaml
verdict: approve | flag
findings: <count>
```
"""

APP = 'const VERDICT_CLASS = {\n  ship: "ship", fix: "fix", flag: "flag",\n};\n'

CAP_SECTION = """- Round cap 2 fix rounds per run. A run begins at dispatch from `inbox/`
  and ends at `ship` or `archive`. An `inbox/` re-queue after a `flag`
  starts a new run and resets `round` to 0. A re-dispatch after a dispatch
  failure with the deliverable byte-unchanged is the same round retried.
  The repair pass is not a fix round. At the cap, any `judgement` finding
  → flag; all `mechanical` → `cap_retire: true`.
"""


# --- tests ------------------------------------------------------------------

class TestVerdictVocabulary(unittest.TestCase):
    def setUp(self):
        self.reviewer = read(CONTRACTS / "REVIEWER.md")

    def test_board_renders_every_diff_review_verdict(self):
        self.assertEqual(unrenderable(self.reviewer, read(APP_JS)), [])

    def test_extraction_is_the_diff_review_block(self):
        block = diff_review_block(self.reviewer)
        self.assertRegex(block, r"(?m)^round: <N>")
        self.assertRegex(block, r"(?m)^review: <M>")
        self.assertEqual(verdicts(block), ["ship", "fix", "flag"])

    def test_unrenderable_fourth_verdict_is_rejected(self):
        fixture = DIFF_REVIEW.format(verdicts="ship | fix | flag | ship-with-edits")
        self.assertEqual(unrenderable(fixture, APP), ["ship-with-edits"])

    def test_plan_gate_block_after_the_diff_review_block_is_ignored(self):
        fixture = DIFF_REVIEW.format(verdicts="ship | fix | flag") + "\n" + PLAN_GATE
        self.assertEqual(unrenderable(fixture, APP), [])

    def test_plan_gate_block_before_the_diff_review_block_is_ignored(self):
        fixture = PLAN_GATE + "\n" + DIFF_REVIEW.format(verdicts="ship | fix | flag")
        self.assertEqual(unrenderable(fixture, APP), [])

    def test_missing_diff_review_section_fails_loudly(self):
        with self.assertRaises(ExtractionError):
            unrenderable(PLAN_GATE, APP)

    def test_block_without_round_key_is_not_trusted(self):
        fixture = DIFF_REVIEW.format(verdicts="ship | fix | flag").replace("round: <N>\n", "")
        with self.assertRaises(ExtractionError):
            diff_review_block(fixture)


class TestRoundCapRules(unittest.TestCase):
    def sections(self) -> dict[str, str]:
        return {
            "REVIEWER.md ## Hard limits": h2_section(read(CONTRACTS / "REVIEWER.md"),
                                                     "## Hard limits"),
            "DISPATCH.md step 12": numbered_item(read(CONTRACTS / "DISPATCH.md"), 12),
            "ORCHESTRATOR.md verdict bullet": orchestrator_verdict_bullet(
                read(CONTRACTS / "ORCHESTRATOR.md")),
        }

    def test_every_section_stating_the_cap_states_every_rule(self):
        for name, section in self.sections().items():
            with self.subTest(section=name):
                self.assertGreaterEqual(len(section.splitlines()), 3)
                self.assertEqual(missing_rules(section), [])

    def test_every_section_names_the_repair_pass(self):
        for name, section in self.sections().items():
            with self.subTest(section=name):
                self.assertIn("repair pass", normalise(section))

    def test_section_missing_one_rule_fails(self):
        self.assertEqual(missing_rules(CAP_SECTION), [])
        for name in CAP_RULES:
            with self.subTest(dropped=name):
                pattern = CAP_RULES[name][0]
                mutated = re.sub(pattern, "", normalise(CAP_SECTION))
                self.assertIn(name, missing_rules(mutated))

    def test_docs_restatements_do_not_contradict_the_contract(self):
        docs = {
            "docs/ARCHITECTURE.md": architecture_cap_paragraph(
                read(ROOT / "docs" / "ARCHITECTURE.md")),
            "README.md": readme_cap_bullet(read(ROOT / "README.md")),
        }
        for name, section in docs.items():
            with self.subTest(doc=name):
                self.assertEqual(doc_contradictions(section), [])

    def test_regardless_restatement_is_caught(self):
        stale = ("- **Round cap 2.** Work that survives two fix rounds without shipping "
                 "needs a human — the verdict becomes `flag` regardless.")
        self.assertIn("says the cap flags regardless", doc_contradictions(stale))


class TestRepairPassNeverRewrites(unittest.TestCase):
    """The repair pass adds a commit; it never rewrites one."""

    def test_step_12_forbids_rewriting_and_keeps_no_rewrite_machinery(self):
        step = normalise(numbered_item(read(CONTRACTS / "DISPATCH.md"), 12))
        self.assertIn("never rewrites a commit", step)
        self.assertIn("one new commit", step)
        for machinery in ("head^{tree}", "ls-remote", "may be rewritten"):
            with self.subTest(machinery=machinery):
                self.assertNotIn(machinery, step)

    def test_mechanical_requires_no_commit_rewrite(self):
        body = next(body for heading, body in h2_sections(read(CONTRACTS / "REVIEWER.md"))
                    if heading.startswith("## Verdict") and "PLAN-REVIEW" not in heading)
        self.assertIn("without rewriting any commit", normalise(body))


if __name__ == "__main__":
    unittest.main()
