# Spec: a waivable rule, silenced with a reason

```yaml
id: 2030-01-01-waived-spec
created: 2030-01-01
```

## Constraints & blast radius

- **May touch**: `src/`
- **Must not touch**: everything else
- **State predicates**: none — nothing branches on disk or git state.

## Requirements

- **FR-001**: Precondition: the dependency's pull request has merged.

## Acceptance criteria (executable)

| # | Check | Command | Pass condition |
|---|-------|---------|----------------|
| AC-1 | Tests | `python3 -m unittest discover tests` | exit 0 |
| AC-2 | Dependency landed | `gh pr view 12 --json state -q .state` | prints `MERGED` |

<!-- speccheck-ok: AC-2 R2 — reads the state of a pull request that exists
     before this item; the row presupposes no pull request of its own. -->
