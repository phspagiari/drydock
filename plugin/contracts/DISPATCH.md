# DISPATCH — execution and landing procedure

The procedure that takes one spec from the inbox to a landed deliverable.
The orchestrator follows it automatically; `/drydock:dispatch <id>` follows it
manually for a single spec. Anything ambiguous here becomes ambiguous in a
running loop, so fix it here first.

> `<PLUGIN_HOME>` is where Claude Code installed the drydock plugin —
> read-only, resolved by every skill from its own location, updated only via
> `/plugin update`. `<STATE_HOME>` is `~/.drydock` (or `$DRYDOCK_STATE_HOME`
> if set) — the queue, deliverables, archive, priors and proposals. It is a
> plain local git repository with **no remote, ever**: nothing here should be
> pushable anywhere, by design. `<namespace>` is the branch namespace read
> from `<STATE_HOME>/config` (set at `/drydock:install`).

## Preflight (fail closed — abort loudly on any miss)

1. Spec exists in `<STATE_HOME>/specs/inbox/<id>/SPEC.md`; frontmatter parses;
   `track`, `target_repo`, `deliverable`, `budget` all present. The optional
   chain fields, if present, must form a legal pair: `pr_url:` requires
   `branch:` (there is no way to push to a pull request without naming the
   branch it tracks), and `branch:` is never the branch every other spec is
   cut from — `main` or `master` is what the board rejects by name, but the
   rule is the target repo's default branch whatever it is called, because
   chaining onto it is just committing to it. The board applies those two
   rules to every card, so a malformed chain is visible before dispatch
   reaches it.
2. **Zero unresolved `[NEEDS CLARIFICATION]` markers.** If any → move to
   `<STATE_HOME>/specs/blocked/<id>/` with `QUESTION.md`; do not execute.
3. Every acceptance-criterion command is runnable from the worktree (tools
   exist, credentials fresh — re-authenticate now, not mid-run).
