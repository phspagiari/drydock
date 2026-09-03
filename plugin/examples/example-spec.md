# Spec: Idempotency keys on POST /v1/transfers

<!--
  A worked example: every section filled the way a spec should be filled.
  The repo, service and incident are fictional — the shape is not.

  Read it for three things: (1) the blast radius is drawn tightly enough that
  an executor knows when to stop and ask; (2) every acceptance criterion is a
  command with a pass condition, and at least one of them encodes the
  *behaviour* rather than compilation health; (3) the escalation conditions
  name the specific judgment calls this work could run into.
-->

```yaml
id: 2026-04-08-transfers-idempotency
track: code
target_repo: ~/code/ledger-api
deliverable: pr
created: 2026-04-08
status: inbox
depends_on: []
budget:
  max_agents: 2
  max_wall_clock: 90m
  max_criteria_retries: 2
```

## Context

`POST /v1/transfers` creates a ledger entry and is not idempotent. The mobile
client retries on any 5xx and on its 10s socket timeout, and last week's
partial outage (INC-4471, `docs/incidents/2026-04-01-transfer-dupes.md`) put
1,842 duplicate transfers into the ledger from 611 client retries — every one
of them a manual reversal. The handler is
`internal/transport/http/transfers.go:88`; persistence is
`internal/adapters/postgres/transfers.go`. The API contract already documents
an `Idempotency-Key` request header as "reserved"
(`api/openapi/transfers.yaml:214`), so clients can send it today and the
server ignores it. Two other services in this repo implement this pattern
against the same Postgres — see `internal/adapters/postgres/idempotency.go`,
added for the payouts endpoint in Q4 — and the intent is to reuse that helper
rather than write a second mechanism.

## Goal

`POST /v1/transfers` becomes idempotent on the `Idempotency-Key` header: the
first request with a given key executes normally and its response is
recorded; any later request with the same key and the same request body
returns that recorded response verbatim, with no second ledger entry, for 24
hours. A later request reusing the key with a *different* body is a client
error, not a silent overwrite. Requests without the header behave exactly as
they do today.

## Non-goals

- Making any other endpoint idempotent. `POST /v1/reversals` has the same
  defect; it is a separate spec (`depends_on` this one, once this ships).
- Changing the client. The mobile app already sends `Idempotency-Key`; nothing
  ships to the app for this to take effect.
- Changing the retention window, the storage backend, or the schema of the
  existing `idempotency_records` table. If 24h turns out to be wrong, that is
  a follow-up with its own numbers.
- Backfilling or reversing the duplicates from INC-4471. Finance is doing that
  manually and has already started.

## Constraints & blast radius

- **May touch**:
  - `internal/transport/http/transfers.go`
  - `internal/transport/http/transfers_test.go`
  - `internal/transport/http/middleware/` (only if the reuse below argues for
    a middleware rather than a handler-local call)
  - `api/openapi/transfers.yaml` (the header's description only — from
    "reserved" to its real semantics)
  - `CHANGELOG.md`
- **Must not touch**:
  - `internal/adapters/postgres/idempotency.go` — reuse it as-is. If it does
    not fit, that is an escalation, not a refactor.
  - Any migration directory. This change adds no columns and no tables.
  - Any other endpoint's handler or test.
- The existing helper's semantics are the contract: same key + same body hash
  → replay; same key + different body hash → `409 Conflict` with error code
  `idempotency_key_reuse`. Do not invent different semantics for this
  endpoint.
- Requests with no `Idempotency-Key` header must take the current code path
  with no added database round-trip. A latency regression on the unkeyed path
  is a defect.
- Go 1.23, standard repo toolchain. No new dependencies.

## Requirements

- **FR-001**: When `Idempotency-Key` is present and unseen, the handler
  executes the transfer as today and records `(key, request_body_hash,
  status_code, response_body)` via the existing helper before responding.
- **FR-002**: When the key has been seen within 24h and the request body hash
  matches, the handler returns the recorded status and body verbatim, creates
  no ledger entry, and sets `Idempotency-Replayed: true` on the response.
- **FR-003**: When the key has been seen within 24h and the body hash differs,
  the handler returns `409` with error code `idempotency_key_reuse` and
  creates no ledger entry.
- **FR-004**: Two concurrent requests carrying the same key produce exactly
  one ledger entry; the loser either replays the winner's response or returns
  `409` with `idempotency_request_in_flight` — whichever the existing helper
  already does. Do not add a second locking mechanism.
- **FR-005**: A request without the header behaves byte-identically to today,
  including on the error paths.
- **FR-006**: `api/openapi/transfers.yaml` describes the header's real
  semantics, the `Idempotency-Replayed` response header, and the two new 409
  error codes.

## Acceptance criteria (executable)

| # | Check | Command | Pass condition |
|---|-------|---------|----------------|
| AC-1 | Build | `go build ./...` | exit 0 |
| AC-2 | Package tests | `go test ./internal/transport/http/... ./internal/adapters/postgres/...` | exit 0; new cases cover FR-002, FR-003, FR-005 by name |
| AC-3 | Race on the concurrent path | `go test -race -run TestTransfers_Idempotency -count=5 ./internal/transport/http/...` | exit 0, no race reports across all 5 runs |
| AC-4 | Replay creates no second entry (the intent) | `go test -run TestTransfers_Idempotency_ReplayWritesNothing -v ./internal/transport/http/... 2>&1 \| tee evidence/ac4.txt` | PASS, and the test asserts the ledger row count is unchanged after the replay — not merely that the status codes match |
| AC-5 | Unkeyed path untouched | `go test -run TestTransfers_NoIdempotencyKey ./internal/transport/http/...` and `git diff --stat -- internal/transport/http/transfers.go` | tests pass; the diff shows no change to the unkeyed branch beyond the new guard |
| AC-6 | Spec document matches behaviour | `make openapi-lint && go test -run TestOpenAPIContract ./internal/transport/http/...` | exit 0 — the contract test reads the YAML, so a description that lies fails here |
| AC-7 | Lint clean for the diff | `make lint` | exit 0, or only findings that reproduce on the base commit (record both runs under `evidence/`) |

## Escalation conditions

- Any unresolved `[NEEDS CLARIFICATION]` at execution time.
- Any acceptance criterion still failing after `max_criteria_retries`.
- The correct change appears to require touching the **must not touch** list —
  in particular, if `internal/adapters/postgres/idempotency.go` cannot be
  reused as-is for FR-004's concurrency behaviour. Report what it does, what
  is needed, and the two or three ways forward; do not extend the helper.
- The existing helper's conflict semantics turn out to differ from what
  Context claims (`409` / `idempotency_key_reuse`). Take the helper as truth,
  stop, and ask whether this spec's FR-003 should change to match it.
- `make lint` or `go build ./...` fails on the untouched base commit. That is
  environment noise, not this work — record it and escalate rather than
  repairing someone else's breakage inside this branch.
- Budget exceeded.

## Assumptions

- The 24h window is the helper's existing default and is not configured
  per-endpoint. If it is configurable, this endpoint uses the same default as
  payouts.
- `Idempotency-Replayed` is a new response header; nothing in the repo emits
  it yet. Named after the payouts endpoint's behaviour if that endpoint
  already sets one — check before inventing the name.
- The body hash covers the raw request body only, not headers or the
  authenticated principal. That is what the helper does for payouts; the same
  choice is inherited here rather than re-argued.
- `CHANGELOG.md` gets one line under Unreleased. If this repo's changelog is
  generated from commit messages rather than edited, drop the file from the
  diff — check before writing it.
