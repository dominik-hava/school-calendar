## Sirius calendar proxy

This repository downloads the upstream Sirius ICS feed, applies local schedule overrides, and serves a standards-compliant `calendar.ics` over HTTPS so macOS Calendar and iOS can subscribe via `https://` or `webcal://`.

### Prerequisites

- Install [uv](https://docs.astral.sh/uv/) and ensure it is on your `PATH`.
- Place your TLS material at `tls/cert.pem` and `tls/key.pem` (self-signed is fine for local testing; Apple devices require a publicly trusted certificate when off-LAN).
- Set `CALENDAR_ICAL_URL` to the upstream Sirius ICS export before running anything (e.g. `export CALENDAR_ICAL_URL="https://sirius.fit.cvut.cz/export.ics"`).
- Edit `config.toml`:
  - `[http]` → tweak timeout/backoff settings if needed.
  - `[serve]` → default host `0.0.0.0`, port `9300`, and TLS paths.
  - `[[rules]]` → lesson-specific moves (primary/secondary categories, target weekday/time, optional overrides).
  - `[[recurring_events]]` → additional injected events with precise recurrence.
- (Optional) Set `SIRIUS_CALENDAR_CONFIG=/absolute/path/to/config.toml` when running via automation. The loader falls back to the repository `config.toml`.
- Sync dependencies once: `uv sync`.

### Generate `calendar.ics`

```bash
uv run python modify_calendar.py
```

The modifier downloads the upstream feed with retries, preserves `VTIMEZONE`, applies rule shifts (including same-week backward moves), injects configured recurring events, and writes atomically to `calendar.ics`. On fetch failure the last known good file is left untouched; check STDOUT for structured logs.

### Serve over HTTPS

```bash
uv run python -m app.server
```

Server defaults come from `[serve]` in `config.toml`, but you can override with `CALENDAR_HOST`, `CALENDAR_PORT`, `CALENDAR_TLS_CERT`, or `CALENDAR_TLS_KEY`. The handler resolves `calendar.ics` from the project root, responds with:

- `Content-Type: text/calendar; charset=utf-8`
- `Cache-Control: no-cache`
- Strong `ETag` based on size + mtime
- `Last-Modified` in GMT
- Proper 304 responses for `If-None-Match` / `If-Modified-Since`

Verify headers after generating the feed:

```bash
curl -I https://localhost:9300/calendar.ics --insecure

etag=$(curl -sI https://localhost:9300/calendar.ics --insecure | tr -d '\r' | awk '/^ETag:/ {print $2}')
curl -I -H "If-None-Match: $etag" https://localhost:9300/calendar.ics --insecure
```

Multiple subscribers (macOS, iOS, or other clients) can now sync efficiently.

### Tests

Run the suite locally:

```bash
uv run pytest
```

Tests cover weekday shifting, `DURATION` handling, RRULE frequency updates, timezone preservation, recurring event injection, and an end-to-end parse to ensure the resulting ICS stays valid.

### macOS & iOS subscription

1. Ensure the service is reachable via HTTPS with a certificate trusted by the device. For remote iPhone access, expose the service publicly (e.g. reverse proxy, Cloudflare Tunnel, or a small VPS with a real cert).
2. macOS: Calendar → File → New Calendar Subscription… → enter `https://your-host:9300/calendar.ics`. Choose an auto-refresh interval (5–15 minutes recommended) and disable alerts if desired.
3. iOS: Settings → Calendar → Accounts → Add Account → Other → Add Subscribed Calendar → paste the same HTTPS URL. Adjust refresh frequency and alerts under account details.

Apple devices do not follow plain HTTP redirects and require HTTPS with a valid certificate when off local network.

#### Outbound HTTPS tunnel (no open ports)

If you do not want to expose your Mac via port-forwarding, run the server locally and publish it through an outbound tunnel provider:

- **Cloudflare Tunnel**: `brew install cloudflared`, then `cloudflared tunnel --hostname calendar.example.com --url https://localhost:9300`. Cloudflare terminates TLS with a trusted certificate and forwards requests back over an outbound-only connection.
- **Tailscale Funnel**: enable [Funnel](https://tailscale.com/blog/funnel) on your tailnet, then `tailscale funnel --bg 9300`. The proxy issues a valid certificate and routes traffic over the Tailscale network without opening your router.

Update the subscription URL in Calendar/iOS to match the tunnel hostname (e.g. `https://calendar.example.com/calendar.ics`). Keep the tunnel process/agent running alongside the server.

### launchd automation

Two launch agents live in `launchd/`:

- `launchd/edu.calendar.refresh.plist.example` — runs `uv run python modify_calendar.py` every 15 minutes.
- `launchd/edu.calendar.server.plist.example` — keeps the FastAPI server alive at login.

Before installing:


1. Copy the example files: `cp launchd/*.plist.example launchd/` (remove `.example` from filenames)
2. Replace `__PROJECT_ROOT__` with this repo's absolute path (e.g., `/Users/yourusername/sirius-calendar`).
3. Replace `__UPSTREAM_CALENDAR_URL__` with your personal Sirius calendar URL (includes access token).
4. Replace `__UV_PATH__` with the output of `which uv` (e.g., `/Users/yourusername/.local/bin/uv`).
5. Replace `__PATH__` with your system PATH or use a minimal one like `/usr/local/bin:/usr/bin:/bin`.
6. Optional: adjust `StartInterval`, log paths, or add environment overrides.
7. Ensure `logs/` exists: `mkdir -p logs`

⚠️ **Security Warning**: The `.plist` files contain your personal access token. Never commit them to version control.

Install for the current user:

```bash
mkdir -p ~/Library/LaunchAgents
cp launchd/edu.calendar.*.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/edu.calendar.refresh.plist
launchctl bootstrap gui/$UID ~/Library/LaunchAgents/edu.calendar.server.plist
```

Force immediate runs if needed:

```bash
launchctl kickstart -k gui/$UID/edu.calendar.refresh
launchctl kickstart -k gui/$UID/edu.calendar.server
```

Logs default to `<project>/logs/*.log`. Use `SIRIUS_CALENDAR_CONFIG` in the plist’s `EnvironmentVariables` section when you relocate the configuration file.

### Troubleshooting

- Modifier errors: inspect `logs/refresh.err.log`. Failures leave the prior `calendar.ics` intact.
- Upstream outages: increase `http.max_retries` / `http.backoff_seconds` in `config.toml`.
- Certificate issues on iOS: use a publicly trusted cert (Let’s Encrypt, Cloudflare) or a tunnel that terminates TLS for you.
- Validation: rerun `uv run pytest` after editing rules to ensure ICS generation still passes parsing checks.
