---
name: install
description: Set up drydock in a fresh Claude Code environment. Use when someone says "/drydock:install", "install drydock", "set up the drydock plugin", typically right after cloning the drydock repo. Configures the repo location, branch namespace, skills symlink, and verifies the toolchain.
---

# /drydock:install — bootstrap a fresh environment

> **DRYDOCK_HOME**: resolve once per invocation as `realpath <this skill's
> base dir>/../..` (the repo root containing `plugin/`). If that resolution
> fails, this skill is running outside a drydock clone — ask where the clone
> is (or clone it now) and work from there.

This is the onboarding. Everything is asked before anything is written; every
write is reported. Nothing installs outside the clone except one symlink.

## 1. Where does drydock live?

Ask: **"Where should your drydock home be?"** Default offer: the current
clone location (DRYDOCK_HOME). If they name a different path, move or
re-clone the repo there and re-resolve DRYDOCK_HOME. The repo IS the
system — queue, contracts, board, plugin.

## 2. Personalize the branch namespace

Ask for their **branch namespace** — usually their GitHub/GitLab handle. It
prefixes every branch drydock creates in a target repo
(`<namespace>/drydock-<id>`), which is what keeps the fleet's work
identifiable and separable from human branches.

Replace every literal `<namespace>` occurrence in:

- `contracts/DISPATCH.md`
- `contracts/ORCHESTRATOR.md`
- `plugin/skills/dispatch/SKILL.md`

Show the diff, then commit `install: branch namespace <handle>`.

## 3. Fresh queue

If this clone carries someone else's queue (`specs/inbox`, `specs/active`,
`specs/blocked`, `deliverables/`, `archive/` non-empty beyond `.gitkeep`):
offer to **reset it** — empty those directories, keep `.gitkeep`, commit
`install: fresh queue`. Never reset without asking; their answer may be
"keep it, I want to read the history".

Also offer to blank `contracts/PRIORS.md` back to its header if it carries
entries from another environment — a prior about someone else's build system
is misinformation to your executors. Point them at `examples/example-priors.md`
for what good entries look like.

## 4. Register the plugin

Symlink the plugin dir into the skills directory:

```sh
ln -s <DRYDOCK_HOME>/plugin ~/.claude/skills/drydock
```

Respect `$CLAUDE_CONFIG_DIR` if set. If the link already exists and points
elsewhere, show both targets and ask before replacing it. Commands appear as
`/drydock:*` in the next session — tell them to restart or `/reload-plugins`.

## 5. Verify (fail closed, report a checklist)

- `python3 --version` ≥ 3.10 — the board server.
- `<DRYDOCK_HOME>/board/server.py serve` boots →
  `curl -sf localhost:8642/healthz` answers → stop it again.
- `git -C <DRYDOCK_HOME> status` clean; warn if there is no remote — the
  queue's git history is the audit log, and backing it up is theirs to
  arrange.
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

If they don't, tell them plainly: run executors with `--permission-mode
acceptEdits` instead (edit `contracts/ORCHESTRATOR.md`), accept that some runs
stall on prompts, and treat that as the cheaper failure. A stalled run is
recoverable; an unreviewed mutation against live infrastructure is not.

## 7. Hand over

Print the quick-start:

1. `/drydock:spec` in any work session → a spec lands in the inbox.
2. `claude` in a pinned pane, on your longest-running model →
   `/drydock:orchestrate` (opens the board, starts the loop).
3. Blocked and delivered cards on the board carry paste-ready `claude "..."`
   commands; `/drydock:review` is the daily pass.

Point them at `README.md` for the model, `contracts/` for the three
contracts, and `examples/example-spec.md` for a spec that shows every section
filled well.
