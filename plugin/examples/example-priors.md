# Example priors — from real runs, anonymized

`contracts/PRIORS.seed.md` ships empty on purpose: priors encode what *your* repos,
build systems and reviewers keep punishing, and a prior inherited from someone
else's codebase is misinformation to your executors.

The entries below are here as **shape references** — what a prior looks like
when it is worth keeping. They came out of real drydock runs against a large
Go monorepo, with repo names, PR numbers and identities removed. Do not copy
them into your `STATE_HOME`; write your own from your own retros.

What makes each one usable: a named mechanism, the command that proves or
disproves it *today*, the consequence for an executor or reviewer, and the
item that taught it.

Priors are stored **hot plus cold**, and this file shows one of every kind —
the hot `PRIORS.md` that every actor loads, one cold per-repo file that only a
spec targeting that repo pulls in, and the three phase files.
`contracts/DISPATCH.md` step 8 carries the routing rule;
`board/split_priors.py` migrates a file that predates it.

---

## The hot file — `<STATE_HOME>/PRIORS.md`

Global, loaded by every actor on every run, and kept short on purpose: aim
for entries totalling under about 50 lines. Everything here is true whatever
repo the spec targets and whatever phase is running.

```markdown
# PRIORS — distilled lessons from past runs

<!-- retro-cursor: a2e1cc8 -->

## Escalating

- **Read the open PRs before proposing to touch another team's files.** An
  escalation reproduced a live consistency violation rigorously from the git
  tree and recommended extending the blast radius to repair it — while the
  repair was already authored, approved and open as someone else's PR, and
  while the merge commit it cited by SHA said so *in its own body*. One
  `gh pr view <n>` inverts the recommendation from "extend the radius" to
  "wait". A divergence introduced minutes-to-hours ago by a named commit is
  far likelier to be mid-sequence than settled: before proposing to repair
  config another team owns, `gh pr view` the commit that created it and
  `gh pr list --search` the paths.
  *(2026-06-02-inventory-test, QUESTION run 4 resolution — second instance of
  the same shape)*

## The machine drydock runs on

- **Clamshell sleep kills long agent sessions and no `caffeinate` flag stops
  it.** `caffeinate -i`, `-w` and even `-dimsu` suppress **idle** sleep only;
  closing the lid is a separate trigger, and `pmset -g log` names it outright
  (`Entering Sleep state due to 'Clamshell Sleep'`). Three reviewer sessions
  launched inside one such window each died mid-response. A review pass needs
  an uninterrupted 20–50 minutes: lid open on AC power, or run it as a cloud
  session.
  *(2026-06-14-toolchain-repair, QUESTION r5 resolution)*
```

## One cold file — `<STATE_HOME>/priors/<slug>.md`

`<slug>` is the basename of the spec's `target_repo`, so `~/code/ledger-api` becomes
`priors/ledger-api.md`. An executor or reviewer working that repo loads it; one
working any other repo never sees it. The `## Target repo:` heading stays at
the top — it is what the splitter recognises, and keeping it makes a re-split
a no-op.

```markdown
## Target repo: ~/code/ledger-api

- **Lint results depend on where the local default-branch ref points, not on
  the branch under test.** The linter config set
  `issues.new-from-merge-base: main`, and the linter resolved the *literal
  local* ref — not `origin/main`. In a worktree whose parent checkout had
  `main` 171 commits behind, a bare lint run reported other people's merged
  debt as this branch's findings: 9 phantom findings, all pre-existing.
  Before treating any lint output as a finding about the branch, prove the
  precondition — `git rev-list --count main..origin/main` → `0`. Note that
  `git fetch origin main:main` is refused while the parent checkout has
  `main` checked out; fast-forward it there instead.
  *(2026-06-14-toolchain-repair, QUESTION run 2 — an entire escalation
  produced by a stale ref)*

- **A worktree that is clean by `git status` is not a *built* worktree.**
  Generated sources (protobuf output, in this repo) were gitignored, so they
  disappeared between sessions while the tree still read clean; the next lint
  run failed as `could not import …/proto/… (typecheck)`, which looks like a
  code defect and is not. Regenerate before running any lint or build
  criterion in a resumed worktree.
  *(2026-06-14-toolchain-repair, RUN.md S2-T1)*

- **A fixture must not reproduce a path segment that repo tooling keys on.**
  A CI workflow matched `**/migrations/**/*.{hcl,sql,sum}` anywhere in the
  tree and then enforced one-migration-directory-per-PR. Twenty-seven fixture
  trees carrying a literal `migrations/` path segment were enough to fail that
  gate and starve a required downstream check. Parameterise the segment in the
  fixture instead. Before adding any fixture tree, grep the CI workflow
  directory for filters matching its paths.
  *(2026-06-02-inventory-test, REVIEW-r1 Finding 1)*
```

## The phase files

The same shape, filed by *when* a prior is needed rather than by which repo
it is about. `priors/_pr-prose.md` is loaded only at READY, so a lesson like
this one costs an executor nothing until it is writing the PR body:

```markdown
## PR prose is where the defects are

- **The prepared PR body outruns the diff as a defect surface.** Across two
  review rounds on a four-commit toolchain repair, the reviewer found three
  findings and **all three were in READY.md's prepared PR text** — never in
  the code. Two were checkable claims about the reader's own repo (that the
  git hooks ran the linter: one `grep -c` → 0; that the body's first heading
  should follow the repo's PR template, confirmed by 16 of the last 25 merged
  PRs), and one was a checkable claim about an upstream release. Executors:
  every factual assertion in the prepared body is subject to the same citation
  discipline as an acceptance criterion, and "which release was first" / "what
  our hooks run" / "what our template says" are each one command. Reviewers:
  read the body before the diff.
  *(2026-06-14-toolchain-repair, REVIEW-r1 Findings 1–2, REVIEW.md Finding 1)*
```

`priors/_spec-writing.md` and `priors/_review.md` work the same way, for
`/drydock:spec` and for the reviewer respectively:

```markdown
## Spec-writing

- **Phase numbering in a proposal is narrative, not a dependency graph.**
  Encode real ordering in `depends_on`, and say explicitly when a same-family
  spec is independent — so parallel dispatch is a decision, not an accident.
  *(phases 0 / 1.5 parallel-run question)*
```

```markdown
## Review findings that repeat

- **A false claim in prose is repaired repo-wide, not at the sites the
  reviewer enumerated.** Round 1 named three locations of a wrong mechanism
  claim; the fix executor repaired exactly those three, and round 2's *only*
  finding was a fourth — three lines above one of them, now contradicting the
  file it deferred to. Cost: one whole review round for a comment. Fix
  executors: for any finding whose defect is a textual claim, grep the **full
  diff** for the claim's phrasing (`git diff BASE...HEAD | grep -niE '<the
  claim>'`) and repair every survivor before declaring it fixed — the
  reviewer's site list is where it was noticed, not where it lives.
  Reviewers: write the sweep, not the list.
  *(2026-06-02-inventory-test, REVIEW-r1 Finding 2 → REVIEW-r2 Finding 1)*
```

Each block opens with the heading its file carries, and that is not cosmetic:
`## Spec-writing`, `## PR prose …` and `## Review …` are the prefixes
`board/split_priors.py` classifies a section on, so a cold file that keeps its
heading is one a re-split leaves alone.
