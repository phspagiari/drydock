# FAQ

## Why isn't this a framework?

Because the hard part is not orchestration, it is judgment — and judgment lives
in the rules, not the runtime.

drydock's rules are five Markdown files in [`contracts/`](../contracts/). They
are read by agents, edited by humans, versioned in git, and re-read on every
invocation. Change `REVIEWER.md` and the next review behaves differently,
including for a loop that is already running. No deploy, no restart, no schema
migration, no plugin API.

A framework would have to encode "delivering with caveats is forbidden" as
code. As prose it takes four lines, it is legible to the person who has to live
with it, and it can be argued with — which matters, because most of these rules
are wrong in some case you have not hit yet. When you find that case, you edit
a paragraph.

The parts that genuinely benefit from being code *are* code: the board is a
small Python server, because rendering a queue as HTML is mechanical.

## Why is git the state machine?

A spec's directory location is its state. Transitions are `git mv` plus a
commit. There is no database, no scheduler, no daemon, no lock table.

This buys four things that are expensive to build otherwise:

- **Restartability.** Every actor can die at any moment; state is on disk. The
  next tick re-derives everything from directory locations, file mtimes and
  live session liveness.
- **An audit log you already know how to read.** `git log --follow` on an item
  directory answers "what happened to this" with no query language.
- **Rules that can change mid-flight**, because they are versioned alongside
  the state they govern.
- **Backup for free.** Push the repo; your queue's full history is backed up by
  the same mechanism as your code.

What it costs: transitions are not atomic the way a transaction is, ordering
has to be derived deterministically rather than assumed, and concurrency is
bounded by convention rather than locks. For a queue whose items take tens of
minutes and whose operator is one person, those are cheap.

The ordering point is worth spelling out, because it looks like a bug until you
see it: the inbox is sorted **lexicographically by id, never by mtime**. Every
move the queue makes rewrites mtime, so mtime ordering would silently reshuffle
the queue every time anything happened. Spec ids start with a date for exactly
this reason.

## What does this cost to run?

Meaningfully more than working interactively, and the honest framing is that
you are trading tokens for your own attention.

Where it goes, in rough order:

- **Executors** dominate. Each is a full Claude Code session doing real work in
  a worktree, typically on your code-tier model.
- **Review rounds** are the second line item, and they are the point. A `fix`
  round costs a review plus a fix executor — and saves a human round trip
  through a pull request, which is the expensive thing being optimised.
- **The orchestrator** is cheap per tick but runs for hours. It re-reads its
  contracts every tick by design, which is a real recurring cost paid on
  purpose so a contract edit takes effect immediately. Tick pacing is
  deliberately slow — 20–30 minutes idle, ~10 with work active, never
  sub-minute — because executor completions arrive as notifications anyway.
  Ticks are the fallback, not the signal.
- **Per-item retros** are one short session per ship.

The controls are in the spec's `budget` block (`max_agents`, `max_wall_clock`,
`max_criteria_retries`), the hard cap of two concurrent executions, the review
round cap of 2, and the model routing table in
[`ORCHESTRATOR.md`](../contracts/ORCHESTRATOR.md) — which exists so `report`
work does not run on a code-tier model.

The thing that actually blows a budget is not the loop; it is a spec whose
acceptance criteria cannot be satisfied, burning retries and review rounds
before escalating. Criteria scoped to your diff, and at least one that encodes
intent, are the cost control.

## How does the permission posture work?

Executors launch with `--permission-mode bypassPermissions`. This is the part
people are right to stop and ask about.

It suppresses the interactive permission **prompt** — necessary, because a
background session has nobody to answer one, and a run that stalls on a prompt
nobody sees is worse than useless. It does **not** widen what drydock may do.

Each executor is a separate Claude Code process. It loads *your* configuration
independently: your `settings.json` permissions, your `PreToolUse` hooks, your
deny rules. Whatever policy you enforce interactively is enforced inside every
executor, per process, and drydock never routes around it. If your setup blocks
mutating infrastructure verbs, that block holds inside executors too — the
contracts say so explicitly, for the orchestrator, the executors and the
reviewer alike.

**So your permission policy is the boundary, and if you don't have one, drydock
does not give you one.** `/drydock:install` asks about this directly. If the
answer is no, run executors with `--permission-mode acceptEdits` and accept
that some runs stall. A stalled run is recoverable; an unreviewed mutation
against live infrastructure is not.

One thing follows that is easy to miss: **a spec is an instruction to an agent
holding your credentials.** Reviewing a spec before dispatch is a real control,
and it is why `/drydock:spec` writes specs instead of executing them. See
[SECURITY.md](../SECURITY.md).

## Can I run this against a repo my team owns?

Yes — that is the design target, and it is why the **zero-metadata rule**
exists.

