# Contributing

drydock is small on purpose. The most useful contributions are a sharper
contract, a prior that saves the next person a review round, or a bug in the
board — in roughly that order.

## Running the board locally

```sh
python3 board/server.py serve            # http://127.0.0.1:8642
python3 -m unittest discover board/tests
```

No install step, no virtualenv, no dependencies. If a change to `board/`
requires adding one, that is the thing to discuss in the issue first — see
House conventions.

Lint before you push:

```sh
uvx ruff check board/
npx markdownlint-cli2
```

Both run in CI (`.github/workflows/ci.yml`) exactly as written above.

## Testing a contract change

The contracts in `contracts/` are prose that agents execute, so they have no
test suite — which makes review the only gate. A contract change should say,
in the pull request:

- **The run that motivated it.** Which item, which artifact — a `REVIEW.md`
  round, a `QUESTION.md` resolution, a `REJECTION.md` routing. A contract
  amendment with no incident behind it is a preference.
- **What it makes worse.** Every rule fires in cases you did not picture.
  Name the case where this one fires wrongly.
- **Whether any step numbers moved.** `contracts/DISPATCH.md` numbers its
  steps 1–17 continuously, and `ORCHESTRATOR.md` and `REVIEWER.md` cite them
  by number ("per DISPATCH step 12"). Renumbering means updating the callers.

`contracts/PROPOSALS.md` is where `/drydock:retro` queues amendments it wants
a human to decide on. If your change is already sitting there as a proposal,
link it.

## House conventions

Stated as rules because contributors guess wrong otherwise:

- **`board/` is standard library only.** The point is that a fresh clone runs
  with no install step. A dependency has to justify losing that.
- **Contracts stay in Markdown.** They are meant to be edited by a human who
  disagrees with them. Nothing in `contracts/` becomes code, YAML, or a
  schema.
- **`board/` is hand-formatted; `ruff format` is not run over it.** `ruff
  check` is the gate. Match the surrounding style rather than reflowing.
- **HTML renders are never committed.** `.gitignore` excludes `*.html`
  outside `board/static/`. Link the `.md`.
- **Queue directories ship empty.** `specs/*`, `deliverables/`, `archive/`
  carry a `.gitkeep` and nothing else — and `contracts/PRIORS.md` ships
  empty too, because a prior from someone else's build system is
  misinformation to your executors.
- **No drydock metadata in a target repo.** The branch and the pull request
  are the entire footprint. This is a hard rule of the model, not a
  preference — see `contracts/DISPATCH.md` step 7.

## Agent-written contributions

Welcome, and worth saying out loud given the premise: say so in the pull
request, and hold the diff to the same bar as anything else. You read it
before we do.

## Release process

Releases are a tag; `.github/workflows/release.yml` does the rest.

```sh
git tag v0.2.0 && git push origin v0.2.0
```

GitHub generates the notes from merged pull requests, so the pull request
titles are the changelog — write them accordingly.
