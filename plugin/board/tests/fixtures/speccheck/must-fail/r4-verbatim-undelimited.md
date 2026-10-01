# Spec: a requirement freezes text with no delimited block

```yaml
id: 2030-01-01-r4-verbatim-undelimited
created: 2030-01-01
```

## Constraints & blast radius

- **May touch**: `src/`
- **Must not touch**: everything else
- **State predicates**: none — nothing branches on disk or git state.

## Requirements

- **FR-001**: The pull request body opens with this sentence, verbatim:
  "Adds retries to the upload client."

## Acceptance criteria (executable)

| # | Check | Command | Pass condition |
|---|-------|---------|----------------|
| AC-1 | Tests | `python3 -m unittest discover tests` | exit 0 |
