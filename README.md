# yoink-dl

Media downloader plugin for [yoink-core](https://github.com/AdamsGH/yoink-core).

Supports video, audio, image, and playlist downloads via yt-dlp and gallery-dl. Per-user quality/codec/proxy settings, NSFW detection, file caching, rate limiting, inline YouTube search, forum topic routing, cookie management, and clipping.

Included in yoink-core as a git submodule at `plugins/yoink-dl`.

## Bot commands

### User commands (all chats)

| Command | Description |
|---|---|
| `/video` | Download video |
| `/audio` | Download audio |
| `/image` | Download image |
| `/playlist` | Download playlist |
| `/search` | Search YouTube |
| `/cut` | Cut video by time range |
| `/link` | Get direct media URL |

URLs sent without a command are auto-detected and downloaded.

### User commands (private chat)

| Command | Description |
|---|---|
| `/settings` | Preferences overview |
| `/format` | Video quality and codec |
| `/args` | Custom yt-dlp arguments |
| `/subs` | Subtitle language |
| `/split` | Split size for large files |
| `/mediainfo` | Toggle media info display |
| `/proxy` | Set download proxy |
| `/cookie` | Manage site cookies |
| `/tags` | Toggle filename tags |
| `/clean` | Clean up bot messages |
| `/usage` | My download stats |

### Moderator commands

| Command | Description |
|---|---|
| `/get_log` | User download log |

### Admin commands

| Command | Description |
|---|---|
| `/uncache` | Remove URL from file cache |
| `/reload_cache` | Reload file cache |

## RBAC

`dl` commands are available to all users with `user` role or higher by default - no explicit feature grant required. Access is enforced per-handler via `AccessPolicy(min_role=user, check_group_enabled=True, check_thread_policy=True)`.

The inline handler is guarded by `FeatureSpec(dl:inline, default_min_role=user)` at the inline dispatcher level.

## API endpoints

Mounted at `/api/v1/dl/`. Auth: JWT Bearer token.

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | /downloads | user | My download history (includes media_type, group_title) |
| GET | /downloads/all | admin | All downloads |
| GET | /settings | user | My dl settings |
| PATCH | /settings | user | Update dl settings |
| GET | /stats/overview | admin | Download statistics |
| GET | /cookies | user | My cookies (includes inherited flag) |
| GET | /cookies/inherited | user | Cookies inherited via shared_cookies permission |
| POST | /cookies | user | Add cookie |
| GET | /cookies/all | admin | All cookies |
| DELETE | /cookies/{domain} | user | Delete cookie |

## Frontend pages

| Path | Role | Description |
|---|---|---|
| `/history` | user | Personal download history; Item list with per-type layout (video/audio/gallery/clip), dynamic search + period filter (7d/30d/90d/All), ExternalLink for supergroup messages |
| `/admin/cookies` | admin | Cookie management; Item layout with favicons, inherited cookies, Upload button |
| `/admin/nsfw` | admin | NSFW ruleset management |
| `/admin/bot-settings` | admin | Global bot settings |
| `/admin/stats` | admin | Download analytics |
| `/settings` | user | Personal preferences |

## Features

- **yt-dlp + gallery-dl** backends with automatic URL detection
- **Per-user settings** - quality, codec (avc1/hevc/av1/vp9), container, proxy, subtitles, split size
- **File cache** - Telegram `file_id` reuse; supports multi-file results (albums)
- **NSFW detection** - configurable blur rules per domain/tag
- **Rate limiting** - per-minute/hour/day limits per user
- **Inline mode** - YouTube search (`@bot query`) with result caching
- **Clipping** - `/cut` cuts video by `HH:MM:SS-HH:MM:SS` range via ffmpeg; `clip_start`/`clip_end` written to download_log on success
- **Clip media type** - clips are stored with `media_type="clip"` (separate from video); shown with Clapperboard icon in history
- **Forum topics** - respects group forum topics, auto-creates "Downloads" DM topic
- **Cookie management** - per-user Netscape cookie files passed to yt-dlp; inherited cookies via `shared_cookies` permission
- **Progress tracking** - real-time download progress in chat
- **gallery-dl** - e621.net and similar sites; multi-file results sent as media groups; gallery title fetched before download; zip archives named after the pool/gallery (`{Pool Name}.zip`)
- **IPv6 rotation** - optional outbound IPv6 source address rotation via `IPv6Pool` service; applied to both yt-dlp and gallery-dl requests
- **Download log** - all download outcomes (ok, cached, error) written to download_log with `user_id`, `group_id`, `thread_id`, `media_type`, `group_title`

## Configuration

| Variable | Default | Description |
|---|---|---|
| `dl_proxy_urls` | - | Comma-separated proxy URLs, round-robin per request |
| `dl_max_file_size` | `50` | Max file size in MB |
| `dl_rate_limit_per_minute` | `5` | Downloads per user per minute |
| `dl_rate_limit_per_hour` | `30` | Downloads per user per hour |
| `dl_rate_limit_per_day` | `100` | Downloads per user per day |
| `dl_nsfw_enabled` | `false` | Enable NSFW detection and blur |
| `ipv6_cidr` | - | IPv6 CIDR block to rotate source addresses from (e.g. `2001:db8::/48`) |
| `ipv6_domains` | - | Comma-separated domains that should use IPv6 rotation |

## Package structure

```
src/yoink_dl/
  plugin.py            # entry point (DlPlugin)
  config.py            # DlConfig (pydantic-settings)
  api/router.py        # FastAPI routes
  bot/middleware.py    # PTB middleware setup
  commands/            # bot command handlers (video, audio, cut, inline, ...)
  download/            # yt-dlp / gallery-dl manager, ffmpeg, music download
  upload/              # Telegram upload, caption builder, media group sender
  url/                 # URL extraction, normalization, resolution, pipeline
  storage/             # SQLAlchemy models and repos
  services/
    proxy.py           # round-robin proxy selector
    cookies.py         # per-user Netscape cookie files
    nsfw.py            # NSFW blur rules
    ipv6_pool.py       # IPv6 source address rotation (IPv6Pool)
  i18n/locales/        # translations (en.yml, ru.yml)
frontend/
  manifest.tsx         # plugin route registration
  src/pages/           # admin/cookies, admin/nsfw, admin/stats, settings, history
```
