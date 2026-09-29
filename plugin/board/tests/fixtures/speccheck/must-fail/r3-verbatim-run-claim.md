# Spec: frozen text that counts the run producing it

```yaml
id: 2030-01-01-r3-verbatim-run-claim
created: 2030-01-01
```

## Constraints & blast radius

- **May touch**: `src/`
- **Must not touch**: everything else
- **State predicates**: none — nothing branches on disk or git state.

## Requirements

- **FR-001**: The pull request body opens with `verbatim:summary`.

```verbatim:summary
Adds retries to the upload client in three files.
```

## Acceptance criteria (executable)

| # | Check | Command | Pass condition |
|---|-------|---------|----------------|
| AC-1 | Body carries summary | `python3 tools/body.py --check summary` | exit 0 |
