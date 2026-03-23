"""
Extract the first URL from a Telegram message.
Works with PTB Message entities.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from telegram import Message

_URL_RE = re.compile(
    r"https?://[^\s\)\]\>\"\']+",
    re.IGNORECASE,
)


def extract_url(message: "Message") -> str | None:
    """
    Return the first URL found in the message.
    Checks entities first (TEXT_LINK, URL), then falls back to regex on text.
    """
    if message.entities:
        for entity in message.entities:
            # TEXT_LINK has url directly on the entity
            if entity.type.name == "TEXT_LINK" and entity.url:
                return entity.url
            # URL entity: extract from text
            if entity.type.name == "URL" and message.text:
                start = entity.offset
                end = entity.offset + entity.length
                return message.text[start:end]

    text = message.text or message.caption or ""
    m = _URL_RE.search(text)
    return m.group(0) if m else None
