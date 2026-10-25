# Downloading Udemy lectures

YoinkTUI uses yt-dlp for Udemy, just like every other supported site. Udemy is
different from YouTube in two important ways:

1. A **course** is the playlist; individual lectures are the videos.
2. Udemy requires a logged-in session and often rejects requests that do not
   look like a real browser.

This guide covers the workflow that works with the current yt-dlp extractor.
Only download content you have purchased, enrolled in, or are otherwise
authorized to access.

## 1. Export your Udemy cookies

The easiest option is a browser extension that exports cookies in Netscape
format, such as **Get cookies.txt LOCALLY**.

1. Log into Udemy in Firefox.
2. Open any `udemy.com` page.
3. Open the extension and export cookies for `udemy.com`.
4. Save the file, for example:

   ```text
   ~/cookies.txt
   ```

5. Verify that it contains your authentication cookies:

   ```bash
   head -1 ~/cookies.txt
   grep -E 'access_token|client_id|dj_session_id' ~/cookies.txt
   ```

The first line should be:

```text
# Netscape HTTP Cookie File
```

If `access_token` and `client_id` are missing, you exported from a logged-out
session or the wrong browser profile. Cookies are login credentials: keep the
file private (`chmod 600`) and never commit or share it.

You can also let yt-dlp read Firefox directly:

```bash
yt-dlp --cookies-from-browser firefox ...
```

If Firefox has multiple profiles, pass the real profile path instead of a
placeholder:

```bash
yt-dlp --cookies-from-browser \
  "firefox:~/.mozilla/firefox/xxxxxxxx.default-release" ...
```

## 2. Use browser impersonation

Udemy/Cloudflare commonly returns `HTTP Error 403: Forbidden` to yt-dlp even
when the cookies are valid. `--impersonate chrome` makes the request look like
a browser and is required for the workflow documented here.

Test a lecture with yt-dlp:

```bash
yt-dlp \
  --cookies ~/cookies.txt \
  --impersonate chrome \
  --simulate \
  "https://www.udemy.com/<course-slug>/learn/v4/t/lecture/<lecture-id>"
```

## 3. URL forms

### Single lecture

The modern Udemy URL looks like this:

```text
https://www.udemy.com/course/<course-slug>/learn/lecture/<lecture-id>?start=465#overview
```

The current yt-dlp Udemy extractor handles the legacy lecture form more
reliably. Remove the playback query/fragment and rewrite it as:

```text
https://www.udemy.com/<course-slug>/learn/v4/t/lecture/<lecture-id>
```

This also works for some lectures:

```text
https://www.udemy.com/<course-slug>/#/lecture/<lecture-id>
```

The `?start=465` parameter is only Udemy's playback position. It does not
select a clip. Use YoinkTUI's clip feature if you want to download a range.

### Whole course

Use the course URL that expands into a playlist:

```text
https://www.udemy.com/course/<course-slug>/learn/
```

Then use the **Playlist** button in YoinkTUI, not Enter. The Playlist screen
shows the lecture entries from the flat playlist probe.

Course extraction is more fragile than single-lecture extraction. If yt-dlp
returns:

```text
ERROR: [udemy:course] ... Unable to extract course id
```

the course page/extractor combination is failing. In that case, use the legacy
single-lecture URLs and queue lectures individually.

## 4. Download in YoinkTUI

Launch YoinkTUI with the same cookie and impersonation arguments:

```bash
yoinktui \
  --yt-dlp-arg=--cookies \
  --yt-dlp-arg=~/cookies.txt \
  --yt-dlp-arg=--impersonate \
  --yt-dlp-arg=chrome
```

For a single lecture:

1. Paste the legacy lecture URL.
2. Press **Enter** to probe it.
3. Choose **Video+Audio**, **Video Only**, or **Audio Only**.
4. Press **d** to download or **q** to add it to the queue.

For a whole course playlist:

1. Paste the course URL.
2. Click **Playlist**.
3. Choose **Video+Audio**, **Video Only**, or **Audio Only**.
4. Click **Queue all**.

Audio Only extracts audio from each lecture using the configured
`audio_format`/`audio_quality` (MP3 by default). The queue is sequential; use
the Queue and Library screens to inspect per-item status.

## 5. DRM and failures

The playlist probe does not tell you which lectures are DRM-protected. Each
lecture is extracted when its turn arrives:

- Non-DRM lectures download normally.
- DRM-protected lectures fail individually with a message like
  `This video is DRM protected`.
- The queue continues with the next item after a failure.
- Failed items are recorded in the Queue screen and Library history.
- Audio Only does **not** bypass DRM.

yt-dlp does not decrypt DRM-protected video, and YoinkTUI does not add a DRM
bypass. A retry will not fix a DRM failure. It may fix an expired-cookie,
network, or temporary Udemy failure.

## 6. Troubleshooting

| Symptom | What to try |
|---------|-------------|
| `HTTP Error 403: Forbidden` | Use `--impersonate chrome`; verify the cookies are from a logged-in session. |
| `Unable to extract course id` | Try the `/learn/` course URL; if it still fails, use legacy lecture URLs individually. |
| Cookies not found | Use the real Firefox profile path, or export `cookies.txt` with the extension. |
| Auth/403 later in a large queue | Refresh `cookies.txt`; the Udemy session may have expired. |
| `This video is DRM protected` | Not fixable with yt-dlp; skip that lecture. |
| `yt-dlp --update-to nightly` says package-manager install | Update with the package manager or install a separate nightly binary. |

If a course expands to a playlist but individual lectures fail, verify one
lecture directly with the yt-dlp command from section 2 before queueing the
whole course.
