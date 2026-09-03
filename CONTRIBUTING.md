# Contributing

drydock is small on purpose. The most useful contributions are a sharper
contract, a prior that saves the next person a review round, or a bug in the
board — in roughly that order.

## Running the board locally

```sh
python3 plugin/board/server.py serve --root /tmp/some-fixture-queue
python3 -m unittest discover plugin/board/tests
```

No install step, no virtualenv, no dependencies. If a change to
`plugin/board/` requires adding one, that is the thing to discuss in the
issue first — see House conventions.

Lint before you push:

```sh
uvx ruff check plugin/board/
npx markdownlint-cli2
```

Both run in CI (`.github/workflows/ci.yml`) exactly as written above.

## Testing a contract change

The contracts in `plugin/contracts/` are prose that agents execute, so they
have no test suite — which makes review the only gate. A contract change
should say, in the pull request:

- **The run that motivated it.** Which item, which artifact — a `REVIEW.md`
  round, a `QUESTION.md` resolution, a `REJECTION.md` routing. A contract
  amendment with no incident behind it is a preference.
- **What it makes worse.** Every rule fires in cases you did not picture.
  Name the case where this one fires wrongly.
- **Whether any step numbers moved.** `plugin/contracts/DISPATCH.md` numbers
  its steps 1–17 continuously, and `ORCHESTRATOR.md` and `REVIEWER.md` cite
  them by number ("per DISPATCH step 12"). Renumbering means updating the
  callers.

`PROPOSALS.md`, in a user's own `STATE_HOME` (`~/.drydock` by default, never
in this repo), is where `/drydock:retro` queues amendments it wants a human
to decide on — a proposal a user brings you is evidence for a contract PR,
not something this repo stores itself.

## House conventions

Stated as rules because contributors guess wrong otherwise:

- **`plugin/board/` is standard library only.** The point is that installing
  the plugin needs no install step of its own. A dependency has to justify
  losing that.
- **Contracts stay in Markdown.** They are meant to be edited by a human who
  disagrees with them. Nothing in `plugin/contracts/` becomes code, YAML, or
  a schema.
- **`plugin/board/` is hand-formatted; `ruff format` is not run over it.**
  `ruff check` is the gate. Match the surrounding style rather than
  reflowing.
- **HTML renders are never committed.** `.gitignore` excludes `*.html`
  outside `plugin/board/static/`. Link the `.md`.
- **This repo never carries anyone's queue.** `specs/`, `deliverables/`,
  `archive/` don't exist here at all — they're created fresh in each user's
  own `STATE_HOME` (`~/.drydock` by default) by `/drydock:install`, which is
  also why `PRIORS.seed.md` and `PROPOSALS.seed.md` in
  `plugin/contracts/` ship empty: a prior from someone else's build system
  is misinformation to your executors, and this repo is "someone else" to
  every user.
- **No drydock metadata in a target repo.** The branch and the pull request
  are the entire footprint. This is a hard rule of the model, not a
  preference — see `plugin/contracts/DISPATCH.md` step 7.
- **`STATE_HOME` never gets a remote.** Every skill and contract that touches
  it treats a configured remote as a hard stop, not a warning. If you're
  changing install or the contracts, preserve that invariant — it's the
  entire reason a user's specs can't end up in a public pull request by
  accident.

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
