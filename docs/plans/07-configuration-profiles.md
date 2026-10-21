# Module 07 — Configuration & Profiles

> Status: 🔴 needs work · Phase: 1 · Primary files: `app.py` (`AppConfig`),
> *(new)* `backend/config.py`

## 1. Purpose

Own **how the user and the environment configure the app**: paths, quality,
containers, presets/profiles, defaults, and precedence rules.

## 2. Current state

- `AppConfig` is a dataclass with a single field (`download_dir`) and is declared
  as a **class attribute**, so it is shared across instances.
- Download dir default: `~/Videos/yoinktui/`.
- Quality cap (`1080`), merge container (`mkv`), and audio format (`mp3`) are
  **hardcoded** in `FormatScreen._start_download` / engine defaults.
- README claims the cap is "configurable via yt-dlp config", but the engine passes
  `--ignore-config`, so that advice does not work today.
- No config file, no env vars, no profiles.

## 3. Goals

- One documented configuration system with clear precedence:
  **CLI flag > env var > config file > built-in default**.
- Reusable **profiles/presets** ("Music", "Archive", "Mobile", "Best").
- Every download policy knob lives here and is consumed by module 01.

**Non-goals:** secret management beyond cookies-path references (module 01).

## 4. Workstreams

### WS 07.1 — Config object — **[P0]**
- [ ] Make `AppConfig` a per-instance object (no shared mutable class default).
- [ ] Define the full schema: see below.
- [ ] Path resolution respecting `XDG_CONFIG_HOME` / `XDG_DATA_HOME`.

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
```

### WS 07.2 — Loader & precedence — **[P0]**
- [ ] TOML loader with validation and helpful error messages.
- [ ] Env-var overrides (`YOINKTUI_DOWNLOAD_DIR`, …).
- [ ] CLI overrides (module 09) merged last.
- [ ] `yoinktui --print-config` / `--write-default-config` (with module 09).

### WS 07.3 — Profiles / presets — **[P1]**
- [ ] Named profiles selectable in the UI (mode + container + cap bundle).
- [ ] Ship built-ins; allow user-defined profiles in config.
- [ ] Show the active profile in the action bar.

### WS 07.4 — Migration & robustness — **[P1]**
- [ ] Config schema version + migration on upgrade.
- [ ] Fall back to defaults on parse errors, surface a warning (never crash).
- [ ] Validate paths are writable; create dirs with correct perms.

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
