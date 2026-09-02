---
name: retro
description: Self-improvement pass over drydock's own history — mine unblock discussions, reviewer findings, and rejection routings into priors and contract amendments. Use when asked "/drydock:retro", "run a drydock retro", "what has drydock learned", or after a run that required several human interventions. The orchestrator dispatches "/drydock:retro <id>" automatically after every ship.
---

# /drydock:retro — the system learns from its own discussions

> **DRYDOCK_HOME**: resolve once per invocation as `realpath <this skill's
> base dir>/../..` (the repo root containing `plugin/`). Every path below is
> relative to it.

## Two modes

- **Per-item, autonomous** (`/drydock:retro <id>` — dispatched by the
  orchestrator after every ship): corpus = that item's directory and git
  history only (QUESTION.md resolutions, REVIEW-r*.md rounds, RUN.md, spec
  amendments). Priors append and commit as usual; **rule proposals go to
  `contracts/PROPOSALS.md`** (proposal, motivating evidence, suggested diff)
  — NEVER applied autonomously. Does not move the retro-cursor. No findings →
  exit silently; do not force a lesson out of a clean run.
- **Full sweep, interactive** (bare `/drydock:retro`, run with the human):
  everything since the retro-cursor, as below — and also walk PROPOSALS.md
  together: approved proposals become contract amendments, declined ones are
  recorded and removed.

## Mine

1. Read the `retro-cursor` commit from `contracts/PRIORS.md`. Everything
   between it and HEAD is this retro's corpus:
   - `QUESTION.md` files + the SPEC.md amendments that answered them (what
     did specs chronically under-specify? what was decided?)
   - `REVIEW.md` / `REVIEW-r*.md` (what does the reviewer keep finding? what
     needed 2 rounds?)
   - `REJECTION.md` files and their fast/slow routing
   - RUN.md handoffs and escalation reports (what surprised executors?)
2. Look for **repetition and near-misses**, not one-offs: the same class of
   question asked twice, the same finding on two items, a rule that existed
   but was rationalized around.

## Distill — each lesson lands in exactly one tier

- **Prior** (advisory, repo- or domain-specific fact): append to
  `contracts/PRIORS.md` with the citing item id. Commit directly — priors are
  knowledge, not policy.
- **Rule** (process failure a prior can't fix): draft the amendment to
  `contracts/DISPATCH.md` / `REVIEWER.md` / `ORCHESTRATOR.md` /
  `templates/spec-template.md`, show the diff and the incident that motivates
  it, and apply **only on the human's approval** — contract changes are
  theirs, always. In per-item mode, the proposal goes to PROPOSALS.md and
  stops there.
- **Skill defect** (a plugin skill produced the failure): fold the correction
  into that skill, with the evidence, using whatever skill-improvement pass
  your setup has.

Refuse to distill a lesson with no citation, and prune any prior the corpus
shows to be wrong or obsolete (note why in the commit).

## Close

1. Update the `retro-cursor` line in `contracts/PRIORS.md` to HEAD; commit
   `retro: <n> priors, <m> rule proposals`.
2. Report: what was learned, what was proposed and approved/declined, and the
   one metric that matters — are human interventions per item trending down?

## Cadence

On demand, plus the automatic per-item pass after every ship. Propose a full
sweep whenever an item needed 2+ human interventions. If retros prove
valuable, schedule the mining half as a recurring autonomous run and keep only
rule-approval interactive.
