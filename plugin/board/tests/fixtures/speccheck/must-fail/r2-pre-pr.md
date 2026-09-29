# Spec: a real command that still needs a pull request

```yaml
id: 2030-01-01-r2-pre-pr
created: 2030-01-01
```

## Constraints & blast radius

- **May touch**: `src/`
- **Must not touch**: everything else
- **State predicates**: none — nothing branches on disk or git state.

## Requirements

- **FR-001**: The required checks pass.

## Acceptance criteria (executable)

| # | Check | Command | Pass condition |
|---|-------|---------|----------------|
| AC-1 | Checks pass | `gh pr checks --required` | every check green |
