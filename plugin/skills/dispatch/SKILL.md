---
name: dispatch
description: Dispatch one drydock spec for execution. Use when asked "/drydock:dispatch <id>", "dispatch <id>", "run that spec", or after an unblock when immediate re-dispatch is wanted instead of waiting for the orchestrator tick.
---

# /drydock:dispatch — execute one spec

> **PLUGIN_HOME**: resolve once per invocation as `realpath <this skill's
> base dir>/../..` (the plugin package root — `contracts/`, `board/`,
> `templates/` are its siblings). **STATE_HOME**: `~/.drydock`, or
> `$DRYDOCK_STATE_HOME` if set — the queue, deliverables, archive.

Manual, single-spec version of the orchestrator's dispatch step. The contract
is `<PLUGIN_HOME>/contracts/DISPATCH.md` — re-read it every invocation; this
skill only adds argument handling on top.

## Argument

- `<id>` given → that spec in `<STATE_HOME>/specs/inbox/<id>/`.
- No id and exactly one spec in inbox → that one, after naming it.
- No id and several → list them (id, title, age) and ask which. Never pick.

## Procedure

1. If 2+ executions are already in `<STATE_HOME>/specs/active/`, say so and
   get explicit go-ahead before adding a third (the orchestrator's
   concurrency cap applies to humans too).
2. Run the `<PLUGIN_HOME>/contracts/DISPATCH.md` preflight, fail closed.
   Unresolved `[NEEDS CLARIFICATION]` → `<STATE_HOME>/specs/blocked/<id>/` +
   `QUESTION.md`, commit in `<STATE_HOME>` (never pushed), report — do not
   execute.
3. Move to `<STATE_HOME>/specs/active/<id>/`, commit `dispatch: <id> -> active`.
4. Worktree per DISPATCH.md, branch `<namespace>/drydock-<id>` (namespace
   from `<STATE_HOME>/config`) off the target repo's default branch, from a
   freshly fetched base.
5. Launch the executor as an independent background session:
   `cd <worktree> && claude --bg --model <model> --permission-mode
   <permission-mode> "<DISPATCH step-8 prompt>"` — model from the routing
   table, permission mode from `<STATE_HOME>/config`, both in
   `<PLUGIN_HOME>/contracts/ORCHESTRATOR.md`.
6. Verify the session actually started (ListAgents / `claude agents` /
   process), then report one line: id, model, worktree, and where to watch
   (`claude agents`, `/drydock:board`).

Do NOT wait for the execution to finish — dispatch-and-return. Completion
lands on the board and in notifications (or the orchestrator's next tick
verifies it).