A repository drydock works on carries no drydock metadata at all. No spec files
committed there, no labels, no tags, no registry. The branch
(`<namespace>/drydock-<id>`) and the pull request are the entire footprint. Your
colleagues see a branch and a well-formed PR in the house style; nothing in the
diff, the description or the commits mentions a spec id or a drydock path.

That is enforced in three places rather than left to good intentions:
[`DISPATCH.md`](../contracts/DISPATCH.md) step 7 states the rule, step 11 makes
the executor discover the target repo's PR conventions (its PR template, its
contributing docs, recently merged human PRs) and forbids drydock terminology
in PR content, and the reviewer checks for leaked terminology on every pass.

The bookkeeping lands on drydock instead: the drydock repo is the sole registry
of which PRs are yours, and PR state is read back per **recorded URL**, never by
scanning the target repo's PR list — scanning would pick up your teammates'
work.

Keep your drydock repo private if your specs quote things your teammates should
not read. The queue is a git repo like any other.

## Does the pull request say a robot wrote it?

Not unless you say so. drydock puts nothing in the PR about its own existence,
and the attribution question is yours to answer by your team's norms — the
mechanism just doesn't decide it for you.

What the PR *does* carry is a title and body written to your repo's conventions
and shipped verbatim from `READY.md`, on work that has already survived an
adversarial review round.

## Why doesn't the agent just open a PR and let me review it there?

Because a pull request is a review artifact, and reviewers read diffs, not
preambles. A deliverable that is 90% right with the remaining 10% explained in
the description gets merged with the 10% unread. That is the failure mode of
every autonomous pipeline.

So drydock forbids the caveat entirely — the zero-calls gate — and moves both
the questions and the mechanical review to *before* the PR exists. Questions
become blocked items you answer in a conversation with full context. Reviewer
findings become fix rounds in the same worktree: no PR churn, no force-push
history, no notification to your team.

By the time you see a PR, the number of decisions it still needs from you is
zero. That is the whole idea, and it is where the name comes from.

## Why is `PRIORS.md` empty?

Because a prior inherited from someone else's codebase is misinformation to
your executors. It will be cited confidently, and it will be wrong.

Priors encode what *your* repos, build systems and reviewers keep punishing —
the lint rule that depends on where your default-branch ref points, the test
target that is flaky on a cold cache. `/drydock:retro` writes them from your own
runs, each citing the item that taught it and the command that proves or
disproves it today.

[`examples/example-priors.md`](../examples/example-priors.md) has four
anonymized entries as shape references. Read them for the shape; do not copy
them into `contracts/PRIORS.md`.

Prune aggressively, too. A prior the evidence has made obsolete is worse than
no prior, and the retro is instructed to remove those and say why in the commit.

## Can drydock change its own rules?

It can propose them; it cannot apply them.

`/drydock:retro` runs automatically after every ship and sorts what it finds
into three tiers. **Priors** it appends directly — they are advisory knowledge,
not policy. **Rule changes** go to
[`PROPOSALS.md`](../contracts/PROPOSALS.md) with the motivating evidence, what
it cost in escalations and rounds, a suggested diff, and the case where the new
rule fires wrongly. A human applies or declines them, in the review pass or a
full sweep. **Skill defects** go back into the skill that produced them.

The separation is deliberate. A system that rewrites its own governing rules
without a human in the loop is one bad inference away from drifting somewhere
nobody chose. A proposal with no stated cost is recorded as a preference, not a
proposal.

## What kinds of work is this actually good for?

The eligibility test is not "is it easy" — it is **can every acceptance
criterion be written as a command runnable without you.**

That test admits a lot of well-specified work with a real verifier: a
behavioural change with a test that proves the behaviour, a migration with a
reversibility check, a report whose query is written and whose output shape is
agreed. It excludes work whose definition of done is a judgment call — most
exploratory design, anything where you would know it when you see it, and
anything whose verifier does not exist yet.

That last case is not a rejection, it is a queue: build the verifier, then the
work becomes eligible. It is also how drydock is meant to grow. The model
routing table ships with two tracks, `code` and `report`, and adding a third is
one row there plus a matching `track:` value in the spec template — but only
once that track's acceptance criteria are executable. Until the verifier
exists, that work stays interactive.

## Can I use it with a coding agent that isn't Claude Code?

Not as it stands. The skills are Claude Code plugin skills, and the orchestrator
dispatches `claude --bg` sessions and verifies liveness through Claude Code's
session list.

The *model* is portable — a git-backed queue, Markdown contracts, worktree
isolation, review before the PR — and the contracts are plain prose that
describes it. Porting means reimplementing the dispatch and liveness layer for
another agent. Nothing in `contracts/` would have to change much.
