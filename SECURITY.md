# Security Policy

## Supported Versions

Only the latest stable release of YoinkTUI receives security updates.

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

If you discover a potential security vulnerability in YoinkTUI, please do **not** open a public issue.

Instead, please report security vulnerabilities via GitHub Private Vulnerability Reporting:
1. Navigate to the repository's [Security advisory tab](https://github.com/Zakariya-Zahid/YoinkTUI/security/advisories).
2. Click **Report a vulnerability**.
3. Provide details including:
   - A description of the vulnerability and its potential impact.
   - Exact steps or code to reproduce the behavior.
   - Affected versions and environment (OS, Python version, yt-dlp version).

Alternatively, email the maintainer directly at: `zakryiabukhari@gmail.com` with the subject `[SECURITY] YoinkTUI Vulnerability Report`.

### Security Scope & Expectations
- YoinkTUI acts as a frontend for `yt-dlp` and `ffmpeg`. Vulnerabilities within upstream tools should be reported directly to their respective upstream maintainers.
- Cookie handling: Cookie files and browser cookie extraction operate strictly under the user's local operating system permissions. YoinkTUI does not transmit or store cookies outside local execution parameters.
