# Security

## Reporting a vulnerability

Report privately through GitHub's
[private vulnerability reporting](https://github.com/phspagiari/drydock/security/advisories/new)
on this repository. Please do not open a public issue for something
exploitable. Expect a first response within a week; this is a solo-maintained
project, not a funded security programme.

## Threat model

Four parts of drydock are worth understanding before you run it, and none is
a vulnerability — they are what the tool does.

**The board serves file contents from the STATE_HOME it is pointed at.**
`plugin/board/server.py` binds `127.0.0.1` only, and exposes a fixed
allowlist of item files (`SPEC.md`, `QUESTION.md`, `DELIVERABLE.md`,
`RUN.md`, `REJECTION.md`, `REPORT.md`, `REVIEW.md`, `READY.md`) plus the
static frontend. There is no authentication, because there is no network
exposure to authenticate. Putting it behind a tunnel, a reverse proxy, or a
`0.0.0.0` bind turns a local dashboard into an unauthenticated file server
for your queue — including whatever your specs and run logs happen to quote.

**STATE_HOME (`~/.drydock` by default) is never given a git remote.**
`/drydock:install` refuses to proceed if one is already configured there,
and every skill and contract that touches STATE_HOME treats a remote
appearing later as a hard stop. This is deliberate: STATE_HOME is where your
specs — which can quote internal systems, credentials-adjacent context, or
anything else your teammates shouldn't read — accumulate as git history.
Before this was a separate, remote-less directory, `/drydock:install` cloned
the drydock tool itself and the same clone doubled as the queue; a `git push`
from that clone, whether by habit or by the orchestrator's own housekeeping,
could have sent that history to whatever remote the clone happened to have —
including this project's own, if you'd also cloned it to contribute a fix.
Get durability without a remote via `git bundle create <path> --all` to
storage your own backup policy already covers.

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
your credentials. Treat `STATE_HOME/specs/inbox/` the way you would treat a
shell script someone handed you — reviewing a spec before it is dispatched is
the control, and it is why `/drydock:spec` writes specs rather than executing
them.

**A spec's `owner:` line hands part of your role to another session.** On
`main` (the released 0.4.0 does not read the line), a spec that names
`owner: <session-name>` sends its blocked, delivered, dispatch-failure and
budget events to whichever session `ListAgents` lists under that name, by
`SendMessage`, and lets that session decide the item's unblocks. Three things
follow:

- **The name is an address, not an identity.** The message goes to the session
  listed under that name when the event happens, and an owner may be a Remote
  Control, cloud or Claude Desktop session as well as one on this machine.
  Each message carries the item's id, a one-line gist of what happened and
  the item's absolute path in STATE_HOME, so an owner that is not on this
  machine is sent that text off it.
- **The unblock takes a session's word that it is the owner**, as it takes
  yours at the keyboard, and `resolved_by:` records what the deciding session
  wrote, not a verified identity. An owner that decides edits `SPEC.md` —
  requirements, criteria, budget, and nothing stops it changing the blast
  radius or the frontmatter in the same edit — and re-queues it, and the next
  executor runs the amended spec with your credentials before you have read
  it. The amendment is an `unblock: <id>` commit in STATE_HOME, the executor
  is still bounded by your permission policy, and the result still goes
  through the adversarial review before it ships. Approving a deliverable —
  for a pull request, marking the draft ready for your team — is not handed to
  the owner: no event asks it to, and `/drydock:review` is written for you.
  That is a convention, as the unblock's is; no skill checks who is running
  it.
- **Delivery is confirmed only where it can be.** Anything short of a
  confirmed delivery comes to you instead, except a message held or refused by
  a Remote Control, cloud or Claude Desktop session, which reports nothing,
  and a delivery notice that arrives after the tick that sent the message,
  which no step handles: that event may reach no one, and the item waits on
  the board. A confirmed delivery means the message reached the session, not
  that anything acted on it. Run the owner on this machine, in the
  orchestrator's permission mode — and note what that means when the loop
  runs in `bypassPermissions`: the owner session then runs without permission
  prompts too, bounded only by your permission policy.

Name as owner only a session you would let answer the question in your place.

## In scope

Path traversal or allowlist escapes in `plugin/board/server.py`; anything
that lets the board serve a file outside the item directory it was asked
for; a contract path that would cause an executor to act outside a spec's
declared blast radius.

## Not in scope

That the board has no authentication on `127.0.0.1`. That executors run with
elevated permissions. That a specification can instruct an agent to do
something destructive — that is the adopter's permission policy and review
pass, described above.
