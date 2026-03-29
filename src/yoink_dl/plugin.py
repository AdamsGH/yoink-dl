"""DownloaderPlugin - implements YoinkPlugin protocol."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter

from yoink.core.plugin import InlineHandlerSpec, JobSpec, PluginContext, WebManifest, WebPage, SidebarEntry
from yoink_dl.config import DownloaderConfig


class DownloaderPlugin:
    name = "dl"
    version = "0.1.0"

    def __init__(self) -> None:
        self._config = DownloaderConfig()

    def get_config_class(self) -> type[DownloaderConfig]:
        return DownloaderConfig

    def get_models(self) -> list:
        from yoink_dl.storage.models import (
            Cookie, DownloadLog, FileCache, NsfwDomain, NsfwKeyword, RateLimit, UserSettings,
        )
        return [UserSettings, DownloadLog, FileCache, RateLimit, Cookie, NsfwDomain, NsfwKeyword]

    def get_handlers(self) -> list:
        from yoink_dl.commands import get_handler_specs
        return get_handler_specs()

    def get_features(self):
        from yoink.core.plugin import FeatureSpec
        return [
            FeatureSpec(
                plugin="dl",
                feature="inline",
                label="Inline search",
                description="YouTube search and URL lookup via @bot inline mode",
                default_min_role="user",
            ),
            FeatureSpec(
                plugin="dl",
                feature="shared_cookies",
                label="Shared admin cookies",
                description="Fall back to admin cookies when user has none for a domain",
                default_min_role="admin",
            ),
        ]

    def get_inline_handlers(self) -> list[InlineHandlerSpec]:
        from yoink_dl.commands.inline import handle_inline
        return [InlineHandlerSpec(
            callback=handle_inline,
            priority=0,
            # No prefix, no pattern: catch-all for any text query or URL.
            # Music plugin runs at priority=10 and claims music platform URLs first.
        )]

    def get_routes(self) -> APIRouter | None:
        from yoink_dl.api.router import router
        return router

    def get_locale_dir(self) -> Path | None:
        return Path(__file__).parent / "i18n" / "locales"

    def get_web_manifest(self) -> WebManifest:
        return WebManifest(pages=[
            WebPage(
                path="/history",
                sidebar=SidebarEntry(
                    label="History", icon="Download", path="/history", section="main",
                ),
            ),
            WebPage(
                path="/admin/cookies",
                sidebar=SidebarEntry(
                    label="Cookies", icon="Cookie", path="/admin/cookies",
                    section="admin", min_role="admin",
                ),
            ),
            WebPage(
                path="/admin/nsfw",
                sidebar=SidebarEntry(
                    label="NSFW", icon="Shield", path="/admin/nsfw",
                    section="admin", min_role="moderator",
                ),
            ),
        ])

    def get_help_section(self, role: str, lang: str, granted_features: set[str] | None = None) -> str:
        import yaml
        from yoink.core.plugin import CommandSpec

        _ROLE_RANK = {"user": 0, "moderator": 1, "admin": 2, "owner": 3}
        rank = _ROLE_RANK.get(role, 0)

        locales_dir = Path(__file__).parent / "i18n" / "locales"
        en_data = yaml.safe_load((locales_dir / "en.yml").read_text())
        loc_file = locales_dir / f"{lang}.yml"
        loc_data = yaml.safe_load(loc_file.read_text()) if loc_file.exists() else {}

        def _section(key: str) -> dict:
            return loc_data.get("help_sections", {}).get(key) \
                or en_data.get("help_sections", {}).get(key) \
                or {}

        def _cmd_desc(cmd_name: str, cmd_en_desc: str) -> str:
            for entry in (loc_data.get("commands") or []):
                if entry.get("command") == cmd_name:
                    return entry.get("description") or cmd_en_desc
            return cmd_en_desc

        sections_cfg = en_data.get("help_sections", {})

        cmds: list[CommandSpec] = self.get_commands()
        visible = [c for c in cmds if _ROLE_RANK.get(c.min_role, 0) <= rank]

        _SECTION_ORDER = [
            ("user",      "download",   ("default",)),
            ("user",      "settings",   ("private",)),
            ("moderator", "moderator",  ("default", "private")),
            ("admin",     "admin",      ("default", "private")),
            ("owner",     "owner",      ("default", "private")),
        ]

        # Guide block - usage tips, shown first as expandable
        guide = _section("guide")
        guide_title = guide.get("title", "")
        guide_body = guide.get("body", "")
        music_guide = _section("music_guide")
        music_guide_title = music_guide.get("title", "")
        music_guide_body = music_guide.get("body", "")

        parts: list[str] = []

        if guide_title and guide_body:
            parts.append(f"<blockquote expandable><b>{guide_title}</b>\n{guide_body}</blockquote>")

        if music_guide_title and music_guide_body:
            parts.append(f"<blockquote expandable><b>{music_guide_title}</b>\n{music_guide_body}</blockquote>")

        for min_role, section_key, scopes in _SECTION_ORDER:
            if _ROLE_RANK.get(min_role, 0) > rank:
                continue
            sec_cmds = [
                c for c in visible
                if c.min_role == min_role and c.scope in scopes
            ]
            if not sec_cmds:
                continue
            sec = _section(section_key)
            title = sec.get("title", section_key.title())
            footer = sec.get("footer", "")
            lines = [f"/{c.command}  - {_cmd_desc(c.command, c.description)}" for c in sec_cmds]
            body = "\n".join(lines)
            if footer:
                body += f"\n\n{footer}"
            is_secondary = min_role != "user"
            if is_secondary:
                parts.append(f"<blockquote expandable><b>{title}</b>\n{body}</blockquote>")
            else:
                parts.append(f"<b>{title}</b>\n{body}")

        return "\n\n".join(parts)

    def get_commands(self) -> list:
        import yaml
        from yoink.core.plugin import CommandSpec

        locales_dir = Path(__file__).parent / "i18n" / "locales"
        en_data = yaml.safe_load((locales_dir / "en.yml").read_text())

        # Build a map of {command -> {lang: description}} from non-English locales
        lang_descriptions: dict[str, dict[str, str]] = {}
        for locale_file in locales_dir.glob("*.yml"):
            lang = locale_file.stem
            if lang == "en":
                continue
            try:
                loc_data = yaml.safe_load(locale_file.read_text())
                for entry in (loc_data.get("commands") or []):
                    cmd = entry.get("command")
                    desc = entry.get("description")
                    if cmd and desc:
                        lang_descriptions.setdefault(cmd, {})[lang] = desc
            except Exception:
                pass

        return [
            CommandSpec(
                command=entry["command"],
                description=entry["description"],
                min_role=entry.get("min_role", "user"),
                scope=entry.get("scope", "default"),
                descriptions=lang_descriptions.get(entry["command"], {}),
            )
            for entry in (en_data.get("commands") or [])
        ]

    def get_jobs(self) -> list[JobSpec]:
        from yoink_dl.bot.progress import _flush_job
        from yoink_dl.storage.repos import FileCacheRepo

        async def _evict_cache(context: object) -> None:
            repo: FileCacheRepo | None = None
            if hasattr(context, "bot_data"):
                repo = context.bot_data.get("file_cache")
            if repo is not None:
                evicted = await repo.evict_expired()
                if evicted:
                    import logging
                    logging.getLogger(__name__).debug(
                        "Evicted %d expired file cache entries", evicted
                    )

        return [
            JobSpec(callback=_flush_job, interval=1.0, first=1.0, name="dl_progress_flush"),
            JobSpec(callback=_evict_cache, interval=3600.0, first=60.0, name="dl_cache_evict"),
        ]

    async def setup(self, ctx: PluginContext) -> None:
        """Populate bot_data with dl-specific services.

        Called once at startup after core bot_data (session_factory,
        user_repo, group_repo, bot_settings_repo) is already populated.
        """
        from yoink_dl.services.cookies import CookieManager
        from yoink_dl.services.nsfw import NsfwChecker
        from yoink_dl.storage.repos import (
            DownloadLogRepo, FileCacheRepo, RateLimitRepo, UserSettingsRepo,
        )

        sf = ctx.session_factory
        bd = ctx.bot_data

        bd["dl_config"] = self._config
        bd["dl_user_repo"] = UserSettingsRepo(sf)
        bd["file_cache"] = FileCacheRepo(sf)
        bd["download_log"] = DownloadLogRepo(sf)
        bd["rate_limit_repo"] = RateLimitRepo(sf)

        cookie_mgr = CookieManager(sf)
        bd["cookie_manager"] = cookie_mgr

        nsfw_checker = NsfwChecker(sf)
        await nsfw_checker.load()
        bd["nsfw_checker"] = nsfw_checker

        bd["settings"] = self._config

        from yoink.core.activity import register_activity_provider  # noqa: PLC0415
        from yoink_dl.activity import dl_activity_provider  # noqa: PLC0415
        register_activity_provider("dl", dl_activity_provider)
