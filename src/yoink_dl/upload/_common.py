from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from telegram.constants import ParseMode

if TYPE_CHECKING:
    from telegram import ReplyParameters


@dataclass(frozen=True)
class CommonSendArgs:
    chat_id: int
    parse_mode: str = ParseMode.HTML
    reply_parameters: ReplyParameters | None = None
    message_thread_id: int | None = None
