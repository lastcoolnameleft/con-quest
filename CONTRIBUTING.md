---
title: Contributing to ConQuest
description: Contribution guidelines for development workflow, testing, and pull requests in ConQuest.
author: lastcoolnameleft
ms.date: 2026-05-14
ms.topic: how-to
keywords:
  - contributing
  - django
  - testing
  - pull requests
estimated_reading_time: 4
---

## Welcome

Thanks for contributing to ConQuest. This project is a Django app with server-rendered templates, real-time updates, and a strong focus on reliability and fair gameplay.

## Development Setup

1. Create a virtual environment and activate it.
2. Install dependencies.
3. Run migrations.
4. Start the development server.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements/dev.txt
python manage.py migrate
python manage.py runserver
```

## Branching and Commits

1. Create a focused branch for each change.
2. Keep commits small and descriptive.
3. Avoid mixing refactors with behavioral changes in one commit.

## Code Style

* Follow existing code patterns and naming conventions.
* Keep changes minimal and targeted to the task.
* Prefer clear, maintainable code over clever shortcuts.

## Testing Expectations

Run tests before opening a pull request.

```bash
pytest
```

Run end-to-end checks when your changes affect UI behavior, auth, moderation, scoring, or realtime flows.

```bash
npx playwright test
```

## Pull Request Checklist

Before requesting review, confirm the following:

* Relevant tests pass locally
* New logic has test coverage where practical
* Documentation and configuration are updated when needed
* No secrets or sensitive values are added to tracked files

## Security and Privacy

* Never commit credentials, API keys, or private tokens.
* Keep `.env` local and out of git.
* Validate user-facing changes for permission and moderation safety.

## Questions and Discussion

If you are unsure about scope or implementation details, open an issue or start a draft pull request early so discussion can happen before large changes are made.
