# Module 02 — Media Metadata & Extraction

> Status: 🟡 P0 complete (v0.2.0) · Phase: 1 · Primary files: `backend/models.py`, `probe()` in `backend/ytdlp.py`
>
> Remaining unchecked items are P1/P2 hardening (invariants, thumbnail proxy,
> multi-audio/subtitle tracks, richer extraction).

## 1. Purpose

Turn a URL into **structured, trustworthy metadata** and normalise yt-dlp's
loose JSON into our domain models. Also owns thumbnail retrieval.

## 2. Current state

- `probe()` runs yt-dlp through `_capture()` with a timeout and cooperative
  cancellation; parsed JSON flows through `MediaInfo.from_dict` /
  `FormatInfo.from_dict`.
- `models.py` coerces `None`/`"NA"`/non-finite numerics and exposes derived
  labels (`label`, `resolution`, `codec_label`, `size`, `has_video`, `has_audio`,
  `duration_label`, `upload_date_label`, `live_label`).
- The old `UrlScreen._on_probed` undefined-`url` bug is fixed; the submitted URL
  is passed through and persisted.
- Probe failures are typed (`UNSUPPORTED` vs `NO_STREAMS`, plus network/auth/
  not-found/geo/cancelled) and rendered by the URL screen inline or in a modal.
- Thumbnails are still fetched by `ThumbnailCard` via `httpx`, so cookies/proxy/
  geo handling is not yet shared with yt-dlp (P1).

## 3. Goals

- A typed, documented metadata model that is the single source of truth.
- Cancellable probing with structured errors.
- Thumbnails that work wherever yt-dlp works.

**Non-goals:** download policy (module 01), rendering (module 04).

## 4. Workstreams

### WS 02.1 — Fix metadata correctness — **[P0]**
- [x] Fix `UrlScreen._on_probed` undefined `url`; pass the submitted URL through.
- [x] Add `probe()` timeout + cancellation (cooperative cancel flag).
- [x] Validate/sanitise numeric fields; add tests for `"NA"`, `None`, `0`, floats.
- [x] Surface `is_live`, `duration`, `upload_date` cleanly in the model.

### WS 02.2 — Typed probe errors — **[P0]**
- [x] Reuse the module 01 error taxonomy for probe failures
      (`NOT_FOUND`, `GEO`, `AUTH`, `NETWORK`, `UNSUPPORTED`).
- [x] Distinguish "site unsupported" from "no streams found".

### WS 02.3 — Model hardening — **[P1]**
- [ ] Add `__post_init__` invariants (width/height/fps sane ranges).
- [ ] Add `to_dict()` / `from_dict()` round-trip with a schema version.
- [x] Extract `label`/`resolution`/`codec_label` logic into testable helpers.
- [ ] Support multi-audio / multi-subtitle tracks in the model.

### WS 02.4 — Thumbnail pipeline — **[P1]**
- [ ] Prefer yt-dlp-provided thumbnail URLs, but fetch with the same
      cookies/proxy as the probe where relevant.
- [ ] Cache thumbnails on disk (hash by URL) to avoid refetching.
- [ ] Bound memory: downscale before handing to `textual-image`.
- [ ] Graceful placeholder on failure (already present) + retry once.

### WS 02.5 — Richer extraction surface — **[P2]**
- [ ] Chapters, subtitles availability, formats' `filesize` vs `filesize_approx`
      reconciliation with confidence.
- [ ] Playlist/collection metadata (for module 05 queue).
- [ ] Description/tags/categories truncation strategy for the info panel.

## 5. Milestones

| Milestone | Scope | Exit criteria |
|-----------|-------|---------------|
| M1 — Correct & cancellable | WS 02.1–02.2 | Probe can be cancelled; no NameError; typed errors |
| M2 — Solid model | WS 02.3 | Round-trip tests; invariants enforced |
| M3 — Reliable thumbnails | WS 02.4 | Cache + fallback; no unbounded memory |

## 6. Acceptance criteria

- Probing a URL twice in a row cannot crash the app.
- Every probe failure renders a typed, human-readable message.
- `MediaInfo` round-trips through `to_dict`/`from_dict` unchanged (tested).

## 7. Dependencies

- Module 01 for the error taxonomy.
- Module 10 for model tests.
- Module 08 for metadata used by history/library.

## 8. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| yt-dlp JSON shape changes | Schema-versioned model + tolerant coercion |
| Large playlists blow memory | Cap + stream metadata (module 05) |
| Thumbnails fail on restricted sites | Reuse yt-dlp session or skip gracefully |

## 9. Metrics

- Probe p50/p95 latency; probe failure breakdown by reason.
- Model round-trip test coverage.

## 10. Open questions

- Should we store raw yt-dlp JSON for replay/debugging (opt-in)?
- Do we need a metadata cache keyed by URL + yt-dlp version?
