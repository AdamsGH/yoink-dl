# Yoink Downloads

Downloads adds media controls and pages to [Yoink](https://github.com/AdamsGH/yoink-core). The active service runs in Yoink's Rust backend with a confined Python extraction worker.

This repository contains the downloader frontend and retained legacy Python implementation. It is not a standalone native service.

## Use

Send a media URL to the bot or use `/download`, `/video`, `/audio`, `/image`, or `/playlist`.

Private settings include format, audio codec, split size, NSFW blur, proxy selection, and shared-cookie opt-in. The Mini App also provides cookies and download history.

Clips, subtitles, format reports, inline search, and stream links have separate command and access constraints. Provider authentication and regional restrictions can prevent a download.

## Cookies and settings

Use `/cookie token` for a short-lived, single-use browser-extension token. Cookie contents remain private credentials. Shared pool access requires current authority.

The settings form sends changed writable fields with an ETag precondition. A concurrent edit requires explicit reload rather than silently overwriting the newer values.

## Setup

Install and operate this component through the core repository. Native configuration uses `YOINK_RUST_*` variables. Python package configuration does not configure the native runtime.

YouTube authentication uses the native credential service and combined Unix gateway. The retained standalone Python/Express walkthrough is not the active deployment.

## Documentation

- [Download guide](https://github.com/AdamsGH/yoink-core/blob/master/docs/features/downloads/README.md)
- [Commands and compatibility](https://github.com/AdamsGH/yoink-core/blob/master/docs/features/downloads/compatibility.md)
- [Settings contract](https://github.com/AdamsGH/yoink-core/blob/master/docs/features/downloads/settings.md)
- [Cookie and OAuth contracts](https://github.com/AdamsGH/yoink-core/blob/master/docs/features/downloads/cookies.md)
- [Installation](https://github.com/AdamsGH/yoink-core/blob/master/docs/operations/installation.md)
