# Module 04 — Format Picker & Preview

> Status: 🟡 in progress · Phase: 2 · Primary files: `tui/widgets.py`
> (`FormatTable`, `InfoPanel`, `ThumbnailCard`, `UrlInput`)

## 1. Purpose

Own the **decision surface**: showing media info, the thumbnail, and the table of
available formats, and letting the user pick one confidently.

## 2. Current state

- `FormatTable` (DataTable): 7 columns, zebra stripes, emits `FormatSelected`.
- `InfoPanel`: label/value rows for title/channel/duration/etc.
- `ThumbnailCard`: `textual-image` `AutoImage` with animated `▶ LOADING`
  placeholder and `-error` state; fetches via `httpx`.
- Selection is single-row; mode buttons live on `FormatScreen` (module 05).
- `ClipModal` provides optional start/end timestamps with presets and validation.
- Local `FormatTable._human_size` duplicates `widgets.human_size`.

## 3. Goals

- The table is sortable, filterable, and trustworthy about size/quality.
- Preview (thumbnail + info) is informative and never blocks selection.
- One formatting implementation, shared everywhere.

**Non-goals:** download/queue mechanics (05).

## 4. Workstreams

### WS 04.1 — Table intelligence — **[P0]**
- [ ] Reuse shared `human_size`/`human_time` (remove the duplicate).
- [ ] Sortable columns (quality, size, bitrate, ext) via header click / keybind.
- [ ] Filter toggle: `Video only` / `Audio only` / `All`.
- [ ] "Recommended" marker on the best stream for the current mode.
- [ ] Handle empty/oversized format lists (pagination or scroll hints).

### WS 04.2 — Selection UX — **[P0]**
- [ ] Clear selected vs. focused row styling (currently both use accent).
- [ ] Show the chosen format summary in the action bar before downloading.
- [ ] Keyboard: `j/k`, `g/G`, `Home/End`, `Enter` select, `d` download.

### WS 04.3 — Preview pane — **[P1]**
- [ ] Thumbnail cache + downscale (shared with WS 02.4).
- [ ] Adaptive layout when terminal is narrow (hide preview, keep table).
- [ ] InfoPanel: duration as `h:mm:ss`, rounded view counts, clickable URL hint.
- [ ] Loading skeletons instead of a bare "LOADING".

### WS 04.4 — Accessibility & i18n readiness — **[P1]**
- [ ] ASCII fallback for emoji/box-drawing glyphs in the table markers.
- [ ] Ensure color is never the *only* signal (markers + text).
- [ ] Externalise user-facing strings (feeds module 06 i18n).

## 5. Milestones

| Milestone | Scope | Exit criteria |
|-----------|-------|---------------|
| M1 — Trustworthy table | WS 04.1–04.2 | Sort/filter + clear selection, shared formatting |
| M2 — Great preview | WS 04.3 | Adaptive layout, cached thumbnails |
| M3 — Accessible | WS 04.4 | ASCII/non-color modes work |

## 6. Acceptance criteria

- Sorting/filtering never loses the confirmed selection.
- Sizes match `human_size` exactly (single implementation, tested).
- Narrow terminals (< 80 cols) still allow selecting and downloading.

## 7. Dependencies

- Module 02 (metadata fields), Module 06 (styling/ASCII), Module 10 (widget tests).

## 8. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| DataTable perf with many formats | Virtualised rows; cap + scroll |
| Graphics protocol variance | Capability detection + placeholder fallback |
| Layout regressions | Snapshot tests (module 10) |

## 9. Metrics

- Keystrokes to select a format (target ≤ 3 typical).
- Snapshot coverage of FormatScreen states.

## 10. Open questions

- Do we show *estimated* final size for `video+audio` merges?
- Should the table support multi-select for batch queueing?
