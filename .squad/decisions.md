# Squad Decisions

## Active Decisions

### UI Theme & Design System (2025-07-18)

**Author:** Neo (Frontend Dev)

Introduced custom CSS theme (`conquest.css`) with indigo/violet gradient branding, CSS custom properties (`--cq-*`), and component classes (`cq-card`, `cq-quest-item`, `cq-badge-*`, `cq-leaderboard-row`). Mobile-first responsive navbar with hamburger menu; emoji-based visual language. Button labels simplified ("Start" vs "Start Quest"). **Impact:** All templates reference theme via `base.html`; test assertions updated; E2E specs updated for new heading text. **Audience:** Backend devs should extend `base.html` and use `cq-*` classes; test writers should verify button/heading text against templates.

## Governance

- All meaningful changes require team consensus
- Document architectural decisions here
- Keep history focused on work, decisions focused on direction
