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
| GET | /downloads | user | My download history (media_type, group_title, clip fields) |
| GET | /downloads/all | admin | All downloads |
| POST | /downloads/{id}/retry | user | Re-queue a download |
| GET | /settings | user | My dl settings (includes has_pool_access flag) |
| PATCH | /settings | user | Update dl settings |
| GET | /admin/settings | admin | Global downloader settings |
| PATCH | /admin/settings | admin | Update global downloader settings |
| GET | /stats/overview | admin | Download statistics |
| GET | /cookies | user | My cookies + inherited pool cookies |
| POST | /cookies | user | Add personal cookie |
| DELETE | /cookies/by-id/{id} | user | Delete personal cookie |
| POST | /cookies/{id}/validate | user | Validate cookie |
| GET | /cookies/pool | admin | List pool cookies |
| POST | /cookies/pool | admin | Add pool cookie |
| DELETE | /cookies/pool/{id} | admin | Delete pool cookie |
| POST | /cookies/pool/refresh-labels | admin | Re-fetch account info for all pool cookies |

## Frontend pages

| Path | Role | Description |
|---|---|---|
| `/history` | user | Download history; Item list with per-type layout, dynamic search + period filter (7d/30d/90d/All), i18n chip labels (Clip/Quality/Duration/Size/Files/Group) |
| `/cookies` | user | Personal cookies + inherited pool cookies; pool toggle in header (visible when has_pool_access); inherited rows show opacity+label based on pool state |
| `/settings` | user | Preferences: quality/codec/container/proxy/subs/split/keyboard; Cookies card with use_pool_cookies toggle (visible when has_pool_access) |
| `/admin/cookies` | moderator | Cookie management: Pool card (avatar, real account name, ScanSearch refresh) + Personal card; shadcn AlertDialog for delete confirm |
| `/admin/nsfw` | admin | NSFW ruleset management |
| `/admin/stats` | admin | Download analytics; Item list with period filter, KPI grid, charts, RankedList for words/mentions |
| `/admin/bot-settings` | admin | Downloader card injected via botSettingsSections: retries, timeout, max file size (slider), rate limits, playlist count |

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
- **Cookie pool** - `is_pool` flag separates personal vs shared pool cookies; round-robin rotation via `CookieManager`; account info (name/avatar) fetched from YouTube/Instagram/Twitter APIs on upload; two-level dedup by session_key (SAPISID/uid) then content_hash
- **Pool access** - users with `shared_cookies` permission (or admin/owner role) get inherited pool cookies; `use_pool_cookies` user setting controls opt-in; `has_pool_access` returned in /dl/settings response
- **Personal+pool rotation** - when both exist for same domain, alternates between personal and pool cookie per user:domain key
- **Progress tracking** - real-time download progress in chat
- **gallery-dl** - e621.net and similar sites; multi-file results sent as media groups; gallery title fetched before download; zip archives named after the pool/gallery (`{Pool Name}.zip`)
- **IPv6 rotation** - optional outbound IPv6 source address rotation via `IPv6Pool` service; applied to both yt-dlp and gallery-dl requests
- **Download retries** - configurable via admin bot-settings (default 3); exponential backoff (1s/2s/4s); retries transient errors (ffmpeg crash, network); status message updated on each retry
- **Informative errors** - BotError shows localized message via i18n key; non-BotError shows sanitized message text instead of generic "unknown error"
- **Download log** - all download outcomes (ok, cached, error) written to download_log with `user_id`, `group_id`, `thread_id`, `media_type`, `group_title`
- **_safe_filename()** - Unicode lookalike substitution for `<>:"/\|?*` chars

## Configuration

