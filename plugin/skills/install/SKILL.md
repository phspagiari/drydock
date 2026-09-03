---
name: install
description: Set up drydock's private state after the plugin has been installed via a marketplace. Use when someone says "/drydock:install", "install drydock", "set up drydock", typically right after `/plugin install drydock@drydock`. Configures STATE_HOME, the branch namespace, permission posture, and verifies the toolchain.
---

# /drydock:install — bootstrap a fresh environment

> **PLUGIN_HOME**: resolve once per invocation as `realpath <this skill's
> base dir>/../..` (the plugin package root Claude Code just installed —
> `contracts/`, `board/`, `templates/`, `examples/` are its siblings). You
> never write here except to read it; it updates only via `/plugin update`.

This is the onboarding. Everything is asked before anything is written; every
write is reported. The plugin's *code* is already installed — this skill's
only job is to create your **STATE_HOME**, the private, remote-less git
repository that holds the queue, and to personalize it.

> If you arrived here by cloning the drydock repo and running
> `claude --plugin-dir ./plugin` — the pre-marketplace install path — stop
> and run `/plugin marketplace add phspagiari/drydock` then
> `/plugin install drydock@drydock` first. That is what makes `/drydock:*`
> commands survive the session and receive updates; this skill assumes it
> already happened.

## 1. Where does your state live?

Ask: **"Where should your drydock state live?"** Default offer:
`~/.drydock` (or `$DRYDOCK_STATE_HOME` if that environment variable is
already set — offer to use it instead of asking again).

This directory is not a clone of anything. It holds only your queue,
deliverables, archive, priors, proposals and config — never the plugin's own
code. Treat it the way you'd treat `~/.aws` or `~/.docker`: a private data
directory, not a project checkout.

- Missing → create it.
- Exists, not yet a git repo → `git init` it now.
- Exists and already a git repo → check `git -C <STATE_HOME> remote -v`.
  **If it prints anything at all, stop and refuse to proceed.** A remote on
  STATE_HOME is the one configuration that turns a private spec into
  something that can be `git push`ed somewhere — public, personal, or just
  the wrong place. Tell them exactly what's configured and ask them to
  either remove the remote (`git -C <STATE_HOME> remote remove <name>`) or
  point STATE_HOME somewhere else. Do not proceed until it prints nothing.
- Exists with unrelated content (not empty, no `specs/`, `deliverables/`,
  `archive/`, `config`) → show what's there and ask before writing into it.

## 2. Personalize

Ask for their **branch namespace** — usually their GitHub/GitLab handle. It
prefixes every branch drydock creates in a target repo
(`<namespace>/drydock-<id>`), which is what keeps the fleet's work
identifiable and separable from human branches.

Ask the **permission posture** question now too (details in step 6) so both
land in the same write. Create `<STATE_HOME>/config`:

```yaml
namespace: <handle>
permission_mode: bypassPermissions   # or acceptEdits, per step 6
```

This file is why nothing about your setup ever needs editing inside the
plugin's own contracts — those are shared, versioned, and updated out from
under you; this one line-per-setting file is yours alone; `git commit` it in
`<STATE_HOME>` (never pushed — see step 1).

## 3. Seed the queue

Create, if missing: `<STATE_HOME>/specs/{inbox,active,blocked}/`,
`<STATE_HOME>/deliverables/`, `<STATE_HOME>/archive/` — all empty.

Copy the seeds once, only if the destination doesn't already exist:
`<PLUGIN_HOME>/contracts/PRIORS.seed.md` → `<STATE_HOME>/PRIORS.md`,
`<PLUGIN_HOME>/contracts/PROPOSALS.seed.md` → `<STATE_HOME>/PROPOSALS.md`.
These live in STATE_HOME from now on — `/plugin update` never touches them
again, which is the point: a prior about someone else's build system was the
old failure mode, and now nothing can silently reintroduce it.

Commit: `install: seed state home` (in `<STATE_HOME>`, never pushed).

## 4. Migrating from the old clone+symlink install

If they used drydock before this refactor: their real queue lives inside a
git clone of the drydock repo itself, registered via a symlink at
`~/.claude/skills/drydock` (or `$CLAUDE_CONFIG_DIR/skills/drydock`) pointing
at `<old-clone>/plugin`. Ask if this applies to them. If so:

1. Find `<old-clone>` (resolve the symlink target's `/../..`).
2. Copy whatever is real (not just `.gitkeep`) from `<old-clone>/specs/`,
   `<old-clone>/deliverables/`, `<old-clone>/archive/`,
   `<old-clone>/contracts/PRIORS.md`, `<old-clone>/contracts/PROPOSALS.md`
   into the matching `<STATE_HOME>` paths from steps 2–3. Preserve item
   directories as-is; do not re-run any spec through preflight again.
3. Recover their old branch namespace from whatever `<namespace>` was
   sed-replaced to inside `<old-clone>/contracts/DISPATCH.md`, and write it
   into `<STATE_HOME>/config`.
4. Commit the import into `<STATE_HOME>` (never pushed):
   `install: import queue from <old-clone>`.
5. Remove the symlink at `~/.claude/skills/drydock` — it is superseded by
   the marketplace install. Tell them `<old-clone>` itself is now just a
   normal git clone; they can delete it, or keep it only if they intend to
   contribute to drydock's own source, in which case it should never again
   be pointed at by a skill symlink or written to by the orchestrator.

No prior install → skip this step entirely, nothing to migrate.

## 5. Verify (fail closed, report a checklist)

- `python3 --version` ≥ 3.10 — the board server.
- `<PLUGIN_HOME>/board/server.py serve --root <STATE_HOME>` boots →
  `curl -sf localhost:8642/healthz` answers → stop it again.
- `git -C <STATE_HOME> status` clean, and `git -C <STATE_HOME> remote -v`
  **still** prints nothing (re-check; step 1 only checked at the start).
  Warn that STATE_HOME's history is unbacked-up by design — offer
  `git bundle create <path> --all` to a location their own backup policy
  already covers, as the recommended way to get durability without ever
  introducing a remote.
- `gh auth status` — needed to open draft PRs, read PR state, and flip
  draft→ready at approval. Missing is a hard warning: without it nothing
  ships.
- `claude --version`, and confirm the install supports `--bg` — executors are
  background sessions. If you can't determine it, say the first dispatch will
  prove it.

## 6. Permission posture — ask, don't assume

Executors run with `--permission-mode bypassPermissions` because a background
session has nobody to answer a prompt. Ask whether they have a permission
policy they trust (deny rules in `settings.json`, a `PreToolUse` hook, or an
equivalent), since that policy is what actually bounds an executor — it loads
per-process in every one.

If they don't, tell them plainly: set `permission_mode: acceptEdits` in
`<STATE_HOME>/config` instead (done back in step 2 — revisit it now if the
answer changes), accept that some runs stall on prompts, and treat that as
the cheaper failure. A stalled run is recoverable; an unreviewed mutation
against live infrastructure is not.

## 7. Hand over

Print the quick-start:

1. `/drydock:spec` in any work session → a spec lands in the inbox.
2. `claude` in a pinned pane, on your longest-running model →
   `/drydock:orchestrate` (opens the board, starts the loop).
3. Blocked and delivered cards on the board carry paste-ready `claude "..."`
   commands; `/drydock:review` is the daily pass.

Point them at `README.md` for the model, `<PLUGIN_HOME>/contracts/` for the
three contracts, and `<PLUGIN_HOME>/examples/example-spec.md` for a spec
that shows every section filled well.
