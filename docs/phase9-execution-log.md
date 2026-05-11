---
title: Con Quest Phase 9 Execution Log
description: Recorded execution evidence for verification and hardening activities in Phase 9
date: 2026-05-10
topic: how-to
---

## Scope

This log captures executed verification evidence for Phase 9 hardening tasks.

## Environment

* Workspace: local development machine
* Runtime: Django dev server on `127.0.0.1:8001`
* Target season slug: `qa-season`

## Executed checks

### Burst rate-limit probe

Command:

```bash
bash scripts/burst-checks.sh qa-season http://127.0.0.1:8001
```

Observed output summary:

* State endpoint summary:
* 200: 120
* 429: 80
* Connection-test endpoint summary:
* 200: 20
* 429: 20
* Sample throttled headers:
* HTTP 429
* `X-RateLimit-Limit: 20`
* `X-RateLimit-Remaining: 0`
* `X-RateLimit-Window: 60`
* `Retry-After: 60`

Result:

* PASS: Throttling engaged at expected limits and returned required headers.

### Deployment sanity route checks

Commands:

```bash
curl -s -o /dev/null -w 'root:%{http_code}\n' http://127.0.0.1:8001/
curl -s -o /dev/null -w 'state:%{http_code}\n' http://127.0.0.1:8001/seasons/qa-season/state/
curl -s -o /dev/null -w 'connection:%{http_code}\n' "http://127.0.0.1:8001/seasons/qa-season/connection-test/?client_time_ms=1000"
```

Observed output:

* `root:200`
* `state:429`
* `connection:429`

Notes:

* The first route check occurred immediately after burst probing, so state and connection responses were intentionally rate-limited.

Fresh-client recheck commands:

```bash
curl -s -H 'X-Forwarded-For: 10.9.8.7' -o /dev/null -w 'state-fresh:%{http_code}\n' http://127.0.0.1:8001/seasons/qa-season/state/
curl -s -H 'X-Forwarded-For: 10.9.8.7' -o /dev/null -w 'connection-fresh:%{http_code}\n' "http://127.0.0.1:8001/seasons/qa-season/connection-test/?client_time_ms=1000"
```

Observed output:

* `state-fresh:200`
* `connection-fresh:200`

Result:

* PASS: Baseline route health is 200 with a fresh client identifier.

### Docker Compose deployment sanity runbook execution

Commands:

```bash
docker compose up --build -d
docker compose ps
docker compose logs web --tail=80
docker compose logs redis --tail=40
curl -s -o /dev/null -w 'root:%{http_code}\n' http://localhost:8000/
curl -s -o /dev/null -w 'state:%{http_code}\n' http://localhost:8000/seasons/qa-season/state/
curl -s -o /dev/null -w 'connection:%{http_code}\n' "http://localhost:8000/seasons/qa-season/connection-test/?client_time_ms=1000"
docker compose down
```

Observed output summary:

* Compose services up:
* `con-quest-web-1` status `Up`
* `con-quest-redis-1` status `Up`
* Web logs show clean Django startup without import/migration failures.
* Redis logs show ready-to-accept-connections startup.
* Route checks:
* `root:200`
* `state:200`
* `connection:200`

Result:

* PASS: Deployment sanity runbook validated successfully in local Docker runtime.

## Automated fairness verification

Command:

```bash
python3 manage.py test tests.test_scheduled_fairness tests.test_submission_timing
```

Result:

* PASS: Canonical scheduled window behavior and submission boundary enforcement validated by tests.

### Multi-client canonical window capture

Command:

```bash
python3 scripts/fairness-capture.py qa-season 1 --base-url http://127.0.0.1:8001
```

Observed output summary:

* `client_a_status: live`
* `client_b_status: live`
* `client_a_started_at` equals `client_b_started_at`
* `client_a_ends_at` equals `client_b_ends_at`
* `started_at_match: True`
* `ends_at_match: True`

Result:

* PASS: Two independently identified clients observed identical canonical start and end windows.

## Phase 9 status update

* Automated verification coverage: complete for current hardening scope.
* Deployment sanity runbook: executed and passing.
* Manual experiential QA available via [docs/manual-qa-runbook.md](docs/manual-qa-runbook.md).
* Remaining manual-only checks:
* Browser network-throttle UX pass (`Slow 3G`) for user experience quality.
* Signed URL expiry behavior with real waiting period and media access validation.
