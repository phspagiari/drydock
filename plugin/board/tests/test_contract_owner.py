"""The contracts route notifications and unblocks the way ``queue_rules.py route`` does.

    python3 -m unittest discover plugin/board/tests

A spec's ``owner:`` changes who hears about it and who may decide its
unblock. The routing is written once, as the *Notifications* bullet of
ORCHESTRATOR.md's Hard limits; every event site names its token and leans on
it, DISPATCH step 13 defers to it, and the spec skill's Unblock mode records
who decided. Each region is extracted by a content anchor and proved
non-empty before anything is judged on it, and every assertion names the
fact it pins, so a deleted sentence fails here on that name.
"""

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import liveness_rules as rules  # noqa: E402

PLUGIN = Path(__file__).resolve().parent.parent.parent
TOKENS = {"BLOCKED": "blocked", "DELIVERED": "delivered",
          "FAILED": "dispatch failure", "BUDGET": "budget exceeded"}


def read(rel: str) -> str:
    return (PLUGIN / rel).read_text()


def flat(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def h2_section(text: str, prefix: str) -> str:
    m = re.search(rf"^{re.escape(prefix)}.*?(?=^## |\Z)", text, re.M | re.S)
    return m.group(0) if m else ""


def top_bullet(section: str, anchor: str) -> str:
    """The section's one top-level ``- `` bullet starting with ``anchor``."""
    found = [b for b in re.split(r"^- ", section, flags=re.M)[1:] if b.startswith(anchor)]
    return found[0] if len(found) == 1 else ""


def sub_items(bullet: str) -> list[str]:
    """The bullet's nested list items (``  1. `` or ``  - ``), whitespace folded."""
    return [flat(i) for i in re.split(r"^  (?:\d+\.|-) ", bullet, flags=re.M)[1:]]


def routing_block() -> str:
    return top_bullet(h2_section(read("contracts/ORCHESTRATOR.md"), "## Hard limits"),
                      "**Notifications**")


class RoutingBlockTest(unittest.TestCase):
    """FR-005: the routing, written once in ORCHESTRATOR.md's Hard limits."""

    def setUp(self):
        self.block = routing_block()
        self.assertTrue(self.block.strip(), "no Notifications bullet in Hard limits")
        self.flat = flat(self.block)
        self.items = sub_items(self.block)
        self.assertGreaterEqual(len(self.items), 4, "routing block lost its steps")

    def one(self, keep, what: str) -> str:
        """The single routing step ``keep`` selects; a FAIL, never an ERROR, otherwise."""
        found = [i for i in self.items if keep(i)]
        self.assertEqual(len(found), 1, f"expected one {what} in the routing block")
        return found[0]

    def test_routing_runs_queue_rules_route(self):
        self.assertIn("python3 <PLUGIN_HOME>/board/queue_rules.py route", self.flat)

    def test_routing_maps_all_four_events_to_tokens(self):
        for token, event in TOKENS.items():
            with self.subTest(token=token):
                self.assertRegex(self.flat, rf"{re.escape(event)}[^→]{{0,40}}→ `{token}`")

    def test_routing_sends_a_live_owner_a_message_and_no_push(self):
        owner = self.one(lambda i: i.startswith("`owner<TAB><name>`"), "owner step")
        for phrase in ("`ListAgents`", "`SendMessage` to `<name>`",
                       "`<TOKEN> <id> — <gist>`", "absolute path of the item's directory",
                       "No `PushNotification` is sent"):
            self.assertIn(phrase, owner, phrase)

    def test_routing_falls_back_to_push_notification(self):
        fallback = [i for i in self.items if "[Cross-session delivery notice]" in i]
        self.assertEqual(len(fallback), 1, "no single fallback step for an unreachable owner")
        for phrase in ("not listed", "send error", "held, refused or expired",
                       "`PushNotification`",
                       "`owner <name> unreachable (<reason>); notified human`"):
            self.assertIn(phrase, fallback[0], phrase)

    def test_a_send_with_no_inbox_for_notices_is_not_confirmed(self):
        # Beyond the spec's first definition of a confirmed delivery, by amendment.
        fallback = self.one(lambda i: "[Cross-session delivery notice]" in i, "fallback step")
        for phrase in ("A send is delivered only when it succeeded and no such notice "
                       "arrived before the tick ends",
                       "no inbox for a notice to reach is not confirmed",
                       "`no delivery notices`"):
            self.assertIn(phrase, fallback, phrase)

    def test_owner_must_be_listed_by_exact_name_and_route_runs_each_event(self):
        owner = self.one(lambda i: i.startswith("`owner<TAB><name>`"), "owner step")
        self.assertIn("a `ListAgents` row whose name is exactly `<name>`", owner)
        run = self.one(lambda i: i.startswith("Run `python3"), "route step")
        self.assertIn("Run it at every event", run)

    def test_every_site_names_a_token_and_borrows_text_when_it_quotes_none(self):
        # Assembled at run time, so the retired claim never appears in the diff.
        self.assertNotIn("names its token " + "and its text", self.flat)
        self.assertIn("A site that quotes no text of its own uses the text another "
                      "site quotes for the same token", self.flat)

    def test_untokened_notifications_stay_with_the_human(self):
        m = re.search(r"A notification these contracts ask for without a token.*?"
                      r"whatever the spec's `owner`\.", self.flat)
        self.assertTrue(m, "no rule for notifications without a token")
        for phrase in ("`eligible`", '"comments addressed"', "is not routed",
                       "to the human by the `PushNotification` tool"):
            self.assertIn(phrase, m.group(0), phrase)

    def test_routing_falls_back_when_route_fails(self):
        failed = [i for i in self.items if "non-zero exit" in i]
        self.assertEqual(len(failed), 1)
        self.assertIn("`PushNotification`", failed[0])
        self.assertIn("tick-report line", failed[0])

    def test_human_route_keeps_todays_push(self):
        human = self.one(lambda i: i.startswith("`human`"), "human step")
        self.assertIn("`PushNotification`", human)

    def test_tick_report_still_carries_the_unblock_command(self):
        self.assertIn("ready-to-paste unblock command", self.flat)

    def test_never_for_dispatch_starts_or_progress(self):
        self.assertIn("never for dispatch starts or progress", self.flat)

    def test_human_in_other_contracts_reads_as_the_unblock_decider(self):
        # DISPATCH steps 10 and 12, REVIEWER.md and the FAQ say "the human";
        # this rule keeps them true when a spec names an owner, without
        # taking the human out of the fallback.
        for phrase in ('say a blocked item reaches "the human"', '"the human decides"',
                       "unblock decider", "`owner` session when one is set and reachable",
                       "the human otherwise",
                       "The human is still notified by the steps above whenever "
                       "delivery to the owner is not confirmed"):
            self.assertIn(phrase, self.flat, phrase)

    def test_routing_names_a_session_never_a_role(self):
        # Drydock knows "a session name" and "human", nothing more.
        for word in ("conductor", "lead", "charter"):
            self.assertNotIn(word, self.flat.lower())


class EventSitesTest(unittest.TestCase):
    """FR-005: every event site in ORCHESTRATOR.md names its token."""

    SITES = {'"spec blocked: <id> — <gist>"': "BLOCKED",
             '"deliverable ready: <id> — reviewed, <link>"': "DELIVERED",
             '"dispatch failure: <id>"': "FAILED",
             '"budget exceeded: <id>"': "BUDGET"}

    def setUp(self):
        text = read("contracts/ORCHESTRATOR.md")
        self.flat = flat(text[:text.index("## Hard limits")])

    def test_every_quoted_event_text_carries_its_token(self):
        for quoted, token in self.SITES.items():
            with self.subTest(token=token):
                starts = [m.start() for m in re.finditer(re.escape(quoted), self.flat)]
                self.assertTrue(starts, f"no site quotes {quoted}")
                for at in starts:
                    self.assertIn(f"`{token}`", self.flat[max(0, at - 40):at + len(quoted) + 40],
                                  f"a site quoting {quoted} does not name `{token}`")

    def test_every_notify_names_a_token(self):
        # A `notify` with no token is a site the routing cannot name.
        for m in re.finditer(r"\bnotify\b", self.flat):
            window = self.flat[m.start():m.start() + 110]
            if (window.startswith("notify per the Notifications policy")
                    or self.flat[:m.start()].endswith("Do not ")):
                continue
            with self.subTest(at=window[:60]):
                self.assertRegex(window, r"`(BLOCKED|DELIVERED|FAILED|BUDGET)`")


class DispatchStep13Test(unittest.TestCase):
    """FR-006: DISPATCH step 13 defers to the routing; a manual dispatch reports in-chat."""

    def test_step_13_defers_to_the_routing(self):
        text = read("contracts/DISPATCH.md")
        m = re.search(r"^13\. .*?(?=^## |^\d+\. )", text, re.M | re.S)
        self.assertTrue(m, "no step 13")
        step = flat(m.group(0))
        for phrase in ("Notifications policy", "`owner`", "`SendMessage`",
                       "`PushNotification`", "in-chat"):
            self.assertIn(phrase, step, phrase)


class PreflightBlocksOnOwnerTest(unittest.TestCase):
    """FR-004: whatever blocks on `marker:` / `chain:` lines blocks on `owner:` too."""

    def test_every_check_consumer_names_owner_lines(self):
        dispatch = read("contracts/DISPATCH.md")
        step_1 = re.search(r"^1\. .*?(?=^2\. )", dispatch, re.M | re.S)
        sites = {
            "DISPATCH step 1": flat(step_1.group(0)) if step_1 else "",
            "ORCHESTRATOR preflight bullet": flat(top_bullet(
                re.sub(r"^   ", "", read("contracts/ORCHESTRATOR.md"), flags=re.M),
                "Run the DISPATCH preflight")),
            "dispatch skill step 2": flat(re.search(
                r"^2\. .*?(?=^3\. )", read("skills/dispatch/SKILL.md"), re.M | re.S).group(0)),
        }
        for name, site in sites.items():
            with self.subTest(site=name):
                self.assertIn("queue_rules.py check", site, f"{name} not extracted")
                self.assertIn("`owner:`", site)


class PermissionsTest(unittest.TestCase):
    """FR-007: an owner runs in the orchestrator's permission mode."""

    def test_permissions_name_the_owner_session_mode(self):
        section = flat(h2_section(read("contracts/ORCHESTRATOR.md"), "## Permissions"))
        self.assertTrue(section)
        for phrase in ("owner", "`<permission-mode>`", "held for", "falls back to the human",
                       "runs in the permission mode this loop's own session runs in",
                       "the config line sets the mode of the sessions this loop launches, "
                       "not of the loop"):
            self.assertIn(phrase, section, phrase)
        # The launch mode is not the owner's mode unless the loop runs in it.
        self.assertNotIn("session runs in `<permission-mode>` too", section)


class UnblockLoopTest(unittest.TestCase):
    """FR-008: the unblock decider, the resolved_by line, the Hard-limits wording."""

    def setUp(self):
        self.unblock = h2_section(read("skills/spec/SKILL.md"), "## Unblock mode")
        self.assertTrue(self.unblock.strip(), "no Unblock mode section")

    def test_unblock_step_names_resolved_by(self):
        step_4 = re.search(r"^4\. .*?(?=^5\. )", self.unblock, re.M | re.S)
        self.assertTrue(step_4, "no Unblock step 4")
        self.assertIn("`## Resolution (YYYY-MM-DD)`", step_4.group(0))
        self.assertIn("`resolved_by: <session-name | human>`", flat(step_4.group(0)))

    def test_owner_may_decide_and_otherwise_stays_blocked(self):
        text = flat(self.unblock)
        for phrase in ("the human, or", "`owner:`", "leaves the item in `blocked/`",
                       "outside drydock", "2. Discuss until the decider decides."):
            self.assertIn(phrase, text, phrase)
        self.assertNotIn("Discuss until the human decides", text)

    def test_hard_limits_names_the_unblock_loop(self):
        limits = flat(h2_section(read("contracts/ORCHESTRATOR.md"), "## Hard limits"))
        self.assertIn("specs change only via the unblock loop (the human, or the spec's "
                      "`owner` when set) and the human's fast rejection in the review pass",
                      limits)
        self.assertNotIn("human's review loop", limits)


class RetroCitationTest(unittest.TestCase):
    """FR-009: a mined resolution's citation names the session that decided."""

    def test_retro_cites_resolved_by(self):
        m = re.search(r"^  - `derived_from:` .*?(?=^  - `depends_on:`)",
                      read("skills/retro/SKILL.md"), re.M | re.S)
        self.assertTrue(m, "no derived_from: sub-bullet in the retro skill")
        bullet = flat(m.group(0))
        self.assertIn("(QUESTION.md Resolution, resolved_by: lead-a)", bullet)
        self.assertIn("reads as `human`", bullet)


QUESTION = """# QUESTION — 2026-11-09-x

## Q1 — which store?

Postgres or the existing queue table?
"""


class ResolvedByLivenessTest(unittest.TestCase):
    """FR-011: a Resolution that opens with resolved_by: still closes the question."""

    def test_resolution_starting_with_resolved_by_is_resolved(self):
        resolved = QUESTION + ("\n## Resolution (2026-11-09)\n\nresolved_by: lead-a\n\n"
                               "Postgres. The queue table has no unique index.\n")
        self.assertTrue(rules.question_open(QUESTION))
        self.assertFalse(rules.question_open(resolved))

    def test_resolved_by_human_and_absent_are_resolved_alike(self):
        for line in ("resolved_by: human\n\n", ""):
            with self.subTest(line=line):
                text = QUESTION + f"\n## Resolution (2026-11-09)\n\n{line}Postgres.\n"
                self.assertFalse(rules.question_open(text))


if __name__ == "__main__":
    unittest.main()
