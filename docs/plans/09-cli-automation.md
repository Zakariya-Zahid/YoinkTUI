# Module 09 — CLI & Automation

> Status: ⚪ not started · Phase: 3 · Primary files: `__main__.py`,
> *(new)* `src/yoinktui/cli.py`

## 1. Purpose

Own **headless use and integration**: command-line flags, non-interactive
downloading, config management, and hooks that let other tools drive us.

## 2. Current state

- `main()` only launches the TUI; no arguments, no subcommands, no output mode.
- The engine (`download()`) is already scriptable in-process.

## 3. Goals

- `yoinktui <url>` works without interacting with the TUI.
- Flags mirror config (module 07) with highest precedence.
- A stable, documented interface for scripts and other TUIs/tools.

**Non-goals:** a daemon/server (revisit if a queue daemon emerges).

## 4. Workstreams

### WS 09.1 — Argument surface — **[P1]**
- [ ] `yoinktui [URL]` — TUI when no URL, direct download when given.
- [ ] Flags: `-o/--output-dir`, `-f/--format`, `-m/--mode`,
      `--quality-cap`, `--container`, `--audio-format`, `--proxy`,
      `--cookies-from-browser`, `-q/--quiet`, `--json`, `--dry-run`.
- [ ] Global: `--config PATH`, `--print-config`, `--write-default-config`,
      `--version`, `--doctor`.
- [ ] Precedence: flags > env > config file > defaults (tested).

### WS 09.2 — Non-interactive mode — **[P1]**
- [ ] Plain/quiet progress to stdout; `--json` NDJSON event stream.
- [ ] Meaningful exit codes per error class (module 01 taxonomy).
- [ ] `--yes-playlist` / `--playlist-items` passthrough.
- [ ] Batch mode: read URLs from stdin / a file.

### WS 09.3 — yt-dlp passthrough & escape hatch — **[P2]**
- [ ] `--ytdlp-arg=…` (repeatable) forwarded verbatim.
- [ ] `--print-command` to show the exact invocation (shared with 05.4).
- [ ] Pass-through for advanced users without polluting the config schema.

### WS 09.4 — Integration hooks — **[P2]**
- [ ] Completion hook: run a user command with file path + metadata
      (`notify-send`, `xdg-open`, scripts).
- [ ] Optional IPC: a socket/`D-Bus`-ish channel so a running TUI can accept
      new URLs from the CLI/other apps.
- [ ] Shell completions (bash/zsh/fish) generated from the arg parser.

## 5. Milestones

| Milestone | Scope | Exit criteria |
|-----------|-------|---------------|
| M1 — Basic CLI | WS 09.1 | `yoinktui URL -o DIR -f 137` downloads headlessly |
| M2 — Automatable | WS 09.2 | `--json` + exit codes + batch/stdin |
| M3 — Integrable | WS 09.3–09.4 | Passthrough + hooks + completions |

## 6. Acceptance criteria

- Same URL downloads identically via TUI and CLI (same engine path).
- `--dry-run --print-command` prints the command and downloads nothing.
- Exit codes are stable and documented.
- `--json` output is valid NDJSON parseable line-by-line.

## 7. Dependencies

- Module 01 (engine + taxonomy), 07 (config precedence), 05 (queue for batch).

## 8. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| CLI/TUI drift | Both call one engine + one config resolver |
| Flag explosion | Curated flags + `--ytdlp-arg` escape hatch |
| TUI-vs-headless UX | Explicit `--json`/`--quiet` contracts |

## 9. Metrics

- % of downloads via CLI vs TUI (informational).
- CLI integration test coverage.

## 10. Open questions

- Is `yoinktui URL` expected to open the TUI pre-filled or to download?
  (Proposal: download; `--tui` to force the UI.)
- Do we need a long-running queue server, or is per-invocation enough?
