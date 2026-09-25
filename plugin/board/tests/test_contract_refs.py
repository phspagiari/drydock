"""Every ``step N`` citation in the contracts and skills resolves to a real step.

    python3 -m unittest discover board/tests

The contracts cite each other's numbered steps by value — "per DISPATCH step
12", "REVIEWER.md step 3", "steps 16–17" — which is why markdownlint's MD029
is off and why DISPATCH.md must never be renumbered. This test is what makes
that rule checkable: it scans ``contracts/*.md`` and ``skills/*/SKILL.md``
and fails on any citation that points at a step that does not exist.

A citation resolves by the word directly before ``step``:

- ``DISPATCH`` / ``DISPATCH.md`` / ``preflight`` → DISPATCH.md's steps;
- ``REVIEWER`` / ``ORCHESTRATOR`` (``.md`` or not) → that contract's steps;
- anything else → the citing file's own steps (a skill's "see step 1" means
  its own ``## 1.`` section), or DISPATCH.md's when the file numbers none.

A file's steps are its top-level ``N.`` list items and ``## N.`` headings.
A lettered sub-step (``step 8b``) counts as its step, and must also exist as
the bold inline label DISPATCH.md uses for sub-steps (``**8b — …``).

What this does not cover: an unqualified citation whose author meant another
file's step (``dispatch/SKILL.md``'s "once step 5" means DISPATCH step 5 and
is checked against the skill's own step 5); citations outside the scanned
files (README, docs/); and whether a cited step still *says* what the citing
sentence claims — only that it exists.
"""

import re
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

PLUGIN = Path(__file__).resolve().parent.parent.parent

STEP_RE = re.compile(r"^(?:#+[ \t]+)?(\d+)\.[ \t]", re.M)
CITE_RE = re.compile(
    r"(?P<qual>\S+)?\s+steps?[\s-]+(?P<a>\d+)(?P<al>[a-z])?\b"
    r"(?:\s*(?:–|-|\.\.|to|and)\s*(?P<b>\d+)(?P<bl>[a-z])?\b)?",
    re.I,
)
NAMED = {"dispatch": "DISPATCH.md", "preflight": "DISPATCH.md",
         "reviewer": "REVIEWER.md", "orchestrator": "ORCHESTRATOR.md"}


def steps(text: str) -> set[int]:
    return {int(n) for n in STEP_RE.findall(text)}


def sources(plugin: Path) -> list[Path]:
    return sorted(plugin.glob("contracts/*.md")) + sorted(plugin.glob("skills/*/SKILL.md"))


def citations(text: str):
    """(qualifier, [(number, letter)]) per citation, line wraps collapsed."""
    for m in CITE_RE.finditer(re.sub(r"\s+", " ", text)):
        qual = (m.group("qual") or "").strip("`*_()[]\"'<>,;:").rsplit("/", 1)[-1]
        refs = [(int(m.group("a")), (m.group("al") or "").lower())]
        if m.group("b"):
            refs.append((int(m.group("b")), (m.group("bl") or "").lower()))
        yield qual, refs, m.group(0).strip()


def dangling(plugin: Path) -> list[str]:
    """``file: citation -> reason`` for every citation that does not resolve."""
    contracts = plugin / "contracts"
    dispatch = (contracts / "DISPATCH.md").read_text()
    bad = []
    for src in sources(plugin):
        text = src.read_text()
        for qual, refs, cited in citations(text):
            name = NAMED.get(qual.lower().removesuffix(".md"))
            if name:
                target = contracts / name
            elif steps(text):
                target = src
            else:
                target = contracts / "DISPATCH.md"
            target_text = target.read_text() if target.is_file() else ""
            have = steps(target_text)
            for n, letter in refs:
                if n not in have:
                    bad.append(f"{src.relative_to(plugin)}: {cited!r} -> no step {n} "
                               f"in {target.name}")
                elif letter and target.name == "DISPATCH.md" and not re.search(
                        rf"\*\*{n}{letter}\b", dispatch):
                    bad.append(f"{src.relative_to(plugin)}: {cited!r} -> no sub-step "
                               f"{n}{letter} in DISPATCH.md")
    return bad


class ContractRefsTest(unittest.TestCase):
    def test_every_citation_resolves(self):
        self.assertEqual(dangling(PLUGIN), [])

    def test_scanner_sees_the_known_citations(self):
        # Guards against a scanner that passes because it matches nothing.
        found = {(src.name, cited) for src in sources(PLUGIN)
                 for _, _, cited in citations(src.read_text())}
        self.assertIn(("DISPATCH.md", "(REVIEWER.md step 3"), found)
        self.assertIn(("ORCHESTRATOR.md", "DISPATCH steps 16–17"), found)
        self.assertGreater(len(found), 20)

    def test_dispatch_steps_are_numbered_without_gaps(self):
        # Sub-steps are bold labels inside a step, never numbered items.
        have = steps((PLUGIN / "contracts/DISPATCH.md").read_text())
        self.assertEqual(have, set(range(1, max(have) + 1)))
        self.assertGreaterEqual(max(have), 17)


class DanglingFixtureTest(unittest.TestCase):
    """The negative case: a tree with citations that must fail."""

    def test_dangling_citations_are_reported(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "contracts").mkdir()
            (root / "skills/demo").mkdir(parents=True)
            (root / "contracts/DISPATCH.md").write_text(
                "# D\n\n1. One.\n2. Two. **2a — Sub.** text\n3. Three.\n")
            (root / "contracts/REVIEWER.md").write_text("# R\n\n1. Read.\n2. Judge.\n")
            (root / "contracts/OTHER.md").write_text(
                "Per DISPATCH step 2, then DISPATCH\nstep 3 across a wrap,\n"
                "then DISPATCH step 2a, then `DISPATCH.md` steps 1–3.\n"
                "Bad: DISPATCH step 9. Bad: DISPATCH step 2z.\n"
                "Bad: REVIEWER.md step 3.\n")
            (root / "skills/demo/SKILL.md").write_text(
                "## 1. First\n\nSee step 1.\n\n## 2. Second\n\nBad: steps 1–4.\n")
            self.assertEqual(dangling(root), [
                "contracts/OTHER.md: 'DISPATCH step 9' -> no step 9 in DISPATCH.md",
                "contracts/OTHER.md: 'DISPATCH step 2z' -> no sub-step 2z "
                "in DISPATCH.md",
                "contracts/OTHER.md: 'REVIEWER.md step 3' -> no step 3 in REVIEWER.md",
                "skills/demo/SKILL.md: 'Bad: steps 1–4' -> no step 4 in SKILL.md",
            ])


if __name__ == "__main__":
    unittest.main()
