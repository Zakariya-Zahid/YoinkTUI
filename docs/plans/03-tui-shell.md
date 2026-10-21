# Module 03 — TUI Shell & Navigation

> Status: 🟡 in progress · Phase: 1 · Primary files: `app.py`, `tui/screens.py`, `tui/__init__.py`

## 1. Purpose

Own the **application shell**: the `App` object, screen routing, global
bindings, application state, and the URL-input entry point.

## 2. Current state

- `YoinkTUIApp` pushes `UrlScreen` on mount; `CSS_PATH="tui/app.tcss"`.
- Flow: `UrlScreen` → (`probe`) → `FormatScreen` → (`download`) → `DownloadScreen`
  → pop back to `FormatScreen`; `ErrorModal` for failures.
- `UrlScreen` shows an inline spinner while probing (no modal).
- `AppConfig` is a **class attribute** (`config: AppConfig = AppConfig()`),
  so all app instances share one mutable config.
- `action_toggle_dark` flips `self.dark`, but custom CSS variables are fixed hex
  so the toggle has little visible effect.

## 3. Goals

- Predictable, extensible navigation with an explicit app state object.
- No shared mutable global state.
- Consistent back/cancel semantics across screens.

**Non-goals:** download mechanics (01), widget internals (04, 05).

## 4. Workstreams

### WS 03.1 — App state & config ownership — **[P0]**
- [ ] Replace the class-level `AppConfig` with a per-instance value created in
      `__init__` (accept overrides for tests/CLI).
- [ ] Introduce an `AppState` object (current `MediaInfo`, selected format,
      mode, queue) to decouple screens.
- [ ] Move config loading to module 07 and inject it here.

### WS 03.2 — Navigation contract — **[P0]**
- [ ] Define a documented screen graph and back-stack rules
      (`docs/contracts/navigation.md`).
- [ ] Guarantee `Esc` semantics per screen (quit / back / cancel) and test them.
- [ ] Prevent duplicate pushes (double-submit, rapid Enter).
- [ ] Restore focus to the right widget after each pop.

### WS 03.3 — Entry point hardening — **[P0]**
- [ ] Validate URL input before probing (scheme, whitespace, paste cleaning).
- [ ] Disable the input while probing; show inline errors instead of stacking modals.
- [ ] Remember the last URL (module 08) and pre-fill on relaunch.

### WS 03.4 — Shell extensibility — **[P1]**
- [ ] Screen registry + typed `ScreenResult` so `push_screen(...)` callbacks
      replace ad-hoc `pop_screen` calls.
- [ ] Global command palette (`Ctrl+P`) listing actions.
- [ ] Central `notify()` service replacing per-screen `StatusToast`.

### WS 03.5 — Lifecycle & teardown — **[P1]**
- [ ] Stop all timers/workers on screen unmount (spinner, elapsed tick).
- [ ] Confirm-on-quit when a download is running (or detach to queue).
- [ ] Handle terminal resize / tiny terminals without crashing (see 06, 12).

## 5. Milestones

| Milestone | Scope | Exit criteria |
|-----------|-------|---------------|
| M1 — State hygiene | WS 03.1 | Two app instances never share config/state |
| M2 — Navigation rules | WS 03.2–03.3 | Documented + tested back/cancel behaviour |
| M3 — Extensible shell | WS 03.4–03.5 | Palette + typed results + clean teardown |

## 6. Acceptance criteria

- `Esc` from every screen does the documented thing (tested).
- Rapid double-submit cannot push two `FormatScreen`s.
- App exits cleanly mid-download with no orphan process and no traceback.

## 7. Dependencies

- Module 07 (Config), Module 08 (last URL/history), Module 10 (navigation tests).

## 8. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Screen coupling grows | `AppState` + typed results, review per PR |
| Timer leaks on pop | Central lifecycle tests |
| Modal stacking | Inline status for retryable errors |

## 9. Metrics

- Screen-navigation test coverage.
- Crashes attributed to shell/lifecycle (target 0).

## 10. Open questions

- Single-window with panes vs. stacked screens long-term?
- Should the queue live in the shell (persistent) or in `DownloadScreen`?