4. `target_repo` clean enough to branch from its default branch.
5. **Fresh base, always**: `git -C <target_repo> fetch origin`, then update
   the local default branch — `git -C <target_repo> pull --ff-only origin
   <default>` (ff-only: if it can't fast-forward because the checkout is
   dirty or diverged, don't force it — branch from `origin/<default>`
   directly and note it in RUN.md). No branch is ever created from a stale
   base.
   **A spec that declares `branch:` waives this against the default branch** —
   it is deliberately basing on work already in flight, so "fresh off
   `<default>`" is not what it asked for. The guarantee is replaced, not
   dropped: after the same `fetch`, three ordered checks decide it.

   - `git -C <target_repo> rev-parse --verify --quiet
     refs/remotes/origin/<branch>` fails → the declared branch has **no
     remote counterpart**. Escalate.
   - `git -C <target_repo> rev-parse --verify --quiet refs/heads/<branch>`
     fails → there is **no local ref**, which is fine, not a fault. That is
     the ordinary shape of a branch pushed from another machine or by someone
     else — the case this feature exists to chain onto. Step 7's `git worktree
     add <path> <branch>` cuts it from `origin/<branch>`, which is by
     construction fresh. Proceed.
   - The local ref exists → `git -C <target_repo> rev-list --count
     <branch>..origin/<branch>` must print `0`. Anything else means the local
     ref is **behind its remote**. Escalate.

   Do not collapse those into the bare `rev-list` alone: it exits 128 when
   `<branch>` has no local ref, which makes this preflight strictly more
   restrictive than the step 7 machinery it guards and blocks a chain that
   would have worked.
   An escalation here goes by step 2's route:
   `<STATE_HOME>/specs/blocked/<id>/` with a `QUESTION.md`, before anything is
   executed. Never base on it anyway and never quietly fast-forward it. The
   reason the waiver needs a replacement rather than nothing: basing on a
   stale ref does not fail loudly, it fails as findings that belong to other
   people's commits, and that has already cost a whole escalation round here.
   A spec that also declares `pr_url:` gets one more proof here, because the
   ship step will push into that pull request rather than open one: `gh pr
   view <pr_url> --json state,headRefName` must report `state` `OPEN` and a
   `headRefName` equal to the declared `branch:`. A closed pull request or a
   head-ref mismatch escalates the same way. Opening a new pull request
   instead is not a fallback — it is the outcome the declaration exists to
   prevent.

## Execute

6. Move `<STATE_HOME>/specs/inbox/<id>/` → `<STATE_HOME>/specs/active/<id>/`;
   commit the move in `<STATE_HOME>`'s own git repo. This commit is never
   pushed — `<STATE_HOME>` has no remote.
7. Create an isolated worktree of `target_repo`, branch named per that repo's
   personal-namespace convention (default `<namespace>/drydock-<id>`).
   The worktree persists until the item lands or aborts — review and fix
   rounds happen inside it.
   **Items that name a branch** — a re-queued item that already owns a PR
   (spec/DELIVERABLE records a `pr_url`), or any spec whose frontmatter sets
   `branch:` to chain onto work in flight: reuse that branch (`git worktree
   add <path> <branch>`) instead of creating one, and where a `pr_url` is
   recorded too, push to the SAME PR at ship — never a new branch or PR.
   Either way, **record the commit the worktree starts at** in RUN.md as
   `base_sha: <sha>` (`git -C <path> rev-parse HEAD`). That sha, not the
   default branch, is what the review (REVIEWER.md step 3) and every later
   fix round diff against, so a chained spec is judged on its own delta
   rather than on everything its base branch already carried.
   **Two specs chaining onto the same `branch:` cannot be dispatched
   concurrently.** Git allows one worktree per branch, so the second
   `git worktree add <path> <branch>` dies with exit 128 (`fatal: '<branch>'
   is already used by worktree at …`) — a raw git error, not a drydock
   escalation — and the orchestrator runs up to 2 executions at once. For a
   series, which is the only reason chaining exists, a `depends_on` edge
   between consecutive members that share a branch is therefore a
   **correctness requirement, not a convention**; they must be serialised.
   Nothing validates that today. Whoever writes the series owns it.
   **Repo-agnostic rule:** the target repo carries zero drydock metadata —
   no labels, tags, or spec files committed there. Branch + PR are the only
   footprint; `<STATE_HOME>` is the sole registry of which PRs are ours.
8. Start a fresh Claude session in the worktree with the prompt:
   *"Execute `<STATE_HOME>/specs/active/<id>/SPEC.md`. First read
   `<STATE_HOME>/PRIORS.md` (lessons from prior runs) and
   `<PLUGIN_HOME>/contracts/DISPATCH.md` steps 9–11 — they govern how you
   verify, get ready, and escalate. You do NOT open a PR — ever. Follow the
   spec exactly: respect Non-goals and blast radius, stop on any escalation
   condition and write QUESTION.md instead of guessing. Work plan-first:
   execute the spec's requirements in order and verify each before moving on.
   Log to `<STATE_HOME>/specs/active/<id>/RUN.md` as you go."*
9. Executor runs all acceptance criteria itself, saving raw output under
   `<STATE_HOME>/specs/active/<id>/evidence/`. Failures get up to
   `max_criteria_retries` fix attempts, then escalate.

## Ready — the zero-calls gate (no PR exists yet)

10. **Delivering with caveats is forbidden.** If ANY of these is true, the
    item goes to `<STATE_HOME>/specs/blocked/<id>/` with `QUESTION.md` — the
    concrete decision needed, the options, what was ruled out; never a bare
    "it failed":
    - any escalation condition fired, or any criterion is not passing;
    - any step outside the declared blast radius was taken or seems needed —
      a breach already committed is STILL an escalation (undo it or ask),
      never a footnote;
    - anything at all would "need the human's call". "The work is complete
      and the failure isn't mine" is not an exemption; it is the escalation.

    Everything the human must decide reaches them BEFORE any PR exists.
    **Before escalating, preserve the state**: commit all work-in-progress to
    the branch and push it to origin (the TARGET repo's remote — this is the
    one push in the whole procedure, and it is never `<STATE_HOME>`), and
    leave RUN.md a handoff a stranger could resume from — where the work
    stands, what remains, what was ruled out. Executors are stateless by
    design: after an unblock, a FRESH executor continues from the amended
    spec + branch + RUN.md, never the old session. Unpushed work in a pruned
    worktree is lost work.
11. **All clean** → write `<STATE_HOME>/specs/active/<id>/READY.md`: criteria
    table with evidence paths, assumptions, and the **prepared PR title +
    body** (or report location). PR content follows the TARGET repo's
    conventions, discovered in this order: the spec's Context pointers, the
    repo's PR template (`.github/PULL_REQUEST_TEMPLATE*`), CONTRIBUTING /
    commit-guideline docs / CLAUDE.md, and recently merged human-authored
    PRs as exemplars. No spec ids, drydock paths, or drydock terminology in
    PR content or commits. Conventions undeterminable → escalation.
    The executor stops here.

## Review → fix → land (orchestrator-driven; still no PR until ship)

12. READY triggers the adversarial review (`<PLUGIN_HOME>/contracts/REVIEWER.md`)
    **on the worktree/branch** — `git diff` against base, not a PR. Verdicts:
    - **fix** → a fix executor runs in the SAME worktree against
      `REVIEW.md`'s findings (criteria = parent's + one check per finding),
      then back to step 10. Round cap 2, then flag.
    - **flag** → `<STATE_HOME>/specs/blocked/<id>/` with REVIEW.md findings as
      the question. The human decides before any PR exists.
    - **ship** → NOW the draft PR is opened (`gh pr create --draft`, title +
      body verbatim from READY.md), branch pushed to the TARGET repo's
      remote. **Unless the item declares a `pr_url`** (spec frontmatter, or
      DELIVERABLE.md from an earlier round): then the push is the whole of
      it, `gh pr create` does not run, and DELIVERABLE.md records that same
      `pr_url:`. A declared pull request that preflight (step 5) could not
      confirm OPEN on the declared branch never gets this far — it escalated
      — and opening a fresh PR in its place is forbidden, not a fallback.
      Move `<STATE_HOME>/specs/active/<id>/` →
      `<STATE_HOME>/deliverables/<id>/` with `DELIVERABLE.md` (what was
      built, criteria + evidence, assumptions, frontmatter
      `pr_url:`/`report_url:`); prune the worktree. The PR lands already
      reviewed and fixed. PR state is later read back per recorded URL,
      never by scanning the target repo's PR list.
13. Commit the move in `<STATE_HOME>`'s own git repo — never pushed, it has
    no remote. Notify per the orchestrator's Notifications policy
    (`PushNotification`; a manual dispatch just reports in-chat).

## Review (the human)

14. Approve → `gh pr ready <url>` (draft → ready for the team's normal
    review) or publish the report; move to `<STATE_HOME>/archive/<id>/`.
15. Reject → write `REJECTION.md` with the reason and its loop:
    `fast` (amend spec → inbox) or `slow` (fold the correction into the
    executing skill → re-queue).

## Comment rounds (after ship — the PR is public and people respond)

16. The orchestrator watches each shipped item's PR for **new human
    comments** (reviews, review comments, issue comments) beyond the
    `comments_seen:` cursor in DELIVERABLE.md. New ones → it compiles them
    into `COMMENTS-r<N>.md` (author, file:line, text, permalink, one entry
    per thread), moves the item `<STATE_HOME>/deliverables/<id>/` →
    `<STATE_HOME>/specs/active/<id>/`, and dispatches a comment-fix executor
    in a worktree recreated from the PR branch.
    **Chained items share a pull request, and this step does not know that.**
    N items that declared the same `pr_url:` each carry their own
    `comments_seen:` cursor over the same PR, so one human comment on it is
    new to all N and dispatches N comment-fix executors — which then race for
    the one branch and hit step 7's exit 128. Nothing deduplicates them.
    Until something does, a comment round on a shared pull request is a
    one-at-a-time operation: run it for a single item and let the others'
    cursors catch up at ship.
17. The comment-fix executor addresses every entry: a code change, or a
    **drafted reply** written into COMMENTS-r<N>.md — it NEVER posts to the
    PR; every word on the PR is the human's. A comment needing the human's
    judgment is an escalation like any other (zero-calls gate applies). The
    changed delta gets one adversarial review round (fresh round counter per
    comment batch, same cap 2), then ship-lite: push to the SAME PR (target
    repo), update `comments_seen:`, move back to `<STATE_HOME>/deliverables/`,
    notify ("comments addressed: <id> — k fixed, m replies drafted"). The
    human posts the drafted replies (or rewrites them) from the review pass.
