# Module 12 — Performance, Resources & Diagnostics

> Status: 🔴 needs work · Phase: 4 · Primary files: all; *(new)* `backend/log.py`,
> `--doctor`

## 1. Purpose

Own **how the app behaves under load and when things go wrong**: speed, memory,
resource limits, logging, and the support surface that makes bugs fixable.

## 2. Current state

- All I/O is already off the UI thread (`@work(thread=True)`), good baseline.
- `set_interval` timers (elapsed tick, probe spinner, thumbnail placeholder)
  are not explicitly stopped on unmount — potential leaks.
- No logging anywhere; errors surface as strings in modals/toasts only.
- No `--doctor`/`--version` diagnostics; `tool_available()` unused.
- Thumbnails decoded in-memory without a size cap.
- No stall/timeout handling on silent downloads.
- Fixed layouts (`min-height: 22`, `right-pane: 60`) risk poor behaviour on
  small or very large terminals.

## 3. Goals

- Snappy UI and bounded memory on large inputs (long playlists, huge thumbnails).
- Actionable diagnostics and logs a user can attach to a bug report.
- Graceful degradation instead of crashes.

**Non-goals:** premature micro-optimisation.

## 4. Workstreams

### WS 12.1 — Responsiveness budget — **[P1]**
- [ ] Measure and document cold start (< 400 ms target) and per-event UI cost.
- [ ] Coalesce high-frequency progress updates (throttle repaint to ~10 Hz).
- [ ] Ensure the event loop never does file/network/syscalls.
- [ ] Profile snapshot rendering for the dashboard.

### WS 12.2 — Memory & resources — **[P1]**
- [ ] Cap thumbnail dimensions before decode; free after display.
- [ ] Run yt-dlp with bounded concurrency (module 01) and no unbounded buffers.
- [ ] Bound activity-log retention and queue size.
- [ ] Stop all timers/workers on screen unmount; add a leak test.

### WS 12.3 — Robustness under load — **[P1]**
- [ ] Large playlists: stream items into the queue, don't materialise all.
- [ ] Disk-full handling (check free space before start; typed `DISK` error).
- [ ] Slow/flaky network: stall timeout, retry, clearer status.
- [ ] Tiny/giant terminals: responsive layout (module 06) + no crashes.

### WS 12.4 — Logging & diagnostics — **[P0]**
- [ ] Structured logging (`backend/log.py`) to
      `~/.local/share/yoinktui/logs/`, rotating, opt-out via `--no-log`.
- [ ] `--verbose` / `DEBUG=yoinktui` env for console logs.
- [ ] `yoinktui --doctor`: versions of Python/yt-dlp/ffmpeg, config path,
      writable check, terminal graphics capability, last error.
- [ ] `--support-bundle`: redacted logs + config + environment for issue reports.

### WS 12.5 — Error surfacing — **[P1]**
- [ ] Wire the module 01 taxonomy into the UI: reason + hint + "copy details".
- [ ] Distinguish retryable vs. fatal; offer retry inline.
- [ ] Never lose the underlying stderr — keep it in the log and the bundle.

## 5. Milestones

| Milestone | Scope | Exit criteria |
|-----------|-------|---------------|
| M1 — Diagnostics first | WS 12.4 | `--doctor` + rotating logs ship |
| M2 — Budgets | WS 12.1–12.2 | Cold start target met; no timer leaks |
| M3 — Load-safe | WS 12.3, 12.5 | 500-item playlist without OOM/hang |

## 6. Acceptance criteria

- Cold start ≤ 400 ms on a reference machine.
- Memory stays bounded during a 500-item playlist download.
- Any crash/error can be reported with a redacted support bundle.
- No orphaned timers/workers after leaving any screen.

## 7. Dependencies

- Module 01 (taxonomy/limits), 05 (queue volume), 06 (layout), 10 (perf tests).

## 8. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Perf work without measurement | Establish benchmarks before optimising |
| Logs leaking URLs/PII | Document + redaction in support bundle |
| Throttling hides progress | Keep final state accurate; throttle only repaint |

## 9. Metrics

- Cold start ms; idle CPU %; peak RSS; leak-test pass; support-bundle success.

## 10. Open questions

- Opt-in anonymous telemetry, or strictly local diagnostics? (Proposal: local.)
- What is the reference machine/hardware for perf targets?
