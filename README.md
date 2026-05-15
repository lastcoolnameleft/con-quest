---
title: ConQuest
description: Multiplayer scavenger hunt and quest platform built with Django, Channels, and HTMX.
---

## Overview

ConQuest is a Django-based web app for creating seasons, publishing quests, submitting proof, moderating entries, and ranking players on a live leaderboard. It uses server-rendered templates with HTMX for fast interactions and Channels for real-time updates.

## Tech Stack

* Python and Django
* Django Channels with Redis
* HTMX and Django templates
* SQLite for local development
* Playwright and pytest for testing

## Quick Start

1. Create and activate a virtual environment.
2. Install dependencies.
3. Run migrations.
4. Start the app.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements/dev.txt
python manage.py migrate
python manage.py runserver
```

## Environment

Create a `.env` file in the repository root and set values you need for local development.

```env
DJANGO_SECRET_KEY=change-me
DJANGO_DEBUG=1
DJANGO_ALLOWED_HOSTS=*
REDIS_URL=redis://127.0.0.1:6379/0
```

## Testing

Run the full test suite with:

```bash
pytest
```

Run Playwright tests with:

```bash
npx playwright test
```

## Project Layout

* `apps/` contains domain apps like quests, submissions, moderation, seasons, and leaderboard
* `con_quest/` contains project settings, routing, and ASGI/WSGI entrypoints
* `templates/` contains server-rendered HTML templates
* `tests/` contains integration and end-to-end test coverage

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.
