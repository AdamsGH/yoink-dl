"""
Pre-download action menu.

Triggered when quality="ask" in /format, or via /cut <url>.

Screen flow (single message, edited in-place):

  [ACTION]   - video info + format buttons
    ┌─────────────────────────────┐
    │ 🎬 Title                    │
    │ ⏱ 22:14  •  360p / 720p    │
    │                             │
    │  [360p]  [720p]  [Best]     │
    │  [🎵 Audio]   [✂️ Cut]      │
    │  [✖ Cancel]                 │
    └─────────────────────────────┘

  [CUT QUALITY]  - after tapping ✂️ Cut
    ┌─────────────────────────────┐
    │ ✂️ Title                    │
    │ Choose quality for clip:    │
    │                             │
    │  [360p]  [720p]  [Best]     │
    │  [← Back]                   │
    └─────────────────────────────┘

  [SEGMENTS]  - after quality chosen
    ┌─────────────────────────────┐
    │ ✂️ Title  •  720p           │
    │                             │
    │ ①  00:00:00 → ──:──:──      │
    │ [▶ Start] [⏹ End] [🗑]      │
    │                             │
    │ [+ Add segment]             │
    │ [✂️ Cut & Download]         │
    │ [← Back]                    │
    └─────────────────────────────┘

  Time input: bot sends one prompt message, user replies,
  bot deletes prompt + reply, menu updates.

Callback data (prefix "am:"):
  am:dl:<token>:<quality>       download at quality
  am:audio:<token>              download as MP3
  am:cut:<token>                open cut quality picker
  am:cutq:<token>:<quality>     quality chosen → segments screen
  am:set:<token>:<idx>:s        awaiting start time for segment idx
  am:set:<token>:<idx>:e        awaiting end time for segment idx
  am:del:<token>:<idx>          delete segment idx
  am:add:<token>                add empty segment
  am:go:<token>                 download with all segments
  am:back:<token>               return to action screen
  am:cancel:<token>             close menu

Session in context.bot_data["am"][token]:
  url, title, duration, formats, thumb,
  clip_quality, segments, awaiting, chat_id, message_id
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor

import yt_dlp

from telegram import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import Application, CallbackQueryHandler, ContextTypes

from yoink_dl.url.clip import ClipSpec
from yoink_dl.utils.safe_telegram import delete_many

logger = logging.getLogger(__name__)

_CB = "am:"
_KEY = "am"
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="am_info")

_QUALITIES = ["2160p", "1440p", "1080p", "720p", "480p", "360p", "240p", "144p"]


# Helpers

def _fmt(secs: int | None) -> str:
    if secs is None:
        return "──:──:──"
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _fmt_dur(secs: float | None) -> str:
    if not secs:
        return ""
    return _fmt(int(secs))


def _sessions(ctx: ContextTypes.DEFAULT_TYPE) -> dict:
    return ctx.bot_data.setdefault(_KEY, {})


# Info extraction

def _extract(url: str) -> tuple[str, float, list[str], str | None]:
    """Blocking: (title, duration_sec, available_qualities, thumb_url)."""
    opts = {"quiet": True, "no_warnings": True, "skip_download": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False) or {}

    title = (info.get("title") or url)[:80]
    duration = float(info.get("duration") or 0)
    thumb = info.get("thumbnail")

    heights: set[int] = set()
    for f in info.get("formats") or []:
        h = f.get("height")
        if isinstance(h, int) and h > 0:
            heights.add(h)

    available: list[str] = []
    for q in _QUALITIES:
        px = int(q[:-1])
        if not heights or any(h >= px * 0.85 for h in heights):
            available.append(q)
    if not available:
        available = ["best"]

    return title, duration, available, thumb


# Text builders

def _text_action(title: str, duration: float, formats: list[str]) -> str:
    dur = f"  •  ⏱ {_fmt_dur(duration)}" if duration else ""
    fmt_line = "  ".join(formats[:6])
    return f"🎬 <b>{title}</b>{dur}\n\n{fmt_line}"


def _text_cut_quality(title: str) -> str:
    return f"✂️ <b>{title}</b>\n\nChoose quality for the clip:"


def _text_segments(title: str, quality: str, segs: list[dict]) -> str:
    lines: list[str] = []
    for i, seg in enumerate(segs):
        num = ("①②③④⑤⑥⑦⑧⑨⑩")[i] if i < 10 else f"{i+1}."
        start = _fmt(seg.get("s"))
        end = _fmt(seg.get("e"))
        lines.append(f"{num}  <code>{start}</code> → <code>{end}</code>")
    segs_text = "\n".join(lines)
    return f"✂️ <b>{title}</b>  •  {quality}\n\n{segs_text}"


# Keyboard builders

def _kb_action(token: str, formats: list[str]) -> InlineKeyboardMarkup:
    q_btns = [
        InlineKeyboardButton(q, callback_data=f"{_CB}dl:{token}:{q}", style="primary")
        for q in formats
    ]
    rows = [q_btns[i:i+4] for i in range(0, len(q_btns), 4)]
    rows.append([
        InlineKeyboardButton("🎵 Audio", callback_data=f"{_CB}audio:{token}"),
        InlineKeyboardButton("✂️ Cut", callback_data=f"{_CB}cut:{token}"),
    ])
    rows.append([InlineKeyboardButton("✖ Cancel", callback_data=f"{_CB}cancel:{token}", style="danger")])
    return InlineKeyboardMarkup(rows)


def _kb_cut_quality(token: str, formats: list[str]) -> InlineKeyboardMarkup:
    q_btns = [
        InlineKeyboardButton(q, callback_data=f"{_CB}cutq:{token}:{q}", style="primary")
        for q in formats
    ]
    rows = [q_btns[i:i+4] for i in range(0, len(q_btns), 4)]
    rows.append([InlineKeyboardButton("← Back", callback_data=f"{_CB}back:{token}")])
    return InlineKeyboardMarkup(rows)


def _kb_segments(token: str, segs: list[dict]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for i in range(len(segs)):
        rows.append([
            InlineKeyboardButton("▶ Start", callback_data=f"{_CB}set:{token}:{i}:s"),
            InlineKeyboardButton("⏹ End",   callback_data=f"{_CB}set:{token}:{i}:e"),
            InlineKeyboardButton("🗑",       callback_data=f"{_CB}del:{token}:{i}", style="danger"),
        ])
    rows.append([InlineKeyboardButton("+ Add segment", callback_data=f"{_CB}add:{token}")])
    rows.append([InlineKeyboardButton("✂️ Cut & Download", callback_data=f"{_CB}go:{token}", style="success")])
    rows.append([InlineKeyboardButton("← Back", callback_data=f"{_CB}back:{token}")])
    return InlineKeyboardMarkup(rows)


# Edit helpers

async def _edit(ctx: ContextTypes.DEFAULT_TYPE, sess: dict, text: str, kb: InlineKeyboardMarkup) -> None:
    """Edit the menu message in-place. Tries caption first (photo msg), falls back to text."""
    chat_id = sess["chat_id"]
    message_id = sess["message_id"]
    has_photo = sess.get("has_photo", False)

    logger.debug("_edit: chat=%s msg=%s has_photo=%s", chat_id, message_id, has_photo)

    if has_photo:
        try:
            await ctx.bot.edit_message_caption(
                chat_id=chat_id, message_id=message_id,
                caption=text, parse_mode=ParseMode.HTML, reply_markup=kb,
            )
            return
        except Exception as e:
            logger.warning("Caption edit failed (%s), trying text edit", e)
            sess["has_photo"] = False

    try:
        await ctx.bot.edit_message_text(
            chat_id=chat_id, message_id=message_id,
            text=text, parse_mode=ParseMode.HTML, reply_markup=kb,
        )
    except Exception as e:
        logger.error("Menu edit failed entirely: %s", e)


# Entry point

async def show_menu(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    url: str,
) -> None:
    """Show the pre-download menu. Called from url_handler or /cut."""
    assert update.message

    status = await update.message.reply_text("⏳ Fetching info…")

    loop = asyncio.get_running_loop()
    try:
        title, duration, formats, thumb = await loop.run_in_executor(_executor, _extract, url)
    except Exception as e:
        logger.warning("Menu info extract failed %s: %s", url, e)
        title, duration, formats, thumb = url[:60], 0.0, ["best", "720p", "480p", "360p"], None

    token = uuid.uuid4().hex[:16]
    sess: dict = {
        "url": url,
        "title": title,
        "duration": duration,
        "formats": formats,
        "thumb": thumb,
        "clip_quality": None,
        "segments": [{"s": None, "e": None}],
        "awaiting": None,       # {"idx": int, "kind": "s"|"e", "prompt_id": int}
        "chat_id": update.message.chat_id,
        "origin_id": update.message.message_id,  # original user message  - delete after download
        "message_id": None,
        "has_photo": False,
    }
    _sessions(context)[token] = sess

    text = _text_action(title, duration, formats)
    kb = _kb_action(token, formats)

    try:
        if thumb:
            msg = await update.message.reply_photo(
                photo=thumb, caption=text,
                parse_mode=ParseMode.HTML, reply_markup=kb,
            )
            sess["has_photo"] = True
        else:
            raise ValueError("no thumb")
    except Exception:
        msg = await update.message.reply_html(text, reply_markup=kb)
        sess["has_photo"] = False

    sess["message_id"] = msg.message_id
    await status.delete()


# Time input dispatch (called from url_handler)

async def handle_time_input(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> bool:
    """
    Consume text message if a time-input is awaited for any session in this chat.
    Returns True if consumed, False to fall through to url_handler.
    """
    if not update.message:
        return False

    chat_id = update.message.chat_id
    token: str | None = None
    sess: dict | None = None

    for tok, s in _sessions(context).items():
        if s["chat_id"] == chat_id and s.get("awaiting"):
            token, sess = tok, s
            break

    if not sess:
        return False

    text = (update.message.text or "").strip()

    if text.lower() in ("/cancel", "cancel"):
        prompt_id = sess["awaiting"].get("prompt_id")
        ids = [mid for mid in [prompt_id, update.message.message_id] if mid]
        await delete_many(context.bot, chat_id, ids)
        sess["awaiting"] = None
        return True

    from yoink_dl.url.clip import parse_time
    try:
        secs = parse_time(text)
    except (ValueError, TypeError):
        await update.message.reply_html(
            "❌ Use <code>MM:SS</code>, <code>HH:MM:SS</code>, or seconds. "
            "Send /cancel to abort."
        )
        return True

    awaiting = sess["awaiting"]
    idx: int = awaiting["idx"]
    kind: str = awaiting["kind"]  # "s" or "e"
    segs: list[dict] = sess["segments"]

    if 0 <= idx < len(segs):
        segs[idx][kind] = secs

    prompt_id = awaiting.get("prompt_id")
    ids = [mid for mid in [prompt_id, update.message.message_id] if mid]
    await delete_many(context.bot, chat_id, ids)
    sess["awaiting"] = None

    # Refresh segment editor
    text_seg = _text_segments(sess["title"], sess["clip_quality"] or "best", segs)
    kb_seg = _kb_segments(token, segs)  # type: ignore[arg-type]
    await _edit(context, sess, text_seg, kb_seg)
    return True


# Callback handler

async def _cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query: CallbackQuery | None = update.callback_query
    if not query or not query.data:
        return
    await query.answer()

    # Strip prefix, split on ":" up to 3 parts: action, token, extra
    raw = query.data[len(_CB):]
    parts = raw.split(":", 2)
    action = parts[0]
    token  = parts[1] if len(parts) > 1 else ""
    extra  = parts[2] if len(parts) > 2 else ""

    logger.info("ask_menu cb: action=%s token=%s extra=%s sessions=%s",
                action, token, extra, list(_sessions(context).keys()))

    sess = _sessions(context).get(token)
    if sess is None:
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        await query.answer("Session expired  - send the URL again.", show_alert=True)
        return

    title   = sess["title"]
    formats = sess["formats"]
    segs    = sess["segments"]

    chat_id = sess["chat_id"]
    origin_id: int | None = sess.get("origin_id")

    def _fire_delete() -> None:
        """Schedule deletion of menu + origin message without blocking download."""
        ids = [mid for mid in [sess.get("message_id"), origin_id] if mid]
        if ids:
            asyncio.ensure_future(delete_many(context.bot, chat_id, ids))

    # cancel
    if action == "cancel":
        _sessions(context).pop(token, None)
        _fire_delete()
        return

    # back → action screen
    if action == "back":
        sess["awaiting"] = None
        await _edit(context, sess, _text_action(title, sess["duration"], formats), _kb_action(token, formats))
        return

    # download at quality
    if action == "dl":
        quality = extra.rstrip("p") if extra not in ("best",) else "best"
        _sessions(context).pop(token, None)
        _fire_delete()
        context.user_data["_ask_quality_override"] = quality
        await _trigger(update, context, sess["url"], clips=None, chat_id=chat_id)
        return

    # audio
    if action == "audio":
        _sessions(context).pop(token, None)
        _fire_delete()
        context.user_data["force_mode"] = "audio"
        await _trigger(update, context, sess["url"], clips=None, chat_id=chat_id)
        return

    # cut → quality picker
    if action == "cut":
        await _edit(context, sess, _text_cut_quality(title), _kb_cut_quality(token, formats))
        return

    # cut quality chosen → segment editor
    if action == "cutq":
        sess["clip_quality"] = extra
        sess["segments"] = [{"s": None, "e": None}]
        segs = sess["segments"]
        await _edit(context, sess, _text_segments(title, extra, segs), _kb_segments(token, segs))
        return

    # set start/end
    if action == "set":
        # extra = "<idx>:<s|e>"
        sub = extra.split(":")
        if len(sub) != 2 or not sub[0].isdigit():
            return
        idx, kind = int(sub[0]), sub[1]
        label = "start" if kind == "s" else "end"
        prompt = await context.bot.send_message(
            chat_id=sess["chat_id"],
            text=(
                f"Send <b>{label} time</b> for segment {idx + 1}:\n"
                f"<code>01:23</code>  or  <code>83</code> sec  •  /cancel to abort"
            ),
            parse_mode=ParseMode.HTML,
        )
        sess["awaiting"] = {"idx": idx, "kind": kind, "prompt_id": prompt.message_id}
        return

    # delete segment
    if action == "del":
        if not extra.isdigit():
            return
        idx = int(extra)
        if len(segs) > 1:
            segs.pop(idx)
        else:
            segs[0] = {"s": None, "e": None}
        await _edit(context, sess, _text_segments(title, sess["clip_quality"] or "best", segs), _kb_segments(token, segs))
        return

    # add segment
    if action == "add":
        segs.append({"s": None, "e": None})
        await _edit(context, sess, _text_segments(title, sess["clip_quality"] or "best", segs), _kb_segments(token, segs))
        return

    # go: run download
    if action == "go":
        valid = [
            ClipSpec(start_sec=sg["s"], end_sec=sg["e"])
            for sg in segs
            if sg.get("s") is not None and sg.get("e") is not None and sg["e"] > sg["s"]
        ]
        if not valid:
            await query.answer("Set valid start and end for at least one segment.", show_alert=True)
            return

        quality = (sess.get("clip_quality") or "best").rstrip("p")
        url = sess["url"]
        _sessions(context).pop(token, None)
        _fire_delete()
        context.user_data["_ask_quality_override"] = quality
        await _trigger(update, context, url, clips=valid, chat_id=chat_id)
        return


async def _trigger(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    url: str,
    clips: list[ClipSpec] | None,
    chat_id: int | None = None,
) -> None:
    from yoink_dl.url.pipeline import run_download as _run_download

    if clips and len(clips) == 1:
        clip: ClipSpec | None = clips[0]
    elif clips:
        clip = None
        context.user_data["_clips"] = clips
    else:
        clip = None

    await _run_download(update, context, url, clip, target_chat_id=chat_id)


def register(app: Application) -> None:
    app.add_handler(CallbackQueryHandler(_cb, pattern=rf"^{_CB}"))
