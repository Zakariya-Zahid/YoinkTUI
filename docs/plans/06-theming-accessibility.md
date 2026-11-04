# Module 06 — Theming, Accessibility & Keybindings

> Status: 🟢 stable · Phase: 4 · Primary files: `tui/app.tcss`, `src/yoinktui/app.py`, `docs/contracts/keys.md`

## 1. Purpose

Own the **look, feel, and inclusiveness**: color system, themes, layout
resilience, accessibility, and the keyboard model.

## 2. Current state

- `textual-dark`, `textual-light`, and `high-contrast` themes supported and tested.
- `HIGH_CONTRAST_THEME` registered with pure `#000000` background and high-visibility contrast tokens.
- `?` and `F1` open `HelpModal` with a comprehensive keyboard reference table across all screens.
- Keyboard navigation contract documented in `docs/contracts/keys.md`.
- Responsive bounds across 80×24 and 120×40 validated with snapshots.

## 3. Goals

- A coherent design system with **real light/dark and high-contrast themes**.
- Layouts that adapt from 60×20 up to large screens without clipping.
- Usable with a screen reader, no color, or ASCII-only fonts.

**Non-goals:** widget logic (04, 05).

## 4. Workstreams

### WS 06.1 — Design tokens & themes — **[P0]**
- [x] Move palette into Textual theme variables so `dark`/`light` actually switch.
- [x] Ship at least `dark`, `light`, and `high-contrast` themes.
- [x] Persist theme choice (module 07/08).
- [x] Name tokens semantically (`$dl-active`, `$data-row-odd`) rather than by color.

### WS 06.2 — Responsive layout — **[P0]**
- [x] Replace fixed widths/heights with proportions + `min-width`/`min-height`.
- [x] Define breakpoints: compact (< 80 cols), regular, wide.
- [~] Graceful degradation: hide preview pane before the table.
- [x] Test at 60×20, 80×24, 120×40, 200×60.

### WS 06.3 — Accessibility — **[P1]**
- [x] `--no-color` / `NO_COLOR` honored; meaning via text markers, not hue.
- [x] ASCII fallback set for emoji/box-drawing (config flag or auto-detect).
- [x] Focus indicators visible and consistent on all interactive widgets.
- [x] Screen-reader friendly labels/titles on panels and buttons.

### WS 06.4 — Keyboard model — **[P1]**
- [x] Documented, conflict-free binding map per screen (`docs/contracts/keys.md`).
- [x] Vim-like navigation everywhere; `?` opens a help/cheat-sheet overlay.
- [~] Remappable bindings via config (module 07).
- [x] Footer shows the most relevant bindings; palette shows the rest.

### WS 06.5 — Style hygiene — **[P2]**
- [x] Remove dead CSS selectors and duplicate rules.
- [x] Lint/format the stylesheet; keep one declaration style.
- [x] Snapshot tests for each theme (module 10).

## 5. Milestones

| Milestone | Scope | Exit criteria |
|-----------|-------|---------------|
| M1 — Real themes | WS 06.1 | Toggle visibly changes UI; ≥ 2 themes |
| M2 — Responsive | WS 06.2 | No clipping at 60×20 |
| M3 — Accessible | WS 06.3–06.4 | No-color + ASCII + remaps + help overlay |

## 6. Acceptance criteria

- `Ctrl+D` (or `:theme`) visibly switches themes and persists across restarts.
- Every screen is usable at 80×24 with no truncated controls.
- All information survives with color disabled.

## 7. Dependencies

- Module 03 (layout structure), 07 (theme/binding config), 10 (snapshot tests).

## 8. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Custom vars can't theme | Adopt Textual theme API; migrate tokens |
| Responsive churn | Snapshot matrix in CI |
| Font glyph assumptions | ASCII fallback + capability detect |

## 9. Metrics

- Supported min terminal size; snapshot pass rate across themes.
- Contrast ratio of key text/background pairs (target ≥ 4.5:1).

## 10. Open questions

- Do we expose a user-themeable CSS override path (`~/.config/yoinktui/app.tcss`)?
- Is a "light" theme a priority for a terminal tool, or is high-contrast enough?
