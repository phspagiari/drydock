<div align="center">

<h1>drydock</h1>

<h3><em>Specs in, pull requests out — an agentic pipeline for Claude Code.</em></h3>

<p>
<strong>Interactive sessions produce specs. A git repo is the queue. An orchestrator dispatches
executor agents into worktrees, and adversarial review happens before any PR exists — ships are
built and inspected in the dock, and launched only when ready.</strong>
</p>

<p>
<a href="https://github.com/phspagiari/drydock/actions/workflows/ci.yml"><img alt="CI" src="https://img.shields.io/github/actions/workflow/status/phspagiari/drydock/ci.yml?branch=main&style=flat-square&label=ci"></a>
<a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/github/license/phspagiari/drydock?style=flat-square"></a>
<a href="https://claude.com/claude-code"><img alt="Built for Claude Code" src="https://img.shields.io/badge/built%20for-Claude%20Code-d97757?style=flat-square"></a>
<!-- Release badge goes live with the first tag; a badge reading "no releases" is worse than no badge:
<a href="https://github.com/phspagiari/drydock/releases"><img alt="Release" src="https://img.shields.io/github/v/release/phspagiari/drydock?style=flat-square&label=changelog"></a>
-->
</p>

<p>
<a href="#quickstart">Quickstart</a> ·
<a href="#how-it-works">How it works</a> ·
<a href="contracts/">Contracts</a> ·
<a href="#the-board">Board</a> ·
<a href="docs/ARCHITECTURE.md">Architecture</a>
</p>

</div>

---

<!-- DEMO: replace this transcript with an animated SVG of a real orchestrator run.
     Record with asciinema, convert with svg-term-cli, commit under docs/media/ and
     reference it here as <img src="docs/media/tick.svg">. SVG rather than GIF: sharp
     at any zoom, small, and it survives GitHub's image proxy in both themes. -->

```console
$ claude                                   # a normal work session; you were debugging
> /drydock:spec
  Acceptance criteria and Assumptions, for confirmation before I write the file:
    AC-1  go build ./services/ledger/...                     exit 0
    AC-2  go test ./services/ledger/transfers/...            all pass, new test for FR-001
    AC-3  replayed POST returns the first entry, no new row  curl script, 1 row in ledger_entries
  ✓ spec: 2026-09-02-transfers-idempotency → specs/inbox/  (dispatchable)

$ claude                                   # a second pane, pinned, left running
> /drydock:orchestrate
  board: http://127.0.0.1:8642
  tick 1  preflight ok → active → worktree ledger-api-wt/2026-09-02-transfers-idempotency
          executor dispatched (opus, background session)
  tick 2  active: RUN.md 4m ago, session alive — no change
  tick 3  ⚠ blocked: 2026-09-02-transfers-idempotency
          "Idempotency-Key collision across tenants: reject 409, or scope the key
           per tenant? Spec says neither, and the schema has no tenant column."
          → claude "/drydock:spec unblock 2026-09-02-transfers-idempotency"

$ claude "/drydock:spec unblock 2026-09-02-transfers-idempotency"
> scope per tenant — the header is client-supplied, tenants must not collide
  ✓ SPEC.md amended (FR-003, AC-4), QUESTION.md records the decision and what was ruled out
  ✓ unblock → specs/inbox/   # a FRESH executor resumes from the spec, never the old session

  tick 4  re-dispatched
  tick 5  READY.md → adversarial review on the worktree (round 1)
  tick 6  REVIEW.md verdict: fix — 2 findings
          · migration is not reversible; no down path        internal/db/0042_idem.sql:1
          · AC-3 asserts row count, not that the response body is the FIRST entry
          → fix executor, same worktree
  tick 7  REVIEW.md verdict: ship — 0 findings
          "Tried: concurrent replay under -race, expired-key eviction, a 24h clock skew."
  ✓ deliverable ready: 2026-09-02-transfers-idempotency — reviewed, github.com/…/pull/4471

$ claude "/drydock:review"
  1 ready for review, 0 blocked
  ── transfers: idempotency keys on POST /v1/transfers ──────────────────────
     4/4 criteria pass, evidence in deliverables/…/evidence/
     review: ship, 1 fix round. Assumptions: 24h key TTL; 409 on body mismatch.
     draft PR #4471 (open, mergeable)
  > approve
  ✓ gh pr ready #4471 — draft → ready for your team's normal review
  ✓ archive: 2026-09-02-transfers-idempotency
```

The pull request in the last line is the first time a human sees a diff. Everything above it —
the clarifying question, the reversibility finding, the gamed acceptance criterion — was resolved
before the PR existed.

## What drydock is

drydock is a queue, a loop, and five Markdown contracts. Work enters as a **spec** written by the
interactive session that was already thinking about the problem. A **git repository is the state
machine**: a spec's directory location *is* its state, and every transition is a commit, so the
queue's history is the audit log. An **orchestrator** ticks over that queue, dispatching executor
agents into isolated git worktrees. When an executor believes it is done, an **adversarial
reviewer** reads the diff and tries to reject it.

