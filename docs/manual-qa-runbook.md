---
title: Con Quest Manual QA Runbook
description: Manual verification steps for reliability, fairness, media access, and burst behavior in Con Quest MVP
date: 2026-05-10
topic: how-to
---

## Purpose

Use this runbook to execute the remaining manual checks from Phase 9.

## Preconditions

* Start services:

```bash
docker compose up --build
```

* Open the app at <http://localhost:8000>
* Create one season with slug `qa-season`
* Create at least one scheduled quest and one open quest in that season
* Join with at least two participant handles

## Scenario 1 Low-bandwidth behavior

### Goal

Verify the app remains usable when network conditions degrade.

### Steps

1. Open the season detail page in Chrome.
2. Open DevTools, then open Network conditions.
3. Set throttling to `Slow 3G`.
4. Trigger `Test Connection` on the season page.
5. Try these actions in order:
* Join season
* Claim open quest
* Submit text-only response

### Expected results

* Connection test reports `Ready` or `Risky` but not a server error
* UI remains responsive and actions return safe feedback
* When throttled too aggressively, endpoints return bounded 429 responses with retry guidance

## Scenario 2 Scheduled fairness under concurrency

### Goal

Validate near-simultaneous quest start behavior for multiple participants.

### Steps

1. Open the same scheduled quest page in two browser windows.
2. In each window, run connection preflight first.
3. As host/admin, start the scheduled quest once.
4. Observe start and end times in both windows.
5. Submit responses near quest end from both windows.

### Expected results

* Both clients receive the same canonical `started_at` and `ends_at` window
* Small client-side receive jitter is acceptable
* Server remains authoritative for accept/reject timing boundaries

### Automated smoke for this scenario

Run this test before manual concurrency checks:

```bash
python3 manage.py test tests.test_scheduled_fairness
```

Expected:

* Scheduled quest start sets one canonical window (`started_at`, `ends_at`)
* Repeated start requests do not reset timing on an already live quest

Run submission boundary-time smoke checks:

```bash
python3 manage.py test tests.test_submission_timing
```

Expected:

* Submissions before `started_at` are rejected
* Submission exactly at `ends_at` is accepted
* Submissions after `ends_at` are rejected unless late grace is configured

Run two-client canonical window capture:

```bash
python3 scripts/fairness-capture.py qa-season <scheduled-quest-id> --base-url http://127.0.0.1:8001
```

Expected:

* `started_at_match: True`
* `ends_at_match: True`

Record output with [docs/fairness-evidence-template.md](docs/fairness-evidence-template.md).

## Scenario 3 Signed media URL and expiry behavior

### Goal

Confirm private media reads use signed links and fail closed after expiry.

### Steps

1. Submit one image response.
2. Open scoring queue as host/admin.
3. Open media link from scoring queue in a new tab.
4. Copy the signed URL and wait past expiry window.
5. Refresh the expired URL directly.

### Expected results

* Initial link opens media successfully
* Expired link no longer grants access
* Opening scoring queue again generates a fresh signed URL

## Scenario 4 Burst rate-limit checks

### Goal

Verify rate-limit behavior under rapid request bursts.

### Steps

1. In a separate terminal, run:

```bash
bash scripts/burst-checks.sh qa-season
```

2. Review summary output.

### Expected results

* `season-state` burst shows a mix of 200 and 429 responses
* 429 responses include `Retry-After` and rate-limit headers
* Connection preflight burst eventually returns 429 with structured payload

## Evidence to capture

* Screenshots of connection preflight output and season status
* Terminal output from burst script
* Notes for any unexpected 5xx, missing headers, or inconsistent timestamps
