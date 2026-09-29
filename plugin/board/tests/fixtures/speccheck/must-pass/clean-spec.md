# Spec: every rule satisfied

```yaml
id: 2030-01-01-clean-spec
created: 2030-01-01
```

## Constraints & blast radius

- **May touch**: `src/`
- **Must not touch**: everything else
- **State predicates**: `READY.md` — written by the executor at the end of
  its run; AC-3 re-reads its prepared text after it is written.

## Requirements

- **FR-001**: The pull request body opens with `verbatim:summary`.

```verbatim:summary
Adds retries to the upload client.
```

## Acceptance criteria (executable)

| # | Check | Command | Pass condition |
|---|-------|---------|----------------|
| AC-1 | Tests | `python3 -m unittest discover tests` | exit 0 |
| AC-2 | No stray debug print | `grep -c 'print(' src/upload.py; grep -c 'def upload' src/upload.py` | the first count is `0` and the second at least 1 (positive control) |
| AC-3 | Summary is the prepared text | `awk '/^## Prepared PR text/{f=1} f&&/^## Ship/{exit} f' READY.md > evidence/ac3.txt; wc -l < evidence/ac3.txt; grep -c 'Adds retries' evidence/ac3.txt` | the extract is non-empty; the summary block's sentence counts at least 1 |

## Ship criteria (owned by the ship step — NOT the executor)

| # | Check | Command | Pass condition |
|---|-------|---------|----------------|
| SC-1 | CI green | the required checks on the pull request | all green |
