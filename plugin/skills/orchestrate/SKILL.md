---
name: orchestrate
description: Start or tick the drydock orchestrator loop. Use when asked "/drydock:orchestrate", "start drydock", "start the orchestrator", or "run a drydock tick". Bare invocation bootstraps and enters a self-paced loop; the "tick" argument runs a single tick (used by the loop itself).
---

# /drydock:orchestrate — the loop

> **DRYDOCK_HOME**: resolve once per invocation as `realpath <this skill's
> base dir>/../..` (the repo root containing `plugin/`). Every path below is
> relative to it.

The orchestrator contract is `contracts/ORCHESTRATOR.md`. **Re-read it on
every invocation** — this is what keeps the running loop current when the
contract changes; never work from a remembered copy.

## Bare invocation (bootstrap)

1. **Duplicate guard**: read `.orchestrator-heartbeat`. If its mtime is under
   45 minutes old, another orchestrator is probably alive — report its age
   and STOP; the human decides whether to proceed anyway.
2. **Model check**: this loop wants your longest-running, highest-context
   model — it re-reads contracts, tracks many items, and lives for hours. If
   the current session is on something smaller, say so in one line, then
   continue; availability beats purity.
3. **Open the board**: ensure it's serving (healthz → start if needed) and
   `open http://localhost:8642` — starting drydock means having the board on
   screen. Bootstrap only; ticks never re-open it.
4. Run one tick (below).
5. Continue self-paced: re-invoke yourself as `/drydock:orchestrate tick` on
   a loop with no fixed interval (the `loop` skill, a scheduler, or whatever
   your setup provides). Pacing per `contracts/ORCHESTRATOR.md` — 20–30 min
   idle, ~10 min with active executions, never subminute.

## `tick` argument (one tick, called by the loop)

Re-read `contracts/ORCHESTRATOR.md` and execute exactly one pass of "Each
tick": inbox dispatch → active verification → housekeeping (board healthz,
repo push, touch `.orchestrator-heartbeat`) → notify per policy. Nothing to
do → report noop so the loop collapses it. Remember that a tick is noop only
*after* housekeeping ran — the PR sweeps and session reconciliation are never
skippable.

## Rules

- One orchestrator per machine — the heartbeat guard is not optional.
- This skill never answers escalations and never reviews deliverables; those
  are `/drydock:spec unblock` and `/drydock:review`, in other sessions.
- Never dispatch executors with the Agent tool. They are independent
  background CLI sessions (`claude --bg`) — in-process subagents bloat this
  session, die with it, and are invisible to the session list.
- Stopping: the human stops the loop (or asks this session to); on stop,
  remove `.orchestrator-heartbeat`.
