# Spec: [SHORT TITLE]

<!--
  The unit of work in drydock. Everything in frontmatter is machine-read by
  the dispatcher; everything in the body is for the executing agent.

  Convention: [NEEDS CLARIFICATION: ...] markers flag gaps — never invent an
  answer to close one. Any marker still present at dispatch time blocks the
  spec into specs/blocked/ instead of executing it.

  A filled-in example lives in examples/example-spec.md.
-->

```yaml
id: YYYY-MM-DD-short-slug        # also the directory name under specs/
track: code                      # code | report (see the routing table in
                                 # contracts/ORCHESTRATOR.md; add your own)
target_repo: ~/code/your-repo    # repo the execution worktree opens on
                                 # ("none" for pure-report work)
deliverable: pr                  # pr | report | dashboard
created: YYYY-MM-DD
status: inbox                    # inbox -> active -> delivered | blocked -> archive
depends_on: []                   # spec ids that must have shipped (deliverables/
                                 # or archive/) before this one is dispatch-eligible
budget:
  max_agents: 4                  # hard cap on concurrent subagents
  max_wall_clock: 2h             # execution aborts and escalates past this
  max_criteria_retries: 2        # failed-criteria fix attempts before escalating
```

## Context

[3–6 sentences: what problem, why now. Pointers to files, tables, dashboards,
prior decisions — paths and links, not prose reconstructions. The executor
starts cold in a fresh worktree and knows only what is written here.]

## Goal

[One paragraph. What exists when this is done that does not exist now.]

## Non-goals

- [Explicit exclusions — what the executor must NOT expand into.]

## Constraints & blast radius

- **May touch**: [dirs/files/services the execution is allowed to modify]
- **Must not touch**: [everything else that could plausibly be tempting]
- [Other constraints: style, dependencies, backwards compatibility, read-only surfaces]

## Requirements

- **FR-001**: [specific, testable capability]
- **FR-002**: [...]
- **FR-00N**: [NEEDS CLARIFICATION: unresolved question — blocks dispatch until answered or explicitly delegated]

## Acceptance criteria (executable)

<!--
  THE GATE. Each criterion is a command the executor runs plus the result that
  counts as pass. A spec whose criteria cannot be run without the human is not
  drydock-eligible — it stays interactive. "Tests pass" alone is rarely enough;
  criteria should encode the *intent* (behavior, metric, threshold), not just
  compilation health. Scope build/test targets to the diff — a repo-wide green
  check you don't control makes the criterion unsatisfiable on a bad day.
-->

| # | Check | Command | Pass condition |
|---|-------|---------|----------------|
| AC-1 | Build | `<scoped build command>` | exit 0 |
| AC-2 | Tests | `<scoped test command>` | all pass, includes new tests for FR-001 |
| AC-3 | [Behavior/metric] | [exact command / query] | [expected output or threshold] |

## Escalation conditions

<!-- When the executor STOPS and files the spec into specs/blocked/ with a
     concrete question, instead of guessing. Defaults below always apply. -->

- Any unresolved `[NEEDS CLARIFICATION]` at execution time.
- Any acceptance criterion still failing after `max_criteria_retries`.
- The correct change appears to require touching the **must not touch** list.
- Budget exceeded.
- [Spec-specific conditions.]

## Assumptions

- [Defaults chosen where the discussion didn't specify. The reviewer sees these first.]
