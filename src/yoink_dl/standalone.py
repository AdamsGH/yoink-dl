"""Standalone entry: runs yoink-core + dl plugin as a single bot."""
from __future__ import annotations

import logging

from telegram import Update

from yoink.core.config import CoreSettings
from yoink.app import build_app
from yoink_dl.plugin import DownloaderPlugin

logging.basicConfig(
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    level=logging.INFO,
)


def main() -> None:
    config = CoreSettings()
    app = build_app(config=config, plugins=[DownloaderPlugin()])
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
        bootstrap_retries=-1,
        poll_interval=0.5,
        timeout=10,
    )
