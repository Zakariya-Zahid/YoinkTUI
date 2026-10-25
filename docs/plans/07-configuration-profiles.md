# Module 07 — Configuration & Profiles

> Status: 🟡 P1 presets complete (v0.3.0) · Phase: 1 · Primary files:
> `backend/config.py` (`AppConfig`), `backend/presets.py`, `app.py` (re-export)
>
> Remaining unchecked items are config schema migration and the settings UI.

## 1. Purpose

Own **how the user and the environment configure the app**: paths, quality,
containers, presets/profiles, defaults, and precedence rules.

## 2. Current state

- `AppConfig` is a per-instance `slots` dataclass defined in
  `backend/config.py`; `app.py` re-exports it for compatibility.
- Full TOML schema lives in `backend/config.py` with XDG paths
  (`$XDG_CONFIG_HOME/yoinktui/config.toml`), validation, and warnings.
- Precedence is **CLI flag > `YOINKTUI_*` env var > TOML file > default**.
- CLI supports `--config`, `--print-config`, `--write-default-config`,
  `--doctor`, plus policy/network/UI flags.
- Invalid values warn and fall back to defaults; a malformed file never crashes.
- Download dir defaults to `~/Videos/yoinktui/` and is created on startup.
- Last URL is stored under `$XDG_STATE_HOME/yoinktui/state.json`.
- Built-in presets (`music`, `archive`, `mobile`) are merged with user-defined
  `[presets.<name>]` tables; the format screen can apply a preset from a modal,
  and the action bar shows the active profile.
- `--print-config` and `--write-default-config` include the effective preset
  tables, so the generated TOML documents the full policy.

## 3. Goals

- One documented configuration system with clear precedence:
  **CLI flag > env var > config file > built-in default**.
- Reusable **profiles/presets** ("Music", "Archive", "Mobile", "Best").
- Every download policy knob lives here and is consumed by module 01.

**Non-goals:** secret management beyond cookies-path references (module 01).

## 4. Workstreams

### WS 07.1 — Config object — **[P0]**
- [x] Make `AppConfig` a per-instance object (no shared mutable class default).
- [x] Define the full schema: see below.
- [x] Path resolution respecting `XDG_CONFIG_HOME` / `XDG_DATA_HOME`
      (plus `XDG_STATE_HOME` for the last-URL state).

Draft schema (`config.toml`):

```toml
[general]
theme = "dark"
default_mode = "video"        # video | vonly | audio
confirm_quit = true

[download]
dir = "~/Videos/yoinktui"
quality_cap = 1080            # 0 = best
container = "mkv"             # mkv | mp4 | auto
audio_format = "mp3"          # mp3 | m4a | opus | flac
audio_quality = "0"
concurrent_fragments = 4
rate_limit = ""               # e.g. "5M"
write_subtitles = false
embed_metadata = true
embed_thumbnail = false
keep_original = false

[network]
proxy = ""
cookies_from_browser = ""     # chrome | firefox | brave | …

[ui]
ascii = false
no_color = false
show_preview = true

[presets.mobile]
mode = "video"
quality_cap = 720
container = "mp4"
audio_format = "m4a"
description = "720p MP4/AAC for phones and tablets"
```

Built-ins are `music`, `archive`, and `mobile`; a `[presets.<name>]` table
overrides only the keys it sets and adds new presets alongside them.

### WS 07.2 — Loader & precedence — **[P0]**
- [x] TOML loader with validation and helpful error messages.
- [x] Env-var overrides (`YOINKTUI_DOWNLOAD_DIR`, …).
- [x] CLI overrides (module 09) merged last.
- [x] `yoinktui --print-config` / `--write-default-config` (with module 09).

### WS 07.3 — Profiles / presets — **[P1]**
- [x] Named profiles selectable in the UI (mode + container + cap bundle).
- [x] Ship built-ins; allow user-defined profiles in config.
- [x] Show the active profile in the action bar.

### WS 07.4 — Migration & robustness — **[P1]**
- [ ] Config schema version + migration on upgrade.
- [x] Fall back to defaults on parse errors, surface a warning (never crash).
- [~] Validate paths are writable; create dirs with correct perms.

## 5. Milestones

| Milestone | Scope | Exit criteria |
|-----------|-------|---------------|
| M1 — Config exists | WS 07.1–07.2 | TOML file drives cap/container/dir; precedence tested |
| M2 — Profiles | WS 07.3 | ≥ 3 presets usable from the UI |
| M3 — Safe upgrades | WS 07.4 | Bad config never crashes; migration tested |

## 6. Acceptance criteria

- Changing `quality_cap`/`container` in `config.toml` changes the yt-dlp command.
- No download policy remains hardcoded in `screens.py`.
- `AppConfig` is never shared between two app instances (tested).

## 7. Dependencies

- Module 01 (consumes policy), 03 (state), 08 (persist last-used), 09 (CLI flags).

## 8. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Config sprawl | Keep the schema minimal; document each key |
| Silent misconfig | Validate loudly, warn, fall back |
| Path/security issues | No shell interpolation; explicit types |

## 9. Metrics

- % of downloads using a non-default profile.
- Config parse error rate (target → 0 with warnings).

## 10. Open questions

- Do we ship a config *write* path in-app (settings screen) or editor-only?
- Is a profile a full bundle or a diff over defaults?
