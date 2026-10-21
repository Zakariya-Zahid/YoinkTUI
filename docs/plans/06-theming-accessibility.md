# Module 06 — Theming, Accessibility & Keybindings

> Status: 🔴 needs work · Phase: 4 · Primary files: `tui/app.tcss`, widget `DEFAULT_CSS`

## 1. Purpose

Own the **look, feel, and inclusiveness**: color system, themes, layout
resilience, accessibility, and the keyboard model.

## 2. Current state

- Single dark palette defined as custom variables in `app.tcss`
  (`$accent`, `$surface-raised`, `$surface-hover`, `$overlay`, …).
- Global `ProgressBar { margin: 0 }`; widget `DEFAULT_CSS` blocks mix built-in
  Textual vars (`$surface`, `$accent`) with app vars.
- Dead styles: `InfoLabel`, `InfoValue`, `.LoadingSpinner`, `.LoadingShimmer`,
  `.selected-row` (never applied as a class), `#dismiss` duplicate, stray
  `.datatable--row-hover`.
- Fixed geometry: `right-pane: width 60`, `min-height: 22`, `.center-box 80`,
  `ErrorModal .dialog 70` → breaks on narrow/short terminals.
- `Ctrl+D` toggles `dark`, but fixed hex vars make the toggle nearly invisible.
- Emoji/box glyphs used in labels (may be double-width or missing in some fonts).

## 3. Goals

- A coherent design system with **real light/dark themes**.
- Layouts that adapt from 60×20 up to large screens without clipping.
- Usable with a screen reader, no color, or ASCII-only fonts.

**Non-goals:** widget logic (04, 05).

## 4. Workstreams

### WS 06.1 — Design tokens & themes — **[P0]**
- [ ] Move palette into Textual theme variables so `dark`/`light` actually switch.
- [ ] Ship at least `dark`, `light`, and `high-contrast` themes.
- [ ] Persist theme choice (module 07/08).
- [ ] Name tokens semantically (`$dl-active`, `$data-row-odd`) rather than by color.

### WS 06.2 — Responsive layout — **[P0]**
- [ ] Replace fixed widths/heights with proportions + `min-width`/`min-height`.
- [ ] Define breakpoints: compact (< 80 cols), regular, wide.
- [ ] Graceful degradation: hide preview pane before the table.
- [ ] Test at 60×20, 80×24, 120×40, 200×60.

### WS 06.3 — Accessibility — **[P1]**
- [ ] `--no-color` / `NO_COLOR` honored; meaning via text markers, not hue.
- [ ] ASCII fallback set for emoji/box-drawing (config flag or auto-detect).
- [ ] Focus indicators visible and consistent on all interactive widgets.
- [ ] Screen-reader friendly labels/titles on panels and buttons.

### WS 06.4 — Keyboard model — **[P1]**
- [ ] Documented, conflict-free binding map per screen (`docs/contracts/keys.md`).
- [ ] Vim-like navigation everywhere; `?` opens a help/cheat-sheet overlay.
- [ ] Remappable bindings via config (module 07).
- [ ] Footer shows the most relevant bindings; palette shows the rest.

### WS 06.5 — Style hygiene — **[P2]**
- [ ] Remove dead CSS selectors and duplicate rules.
- [ ] Lint/format the stylesheet; keep one declaration style.
- [ ] Snapshot tests for each theme (module 10).

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