| Variable | Default | Description |
|---|---|---|
| `MAX_FILE_SIZE_GB` | `2.0` | Max file size (runtime override via admin settings) |
| `DOWNLOAD_TIMEOUT` | `1200` | Seconds per job (runtime override via admin settings) |
| `DOWNLOAD_RETRIES` | `3` | Retry count fallback (runtime value in BotSetting dl.download_retries) |
| `MAX_PLAYLIST_COUNT` | `50` | Max playlist items (runtime override) |
| `RATE_LIMIT_PER_MINUTE` | `5` | Per-user rate limit (runtime override) |
| `RATE_LIMIT_PER_HOUR` | `30` | Per-user rate limit (runtime override) |
| `RATE_LIMIT_PER_DAY` | `100` | Per-user rate limit (runtime override) |
| `YOUTUBE_POT_ENABLED` | `true` | Enable PO Token provider for YouTube |
| `YOUTUBE_POT_URL` | `http://localhost:4416` | PO Token provider URL |
| `IPV6_CIDR` | - | IPv6 CIDR for source address rotation (ISP must route to host) |
| `IPV6_DOMAINS` | - | Comma-separated domains to use IPv6 rotation |
| `LOG_CHANNEL` | - | Channel ID for download log forwarding |

Note: rate limits, timeout, max file size, retries, and playlist count are stored in BotSetting KV (`dl.*` keys) and editable at runtime via admin bot-settings page. Config values are used as fallback defaults only.

## Services

| Service | Description |
|---|---|
| `cookie_account.py` | `fetch_account_info()`: fetches real name/avatar from YouTube (`youtubei/v1/account/account_menu` + SAPISID hash), Instagram, Twitter APIs |
| `cookies.py` | `CookieManager`: personal/pool CRUD, round-robin, `sync_from_file` after download, `mark_pool_invalid` on 403/401, `_rotate_personal_and_pool()` for alternating rotation |
| `proxy.py` | Round-robin proxy selector |
| `nsfw.py` | NSFW blur rules |
| `ipv6_pool.py` | `IPv6Pool`: source address rotation from a routed /56 prefix |

## Package structure

```
src/yoink_dl/
  plugin.py            # entry point (DlPlugin)
  config.py            # DlConfig (pydantic-settings)
  activity.py          # ActivityProvider registered with core at startup
  api/
    router.py          # thin FastAPI router (mounts sub-routers)
    routers/
      downloads.py     # /downloads, /downloads/{id}/retry
      cookies.py       # /cookies, /cookies/pool, /cookies/{id}/validate
      nsfw.py          # /nsfw/domains, /nsfw/keywords, /nsfw/check
    schemas.py         # request/response models
  bot/middleware.py    # PTB middleware setup
  commands/            # bot command handlers (video, audio, cut, inline, ...)
  download/            # yt-dlp / gallery-dl manager, ffmpeg, music download
  upload/              # Telegram upload, caption builder, media group sender
  url/
    pipeline/          # run.py (run_download), helpers.py (utilities)
    resolver.py        # URL resolution
    domains.py         # domain lists
  storage/
    models.py          # ORM models
    repos/             # settings.py, download.py, cookie.py, cache.py
  services/
    proxy.py           # round-robin proxy selector
    cookies.py         # CookieManager: personal/pool CRUD, round-robin, sync_from_file
    cookie_account.py  # account info fetcher (YouTube/Instagram/Twitter)
    nsfw.py            # NSFW blur rules
    ipv6_pool.py       # IPv6 source address rotation (IPv6Pool)
  i18n/locales/        # translations (en.yml, ru.yml)
frontend/
  manifest.tsx         # plugin route registration
  src/
    api/               # typed API modules: cookies.ts, downloads.ts, nsfw.ts, settings.ts, dl-stats.ts
    components/        # CookieFavicon.tsx
    hooks/             # useFavicon.ts
    lib/               # cookie-utils.ts (parseDomainFromNetscape)
    pages/
      history/         # HistoryPage.tsx
      settings/        # SettingsPage.tsx
      cookies/         # CookiesPage.tsx
      admin/cookies/   # AdminCookiesPage.tsx + useAdminCookies.ts
      admin/nsfw/      # AdminNsfwPage.tsx
      admin/stats/     # DlStatsPage.tsx
      admin/bot-settings/ # DlSettingsSection.tsx (injected via botSettingsSections)
```
