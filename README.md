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
| GET | /downloads | user | My download history |
| GET | /downloads/all | admin | All downloads |
| GET | /settings | user | My dl settings |
| PATCH | /settings | user | Update dl settings |
| GET | /stats/overview | admin | Download statistics |
| GET | /cookies | user | My cookies |
| POST | /cookies | user | Add cookie |
| GET | /cookies/all | admin | All cookies |
| DELETE | /cookies/{domain} | user | Delete cookie |

## Frontend pages

| Path | Role | Description |
|---|---|---|
| `/history` | user | Personal download history |
| `/admin/cookies` | admin | Cookie management |
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
- **Clipping** - `/cut` cuts video by `HH:MM:SS-HH:MM:SS` range via ffmpeg
- **Forum topics** - respects group forum topics, auto-creates "Downloads" DM topic
- **Cookie management** - per-user Netscape cookie files passed to yt-dlp
- **Progress tracking** - real-time download progress in chat
- **gallery-dl** - e621.net and similar sites; multi-file results sent as media groups

## Configuration

| Variable | Default | Description |
|---|---|---|
| `dl_proxy_urls` | - | Comma-separated proxy URLs, round-robin per request |
| `dl_max_file_size` | `50` | Max file size in MB |
| `dl_rate_limit_per_minute` | `5` | Downloads per user per minute |
| `dl_rate_limit_per_hour` | `30` | Downloads per user per hour |
| `dl_rate_limit_per_day` | `100` | Downloads per user per day |
| `dl_nsfw_enabled` | `false` | Enable NSFW detection and blur |

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
  services/            # proxy, cookies, NSFW detection
  i18n/locales/        # translations (en.yml, ru.yml)
frontend/
  manifest.tsx         # plugin route registration
  src/pages/           # admin/cookies, admin/nsfw, admin/stats, settings, history
```
