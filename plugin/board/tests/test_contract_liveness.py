"""The contracts carry the rules the liveness tests pin (DISPATCH 5 and 7, ORCHESTRATOR).

    python3 -m unittest discover plugin/board/tests

Every assertion runs against one named region, located by its content and
extracted first — never against a whole file, and never by line number,
because other changes keep shifting the lines above these regions. Each
extraction is proved before it is trusted: the region must start on its
anchor and stop right before the boundary that ends it. Set
``DRYDOCK_EVIDENCE_DIR`` to also write each region's line count and first and
last lines there.
"""

import os
import re
import sys
import unittest
from itertools import pairwise
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import liveness_rules as rules  # noqa: E402

PLUGIN = Path(__file__).resolve().parent.parent.parent
STEP_LINE = re.compile(r"^(?:#+[ \t]+)?\d+\.[ \t]|^## ")
BULLET = "   - "


def lines_of(name: str) -> list[str]:
    return (PLUGIN / "contracts" / name).read_text().splitlines()


def numbered_item(lines: list[str], anchor: str) -> list[str]:
    """The numbered list item whose first line starts with ``anchor``, up to
    (not including) the next numbered item or ``## `` heading."""
    starts = [i for i, line in enumerate(lines) if line.startswith(anchor)]
    if len(starts) != 1:
        raise AssertionError(f"anchor {anchor!r} found {len(starts)} times")
    start = starts[0]
    end = next((i for i in range(start + 1, len(lines)) if STEP_LINE.match(lines[i])),
               len(lines))
    while lines[end - 1].strip() == "":
        end -= 1
    return lines[start:end]


def bullet(item: list[str], contains: str) -> list[str]:
    """The top-level bullet of a numbered item that contains ``contains``."""
    starts = [i for i, line in enumerate(item) if line.startswith(BULLET)] + [len(item)]
    found = [item[a:b] for a, b in pairwise(starts)
             if contains in flat(item[a:b])]
    if len(found) != 1:
        raise AssertionError(f"bullet containing {contains!r} found {len(found)} times")
    region = found[0]
    while region[-1].strip() == "":
        region = region[:-1]
    return region


def after(region: list[str], anchor: str) -> list[str]:
    """The tail of a region from the line holding ``anchor`` on."""
    hits = [i for i, line in enumerate(region) if anchor in line]
    if len(hits) != 1:
        raise AssertionError(f"anchor {anchor!r} found {len(hits)} times")
    return region[hits[0]:]


def flat(region: list[str]) -> str:
    """The region's prose with hand-wrapping undone."""
    return re.sub(r"\s+", " ", " ".join(region)).strip()


def regions() -> dict[str, list[str]]:
    dispatch, orch = lines_of("DISPATCH.md"), lines_of("ORCHESTRATOR.md")
    active = numbered_item(orch, "2. **Active**")
    failure = bullet(active, "Executor died without moving state")
    return {
        "DISPATCH step 5": numbered_item(dispatch, "5. **Fresh base, always**"),
        "DISPATCH step 7": numbered_item(dispatch, "7. Create an isolated worktree"),
        "ORCHESTRATOR Active": active,
        "ORCHESTRATOR phase table": [line for line in bullet(active, "**Phase** (DISPATCH")
                                     if line.lstrip().startswith("|")],
        "ORCHESTRATOR ready-to-review bullet": bullet(active, "Executor wrote `READY.md`"),
        "ORCHESTRATOR dispatch-failure bullet": failure,
        "ORCHESTRATOR dispatch-failure stall text": after(failure, "alive but stalled"),
        "ORCHESTRATOR budget bullet": bullet(active, '("budget exceeded: <id>")'),
    }


def write_evidence(found: dict[str, list[str]]) -> None:
    out = os.environ.get("DRYDOCK_EVIDENCE_DIR")
    if not out:
        return
    with open(Path(out) / "contract-regions.txt", "w") as fh:
        for name, region in found.items():
            fh.write(f"{name}: {len(region)} lines\n  first: {region[0]}\n"
                     f"  last:  {region[-1]}\n")


