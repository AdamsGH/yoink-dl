"""
/args  - custom yt-dlp arguments as key=value pairs.

Usage:
  /args                     - show current args
  /args key=value           - set a single arg
  /args reset               - clear all custom args
  /args key=value key2=...  - set multiple args

Stored as JSON dict in user settings (args_json).
Keys are validated against an allowlist to prevent abuse.
"""
from __future__ import annotations

import json
import shlex

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, ContextTypes

from yoink_dl.bot.middleware import get_user_repo
from yoink.core.i18n import t

# Allowlisted yt-dlp options safe to expose to users
_ALLOWED_KEYS = {
    "ratelimit",
    "sleep_interval",
    "max_sleep_interval",
    "concurrent_fragment_downloads",
    "retries",
    "fragment_retries",
    "skip_unavailable_fragments",
    "write_description",
    "write_thumbnail",
    "embed_thumbnail",
    "embed_metadata",
    "add_chapters",
    "sponsorblock_remove",
    "sponsorblock_mark",
}


def _format_args(args: dict) -> str:
    if not args:
        return "<i>No custom args set.</i>"
    lines = [f"<code>{k}</code> = <code>{v}</code>" for k, v in args.items()]
    return "\n".join(lines)


async def _cmd_args(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_user:
        return
    repo = get_user_repo(context)
    uid = update.effective_user.id
    user = await repo.get_or_create(uid)
    lang = user.language

    raw = " ".join(context.args or [])

    if not raw:
        text = t("args.title", lang) + "\n\n" + _format_args(user.args_json)
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("🗑 Reset", callback_data="args:reset"),
        ]]) if user.args_json else None
        await update.message.reply_html(text, reply_markup=kb)
        return

    if raw.strip().lower() == "reset":
        await repo.update(uid, args_json={})
        await update.message.reply_html(t("args.reset", lang))
        return

    # Parse key=value pairs
    try:
        tokens = shlex.split(raw)
    except ValueError as e:
        await update.message.reply_html(t("args.parse_error", lang, error=e))
        return

    updates: dict = {}
    errors: list[str] = []
    for token in tokens:
        if "=" not in token:
            errors.append(f"<code>{token}</code>  - missing '='")
            continue
        key, _, val = token.partition("=")
        key = key.strip().lower().replace("-", "_")
        if key not in _ALLOWED_KEYS:
            errors.append(f"<code>{key}</code>  - not allowed")
            continue
        # Basic type coercion
        if val.lower() in ("true", "yes"):
            updates[key] = True
        elif val.lower() in ("false", "no"):
            updates[key] = False
        elif val.isdigit():
            updates[key] = int(val)
        else:
            updates[key] = val

    if errors:
        await update.message.reply_html(t("args.validation_errors", lang, errors="\n".join(errors)))
        return

    merged = {**user.args_json, **updates}
    await repo.update(uid, args_json=merged)
    await update.message.reply_html(
        t("args.saved", lang) + "\n\n" + _format_args(merged)
    )


async def _cb_args_reset(update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from telegram import CallbackQuery
    query: CallbackQuery | None = update.callback_query
    if not query or not update.effective_user:
        return
    await query.answer()
    repo = get_user_repo(context)
    user = await repo.update(update.effective_user.id, args_json={})
    await query.edit_message_text(t("args.reset", user.language), parse_mode="HTML")


def register(app: Application) -> None:
    from telegram.ext import CallbackQueryHandler
    app.add_handler(CommandHandler("args", _cmd_args))
    app.add_handler(CallbackQueryHandler(_cb_args_reset, pattern=r"^args:reset$"))
