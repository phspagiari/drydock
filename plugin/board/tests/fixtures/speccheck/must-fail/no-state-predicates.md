# Spec: constraints that never say who writes the state it reads

```yaml
id: 2030-01-01-no-state-predicates
created: 2030-01-01
```

## Constraints & blast radius

- **May touch**: `src/`
- **Must not touch**: everything else

## Requirements

- **FR-001**: The resume path starts when `RUN.md` is absent.

## Acceptance criteria (executable)

| # | Check | Command | Pass condition |
|---|-------|---------|----------------|
| AC-1 | Tests | `python3 -m unittest discover tests` | exit 0 |
