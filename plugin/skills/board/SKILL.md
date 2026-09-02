---
name: board
description: Start and open the live drydock board (localhost:8642). Use when asked "/drydock:board", "open the board", "show the drydock board", "board status", or "stop the board".
---

# /drydock:board — dashboard control

> **DRYDOCK_HOME**: resolve once per invocation as `realpath <this skill's
> base dir>/../..` (the repo root containing `plugin/`). Every path below is
> relative to it.

The board is `<DRYDOCK_HOME>/board/server.py serve` on
`http://localhost:8642` — localhost-only, reads the queue from disk per
request, nothing to regenerate and nothing published. Normally the
orchestrator keeps it alive; this skill is for direct control from any
session.

## Default (`/drydock:board`, "open the board")

1. `curl -sf localhost:8642/healthz` — if it answers `ok`, skip to 3.
2. Down → start it as a background Bash task:
   `<DRYDOCK_HOME>/board/server.py serve`. Re-check healthz (retry ~2s); if
   still down, read the task output and report the error instead of opening a
   dead page.
3. `open http://localhost:8642` and report one line: board state + queue
   counts from `curl -s localhost:8642/api/state` (blocked / ready / active /
   inbox).

## `/drydock:board status`

Healthz + the counts line. Don't open the browser.

## `/drydock:board stop`

Find the listener (`lsof -ti :8642`) and kill that PID only — never a broader
`pkill`. Confirm the port is free afterwards. Note that the orchestrator's
housekeeping will restart it on a future tick unless that loop is paused too.
