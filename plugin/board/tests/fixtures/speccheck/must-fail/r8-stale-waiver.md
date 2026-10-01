# Spec: a waiver for a row that no longer exists

```yaml
id: 2030-01-01-r8-stale-waiver
created: 2030-01-01
```

## Constraints & blast radius

- **May touch**: `src/`
- **Must not touch**: everything else
- **State predicates**: none — nothing branches on disk or git state.

## Requirements

- **FR-001**: The upload client retries.

## Acceptance criteria (executable)

| # | Check | Command | Pass condition |
|---|-------|---------|----------------|
| AC-1 | Tests | `python3 -m unittest discover tests` | exit 0 |

<!-- speccheck-ok: AC-4 R5 — AC-4 was removed; this annotation outlived it -->
