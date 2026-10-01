# Plan: a task whose Verify is a wish

## Approach

Add retries to the upload client.

## Files

- `src/upload.py`

## Tasks

| # | Task | Files | Verify | After |
|---|------|-------|--------|-------|
| T1 | FR-001: retry on 503 | `src/upload.py` | `python3 -m unittest tests.test_upload` | — |
| T2 | FR-002: log each retry | `src/upload.py` | check the logs look right | T1 |
