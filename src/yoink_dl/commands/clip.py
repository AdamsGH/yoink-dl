"""Clip command - download a time-clipped segment via URL timestamp params."""
from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes


async def cmd_clip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # TODO: implement
    if not update.message:
        return
    await update.message.reply_text("TODO: clip")
