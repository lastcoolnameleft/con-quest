## Quick start

```
docker compose up -d redis
source .venv/bin/activate
python3 manage.py runserver
```

## Purpose

Use this runbook to get Con Quest running locally for day-to-day development.

## Prerequisites

* macOS, Linux, or Windows with terminal access
* Git
* Docker Desktop with Docker Compose, or Python 3.12+ and pip

## Option A Docker first workflow

### 1. Clone and configure environment

```bash
git clone <your-repo-url>
cd con-quest
cp .env.example .env
```

### 2. Start services

```bash
docker compose up --build
```

This starts:

* Django app at port 8000
* Redis at port 6379

### 3. Open the app

* App: <http://localhost:8000>
* Admin: <http://localhost:8000/admin>

### 4. Stop services

```bash
docker compose down
```

## Option B Native Python workflow

### 1. Clone and configure environment

```bash
git clone <your-repo-url>
cd con-quest
cp .env.example .env
```

### 2. Create and activate virtual environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install --upgrade pip
pip install -r requirements/base.txt
pip install -r requirements/dev.txt
```

### 4. Apply migrations

```bash
python3 manage.py migrate
```

### 5. Start app server

```bash
python3 manage.py runserver
```

### 6. Open the app

* App: <http://localhost:8000>
* Admin: <http://localhost:8000/admin>

## Create an admin user

Run once per local database:

```bash
python3 manage.py createsuperuser
```

## Quick health checks

Run these after setup or after large changes:

```bash
python3 manage.py check
python3 manage.py test
```

## Helpful dev commands

Run fairness smoke tests:

```bash
python3 manage.py test tests.test_scheduled_fairness tests.test_submission_timing
```

Run throttle and resilience tests:

```bash
python3 manage.py test tests.test_throttle_headers tests.test_realtime_resilience
```

Run burst check script against local app:

```bash
bash scripts/burst-checks.sh qa-season
```

## Common issues

### Redis connection warnings during tests

Some tests intentionally exercise resilience paths and may log connection warnings when Redis is unavailable. Test success criteria is green test results, not silent logs.

### Port 8000 already in use

Stop the existing process using port 8000 or map a new host port in `docker-compose.yml`.

### Missing environment file

If startup fails on configuration, confirm `.env` exists and was copied from `.env.example`.

## Observability tips

Submission fairness rejections now emit structured INFO logs from `apps.submissions.views`.

What to look for in server output:

* `Submission timing rejected for assignment ...`
* Rejection reason (`not started yet`, `window has closed`)
* Canonical scheduled timestamps (`started_at`, `ends_at`)

These logs help confirm server-authoritative timing decisions during local debugging.

## Related runbooks

* Deployment checks: [docs/deployment-sanity-runbook.md](docs/deployment-sanity-runbook.md)
* Manual QA: [docs/manual-qa-runbook.md](docs/manual-qa-runbook.md)
