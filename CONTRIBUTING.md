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
uvx ruff@0.16.5 check plugin/board/
npx markdownlint-cli2
```

Both run in CI (`.github/workflows/ci.yml`): ruff at the version pinned above,
markdownlint through its GitHub action.

## Testing a contract change

The contracts in `plugin/contracts/` are prose that agents execute. Most of
that prose has no test, and review is its only gate. Some sentences are
pinned: tests in `plugin/board/tests/` find a region of a contract or skill by
its content and assert what it must say.

| Test | What it pins |
|---|---|
| `test_contract_refs.py` | DISPATCH.md's steps are exactly 1–17, with the `8a`–`8c` and `12a`–`12d` labels, and every `step N` citation in `plugin/contracts/` and `plugin/skills/` resolves |
| `test_contract_rules.py` | REVIEWER.md's diff-review verdicts against the board's `static/app.js`; the round-cap rules in REVIEWER.md, DISPATCH step 12 and ORCHESTRATOR.md, and their restatements in `README.md` and `docs/ARCHITECTURE.md`; the repair pass never rewriting a commit |
| `test_contract_liveness.py` | The liveness and branch-drift clauses of DISPATCH steps 5 and 7 and ORCHESTRATOR.md's Active step |
| `test_session_contracts.py` | DISPATCH.md's *Every session* section, the pointers to it from step 8's prompts and REVIEWER.md, and ORCHESTRATOR.md's Hard limits: the loop as a session, and the finished-work clause |
| `test_contract_slots.py` | The concurrency gates (ORCHESTRATOR.md's Inbox step, the dispatch skill's step 1) run `queue_rules.py slots` and state no count; the Hard limits default equals `DEFAULT_MAX_CONCURRENT`; DISPATCH step 7's chained-spec clause names the key and no count |
| `test_contract_owner.py` | The Notifications routing in ORCHESTRATOR.md's Hard limits and every event site's token, DISPATCH step 13, the `owner:` line at every `queue_rules.py check` site (DISPATCH step 1, ORCHESTRATOR.md's preflight bullet, the dispatch skill's step 2), the owner's permission mode, the spec skill's Unblock mode and `resolved_by:`, the retro's citation of it |

`test_owner_route.py`, `test_queue_rules.py` and `test_server.py` also read
`plugin/templates/spec-template.md`.

What none of them checks is whether an agent following the prose does the
right thing, or whether a sentence outside those regions is still true. A
green suite says the pinned sentences are there; it does not review the rest.

If you change a pinned sentence, run the suite. A failure means a test still
expects the old text: when the rule itself changed, change the test in the
same pull request so the new sentence is pinned as the old one was, and name
the assertion you changed in the description. When only the wording changed,
keep the words the test anchors on.

A contract change should say, in the pull request:

- **The run that motivated it.** Which item, which artifact — a `REVIEW.md`
  round, a `QUESTION.md` resolution, a `REJECTION.md` routing. A contract
  amendment with no incident behind it is a preference.
- **What it makes worse.** Every rule fires in cases you did not picture.
  Name the case where this one fires wrongly.
- **Whether any step numbers moved.** `plugin/contracts/DISPATCH.md` numbers
  its steps 1–17 continuously, and `ORCHESTRATOR.md` and `REVIEWER.md` cite
  them by number ("per DISPATCH step 12"). Renumbering means updating the
  callers; `test_contract_refs.py` fails on a citation that no longer
  resolves in the contracts and skills, but not in `README.md` or `docs/`.

A change a user would notice also gets a line under `## [Unreleased]` in
`CHANGELOG.md`.

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

A release is one pull request, then a tag:

1. Set `"version"` in `plugin/.claude-plugin/plugin.json` to the new
   version.
2. In `CHANGELOG.md`, move what is under `## [Unreleased]` into a new
   `## [<version>] — <date>` section, leave under `Unreleased` only what is
   still queued, and update the link references at the bottom.
3. Merge that pull request.
4. Tag the commit it landed as on `main`, and push the tag:

```sh
git tag v<version> <commit> && git push origin v<version>
```

Pushing a `v*` tag runs `.github/workflows/release.yml`, which creates the
GitHub release with generated notes. Those notes list the merged pull
requests by title, not `CHANGELOG.md`, so write the titles accordingly.
Do not create the GitHub release by hand before pushing the tag: the
workflow's `gh release create` fails when a release for that tag already
exists. If the notes need more, edit the generated release afterwards.
