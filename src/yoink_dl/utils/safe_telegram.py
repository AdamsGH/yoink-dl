"""
Safe wrappers around common Telegram API calls.
Handles FloodWait (RetryAfter in PTB) and other transient errors.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict

from telegram import Bot, Message
from telegram.error import RetryAfter, BadRequest, TimedOut
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

_MAX_RETRIES = 3


async def safe_send(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    text: str,
    **kwargs,
) -> Message | None:
    for attempt in range(_MAX_RETRIES):
        try:
            return await context.bot.send_message(chat_id=chat_id, text=text, **kwargs)
        except RetryAfter as e:
            logger.warning("RetryAfter %ds (attempt %d)", e.retry_after, attempt + 1)
            await asyncio.sleep(e.retry_after)
        except TimedOut:
            await asyncio.sleep(2)
        except Exception as e:
            logger.error("safe_send failed: %s", e)
            return None
    return None


async def safe_edit(
    message: Message,
    text: str,
    **kwargs,
) -> Message | None:
    for attempt in range(_MAX_RETRIES):
        try:
            return await message.edit_text(text, **kwargs)
        except RetryAfter as e:
            await asyncio.sleep(e.retry_after)
        except BadRequest as e:
            if "Message is not modified" in str(e):
                return message
            logger.warning("safe_edit BadRequest: %s", e)
            return None
        except TimedOut:
            await asyncio.sleep(2)
        except Exception as e:
            logger.error("safe_edit failed: %s", e)
            return None
    return None


async def safe_delete(message: Message) -> bool:
    try:
        await message.delete()
        return True
    except Exception as e:
        logger.warning("safe_delete failed: %s", e)
        return False


async def delete_many(bot: Bot, chat_id: int, message_ids: list[int]) -> None:
    """
    Delete up to 100 messages in a single API call (Bot API 6.0+).
    Falls back to individual deletes if bulk call fails.
    Silently ignores errors (no permissions, already deleted, etc.).
    """
    ids = [mid for mid in message_ids if mid]
    if not ids:
        return
    try:
        await bot.delete_messages(chat_id=chat_id, message_ids=ids)
    except Exception as exc:
        logger.debug("Bulk delete failed (chat=%s, ids=%s): %s", chat_id, ids, exc)
        results = await asyncio.gather(
            *(bot.delete_message(chat_id=chat_id, message_id=mid) for mid in ids),
            return_exceptions=True,
        )
        for mid, res in zip(ids, results):
            if isinstance(res, Exception):
                logger.debug("delete_message failed (chat=%s, msg=%s): %s", chat_id, mid, res)


async def safe_answer_callback(
    context: ContextTypes.DEFAULT_TYPE,
    query_id: str,
    text: str = "",
    show_alert: bool = False,
) -> None:
    try:
        await context.bot.answer_callback_query(
            callback_query_id=query_id,
            text=text,
            show_alert=show_alert,
        )
    except Exception as e:
        logger.warning("safe_answer_callback failed: %s", e)
