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
Claude Code plugin. It is read-only from here on; an update is how it changes (see
[Staying current](#staying-current)). Then:

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
   files, so a later plugin update can never quietly reset them. A config this step creates
   also gets `max_concurrent: 5` (see [How many run at once](#how-many-run-at-once)).
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

### Staying current

drydock's `plugin.json` carries a version, and Claude Code fetches a new copy
of a plugin only when its version changes, so an install moves from one
drydock release to the next, not with every commit to `main`. In a session,
this refreshes the marketplace and updates the plugins installed from it:

```text
/plugin marketplace update drydock
```

From a shell:

```sh
claude plugin update drydock@drydock
```

Auto-update is off by default for a third-party marketplace like this one;
you can turn it on for it under `/plugin` > Marketplaces. A session that is
already running keeps the version it loaded; restart it to pick up the update
(Claude Code also has `/reload-plugins`). After updating, stop the
orchestrator loop and start it again, so that the loop and the sessions it
launches run the same version. STATE_HOME is not part of the plugin, so no
update touches your queue, config or priors. The details are in Claude Code's
[plugin documentation](https://code.claude.com/docs/en/plugins).

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

A check that only makes sense once a pull request exists — CI green, a merge, a
deploy, a human's sign-off — is not an acceptance criterion. It goes in the
spec's Ship criteria table, which the executor carries forward unevaluated, so
it no longer makes the work ineligible.

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

You will be notified on four events — delivered, blocked, dispatch failure,
budget exceeded. Never on dispatch starts or progress. If it is quiet, it is
working. Three other notifications also reach you: a failed run of
`queue_rules.py eligible` or of `queue_rules.py slots` (the queue or the config
is malformed, and that tick dispatched nothing), and a comment round on a
delivered pull request finishing ("comments addressed"). A spec that names an
`owner:` session sends its four events to that session instead — see
[Handing a spec to another session](#handing-a-spec-to-another-session).

## How many run at once

This section, [Handing a spec to another session](#handing-a-spec-to-another-session)
and everything elsewhere in drydock's docs about `max_concurrent`, `slots`, a
spec's `owner` or `resolved_by:` describe 0.5.0 and later. 0.4.0 and earlier
have neither feature: their cap is a fixed 2 that no config line changes, and
they never read `owner:`. To tell which you have, ask the installed plugin for
`slots`. A plugin from 0.5.0 or later prints three numbers; one from 0.4.0
prints:

```console
$ python3 <PLUGIN_HOME>/board/queue_rules.py slots --root <STATE_HOME>
usage: queue_rules [-h] {eligible,check} ...
queue_rules: error: argument command: invalid choice: 'slots' (choose from 'eligible', 'check')
```

Such a plugin, like one from 0.3.0 or earlier (which has no `queue_rules.py`
at all), ignores a `max_concurrent:` line and an `owner:` line without saying
so.

The orchestrator dispatches a spec from the inbox only while fewer than
`max_concurrent` items are in `specs/active/`. It is a line in
`STATE_HOME/config`, beside `namespace:` and `permission_mode:`, and when the
line or the file is absent the cap is 5. An item holds its place from dispatch
until it leaves `active/`, and its plan gate, its review and its fix rounds all
happen there, so an item under review still counts. The cap gates new
dispatches only: a comment round moves a delivered item back into `active/`
without consulting it, and `/drydock:dispatch` goes over it when you say so,
so `active` can exceed the cap. The subagents inside one execution are bounded
separately, by the spec's `budget.max_agents`.

To see the cap and what is free, look at the board's header, which reads
`active <n>/<cap>` (its tooltip has the free count), or run the code the loop
itself gates on:

```console
$ python3 <PLUGIN_HOME>/board/queue_rules.py slots --root <STATE_HOME>
3       5       2
```

The three fields are tab-separated: free, cap, active. `<PLUGIN_HOME>` is where
Claude Code installed the plugin — the `installPath` recorded for
`drydock@drydock` in `~/.claude/plugins/installed_plugins.json` — or `plugin/`
in a clone of this repository; without `--root`, `slots` reads
`$DRYDOCK_STATE_HOME`, else `~/.drydock`.

To change the cap, edit the line and commit the change in STATE_HOME:

```yaml
max_concurrent: 2
```

Nothing caches it: each tick's Inbox step runs `slots` before dispatching and
again after every dispatch, so the new value applies from the next tick
without restarting the loop. Lowering it below the number already active
stops nothing — `slots` reports 0 free, and dispatch from the inbox waits
until enough items have left `active/`. `/drydock:dispatch <id>` reads the
same numbers; when nothing is free it says so and asks before dispatching
anyway.

The value is a positive whole number with no quotes and no leading zero, on
one line; a trailing `# comment` is fine. Zero, a negative number, a word, an
empty value or a second `max_concurrent:` line makes `slots` exit 2, with
nothing on stdout and the reason on stderr:

```console
$ python3 <PLUGIN_HOME>/board/queue_rules.py slots --root <STATE_HOME>
queue_rules: max_concurrent: '0' is not a positive integer
```

While the config reads like that, the orchestrator skips dispatch on every
tick and notifies you (this one never goes to a spec's owner); it still
verifies what is already running. `/drydock:dispatch` reports the error and
stops. The board's header shows `active ?/?`, with the reason as its tooltip.

**Upgrading.** In 0.4.0 the limit was 2 and no config line changed it. From
0.5.0, a config without a `max_concurrent:` line means 5, so an install that
upgrades without adding the line goes from 2 to 5. To keep 2, add
`max_concurrent: 2`. `/drydock:install` writes the line only into a config it
creates, so re-running it does not add the line to yours.

More at once also means more chances to collide: two specs chained onto the
same `branch:` cannot run concurrently, so a series that shares a branch needs
a `depends_on` edge between consecutive members (DISPATCH step 7).

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

When the spec names an `owner:`, that session may run the unblock and decide
instead of you; if it cannot decide, the item stays blocked. Either way the
`## Resolution` opens with a `resolved_by:` line naming who decided — the
session, or `human`.

Then the item goes back to `inbox` and a **fresh** executor picks it up from
the amended spec, the branch, and `RUN.md`. The old session is never resurrected
— see [ARCHITECTURE.md](ARCHITECTURE.md#stateless-handoff) for why.

If `QUESTION.md` is not self-contained enough to decide from, that is itself a
defect worth routing back into the executing skill. Say so when you answer.

## Handing a spec to another session

By default every event and every blocked question comes to you. A spec can
instead name a Claude Code session that answers for it — the session that
wrote it, say, and is still working on the surrounding problem. Like the
concurrency cap, this arrived in 0.5.0 and 0.4.0 does not have it (see
[How many run at once](#how-many-run-at-once) to tell which you have). Add one
line to the spec's frontmatter, the `yaml` block at the top; the template
carries it commented out:

```yaml
owner: ledger-work
```

The value is the session's name as `ListAgents` shows it — the bare name,
without the bracketed `[ref]` a row prints after it. `ListAgents` is a tool a
session calls, not a command you type: to see the names, ask a session on this
machine to list the sessions it can message. drydock does not name the owner
session, and an owner that runs the unblock keeps the name it has. The name
may hold letters, digits, `_`, `.` and `-`, at most 64 characters, starting
with a letter or a digit; a session whose name has a space or any other
character cannot be an owner. No quotes. Write one
`owner:` line, at the start of a line, inside that first block. A
commented-out line, an indented one, or one anywhere else in the spec is not
read, and the spec stays yours. `/drydock:spec` does not ask about an owner
and does not write the line: add it to `<STATE_HOME>/specs/inbox/<id>/SPEC.md`
once the spec is written, before it is dispatched, and commit in STATE_HOME.
To see what the orchestrator will read:

```console
$ python3 <PLUGIN_HOME>/board/queue_rules.py route <STATE_HOME>/specs/inbox/<id>/SPEC.md
owner   ledger-work
```

It prints `human` when there is no owner. A name outside that alphabet, or two
`owner:` lines, makes `route` exit 2, and `queue_rules.py check` reports it as
an `owner:` line, so preflight blocks the spec before it runs and that
blocked event comes to you.

**Permission mode.** The owner session must run in the same permission mode as
the orchestrator's own session — the mode that pane is running in. That is not
necessarily `permission_mode:` in your config, which sets the mode of the
sessions the loop launches. A session in a different mode holds cross-session
messages for its user's approval, may let them expire, or refuses them, and a
held message is not a delivered one. If the loop runs in `bypassPermissions`,
so must the owner; if that is a session you also work in by hand, it then
runs without permission prompts, bounded only by your permission policy.

**What the owner receives.** At each of the four events — `BLOCKED`,
`DELIVERED`, `FAILED` (dispatch failure) and `BUDGET` — the orchestrator runs
`route` on the spec afresh, so an owner added or changed during an unblock
applies from the next event. When a `ListAgents` row carries that exact name,
the orchestrator sends the session a `SendMessage` of two lines: the token,
the item id and a one-line gist of what happened, then the absolute path of
the item's directory. For a blocked item it looks like:

```text
BLOCKED 2026-09-02-transfers-idempotency — Idempotency-Key collision across tenants: reject 409, or scope per tenant?
/Users/you/.drydock/specs/blocked/2026-09-02-transfers-idempotency
```

When that message is delivered you get no notification for the event. That
includes `DELIVERED`: for a spec with a reachable owner nothing tells you its
deliverable is ready, though approving it is still yours. You find it on the
board and in your next `/drydock:review`. The orchestrator's tick report still
carries the paste-ready unblock command for blocked items.

**How the owner unblocks.** The message is those two lines and nothing more:
it does not tell the session to run the unblock. Whether the owner session acts
on a `BLOCKED` line by itself or waits for whoever is driving it is up to that
session and to you. To decide, the owner runs `/drydock:spec unblock <id>` in
its own session, keeping its own name. The skill accepts it as the decider
because the spec names it; a session that says it is the owner is taken at its
word. It decides, writes the answer into `SPEC.md`, appends the
`## Resolution` to `QUESTION.md` with `resolved_by: ledger-work` as its first
line, and moves the item back to the inbox. An owner that cannot decide leaves
the item in `blocked/` and writes nothing; how it gets a decision from there
is outside drydock. You can still run the unblock yourself at any time — the
line then reads `resolved_by: human`. The unblock reads and writes STATE_HOME
(`~/.drydock`, or `$DRYDOCK_STATE_HOME`) on the machine where it runs, so an
owner that is to answer questions has to run where your STATE_HOME is, with
the same `$DRYDOCK_STATE_HOME` if you set one.

**What falls back to you.** The event comes to you as a notification, and the
tick report gets the line `owner <name> unreachable (<reason>); notified
human`, when:

- no `ListAgents` row is named exactly `<name>`;
- the send fails, including an error asking which of two sessions by that
  name was meant;
- a `[Cross-session delivery notice]` arrives before the tick ends saying the
  message was held, refused or expired;
- the send's result says the orchestrator's session has no inbox for such a
  notice (the reason is `no delivery notices`).

A failed `route` — an invalid `owner:`, an unreadable `SPEC.md` — also sends
the event to you, with `route`'s error in the tick report. The three
notifications that carry no event token (a failed `eligible` or `slots` run,
"comments addressed") always come to you, whatever the spec's owner. A
`/drydock:dispatch` you run by hand reports its own outcome — dispatched, or
blocked at preflight — in its chat, not to the owner; the item's later events
are raised by the orchestrator, when one is running, and routed as above.

Three cases do not fall back. A Remote Control, cloud or Claude Desktop
session reports nothing when it holds, refuses or lets a message expire, so
the orchestrator cannot tell the message was not delivered and you are not
notified. A send counts as delivered when no delivery notice arrived before
the end of the tick that sent it, and the contracts give no step for a notice
that arrives later. And a delivered message is only delivered: it reached the
session, which is not the same as the session acting on it, and the
orchestrator does not send it again or follow up. In each case the item stays
where the event left it, on the board. Keep the owner on this machine, in the
loop's permission mode, and treat the board as the record.

**What an owner does not do.** It decides its spec's unblocks and nothing
else. It does not approve or reject deliverables: a `DELIVERED` event tells
the owner the reviewed deliverable is ready, and `/drydock:review` — approve,
reject, and with approval marking a pull request ready — is written for you.
That is a convention, like the unblock's: no skill checks who runs it. The
owner hears only about specs that name it.

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
  normal review, and the item moves to `archive/`. A pull request shared with
  other items (chained through `pr_url:`) stays draft; marking it ready is yours.
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
