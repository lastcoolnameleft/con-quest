# Neo — History

## Session Log

- **2026-05-17:** Team created. Project: con-quest — multiplayer scavenger hunt platform. Stack: Django 6, HTMX, Django Channels, Redis, Azure Blob Storage. Owner: Tommy Falgout.
- **2025-07-18:** Comprehensive UI/UX overhaul — added custom CSS theme (`static/css/conquest.css`), redesigned all player-facing templates with branded visuals, better navigation, and improved empty states. Updated tests to match new copy.

## Learnings

- Templates live at project-level `templates/` not per-app. Key ones: `base.html`, `seasons/index.html`, `seasons/detail.html`, `leaderboard/season_leaderboard.html`, `registration/login.html`.
- The navbar in `base.html` now uses Bootstrap collapse for mobile hamburger menu. Connection test dot is clickable (no separate button).
- Custom CSS is served from `static/css/conquest.css` — uses CSS custom properties for theming (primary: indigo/violet gradient).
- Tests assert on UI text — changing button labels or headings requires updating `tests/test_join_and_claim.py`, `tests/test_full_lifecycle_and_scale.py`, `tests/test_scoring_reason.py`, `tests/test_submission_resilience.py` and E2E specs.
- `seasons/index.html` has a hero section for first-time visitors (no joined seasons) and hides it for returning players.
- `seasons/detail.html` uses color-coded status bars on quest cards (CSS class: `cq-status-bar` + status name).
- The leaderboard uses emoji medals (🥇🥈🥉) for top 3 instead of plain rank numbers.
- Login page uses `<details>` to hide username/password form, promoting OAuth buttons.
- All empty states use `cq-empty-state` class with emoji icons and helpful guidance text.
