# Spec: a criterion the executor cannot evaluate

<!--
  The acceptance row below is the historical defect, copied as it was
  written: a criterion that needs a pull request, in a table whose executor
  stops before any pull request exists. Its Command cell is prose.
-->

```yaml
id: 2030-01-01-ac11-unevaluable
track: code
target_repo: ~/code/your-repo
deliverable: pr
created: 2030-01-01
```

## Constraints & blast radius

- **May touch**: `src/`
- **Must not touch**: everything else
- **State predicates**: none — nothing branches on disk or git state.

## Requirements

- **FR-001**: The linter runs clean on the pinned version.

## Acceptance criteria (executable)

| # | Check | Command | Pass condition |
|---|-------|---------|----------------|
| AC-1 | Lint green | `make lint` | exit 0 |
| AC-11 | CI green | all required checks on the PR | green |
