# yoink-dl

Media downloader plugin for [yoink-core](https://github.com/AdamsGH/yoink-core). Uses yt-dlp and gallery-dl. Supports video, audio, image, and playlist downloads with per-user quality/codec/proxy settings, NSFW detection with blur, file caching, rate limiting, inline mode, forum topics, and DM topics.

Included in yoink-core as a git submodule at `plugins/yoink-dl`.

## Bot commands

### User commands (all chats)

| Command | Description |
|---|---|
| /video | Download video |
| /audio | Download audio |
| /image | Download image |
| /playlist | Download playlist |
| /search | Search YouTube |
| /cut | Cut video by time range |
| /link | Get direct media URL |

URLs sent without a command are detected and downloaded automatically.

### User commands (private chat)

| Command | Description |
|---|---|
| /settings | Preferences overview |
| /format | Video quality and codec |
| /args | Custom yt-dlp arguments |
| /subs | Subtitle language |
| /split | Split size for large files |
| /mediainfo | Toggle media info display |
| /proxy | Set download proxy |
| /cookie | Manage site cookies |
| /tags | Toggle filename tags |
| /clean | Clean up bot messages |

### Moderator commands

| Command | Description |
|---|---|
| /get\_log | User download log |
| /usage | User usage stats |

### Core admin commands (available regardless of active plugins)

`/block`, `/unblock`, `/ban_time`, `/broadcast`, `/group`, `/thread`, `/runtime` are provided by yoink-core.

### DL admin commands

| Command | Description |
|---|---|
| /uncache | Remove URL from cache |
| /reload\_cache | Reload file cache |

## API endpoints

Mounted at `/api/v1/dl/`. Auth: JWT Bearer token.

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | /downloads | user | My download history |
| GET | /downloads/all | admin | All downloads |
| POST | /downloads/{id}/retry | user | Retry failed download |
| GET | /settings | user | My dl settings |
| PATCH | /settings | user | Update dl settings |
| GET | /stats/overview | admin | Download statistics |
| GET | /cookies | user | My cookies |
| POST | /cookies | user | Add cookie |
| GET | /cookies/all | admin | All cookies |
| DELETE | /cookies/{domain} | user | Delete cookie |

## Features

- **yt-dlp + gallery-dl** backends with automatic URL detection
- **Per-user settings** - quality, codec (avc1/hevc/av1/vp9), container, proxy, subtitles, split size
- **File cache** - Telegram file\_id reuse to avoid re-uploading
- **NSFW detection** - configurable blur for detected content
- **Rate limiting** - per-minute, per-hour, per-day limits
- **Inline mode** - YouTube search with result caching
- **Forum topics** - respects group forum topics, auto-creates "Downloads" topic in DM
- **Cookie management** - per-user Netscape cookie files
- **Progress tracking** - real-time download progress in chat

## Package structure

```
src/yoink_dl/
  plugin.py            # entry point (DlPlugin)
  api/router.py        # FastAPI routes
  bot/middleware.py     # PTB middleware setup
  commands/            # bot command handlers
  download/            # yt-dlp/gallery-dl manager
  upload/              # Telegram upload, caption builder
  url/                 # URL extraction, normalization, resolution, pipeline
  storage/             # SQLAlchemy models and repos
  services/            # NSFW detection
  i18n/locales/        # translations (en.yml, ru.yml)
frontend/
  manifest.tsx         # plugin route registration
  src/pages/           # React pages for WebApp
```

## Tests

97 tests covering URL normalization, resolution, captions, NSFW detection, rate limiting, file cache, and download log.

```bash
# from yoink-core root
just test-dl
```
