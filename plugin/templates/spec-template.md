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
# branch: their/feature-branch   # optional: chain onto an EXISTING branch —
                                 # the worktree is created on it instead of on
                                 # a new <namespace>/drydock-<id> cut off the
                                 # default branch. What is never legal is
                                 # naming the default branch itself here:
                                 # that is committing straight to it, not
                                 # chaining onto work in flight.
                                 # Dispatch proves it is not behind its remote.
# pr_url: <existing PR url>      # optional: push into this OPEN pull request at
                                 # ship instead of opening a new draft one, and
                                 # replace its title and body with the reviewed
                                 # prepared text (a full replacement).
                                 # Requires branch:, which must be its head ref.
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
- **State predicates**: [for every requirement or criterion that branches on
  a file's presence, absence or content: the file, who writes it (a drydock
  step, a sibling spec, the harness, a human) and when. For every git ref
  read: which one (checkout `HEAD`, `origin/<default>`, `origin/<branch>`,
  `<base_sha>`) and why that one. For state something other than drydock
  writes: where it actually lands, not where it would be convenient. Write
  `none` if nothing branches on disk or git state.]
- [Other constraints: style, dependencies, backwards compatibility, read-only surfaces]

## Requirements

<!--
  Text a requirement freezes word-for-word lives in a fenced block whose
  info string is verbatim:<name>, and the requirement names that block.
  Frozen text makes no countable or exhaustiveness claim about the run
  producing it: no tally of commits, findings, rounds, files or sites, no
  distance in lines, no "only", "never", "no other" or "the last". A repair
  the spec itself mandates can falsify a tally, and frozen text cannot be
  corrected without a human. Describe the register, not the tally. At least
  one acceptance criterion names each block.
-->

- **FR-001**: [specific, testable capability]
- **FR-002**: [...]
- **FR-00N**: [NEEDS CLARIFICATION: unresolved question — blocks dispatch until answered or explicitly delegated]

## Acceptance criteria (executable)

<!--
  THE GATE. Each criterion is a command the executor runs plus the result that
  counts as pass, and it runs before any pull request exists. A criterion that
  needs a pull request, a merge, a deploy or a human belongs in Ship criteria
  below; a spec whose every criterion needs the human is not drydock-eligible
  — it stays interactive. "Tests pass" alone is rarely enough; criteria should
  encode the *intent* (behavior, metric, threshold), not just compilation
  health. Scope build/test targets to the diff — a repo-wide green check you
  don't control makes the criterion unsatisfiable on a bad day.

  A check that cannot fail is not a check. It has three faces:

  (a) Read the region under test, never the whole file. A criterion whose
      command reads a drydock artifact (READY.md, RUN.md, DELIVERABLE.md,
      QUESTION.md, REVIEW*.md) scopes its read to that region, because the
      criterion's own report lands in the same file as its subject. An
      extraction is part of the criterion: assert its boundaries (line
      count, first line, last line) into evidence/ before trusting a grep
      over it. Report a finding by describing the offending phrase, never
      by reproducing it, in any file a criterion reads.
  (b) Never reproduce the token a check counts. Assemble it at run time
      (printf) rather than writing it into the table or the prose, or the
      check counts its own description.
  (c) Tell "no sample" from "unchanged". A criterion comparing two samples
      first asserts each one exists; an absent or empty sample is
      indeterminate, never equal, pass, clean or stalled. A criterion
      asserting absence carries a positive control in the same row, one
      pattern that must match, so a broken matcher cannot read as a clean
      result. A command whose failure mode is empty output has its exit
      status checked (echo "exit=$?"), not only its stdout.

  The Command cell holds at least one backtick code span. speccheck.py
  enforces these rules by id; a waivable one is silenced by an HTML comment
  directly beneath the table reading
  speccheck-ok: <row-id> <RULE-ID> — <reason>
-->

| # | Check | Command | Pass condition |
|---|-------|---------|----------------|
| AC-1 | Build | `<scoped build command>` | exit 0 |
| AC-2 | Tests | `<scoped test command>` | all pass, includes new tests for FR-001 |
| AC-3 | [Behavior/metric] | `<exact command / query>` | [expected output or threshold] |

## Ship criteria (owned by the ship step — NOT the executor)

<!--
  Checks that presuppose a pull request, a merge, a deploy or a human. The
  executor stops before any of those exist, so it never evaluates this table:
  it carries the table into READY.md as declared, for the ship step and the
  human. Rows are numbered SC-n. Delete the placeholder row if nothing here
  needs one.
-->

| # | Check | Command | Pass condition |
|---|-------|---------|----------------|
| SC-1 | [CI green] | [the required checks on the pull request] | [all green] |

## Escalation conditions

<!-- When the executor STOPS and files the spec into specs/blocked/ with a
     concrete question, instead of guessing. Defaults below always apply. -->

- Any unresolved clarification marker (the bracketed form described at the
  top of this file: the two words, a colon, a body) at execution time.
- Any acceptance criterion still failing after `max_criteria_retries`.
- The correct change appears to require touching the **must not touch** list.
- Budget exceeded.
- [Spec-specific conditions.]

## Assumptions

- [Defaults chosen where the discussion didn't specify. The reviewer sees these first.]
