# Spec: escalation boilerplate that matches the marker check

```yaml
id: 2030-01-01-r9-token-reproduced
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

## Escalation conditions

- Any unresolved `[NEEDS CLARIFICATION]` at execution time.
