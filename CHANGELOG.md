# Changelog

All notable changes to drydock. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions are the
plugin's `plugin/.claude-plugin/plugin.json` and the git tags that
`.github/workflows/release.yml` turns into releases.

## [Unreleased]

Queued in the drydock STATE_HOME and not yet landed — listed so the gap
between "designed" and "shipped" is on the record:

- Criterion construction (`speccheck.py`, ship criteria vs acceptance
  criteria, R1/R2 rules callable against `PLAN.md`'s `Verify` column).
- Escalation and evidence discipline (QUESTION.md shape rule, evidence
  provenance after a fix round).
- Chained items' prepared PR text applied at ship (PROPOSALS P15).

## [0.4.0] — 2026-09-28

The release that turns the priors from an append-only log into a maintained
view, and the executor from one session into three. Design note:
[`docs/design/2026-09-18-ivm-priors.md`](docs/design/2026-09-18-ivm-priors.md).
308 tests on `main` (was ~90); CI green at `3fe3305`.

### Added

- **Plan / gate / implement phases** (#6). DISPATCH step 8 runs three fresh
  sessions with an artifact as the only handoff: a plan executor writes
  `PLAN.md` from the new `plugin/templates/plan-template.md` (mandatory
  `## Tasks` table with a runnable `Verify` per row) and exits without
  touching the worktree; a plan gate — a new section at the end of
  `REVIEWER.md` — checks coverage, runnable verifies, blast radius,
  non-goals, task ordering and markers, and writes `PLAN-REVIEW.md` with
  `approve` or `flag`; an implement executor starts cold from the spec and
  the plan, never sees the plan session's transcript, works the tasks in
  `After`-order and ticks each in `RUN.md`. After an unblock it resumes
  from the first unticked task. A `phase:` line in `RUN.md`'s header —
  written with `base_sha:` and the `## Log` heading in one
  write-then-rename — is the discriminator; the state table in
  `ORCHESTRATOR.md` fails closed on any value it does not name. Items in
  flight when this landed finish under the single-phase prompt.
- **Hot/cold priors** (#5). `<STATE_HOME>/PRIORS.md` is the hot file (global,
  every actor, target ≈ 50 lines); `<STATE_HOME>/priors/<slug>.md` per
  target repo and `_spec-writing.md` / `_pr-prose.md` / `_review.md` per
  phase load conditionally. Each consumer declares its slice: spec skill,
  executor (implement and READY), reviewer, retro. `plugin/board/split_priors.py`
  migrates a monolithic file (line-count conserving, hot file written last,
  idempotent), and `/drydock:install` runs it when the file still carries a
  `## Target repo:` heading.
- **Prior records and a per-repo code cursor** (`ad78e65`, `4571f3e`).
  Every prior the retro writes carries `scope`, `derived_from`, `depends_on`
  (free text; backticked tokens with `* ? / .` are path globs) and
  `asserted`; legacy bullets parse as `depends_on: unknown`. Each cold repo
  file may carry `code-cursor: <sha>`, keyed to `origin/<default>` (never
  the checkout's `HEAD`). `plugin/board/priors_check.py` gains `parse`,
  `stale`, `advance [--if-ancestor]`; DISPATCH step 5 writes the item's
  `PRIORS-STALE.md`, which 8a and 8c read as a caveat. The retro promotes a
  lesson asserted under two repo files to the hot file.
- **Merge propagation into priors** (`d928118`, `cb74df1`, `c6faf70`,
  `ec047a5`). DISPATCH step 14: once a `pr` deliverable's pull request has
  merged, `/drydock:review` batches every `propagate: pending` item per repo,
  places the merge against the cursor (already covered → close; side line →
  stop for the human), lists `<cursor>..<merge>`, pre-filters the repo's
  priors by their globs (`priors_check.py candidates`; glob-less priors are
  always candidates), has an agent return `holds` / `stale` / `retract`
  with the deciding hunk, applies all verdicts in one `retract` call, and
  advances the cursor only if the old one is an ancestor. Writes
  `<STATE_HOME>` only — a target repo's `CLAUDE.md` is out of bounds by the
  same reasoning that split plugin from state in 0.3.0.
- **Executor liveness and branch drift** (`813cb25`). A `.progress` file in
  the item's state directory (`last_progress:`, optional `hold:`, `step:`,
  `note:`; write-then-rename) replaces elapsed wall clock as the stall
  signal; `RUN.md` keeps exactly one live writer. A suspect stamp is
  corroborated against `RUN.md` growth and the session transcript
  (subagent transcripts included) across ≥ 30 s before it is called a
  stall; process CPU and the session status string are declared
  non-evidence. Finished work — `READY.md`, or an open `QUESTION.md` — is
  excluded from every recovery action, and a `READY.md` with a clean tree
  and a stable `HEAD` for 5 minutes goes to review whatever the session is
  doing. Chained preflight now checks a local ref **ahead** of its remote
  (`rev-list --left-right --count`), records `preflight_sha`, and step 7
  re-verifies the worktree and `ls-remote` against it (TOCTOU).
- **Every session — no prompts, verified effects** (#8). A new DISPATCH
  section binding every session drydock starts: non-interactive command
  forms only; assert the destination is absent before any `mv`, `cp` or
  `git mv`; never pipe a long producer into `| head`; a reported effect is
  an asserted post-state. `<STATE_HOME>` changes through `git mv` / `git rm`
  and the commit's `--stat` is read back. `ORCHESTRATOR.md` Hard limits:
  the loop is a session too, runs `server.py check` once per tick, and
  never destroys finished work. `server.py check` reports a `REVIEW.md` or
  `PLAN-REVIEW.md` byte-identical to one of its own `-r<N>.md` archives.
- **Mechanical findings never call a human** (#9). Every review finding
  carries `repair: mechanical | judgement` (mechanical only with a verbatim
  replacement, a check that fails before and passes after, a diff-wide
  sweep for textual claims, and no commit rewrite) and `surface:
  ship-facing | internal`. DISPATCH step 12 gains the mechanical repair pass
  (12a apply, 12b verify, 12c prove scope, 12d route), run at most once per
  run and never rewriting a commit. `round` now counts fix-executor rounds
  in the current run; `review:` is item-level provenance; at the cap, an
  all-mechanical remainder retires to ship via `cap_retire: true`.
- **Shared pull requests stay draft on approve** (#7). Step 14 skips
  `gh pr ready` when the item's spec declares a `pr_url`, or another spec
  declares this item's `pr_url` as the one it chains onto. The board's
  delivered card says so.
- **Tested queue rules** (#10). `plugin/board/queue_rules.py` is the one
  implementation of dependency eligibility and marker detection
  (`eligible`, `check`); the Inbox step and preflight items 1–2 run it
  instead of re-deriving the rules. Markers inside code spans, fences and
  HTML comments no longer block a spec that merely describes the convention.
- **Contract guards as tests.** `test_contract_refs.py` pins DISPATCH's
  steps to exactly 1–17, requires the `8a`/`8b`/`8c` and `12a`–`12d`
  labels once each and never as headings, and resolves every cross-file
  `step N` citation. `test_contract_rules.py`, `test_contract_liveness.py`,
  `test_session_contracts.py` and `test_state_invariants.py` pin the
  verdict vocabulary against `app.js`, the round-cap rules across all
  restatements, the no-rewrite rule, the liveness clauses and the
  finished-work exclusion. `test_session_premises.py` reproduces the shell
  behaviour the no-prompts rule rests on.
- `CHANGELOG.md` (this file).

### Changed

- DISPATCH step 8's executor prompt reads the hot file plus its repo's cold
  file, not the whole of `PRIORS.md`; step 11 reads `_pr-prose.md`; the
  reviewer reads hot + repo + `_review.md`; `/drydock:spec` reads hot +
  `_spec-writing.md`.
- The retro's Distill step files each prior by scope, writes the four-field
  record, and applies the promotion rule.
- `ORCHESTRATOR.md` Active derives each item's state from disk (`phase:`,
  `PLAN.md`, `PLAN-REVIEW.md`) before verifying progress; the dead-executor
  and liveness checks are scoped to the states where a session should be
  running, and a dead gate is relaunched as a gate, never as a planner.
- `README.md`, `docs/ARCHITECTURE.md` and `docs/QUICKSTART.md` restate the
  round cap, the approve step and the priors layout to match.
- `plugin/board/server.py` re-exports `field`, `deps_of` and `chain_errors`
  from `queue_rules.py`; `scan_item()` exposes `chained` and `state_errors`.

### Fixed

- Approving the first item of a chained series no longer marks the shared
  pull request ready for the team (#7; two occurrences on 2026-09-25).
- A spec whose `depends_on` is a multi-line YAML list is no longer reported
  eligible with dependencies unmet (#10).
- A spec that mentions `NEEDS CLARIFICATION` in prose, a code span or the
  template's header comment no longer blocks itself (#10).
- A session frozen by host sleep is no longer blocked as a budget failure,
  and a session wedged on a closed pipe or an interactive prompt is no
  longer invisible to the clock (`813cb25`).
- `rm`, `cp` and `mv` aliased to `-i` no longer wedge a background session
  or silently do nothing and exit 0 (#8).
- An orchestrator "archive" done with `cp` no longer leaves a stale
  `REVIEW.md` that reads as current (`server.py check`, #8).
- A cap-forced `flag` on a finding whose replacement and check were already
  written no longer costs an escalation, an unblock and a re-dispatch (#9).
- The round counter no longer accrues across human re-queues (#9).
- The repair pass no longer calls `retract` with an empty key list when every
  verdict holds (`ec047a5`); propagation places the merge against the cursor
  before diffing, so a cursor a retro already advanced past the merge does
  not produce an inverted range (`c6faf70`).

### Known limitations

- `.progress` is not yet ignored by `<STATE_HOME>/.gitignore`; move commits
  may carry a stale stamp (harmless, no remote).
- The board has no plan-phase card state; a plan/gate item renders as active.
- `<slug>` is the target repo's basename — two repos with the same basename
  share a cold file.
- `chain_errors` knows `main` and `master` only.
- The hot file's 50-line target is advisory; nothing enforces it.
- Commit-message defects are never mechanical (the repair pass never
  rewrites a commit); they reach the human in the accepted-at-ship list.

## [0.3.0] — 2026-09-18

### Added

- Chain a spec onto an existing branch and pull request: `branch:` and
  `pr_url:` frontmatter, chained preflight (behind-only), push into an open
  PR at ship instead of opening a new one (#4).

### Changed

- The plugin is separated from its state: `PLUGIN_HOME` (installed via a
  self-referencing marketplace, updated by `/plugin update`) vs
  `STATE_HOME` (`~/.drydock`, its own local git repository, a remote on it
  is a hard stop). Personalisation moves to `STATE_HOME/config`;
  `/drydock:install` migrates the old clone+symlink layout (#3).

## [0.1.0] — 2026-09-12

- First packaged release: skills (spec, orchestrate, dispatch, review,
  board, install, retro), contracts, templates, the stdlib board and its
  tests, CI (ruff, unittest, markdownlint, actionlint).

[Unreleased]: https://github.com/phspagiari/drydock/compare/v0.4.0...HEAD
[0.4.0]: https://github.com/phspagiari/drydock/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/phspagiari/drydock/releases/tag/v0.3.0
[0.1.0]: https://github.com/phspagiari/drydock/commits/8837509
