# Quickstart

From a plugin install to a merged pull request, with the three-session layout
that makes the whole thing work.

## Prerequisites

| Need | Why | Check |
|---|---|---|
| [Claude Code](https://claude.com/claude-code) with `--bg` support | Executors are background sessions, not in-process subagents | `claude --version` |
| Python 3.10+ | The board. Standard library only — nothing to install | `python3 --version` |
| git 2.x with worktree support | Every execution runs in an isolated worktree | `git worktree list` |
| [`gh`](https://cli.github.com), authenticated | Opens draft PRs, reads their state, flips draft to ready | `gh auth status` |

`gh` missing is the one that quietly breaks everything downstream: without it
nothing ships, because `ship` *is* `gh pr create --draft`.

## Install

```text
/plugin marketplace add phspagiari/drydock
/plugin install drydock@drydock
```

That installs the plugin itself — skills, contracts, board — the same way you'd install any other
Claude Code plugin. It is read-only from here on; `/plugin update drydock` is how it changes. Then:

```text
/drydock:install
```

This is a different, smaller job: it never touches the plugin's code, only your own **STATE_HOME**
(`~/.drydock` by default) — a private, local-only git repository, never given a remote, that holds
your queue, deliverables, archive, and priors. It asks before it writes anything, and reports every
write. Seven steps:

1. **Where STATE_HOME lives.** Default `~/.drydock`. Not a clone of anything — a private data
   directory, like `~/.aws` or `~/.docker`. If it already has a git remote configured, install
   refuses to proceed until you remove it or point elsewhere: a remote is the one thing that could
   ever let a spec leak somewhere it shouldn't.
2. **Personalize**: your **branch namespace**, usually your git forge handle — every branch
   drydock creates in a target repo is `<namespace>/drydock-<id>` — and your permission posture
   (step 6). Both get written to `STATE_HOME/config`, never sed-replaced into the plugin's own
   files, so a later `/plugin update` can never quietly reset them.
3. **Seed the queue**: empty `specs/{inbox,active,blocked}`, `deliverables/`, `archive/`, plus
   `PRIORS.md` and `PROPOSALS.md` copied once from the plugin's seed templates.
4. **Migrate**, if you used drydock before this refactor: your real queue lived inside a cloned
   repo registered via a manual skills symlink. Install detects that layout, offers to copy your
   real items into the new STATE_HOME, and retires the old symlink.
5. **Verification**, fail-closed: Python, the board booting and answering `/healthz` against
   STATE_HOME, STATE_HOME's git state (clean, and still no remote), `gh auth status`, and whether
   your Claude Code install supports `--bg`.
6. **Permission posture** — the question that matters. See below.
7. **Hand-over** — the three commands you'll actually run day to day.

### The permission question

Executors run with `--permission-mode bypassPermissions`, because a background
session has nobody to answer a prompt: without it, a run stalls invisibly
rather than finishing or escalating.

That flag suppresses the *prompt*, not your policy. Every executor is a
separate Claude Code process that loads your `settings.json`, your `PreToolUse`
hooks and your deny rules, and drydock never routes around them. **Your
permission policy is the boundary**, which means install asks whether you
actually have one.

If you don't, say so, and run executors with `--permission-mode acceptEdits`
instead — set `permission_mode: acceptEdits` in `STATE_HOME/config`, no
contract file to edit. Some runs will stall on prompts. Take that trade: a
stalled run is recoverable; an unreviewed mutation against live
infrastructure is not.

## The three-session topology

drydock is not one session. Trying to run it as one is the most common way to
have a bad time, because the orchestrator's context fills with work that
belongs elsewhere.

| Session | What runs there | Model | Lifetime |
|---|---|---|---|
| **Spec sessions** | `/drydock:spec` at the end of whatever you were doing. Many of these, one per piece of work | Whatever you were already using | The discussion |
| **The orchestrator pane** | `/drydock:orchestrate`, pinned and left alone. The board opens from here | Your longest-running, highest-context model | Hours to days |
| **Review sessions** | `/drydock:review`, and `/drydock:spec unblock <id>` for each escalation | Your interactive default | Minutes |

The separation is enforced by the contracts, not just recommended: the
orchestrator never answers an escalation and never judges a deliverable. Those
happen in their own sessions so the loop stays thin, stays cheap, and stays
alive.

The board's blocked and delivered cards carry the paste-ready
`claude "/drydock:… <id>"` command for exactly this reason — clicking through
from the board opens the right kind of session for the item.

## Your first spec

Do not write a spec from scratch. The whole point of `/drydock:spec` is that it
runs at the *end* of a session that already did the thinking, when the context
is hot.

So: pick something real but small, and go investigate it the way you normally
would — read the code, run the queries, form the plan. Then, instead of
building it:

```text
/drydock:spec
```

The skill will show you two sections before writing anything: **acceptance
criteria** and **assumptions**. Those gate everything downstream, so read them
properly.

### The eligibility test

Every acceptance criterion must be a command plus the result that counts as a
pass, runnable without you. If you cannot write them that way, this work is not
drydock-eligible yet — the honest answer is to name the missing verifier and
keep the work interactive.

A criteria table that will actually hold:

```markdown
| # | Check | Command | Pass condition |
|---|-------|---------|----------------|
| AC-1 | Build | `go build ./services/ledger/...` | exit 0 |
| AC-2 | Tests | `go test ./services/ledger/transfers/...` | all pass, includes a new test for FR-001 |
| AC-3 | Replay is idempotent | `scripts/replay-transfer.sh` | second POST returns the first entry; 1 row in `ledger_entries` |
```

AC-3 is the one that matters. AC-1 and AC-2 are the floor — they prove the code
compiles and the tests you wrote pass, which is not the same as proving the
feature works. **At least one criterion has to encode the feature's intent.**
Without it, an executor can satisfy every criterion and still deliver the wrong
thing, and the reviewer's "criteria gaming" hunt is what will catch it — a
round later than you'd like.

Two more things the skill will hold you to:

- **Scope build and test targets to your diff.** A repo-wide green check you do
  not control makes the criterion unsatisfiable on somebody else's bad day.
- **Never invent an answer to close a gap.** An open question becomes a
  `[NEEDS CLARIFICATION: …]` marker, and any marker still present at dispatch
  blocks the spec instead of executing it. Answer it now, in-session, while the
  context is hot — that is much cheaper than answering it as an escalation
  tomorrow.

Read [`examples/example-spec.md`](../plugin/examples/example-spec.md) for every section
filled the way it should be.

## Run it

In the pinned pane:

```text
/drydock:orchestrate
```

It opens the board at `http://127.0.0.1:8642`, runs a first tick, then paces
itself — 20–30 minutes when idle, about 10 with executions active, never
sub-minute. You will see your spec move `inbox → active`, a worktree appear,
and an executor start.

To skip the wait on the first one:

```sh
claude "/drydock:dispatch <id>"
```

You will be notified on exactly four events — delivered, blocked, dispatch
failure, budget exceeded. Never on dispatch starts or progress. If it is quiet,
it is working.

## When something comes back blocked

This is the normal, healthy path — not a failure. An executor hit a decision
it could not make and stopped before doing anything you would have to undo.

```sh
claude "/drydock:spec unblock <id>"
```

You get the question, the options, and what was ruled out. Decide, and the
answer is written **into `SPEC.md`** — the next executor sees only the spec, so
a decision recorded anywhere else is invisible. The reasoning is appended to
`QUESTION.md` as a `## Resolution` section, which is what `/drydock:retro` mines
later.

Then the item goes back to `inbox` and a **fresh** executor picks it up from
the amended spec, the branch, and `RUN.md`. The old session is never resurrected
— see [ARCHITECTURE.md](ARCHITECTURE.md#stateless-handoff) for why.

If `QUESTION.md` is not self-contained enough to decide from, that is itself a
defect worth routing back into the executing skill. Say so when you answer.

## The review pass

Once a day:

```sh
claude "/drydock:review"
```

Blocked items first (they gate other work), then deliverables, oldest first,
one at a time. Each deliverable arrives with its criteria table and evidence
paths, its assumptions surfaced first, the adversarial reviewer's verdict and
what it tried and failed to break, and a link to a draft PR that already exists.

Three verdicts:

- **Approve** → `gh pr ready <url>` flips the draft to ready for your team's
  normal review, and the item moves to `archive/`.
- **Reject** → you must route it. *Fast* means the spec was wrong: amend it
  together, back to the inbox. *Slow* means the execution or the skill was
  wrong: the correction is folded into the skill that produced the failure,
  then re-queued. An unrouted rejection teaches the system nothing, and the
  skill will refuse to archive one.
- **Skip** → left in place.

A deliverable arriving **without** a `REVIEW.md` is flagged loudly — it
predates the reviewer stage or bypassed it, and deserves your own suspicion.

After that, the PR is in your team's hands. If people comment on it, the
orchestrator notices, compiles the threads into `COMMENTS-r<N>.md`, and
dispatches a fix executor that changes code and **drafts** replies. It never
posts them. Every word on the PR is yours.
