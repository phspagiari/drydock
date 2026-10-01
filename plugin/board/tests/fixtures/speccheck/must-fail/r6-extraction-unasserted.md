# Spec: a criterion trusts an extract it never measured

```yaml
id: 2030-01-01-r6-extraction-unasserted
created: 2030-01-01
```

## Constraints & blast radius

- **May touch**: `src/`
- **Must not touch**: everything else
- **State predicates**: `RUN.md` — written by the executor as it works.

## Requirements

- **FR-001**: The run log records the retry budget.

## Acceptance criteria (executable)

| # | Check | Command | Pass condition |
|---|-------|---------|----------------|
| AC-1 | Budget logged | `sed -n '/^## Log/,$p' RUN.md > evidence/log.txt; grep -c 'retry budget' evidence/log.txt` | count at least 1 |