> [!NOTE]
> Most agentic pipelines review code in the pull request. drydock reviews it in the worktree, and
> the pull request only exists once the work has already survived review and been fixed in-branch.
> A PR appearing in your team's repo means a robot already tried to break it and failed.

The other half is what happens when an agent *can't* finish. Delivering with caveats is forbidden:
an executor that hits an unresolved question, a failing criterion, or a step outside its declared
blast radius stops, writes the concrete decision you need into `QUESTION.md`, and files itself into
`specs/blocked/`. Everything you must decide reaches you before any PR exists — never as a footnote
in a description you would have skimmed.

## Quickstart

**Prerequisites:** [Claude Code](https://claude.com/claude-code), Python 3.10+, git 2.x with
worktree support, and [`gh`](https://cli.github.com) authenticated (drydock opens draft PRs and
reads their state through it).

```sh
git clone https://github.com/phspagiari/drydock.git
cd drydock
claude --plugin-dir ./plugin      # loads /drydock:* for this session only
```

Then, in that session:

```text
/drydock:install
```

Install asks before it writes anything: where drydock should live, your **branch namespace**
(usually your git forge handle — it prefixes every branch drydock creates, as
`<namespace>/drydock-<id>`), whether to reset the queue, and what your permission posture is. It
symlinks the plugin into your skills directory so `/drydock:*` survives the session, then verifies
the toolchain and fails loudly on anything missing. See [docs/QUICKSTART.md](docs/QUICKSTART.md)
for the walkthrough and your first spec.

> [!WARNING]
> The orchestrator dispatches agents that **write to your repositories unattended**, and the board
> serves file contents from the repo it is pointed at over `127.0.0.1`. Executors run as background
> sessions with `--permission-mode bypassPermissions` — which does not widen what drydock may do,
> because every executor is a separate Claude Code process that loads *your* `settings.json`, hooks
> and deny rules. **Your permission policy is the boundary.** If you do not have a deny layer you
> trust, run executors with `--permission-mode acceptEdits` and accept that some runs stall on
> prompts. Read [SECURITY.md](SECURITY.md) before the first dispatch.

## How it works

### The queue

A spec's directory is its state. Nothing else records it — no database, no daemon, no sidecar file.

| Directory | API key | What it means | What moves it out |
|---|---|---|---|
| `specs/inbox/<id>/` | `inbox` | Written and dispatchable — or waiting on a `depends_on` id that has not shipped | Preflight passes → `active`; an unresolved `[NEEDS CLARIFICATION]` → `blocked` |
| `specs/active/<id>/` | `active` | An executor is running in a worktree. Review and fix rounds happen here | Reviewer's `ship` → `deliverables/`; `flag` → `blocked` |
| `specs/blocked/<id>/` | `blocked` | A human decision is needed. `QUESTION.md` holds it: the question, the options, what was ruled out | `/drydock:spec unblock <id>` writes the answer into the spec → `inbox` |
| `deliverables/<id>/` | `delivered` | Draft PR open and already reviewed — **ready for your review** | `/drydock:review`: approve → `archive/`; reject → `inbox` |
| `archive/<id>/` | `archive` | Approved, or the PR merged | Terminal |

`delivered` is the key the board's API uses for the middle column; the human-facing state is
"ready for review". A merged PR found during housekeeping archives itself — the merge *was* the
approval completing.

### The contracts

The rules are Markdown, not code, because they are meant to be edited by a human who disagrees with
them. Every skill re-reads its contract on every invocation, so an edit takes effect on the next
tick of a loop that is already running.

| Contract | Governs | Read by | When |
|---|---|---|---|
| [`ORCHESTRATOR.md`](contracts/ORCHESTRATOR.md) | The tick: inbox dispatch, active verification, housekeeping, notification policy | The orchestrator session | Every tick |
| [`DISPATCH.md`](contracts/DISPATCH.md) | One spec from inbox to landed deliverable — preflight, worktree, the zero-calls gate, ship, comment rounds. Steps 1–17 | Orchestrator, `/drydock:dispatch`, and executors (steps 9–11) | Any tick that dispatches or lands work |
| [`REVIEWER.md`](contracts/REVIEWER.md) | The adversarial pass: what to hunt for, the `ship`/`fix`/`flag` verdict, the round cap | The reviewer session | When an executor writes `READY.md` |
| [`PRIORS.md`](contracts/PRIORS.md) | Accumulated lessons — advisory knowledge, not policy. Ships empty on purpose | Every executor before work, every reviewer while grounding | Start of every run |
| [`PROPOSALS.md`](contracts/PROPOSALS.md) | Rule changes a retro wants, with evidence and a suggested diff. Applied only by a human | `/drydock:retro`, `/drydock:review` | A per-item retro queues; the review pass decides |

### The commands

| Command | Does | Where you run it |
|---|---|---|
| `/drydock:spec` | Converges the session you are in into a spec instead of building mid-analysis | Any work session |
| `/drydock:spec unblock <id>` | Answers an escalation, writes the decision into the spec, re-queues it | Its own session |
| `/drydock:orchestrate` | Starts the loop, or runs one tick | A pinned pane, on your longest-running model |
| `/drydock:dispatch <id>` | Runs one spec now instead of waiting for a tick | Anywhere |
| `/drydock:review` | The human pass: blocked questions first, then deliverables | Daily |
| `/drydock:board` | Starts and opens the board | Anywhere |
| `/drydock:retro` | Mines runs into priors and queued rule proposals | Automatic after each ship; the full sweep is interactive |
| `/drydock:install` | Bootstraps a fresh environment | Once |

### The rules that hold it together

These are distilled from the contracts; each is load-bearing, and each exists because the failure
it prevents is expensive.

- **The zero-calls gate.** Delivering with caveats is forbidden. Any failing criterion, any fired
  escalation condition, any step outside the declared blast radius — including a breach already
  committed — is an escalation, not a footnote. "The work is complete and the failure isn't mine"
  is not an exemption.
- **No PR until `ship`.** The reviewer's verdict is what opens it, and the title and body ship
  verbatim from `READY.md`.
- **Executors are stateless by design.** After an unblock, a *fresh* executor resumes from the
  amended spec, the branch, and `RUN.md` — never the old session. Which is why an escalating
  executor must push its work and leave `RUN.md` a handoff a stranger could resume from.
- **The target repo carries zero drydock metadata.** No spec files, labels or tags committed
  there; the branch and the PR are the entire footprint. The drydock repo is the sole registry of
  which PRs are yours, and PR state is read back per recorded URL — never by scanning the target
  repo's PR list.
- **Executors never speak on the PR.** A comment needing an answer becomes a *drafted* reply you
  post or rewrite. Every word on the PR is yours.
- **Round cap 2.** Work that survives two fix rounds without shipping needs a human, not a third
  robot — the verdict becomes `flag` regardless.
- **Deterministic FIFO.** The inbox is ordered lexicographically by id, never by mtime, because
  moves and edits reset mtime.
- **Bounded concurrency.** Two executions at a time, one relaunch per spec, and a heartbeat file
  that stops a second orchestrator from starting.

Full lifecycle, the actor model, and the state diagram: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## The board

```sh
python3 board/server.py serve --port 8642
```

Standard library only, no install step, no build. It reads the queue from disk on every request —
no cache, no background daemon, no regeneration step, so **what you see is what is on disk right
now**. It binds `127.0.0.1` only and serves a fixed allowlist of item files. Blocked and delivered
cards carry the paste-ready `claude "…"` command that works them.

<!-- BOARD SCREENSHOT: docs/media/board.png — capture with a populated fixture queue, dark theme. -->

## Writing a spec

Start from [`templates/spec-template.md`](templates/spec-template.md); read
[`examples/example-spec.md`](examples/example-spec.md) for every section filled the way it should
be. The sections are Context, Goal, Non-goals, Constraints & blast radius, Requirements, Acceptance
criteria, Escalation conditions, and Assumptions.

**Acceptance criteria are the gate, and the section newcomers under-fill.** Each one is a command
plus the result that counts as a pass. The eligibility test is blunt: if you cannot write every
criterion as a command runnable without you, the work is not drydock-eligible yet — name the
verifier that is missing and keep the work interactive. "Tests pass" alone is rarely enough; at
least one criterion has to encode the feature's actual intent rather than compilation health.

Gaps become `[NEEDS CLARIFICATION: …]` markers rather than invented answers. Any marker still
present at dispatch blocks the spec instead of executing it.

## Design principles

- **Markdown contracts over code.** A human can edit the rules, mid-flight, without a deploy.
- **Git as the state machine.** Directory = state, transition = commit, history = audit log. No
  database, no daemon, no scheduler.
- **Standard library only.** A fresh clone runs. The board has no dependency surface to audit.
- **Review before the PR exists.** The expensive round trip is a human reading a bad diff.
- **Fail closed.** Preflight aborts loudly, escalation beats guessing, and a caveat is a stop.
- **The system learns from its own arguments.** `/drydock:retro` mines unblock resolutions and
  reviewer findings into priors, and queues rule changes for a human — it never amends a contract
  itself.

## Status

> [!NOTE]
> Early. The model is settled and the contracts are stable enough to run against real repositories,
> but the surface will move: the model-routing table has two tracks (`code`, `report`) and is meant
> to be extended, and `contracts/PRIORS.md` ships empty because priors are only true of the repos
> that taught them. Contract disagreements are the most useful issue you can file — bring them to
> [Discussions](https://github.com/phspagiari/drydock/discussions).

## More

[Architecture](docs/ARCHITECTURE.md) ·
[Quickstart](docs/QUICKSTART.md) ·
[FAQ](docs/FAQ.md) ·
[Contributing](CONTRIBUTING.md) ·
[Security](SECURITY.md) ·
[MIT](LICENSE)
