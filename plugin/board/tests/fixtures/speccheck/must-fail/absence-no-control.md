# Spec: a sweep that passes on reading nothing

<!--
  The shape of a real miss: a corroboration sweep whose pattern the
  matcher rejected printed its fallback, and "prints nothing" read as
  "no such claim". Nothing in the row could tell the two apart.
-->

```yaml
id: 2030-01-01-absence-no-control
created: 2030-01-01
```

## Constraints & blast radius

- **May touch**: `docs/`
- **Must not touch**: everything else
- **State predicates**: none — nothing branches on disk or git state.

## Requirements

- **FR-001**: No document claims the cache is write-through.

## Acceptance criteria (executable)

| # | Check | Command | Pass condition |
|---|-------|---------|----------------|
| AC-1 | No write-through claim | `grep -rniE 'write(-\| )through' docs/` | prints nothing |
