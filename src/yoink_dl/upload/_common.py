from __future__ import annotations

from dataclasses import dataclass

from telegram import ReplyParameters
from telegram.constants import ParseMode


@dataclass(frozen=True)
class CommonSendArgs:
    chat_id: int
    parse_mode: str = ParseMode.HTML
    reply_parameters: ReplyParameters | None = None
    message_thread_id: int | None = None
