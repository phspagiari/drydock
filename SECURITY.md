# Security

## Reporting a vulnerability

Report privately through GitHub's
[private vulnerability reporting](https://github.com/phspagiari/drydock/security/advisories/new)
on this repository. Please do not open a public issue for something
exploitable. Expect a first response within a week; this is a solo-maintained
project, not a funded security programme.

## Threat model

Two parts of drydock are worth understanding before you run it, and neither is
a vulnerability — they are what the tool does.

**The board serves file contents from the repo it is pointed at.** `board/server.py`
binds `127.0.0.1` only, and exposes a fixed allowlist of item files
(`SPEC.md`, `QUESTION.md`, `DELIVERABLE.md`, `RUN.md`, `REJECTION.md`,
`REPORT.md`, `REVIEW.md`, `READY.md`) plus the static frontend. There is no
authentication, because there is no network exposure to authenticate. Putting
it behind a tunnel, a reverse proxy, or a `0.0.0.0` bind turns a local
dashboard into an unauthenticated file server for your queue — including
whatever your specs and run logs happen to quote.

**The orchestrator dispatches agents that write to your repositories,
unattended.** Executors run as background Claude Code sessions with
`--permission-mode bypassPermissions`, because a background session has nobody
to answer a permission prompt. That flag does not widen what drydock may do:
each executor is a separate Claude Code process that loads *your*
configuration — your `settings.json` permissions, your `PreToolUse` hooks,
your deny rules — and drydock never routes around them. **Your permission
policy is the boundary.** If you do not have a deny layer you trust, run
executors with `--permission-mode acceptEdits` instead and accept that some
runs stall on prompts. A stalled run is recoverable; an unreviewed mutation
against live infrastructure is not.

What follows from that: a specification is an instruction to an agent with
your credentials. Treat `specs/inbox/` the way you would treat a shell script
someone handed you — reviewing a spec before it is dispatched is the control,
and it is why `/drydock:spec` writes specs rather than executing them.

## In scope

Path traversal or allowlist escapes in `board/server.py`; anything that lets
the board serve a file outside the item directory it was asked for; a contract
path that would cause an executor to act outside a spec's declared blast
radius.

## Not in scope

That the board has no authentication on `127.0.0.1`. That executors run with
elevated permissions. That a specification can instruct an agent to do
something destructive — that is the adopter's permission policy and review
pass, described above.