class ExtractionTest(unittest.TestCase):
    """Prove every region before any assertion leans on it."""

    @classmethod
    def setUpClass(cls):
        cls.r = regions()
        write_evidence(cls.r)

    def test_numbered_regions_stop_at_their_boundary(self):
        dispatch, orch = lines_of("DISPATCH.md"), lines_of("ORCHESTRATOR.md")
        for name, text, nxt in (("DISPATCH step 5", dispatch, "## Execute"),
                                ("DISPATCH step 7", dispatch, "8. Start the executor"),
                                ("ORCHESTRATOR Active", orch, "3. **Housekeeping**")):
            region = self.r[name]
            start = next(i for i, line in enumerate(text) if line == region[0])
            following = [line for line in text[start + len(region):] if line.strip()]
            self.assertTrue(following[0].startswith(nxt), (name, following[0]))
            self.assertGreater(len(region), 10, name)

    def test_bullets_are_single_bullets(self):
        for name in ("ORCHESTRATOR ready-to-review bullet",
                     "ORCHESTRATOR dispatch-failure bullet", "ORCHESTRATOR budget bullet"):
            region = self.r[name]
            self.assertTrue(region[0].startswith(BULLET), name)
            self.assertEqual([line for line in region if line.startswith(BULLET)], [region[0]])

    def test_phase_table_has_rows(self):
        self.assertGreater(len(state_names(self.r["ORCHESTRATOR phase table"])), 3)


def state_names(table: list[str]) -> list[str]:
    """The State column of plan-phase's table, read from the contract."""
    cells = [row.strip().strip("|").split("|")[0].strip() for row in table]
    return [c for c in cells if c and c != "State" and not set(c) <= set("-: ")]


class ContractLivenessTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = {name: flat(region) for name, region in regions().items()}
        cls.table = regions()["ORCHESTRATOR phase table"]

    def assertSays(self, region: str, *phrases: str):
        for phrase in phrases:
            self.assertIn(phrase, self.r[region], f"{region} lacks {phrase!r}")

    def test_step_5_is_symmetric_and_keeps_the_ordering_guard(self):
        self.assertSays("DISPATCH step 5", "rev-list --left-right --count",
                        "<branch>...origin/<branch>", "exits 128", "**ahead of its remote**",
                        "**behind its remote**", "git log --oneline origin/<branch>..<branch>",
                        "git log --oneline <branch>..origin/<branch>", "preflight_sha")
        self.assertNotIn("rev-list --count <branch>..origin/<branch>", self.r["DISPATCH step 5"])

    def test_step_7_carries_the_stamp_and_the_base_proof(self):
        self.assertSays("DISPATCH step 7", ".progress", "write-then-rename", "last_progress:",
                        "hold:", "preflight_sha", "exactly one live writer",
                        "ls-remote origin refs/heads/<branch>", "needs no fetch",
                        "A second mismatch in the same dispatch escalates without re-validating",
                        "For a spec without `branch:`, first re-point the branch just cut at "
                        "the fresh `preflight_sha`", "A chained branch is never re-pointed",
                        "stamps on progress, not on a clock", "**working** time")

    def test_orchestrator_threshold_and_corroboration(self):
        budget = "ORCHESTRATOR budget bullet"
        self.assertSays(budget, "within 10 minutes", "at least 30 seconds apart",
                        "RUN.md's size and mtime", "the session transcript",
                        "newest `*.jsonl` found **recursively** under",
                        "`~/.claude/projects/<worktree-slug>/`",
                        "**The session transcript includes its subagent transcripts.**",
                        "`<worktree-slug>/<session-id>/subagents/agent-*.jsonl`",
                        "every `/` and `.` replaced by `-`",
                        "never stopped on age alone", "fall back to RUN.md's mtime",
                        "every tick for every item in those states**")
        self.assertEqual(rules.STALL_THRESHOLD.total_seconds(), 600)
        self.assertEqual(rules.CORROBORATION_GAP.total_seconds(), 30)

    def test_unsampleable_is_indeterminate_and_dead_is_listagents(self):
        self.assertSays("ORCHESTRATOR budget bullet", "cannot be sampled is not evidence",
                        "no `*.jsonl` at any depth",
                        "a sampler whose output is empty or failed",
                        "Two empty samples are never \"unchanged\"",
                        "**indeterminate, never stalled**", "ListAgents",
                        "`claude agents`", "executor defect", "the one relaunch")

    def test_no_process_sampling_anywhere_in_the_rule(self):
        # Nothing records a pid, and process CPU misclassifies both ways.
        for region in ("ORCHESTRATOR budget bullet", "ORCHESTRATOR dispatch-failure bullet",
                       "ORCHESTRATOR ready-to-review bullet"):
            for banned in ("ps -o", "pgrep", "<pid>", "lsof"):
                self.assertNotIn(banned, self.r[region], f"{region} samples a process")

    def test_finished_work_exclusions_precede_the_rescue(self):
        # Both arms must head the handler, open QUESTION first, before any rescue.
        text = self.r["ORCHESTRATOR dispatch-failure stall text"]
        head = text.index("**Finished work is excluded first, and the exclusion covers "
                          "this whole handler**")
        question = text.index("**(i) An open `QUESTION.md`**")
        ready = text.index("**(ii) `READY.md`**")
        self.assertLess(head, question)
        self.assertLess(question, ready)
        for guard in (question, ready):
            self.assertLess(guard, text.index("rescue/<id>-wip"))
            self.assertLess(guard, text.index("reset the item's branch"))
        self.assertSays("ORCHESTRATOR dispatch-failure stall text",
                        "its last `##` heading does not begin with `## Resolution`",
                        "complete the move to `blocked/`",
                        "notify with the unblock command",
                        "paths appended to that QUESTION.md as a note",
                        "nothing is stashed or committed",
                        "whatever the state of the tree or of `READY.md`",
                        "is history carried in from an earlier unblock",
                        "QUESTION.md naming the dirty paths",
                        "never rescue, reset or relaunch it")

    def test_orchestrator_status_string_is_not_evidence(self):
        self.assertSays("ORCHESTRATOR budget bullet", "status string",
                        "**not evidence either way**", "keep-awake guard")

    def test_orchestrator_ready_window(self):
        self.assertSays("ORCHESTRATOR ready-to-review bullet", "5-minute window",
                        "status --porcelain` empty", "does not wait for the stall handling",
                        "never rescues, resets or relaunches an item whose `READY.md` is present",
                        "`READY.md` beside an open `QUESTION.md`",
                        "the escalation wins: do not dispatch the reviewer")
        self.assertEqual(rules.READY_WINDOW.total_seconds(), 300)

    def test_orchestrator_rescue_and_the_two_clocks(self):
        self.assertSays("ORCHESTRATOR dispatch-failure stall text", "rescue/<id>-wip",
                        "**elapsed** and **stalled** minutes as separate numbers",
                        "never force-push", "Re-run every acceptance criterion")

    def test_added_text_cites_the_state_list_without_enumerating_it(self):
        names = state_names(self.table)
        self.assertSays("ORCHESTRATOR budget bullet", "the dead-executor check above is scoped to")
        for region in ("ORCHESTRATOR budget bullet", "ORCHESTRATOR ready-to-review bullet",
                       "ORCHESTRATOR dispatch-failure stall text"):
            for name in names:
                self.assertNotRegex(self.r[region].lower(), rf"\b{re.escape(name.lower())}\b",
                                    f"{region} names the state {name!r}")


if __name__ == "__main__":
    unittest.main()
