---
name: review
description: The drydock review pass — walk deliverables awaiting approval and blocked questions, one at a time, and apply the human's verdicts. Use when asked "/drydock:review", "review the queue", "morning pass", "what's waiting for me in drydock".
---

# /drydock:review — the review pass

> **PLUGIN_HOME**: resolve once per invocation as `realpath <this skill's
> base dir>/../..` (the plugin package root). **STATE_HOME**: `~/.drydock`,
> or `$DRYDOCK_STATE_HOME` if set — where the queue actually lives.

Walk `<STATE_HOME>/deliverables/` and `<STATE_HOME>/specs/blocked/`, oldest
first, blocked items before deliverables (they gate other work). One item at
a time; apply the verdict fully before showing the next.

**With an `<id>` argument** (`/drydock:review <id>`, typically launched from a
board card): review just that item — same presentation and verdicts, skip the
full walk, but still open with the stale-PR flags line. If your setup names
sessions, name this one `review-<id>`.

## Opening

Report the shape of the pass in one line: N blocked, M ready, any open
entries in `<STATE_HOME>/PROPOSALS.md` (rule changes the per-item retros
queued — offer to walk them at the end of the pass), plus any **stale-PR
flags** —
archived or delivered PRs still open with merge conflicts or unmerged for
more than 5 days (check each recorded `pr_url` via `gh pr view --json
state,mergeable,updatedAt`; never scan the target repo's PR list).

## Per blocked item

Hand off to `/drydock:spec unblock <id>` (that skill owns the flow). After it
re-queues, offer immediate `/drydock:dispatch <id>`.

## Per deliverable

1. Present: title, what was built (from `DELIVERABLE.md`), the acceptance
   criteria table with evidence paths, **assumptions first-class** (the
   reviewer-should-look-here list), PR link + live PR state — and the
   **adversarial review verdict** from `REVIEW.md` (per
   `<PLUGIN_HOME>/contracts/REVIEWER.md`). Deliverables only exist post-`ship`
   — the PR
   arrived already reviewed and fixed in-branch — so present what the
   reviewer tried and couldn't break, plus how many fix rounds it took. A
   deliverable WITHOUT `REVIEW.md` predates the reviewer stage or bypassed
   it — flag that loudly and review it yourself with extra suspicion. Do not
   paste whole diffs; the PR is where the diff gets reviewed.
2. If the item carries `COMMENTS-r*.md` with drafted replies not yet posted,
   present them — the human posts each (verbatim or rewritten) or discards
   it; executors never speak on the PR.
3. Take the verdict:
   - **Approve** → for `pr` deliverables: `gh pr ready <url>` (draft → ready
     for the team's normal review), then move `<STATE_HOME>/deliverables/<id>/`
     → `<STATE_HOME>/archive/<id>/`, commit `approve: <id>` (in `<STATE_HOME>`,
     never pushed). For reports: publish per the spec's stated destination,
     then archive.
   - **Reject** → require the routing, never accept a bare no:
     - *fast* (spec was wrong/incomplete): capture the reason in
       `REJECTION.md` (`loop: fast`), amend `SPEC.md` together now, move back
       to `<STATE_HOME>/specs/inbox/<id>/`, commit `reject-fast: <id>`.
     - *slow* (execution/skill was wrong): `REJECTION.md` (`loop: slow`), fold
       the correction into the skill that produced the failure — with the
       rejection as the evidence — then re-queue to inbox, commit
       `reject-slow: <id>`.
   - **Skip** → leave in place, note it, move on.
4. Close the pass with a one-line summary: approved / rejected(fast/slow) /
   answered / skipped, and what the orchestrator will pick up next tick.

## Rules

- Approve mutates the target repo's PR state (draft→ready) — apply it only on
  an explicit per-item verdict, never inferred, never batched.
- An unrouted rejection teaches the system nothing; refuse to archive one.
- Merged PRs found during the stale-check → move their items to
  `<STATE_HOME>/archive/` automatically and mention it (merge was the
  approval's completion).
