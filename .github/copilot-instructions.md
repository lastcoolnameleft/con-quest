# Copilot Instructions for ConQuest

## Build & Run

```bash
# Install dependencies
pip install -r requirements/dev.txt

# Run migrations and start dev server
python manage.py migrate
python manage.py runserver
```

Docker alternative: `docker-compose up`

## Testing

```bash
# Unit/integration tests (pytest + pytest-django)
pytest

# Single test file
pytest tests/test_moderation_flow.py

# Single test by name
pytest -k "test_name_substring"

# E2E tests (Playwright, auto-starts dev server)
npx playwright test

# Single e2e spec
npx playwright test tests/e2e/smoke.spec.js
```

## Linting

```bash
ruff check .
ruff format --check .
```

## Architecture

ConQuest is a multiplayer scavenger hunt platform. Key architectural decisions:

- **Django 6 + Daphne ASGI** — serves both HTTP and WebSocket traffic
- **HTMX + server-rendered templates** — no JS framework; interactivity via HTMX partial responses
- **Django Channels + Redis** — real-time updates pushed to clients via WebSocket consumers in `apps/realtime/`
- **Azure Blob Storage** — media uploads (submission photos/videos) stored via `apps/submissions/storage.py`
- **django-allauth** — authentication with Google and GitHub OAuth providers
- **Custom user model** — `apps.accounts.Account` (set as `AUTH_USER_MODEL`)

### Domain Model Hierarchy

Season → SeasonQuest → QuestAssignment → Submission → ModerationDecision → Leaderboard score

- **Seasons** own quests and participants
- **SeasonQuest** links a reusable `Quest` template to a specific season with overrides (title, timing, points)
- **QuestAssignment** tracks per-participant quest state with a status machine: pending → submitted → scored/missed/excused
- **SeasonQuest** has its own status machine: draft → pending → active → complete → archived (see `allowed_next_statuses()`)

### App Responsibilities

| App | Role |
|-----|------|
| `accounts` | Custom user model, login forms |
| `seasons` | Season + participant management, join codes |
| `quests` | Quest templates, SeasonQuest lifecycle, assignments |
| `submissions` | Proof uploads, media validation, storage |
| `moderation` | Review queue, approve/reject decisions |
| `leaderboard` | Score aggregation and ranking |
| `realtime` | WebSocket consumers, channel events |
| `audit` | Activity logging |
| `common` | Shared utilities, context processors, rate limiting |

## Conventions

- **Settings via env vars** — loaded from `.env` with `python-dotenv`; see `.env.example` for required keys
- **HTMX partials** — views return full pages or HTML fragments based on `request.htmx`; templates live in `templates/` (project-level, not per-app)
- **TextChoices for status fields** — all status/mode fields use Django `TextChoices` enums with explicit transition logic
- **pytest for all Python tests** — configured in `pytest.ini` with `DJANGO_SETTINGS_MODULE = con_quest.settings`
- **factory-boy for test fixtures** — use factories rather than raw model creation in tests
- **Ruff for linting/formatting** — included in dev dependencies
