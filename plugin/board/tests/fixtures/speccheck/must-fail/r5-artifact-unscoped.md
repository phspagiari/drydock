# Spec: a criterion greps the whole report it is reported in

```yaml
id: 2030-01-01-r5-artifact-unscoped
created: 2030-01-01
```

## Constraints & blast radius

- **May touch**: `src/`
- **Must not touch**: everything else
- **State predicates**: `READY.md` — written by the executor at the end of
  its run, before this criterion is re-run.

## Requirements

- **FR-001**: The prepared text names the retry budget.

## Acceptance criteria (executable)

| # | Check | Command | Pass condition |
|---|-------|---------|----------------|
| AC-1 | Budget named | `grep -c 'retry budget' READY.md` | count at least 1 |
