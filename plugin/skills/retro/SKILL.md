---
name: retro
description: Self-improvement pass over drydock's own history — mine unblock discussions, reviewer findings, and rejection routings into priors and contract amendments. Use when asked "/drydock:retro", "run a drydock retro", "what has drydock learned", or after a run that required several human interventions. The orchestrator dispatches "/drydock:retro <id>" automatically after every ship.
---

# /drydock:retro — the system learns from its own discussions

> **PLUGIN_HOME**: resolve once per invocation as `realpath <this skill's
> base dir>/../..` (the plugin package root). **STATE_HOME**: `~/.drydock`,
> or `$DRYDOCK_STATE_HOME` if set — where `PRIORS.md`, `PROPOSALS.md` and the
> queue actually live and get committed (locally; `<STATE_HOME>` has no
> remote). Contract amendments below still target files under
> `<PLUGIN_HOME>/contracts/` and `<PLUGIN_HOME>/templates/` — those are the
> plugin's own source and changing them is a normal edit to that clone/repo,
> outside the STATE_HOME/no-remote rule.

## Two modes

- **Per-item, autonomous** (`/drydock:retro <id>` — dispatched by the
  orchestrator after every ship): corpus = that item's directory and git
  history only (QUESTION.md resolutions, REVIEW-r*.md rounds, RUN.md, spec
  amendments). Priors append and commit as usual; **rule proposals go to
  `<STATE_HOME>/PROPOSALS.md`** (proposal, motivating evidence, suggested
  diff) — NEVER applied autonomously. Does not move the retro-cursor. No
  findings → exit silently; do not force a lesson out of a clean run.
- **Full sweep, interactive** (bare `/drydock:retro`, run with the human):
  everything since the retro-cursor, as below — and also walk
  `<STATE_HOME>/PROPOSALS.md` together: approved proposals become contract
  amendments, declined ones are recorded and removed.

## Mine

1. Read the `retro-cursor` commit from `<STATE_HOME>/PRIORS.md` (it stays in
   the hot file), and read the existing priors **in full** — `PRIORS.md` plus
   every file in `<STATE_HOME>/priors/`. Retro is the one actor that loads
   all of them: it needs to see what is already asserted before appending a
   near-duplicate, and pruning needs the same whole view. Everything between
   the cursor and HEAD is this retro's corpus:
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

- **Prior** (advisory, repo- or domain-specific fact): append with the citing
  item id, to the file the prior's **scope** implies. Commit directly (in
  `<STATE_HOME>`, never pushed) — priors are knowledge, not policy.

  Retro is the only actor that reads every priors file, because it is the one
  that writes them; everybody else loads a slice (DISPATCH step 8). So the
  filing decision is retro's alone, and getting it wrong is how a prior
  becomes invisible to the phase that needed it:

  | The prior is true of | Append it to | Under the heading |
  |---|---|---|
  | one target repo | `<STATE_HOME>/priors/<slug>.md` — `<slug>` is the basename of `target_repo` (`~/code/ledger-api` → `priors/ledger-api.md`) | `## Target repo: <path>` |
  | writing specs | `<STATE_HOME>/priors/_spec-writing.md` | `## Spec-writing` |
  | prepared PR titles and bodies | `<STATE_HOME>/priors/_pr-prose.md` | `## PR prose …` |
  | reviewing | `<STATE_HOME>/priors/_review.md` | `## Review …` |
  | the loop itself, everywhere | `<STATE_HOME>/PRIORS.md` — the hot file | any topic heading |

  Create the cold file (and `<STATE_HOME>/priors/` itself) if it is missing,
  and put that third column's heading at its top. Those prefixes are what
  `board/split_priors.py` classifies on. A section under some other heading
  still loads — the phase reads its whole file — but it is no longer one
  the splitter can place, so a later re-split stops being a no-op and files
  it hot, which is the splitter's deliberate default for a heading it does
  not recognise. The three phase headings match on their prefix, so a tail
  is welcome (`## PR prose is where the defects are`); `## Target repo:`
  matches whole, case-insensitively.

  **The hot file is the scarce one** — it is loaded by every actor on every
  run, and it is meant to stay around 50 lines. A lesson that is really
  about one repo or one phase does not belong there, however important it
  feels while you are writing it. A STATE_HOME with no `priors/` directory
  is a pre-split one: append to `PRIORS.md` as before and let
  `/drydock:install` migrate it.
- **Rule** (process failure a prior can't fix): draft the amendment to
  `<PLUGIN_HOME>/contracts/DISPATCH.md` / `REVIEWER.md` / `ORCHESTRATOR.md` /
  `<PLUGIN_HOME>/templates/spec-template.md`, show the diff and the incident
  that motivates it, and apply **only on the human's approval** — contract
  changes are theirs, always. In per-item mode, the proposal goes to
  `<STATE_HOME>/PROPOSALS.md` and stops there.
- **Skill defect** (a plugin skill produced the failure): fold the correction
  into that skill, with the evidence, using whatever skill-improvement pass
  your setup has.

Refuse to distill a lesson with no citation, and prune any prior the corpus
shows to be wrong or obsolete (note why in the commit).

## Close

1. Update the `retro-cursor` line in `<STATE_HOME>/PRIORS.md` to HEAD; commit
   `retro: <n> priors, <m> rule proposals` (in `<STATE_HOME>`, never pushed).
2. Report: what was learned, what was proposed and approved/declined, and the
   one metric that matters — are human interventions per item trending down?

## Cadence

On demand, plus the automatic per-item pass after every ship. Propose a full
sweep whenever an item needed 2+ human interventions. If retros prove
valuable, schedule the mining half as a recurring autonomous run and keep only
rule-approval interactive.
