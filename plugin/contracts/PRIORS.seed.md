# PRIORS — distilled lessons from past runs

> This is the **seed** copied to `<STATE_HOME>/PRIORS.md` once, by
> `/drydock:install`. It is part of the plugin package and gets overwritten
> on `/plugin update` — the live file your executors read and your retros
> append to lives in `<STATE_HOME>` (`~/.drydock` by default), never here.

This file is the **hot** half of the priors. It is global, every actor loads
it on every run, and that is what makes its entries expensive: aim to keep
them under about 50 lines in total. The target is advisory — nothing enforces
it — but a hot file that grows without bound is the problem the split was
made to fix.

The **cold** halves live in `<STATE_HOME>/priors/` and load conditionally:

| File | Loaded by | Section heading inside it |
|---|---|---|
| `priors/<slug>.md` | the executor and the reviewer, when the spec's `target_repo` matches. `<slug>` is the path's basename — `~/code/ledger-api` → `priors/ledger-api.md` | `## Target repo: <path>` |
| `priors/_spec-writing.md` | `/drydock:spec`, never an executor | `## Spec-writing` |
| `priors/_pr-prose.md` | the executor at READY (DISPATCH step 11) | `## PR prose …` |
| `priors/_review.md` | the reviewer | `## Review …` |

That third column is not decoration: it is what `board/split_priors.py`
classifies a section on, so keeping it at the top of each cold file is what
keeps a later re-split a no-op. The three phase headings are matched on
their prefix, so a tail is welcome (`## PR prose is where the defects are`).

`/drydock:retro` reads all of them and decides which one a new prior belongs
in; `contracts/DISPATCH.md` step 8 carries the loading rule itself. Two target
repos whose paths end in the same basename share one cold file — a known
limitation of slugging on the basename, and one worth renaming a checkout
over if you ever hit it.

Read by every executor (before work) and every reviewer (while grounding).
Appended by `/drydock:retro`, which mines QUESTION.md resolutions, REVIEW
findings, and REJECTION routings since the last retro. Every entry cites the
item that taught it. Entries are advisory knowledge — rules live in the
contracts.

<!-- retro-cursor: HEAD -->

<!--
  This file ships empty on purpose. Priors are yours: they encode what YOUR
  target repos, build systems and reviewers keep punishing, and a prior
  inherited from someone else's codebase is misinformation.

  Shape of an entry. In this hot file it sits under a topic heading; in a
  cold repo file it sits under that file's `## Target repo: <path>` heading,
  which is also what the splitter recognises:

    - **[<slug>/<key>]** **One-sentence claim in bold.** The mechanism,
      concretely enough that a fresh executor can act on it — including the
      command that proves or disproves it today.
      *(<item-id>, <artifact that taught it>)*
      - scope: <target repo path, or global>
      - derived_from: <item-id>
      - depends_on: <what would make the prior obsolete, as a checkable
        fact; backtick the paths it rests on, e.g. `.git/worktrees/**`>
      - asserted: <YYYY-MM-DD>

  `<slug>` is the repo's cold-file slug, or `global` in this hot file. A
  bullet without the four sub-bullets is a legacy prior: still legal, read
  as `depends_on: unknown`. A cold repo file may also carry one
  `<!-- code-cursor: <full sha> -->` line under its heading, the repo commit
  its priors were last validated against; `board/priors_check.py` reads it,
  and only `/drydock:retro` advances it.

  See `examples/example-priors.md` for worked entries from real runs.

  Prune aggressively: a prior the corpus shows to be wrong or obsolete is
  worse than no prior. Note why in the commit that removes it.
-->
