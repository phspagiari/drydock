# Spec: Route fixture — the owner line is commented out

<!--
  A fixture for queue_rules.py route and check. It is a whole spec in the
  template's shape so that the parser meets the frontmatter where a real
  spec carries it; only the frontmatter line it is named for varies.
-->

```yaml
id: 2026-11-09-route-commented
track: code
target_repo: ~/code/your-repo
deliverable: pr
created: 2026-11-09
status: inbox
depends_on: []
# owner: lead-a
budget:
  max_agents: 4
  max_wall_clock: 2h
  max_criteria_retries: 2
```

## Context

Retried transfers settle twice when the client resends after a timeout.
The handler is `ledger/transfers/handler.go`.

## Goal

The ledger service rejects a transfer whose idempotency key it has already
settled, instead of settling it twice.

## Non-goals

- Changing the settlement batch schedule.

## Constraints & blast radius

- **May touch**: `ledger/transfers/`
- **Must not touch**: `ledger/settlement/`
- **State predicates**: none

## Requirements

- **FR-001**: A second transfer with a settled idempotency key is rejected
  with a conflict status and settles nothing.

## Acceptance criteria (executable)

| # | Check | Command | Pass condition |
|---|-------|---------|----------------|
| AC-1 | Build | `make build` | exit 0 |
| AC-2 | Tests | `make test` | all pass, includes new tests for FR-001 |

## Ship criteria (owned by the ship step — NOT the executor)

| # | Check | Command | Pass condition |
|---|-------|---------|----------------|
| SC-1 | CI green | the required checks on the pull request | all green |

## Escalation conditions

- Any acceptance criterion still failing after `max_criteria_retries`.
- The correct change appears to require touching the **must not touch** list.
- Budget exceeded.

## Assumptions

- Idempotency keys are unique per tenant.
