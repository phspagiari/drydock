# CLAUDE.md

drydock is a Claude Code plugin for spec-driven agentic execution: sessions
write specs into a git-backed queue, an orchestrator dispatches executors into
worktrees, and an adversarial reviewer judges the work before any pull request
exists. Its rules are Markdown contracts that agents execute; its code is a
standard-library Python board and the queue predicates those contracts run.

Read [README.md](README.md) for the model, [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
before changing anything structural, and [CONTRIBUTING.md](CONTRIBUTING.md)
for the house rules this file condenses.

## Layout

- `plugin/contracts/` — `ORCHESTRATOR.md`, `DISPATCH.md`, `REVIEWER.md`, and
  the empty `PRIORS.seed.md` / `PROPOSALS.seed.md`.
- `plugin/skills/<name>/SKILL.md` — the `/drydock:*` commands.
- `plugin/templates/` — the spec and plan templates; `plugin/examples/` — a
  worked spec and example priors.
- `plugin/board/` — `server.py` (the board), `queue_rules.py`, `speccheck.py`,
  `pr_text.py`, `priors_check.py`, `split_priors.py`; `static/` is the
  frontend, `tests/` the suite and its fixtures.
- `docs/` — user docs; `docs/design/` holds design notes.

## Test and lint

From the repo root, the checks CI (`.github/workflows/ci.yml`) runs on code
and prose:

```sh
python3 -m unittest discover plugin/board/tests
uvx ruff@0.16.5 check plugin/board/
npx --yes markdownlint-cli2
```

CI runs the suite on Python 3.10, and also runs `actionlint` over the
workflows; run it if you edit `.github/workflows/`. Tests read the contracts,
the skills, the spec template, `README.md` and `docs/ARCHITECTURE.md`, so run
the suite after a prose edit too, not only after a code change.

## Rules that are easy to break

- **Contracts are prose an agent executes, and some sentences are pinned.**
  `test_contract_*.py` and `test_session_contracts.py` find regions by content
  and assert their wording. When you change a pinned rule on purpose, change
  its test in the same pull request and say so; never loosen an assertion to
  get green. CONTRIBUTING.md lists what each test pins.
- **`DISPATCH.md` steps are numbered 1–17 and cited by number** across the
  contracts and skills ("DISPATCH step 12"). Never renumber them;
  `test_contract_refs.py` fails on a dangling citation. MD029 is off for this.
- **One implementation per rule.** Eligibility, markers, chains, owners and
  the concurrency cap live in `queue_rules.py` (`eligible`, `check`, `slots`,
  `route`); contracts run the CLI and never re-derive its answer by hand. The
  cap is `max_concurrent`: the two gates (ORCHESTRATOR's Inbox step, the
  dispatch skill's step 1) and DISPATCH step 7 state no count, and the one
  default a contract writes, in ORCHESTRATOR's Hard limits, is pinned to
  `DEFAULT_MAX_CONCURRENT`.
- **`<PLUGIN_HOME>` is read-only at run time; `<STATE_HOME>` is the user's.**
  STATE_HOME (`~/.drydock` or `$DRYDOCK_STATE_HOME`) is a private local git
  repository that never gets a remote. Work on this repo never reads or
  writes a real one, and no change may add a remote or a push there.
- **Tests never touch a real STATE_HOME.** Build fixtures in a temporary
  directory and pass `--root` or set `DRYDOCK_STATE_HOME` to it.
- **Standard library only, Python 3.10 floor** (`target-version = "py310"`).
  A dependency is a discussion, not a commit.
- **`ruff check`, never `ruff format`.** `plugin/board/` is hand-formatted.
- **This repo carries no queue** (`specs/`, `deliverables/`, `archive/`).
- **No `.html` is committed** outside `plugin/board/static/`; `.gitignore`
  excludes the rest. Stage files by path.
- **A target repo gets no drydock metadata** (DISPATCH step 7), and the docs
  state no version for unreleased work: `plugin/.claude-plugin/plugin.json`
  changes only at a release.

## Commits and pull requests

Subjects start with the area: `contracts:`, `board:`, `docs:`, `tests:`,
`priors:`, `plugin:`, `ci:`. The body says what changed and why.
Record user-visible changes under `## [Unreleased]` in `CHANGELOG.md`.

A pull request fills `.github/PULL_REQUEST_TEMPLATE.md`: what changed; how you
verified it, with the command and what it printed; for a contract change, the
run that motivated it, what the new rule makes worse, and the callers you
updated if a DISPATCH step moved; and whether an agent wrote it.
