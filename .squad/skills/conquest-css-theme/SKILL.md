# Skill: ConQuest CSS Theme

## Pattern

Use `cq-*` CSS classes from `static/css/conquest.css` for consistent styling across templates.

## Key Classes

| Class | Purpose |
|-------|---------|
| `cq-navbar` | Gradient navbar |
| `cq-hero` | Full-width hero section |
| `cq-card` | Rounded card with shadow |
| `cq-quest-item` | Quest list card with hover |
| `cq-status-bar` | 4px color bar (add `.active`, `.pending`, `.complete`) |
| `cq-badge cq-badge-{status}` | Colored status pill |
| `cq-points` | Points pill (⭐ 5 pts) |
| `cq-join-card` | Dashed-border join form card |
| `cq-leaderboard-row` | Leaderboard entry with rank highlight |
| `cq-empty-state` | Empty state with emoji + guidance text |
| `cq-season-header` | Gradient page header |
| `btn-cq-primary` | Gradient pill button |
| `btn-cq-success` | Green pill button |

## CSS Custom Properties

All theme colors are in `:root` as `--cq-*` variables (primary, success, warning, danger, etc).

## When To Use

- New player-facing templates should use these classes instead of raw Bootstrap
- Admin/control templates can stay with default Bootstrap
