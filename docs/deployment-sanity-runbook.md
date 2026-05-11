---
title: Con Quest Deployment Sanity Runbook
description: Post-deploy sanity checks for Docker Compose deployments of Con Quest MVP
date: 2026-05-10
topic: how-to
---

## Purpose

Use this runbook after deployment to verify baseline app health before broader QA.

## Prerequisites

* Deployment host has Docker and Docker Compose installed
* `.env` exists and contains required runtime values
* Ports 8000 and 6379 are available or intentionally remapped

## Step 1 Build and start services

```bash
docker compose up --build -d
```

Expected:

* `web` and `redis` containers start successfully
* No crash-looping containers

## Step 2 Verify container health and logs

```bash
docker compose ps
docker compose logs web --tail=100
docker compose logs redis --tail=50
```

Expected:

* `web` shows Django server startup without import or migration failures
* `redis` accepts connections
* No repeated stack traces

## Step 3 Verify Django health and routes

```bash
curl -i http://localhost:8000/
curl -i http://localhost:8000/seasons/qa-season/state/
```

Expected:

* Root returns HTTP 200
* Season state returns HTTP 200 or 404 for unknown slug, but no 500
* Rate-limit headers appear on state responses

## Step 4 Verify websocket fallback posture

```bash
curl -i "http://localhost:8000/seasons/qa-season/connection-test/?client_time_ms=1000"
```

Expected:

* JSON payload contains status and guidance
* `X-RateLimit-*` headers are present
* If Redis is down, endpoint degrades safely instead of failing

## Step 5 Run application checks

```bash
python3 manage.py check
python3 manage.py test
```

Expected:

* System checks pass
* Test suite remains green in deployment environment

## Step 6 Rollback trigger criteria

Rollback immediately if any condition occurs:

* Repeated 5xx on root, season detail, or submission routes
* Redis/channel failures causing user-facing request failures
* Upload or scoring flows failing with unhandled exceptions

## Step 7 Shutdown command

```bash
docker compose down
```
