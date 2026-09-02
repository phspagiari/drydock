---
name: spec
description: Converge the current interactive session into a drydock spec instead of building mid-analysis. Use when asked "/drydock:spec", "write the spec", "spec this", "send this to drydock", or when a work discussion has converged and the next step would otherwise be building the thing in-session. Writes a dispatchable SPEC.md into the drydock inbox. Also handles unblocking: "/drydock:spec unblock <id>", "unblock <id>", "answer the drydock question" resolves a spec in specs/blocked/ and re-queues it.
---

# /drydock:spec — session exit through the queue

> **DRYDOCK_HOME**: resolve once per invocation as `realpath <this skill's
> base dir>/../..` (the repo root containing `plugin/`). Every path below is
> relative to it.

The session's deliverable is a **spec**, not the work itself. This skill ends
the discussion phase by writing `specs/inbox/<id>/SPEC.md` from
`templates/spec-template.md`.

## Hard rules

- **No building during analysis.** Investigation is read-only: read code, run
  queries, check dashboards. If artifacts were already half-built this
  session, say so — the human decides whether they seed the spec or get
  discarded.
- **Never invent an answer to close a gap.** An unresolved question becomes a
  `[NEEDS CLARIFICATION: …]` marker — but first ask now, in-session, while
  context is hot. Markers left in the spec block dispatch.
- **The eligibility test is the acceptance criteria.** If you cannot write
  every criterion as a command + pass condition runnable without the human,
  say this work is not drydock-eligible yet and name the verifier that is
  missing. Do not write a spec with vibes-based criteria.

## Procedure

1. Re-read the session and draft, in order: Goal, Non-goals, Constraints &
   blast radius, Requirements, Acceptance criteria, Escalation additions,
   Assumptions. Pull Context pointers as paths/links, not prose.
2. Show the two sections that gate everything — **Acceptance criteria** and
   **Assumptions** — in chat for confirmation before writing the file. (The
   rest is reviewed in the file itself.)
3. Pick `id` = `YYYY-MM-DD-short-slug`. Fill frontmatter: `track`,
   `target_repo`, `deliverable`, `budget` (defaults: 4 agents / 2h / 2
   retries — scale down for small work, never up without asking), and
   `depends_on` — if this work builds on another spec's outcome, list that
   id; the orchestrator won't dispatch it until the dependency has shipped.
   Ask when ordering seems to matter and nobody has said.
4. Write `specs/inbox/<id>/SPEC.md`. Commit the drydock repo: `spec: <id>`.
5. Report: spec id, dispatch state (dispatchable, or blocked on N
   clarifications), and the next action — the orchestrator picks it up on its
   next tick, or `/drydock:dispatch <id>` runs it now.

## Unblock mode (`/drydock:spec unblock <id>`)

Escalations are answered here — never in the orchestrator session (keep the
loop thin) and never by resurrecting the executor.

1. Read `specs/blocked/<id>/QUESTION.md` and its `SPEC.md`. Present the
   decision: the question, the options, what was ruled out. If QUESTION.md is
   not self-contained enough to decide from, flag it — that is an
   executor-quality defect for the slow loop, in addition to answering.
2. Discuss until the human decides. A simple call is one exchange; if the
   question reveals the spec itself was wrong, treat it as a mini spec
   session and amend properly (requirements, criteria, budget — whatever the
   answer implies), not just the one marker.
3. Write the resolution INTO `SPEC.md` (resolve the `[NEEDS CLARIFICATION]`
   or amend the sections), never as a side note. The next executor sees only
   the spec.
4. **Record the decision durably**: append a `## Resolution (YYYY-MM-DD)`
   section to `QUESTION.md` — the decision, the rationale in one or two
   sentences, and the options considered and rejected (with why). This is
   what `/drydock:retro` mines; a resolution that only lives in the spec diff
   loses the reasoning.
5. Move `specs/blocked/<id>/` → `specs/inbox/<id>/` (QUESTION.md stays in the
   directory as history), commit `unblock: <id>`. The orchestrator
   re-dispatches on its next tick — do not dispatch from here.

If your setup names sessions, name this one `unblock-<id>` — sessions
launched from a board card are otherwise indistinguishable in the session
list.

## Anti-patterns

- Writing the spec so tightly it's just the implementation in disguise —
  specify *what* and *how verified*, not every line of *how*.
- Padding criteria with a build command alone. Build and tests are the floor;
  at least one criterion must encode the feature's actual intent.
- Splitting one coherent piece of work into many specs to make the queue
  look busy. One spec = one reviewable deliverable.
