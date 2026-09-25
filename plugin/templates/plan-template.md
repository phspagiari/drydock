# Plan: [SPEC TITLE]

<!--
  The handoff between the plan phase and the implement phase (DISPATCH
  step 8). The plan executor writes this file into
  <STATE_HOME>/specs/active/<id>/PLAN.md and exits; the gate reads it; a
  fresh implement executor reads it with SPEC.md and nothing of the plan
  session's transcript. Anything the implement phase needs to know goes here
  or it is lost.

  Write it as the plan session's LAST act, or to a temporary name renamed
  into place: "PLAN.md present" is what tells the orchestrator the plan is
  finished, so it must never observe a half-written one.

  Clarification markers use the spec template's syntax and mean the same
  thing: a gap the human must close — never invent an answer to close one.
  An unresolved marker anywhere in this file blocks the item into
  specs/blocked/ with QUESTION.md. (Deleting this comment is fine; the
  sections below are what the gate checks.)
-->

## Approach

[One paragraph. How the spec's goal gets built in THIS repo — which
mechanism, which layer, which existing helper — and why that one.]

## Files

<!--
  Every path the implement phase may touch. Must be a subset of the spec's
  "May touch"; the gate flags anything outside it. Globs are fine.
-->

- `[path/to/file]`

## Tasks

<!--
  Mandatory. The implement executor works these rows in After-order, runs
  each row's Verify, and ticks the row in RUN.md with the path of the verify
  output before starting the next. After an unblock, a fresh executor
  resumes from the first unticked row.

  - #:      T1, T2, … — stable ids; RUN.md ticks cite them.
  - Task:   one change, naming the spec requirement(s) it serves (FR-00N).
            Every FR in the spec maps to at least one row.
  - Files:  the subset of ## Files this row touches.
  - Verify: a command that runs from the worktree and proves the row —
            not "looks right", not "review the diff".
  - After:  ids this row depends on, or — for none.
-->

| # | Task | Files | Verify | After |
|---|------|-------|--------|-------|
| T1 | [FR-001: …] | `[path]` | `[command]` | — |
| T2 | [FR-002: …] | `[path]` | `[command]` | T1 |

## Risks

[What reading the repo turned up that the spec did not anticipate: a
contract the spec's mechanism collides with, a caller it did not list, a
criterion that cannot pass as written. A risk that needs the human's call is
raised here as a clarification marker, and blocks the item.]

## Assumptions

- [Defaults the plan chose where the spec was silent. The gate reads these
  first.]
