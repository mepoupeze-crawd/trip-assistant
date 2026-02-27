"""Telegram bot process entrypoint.

Registers the briefing ConversationHandler and the /check delivery command,
then starts long-polling.  Designed to run as a standalone process (separate
from the FastAPI and Celery worker processes).

Usage:
    python -m src.bot.main
    # or from docker-compose: command: python -m src.bot.main
"""

from __future__ import annotations

import asyncio
import signal

import structlog
from telegram.ext import Application, CommandHandler

from src.bot.handlers.briefing import briefing_conversation_handler
from src.bot.handlers.delivery import check_handler
from src.lib.config import settings

log = structlog.get_logger(__name__)


async def main() -> None:
    """Build the Application, register handlers, and run long-polling."""

    log.info("bot_starting", api_base_url=settings.api_base_url)

    app = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .build()
    )

    # ── Register handlers ─────────────────────────────────────────────────────
    # Briefing conversation (covers /start and all steps through CONFIRM)
    app.add_handler(briefing_conversation_handler)

    # /check — delivery polling command (works outside the conversation)
    app.add_handler(CommandHandler("check", check_handler))

    # ── Start polling ─────────────────────────────────────────────────────────
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)

    log.info("bot_running", polling=True)

    # Block until SIGINT / SIGTERM
    stop_event = asyncio.Event()

    def _signal_handler() -> None:
        log.info("bot_shutdown_signal_received")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            # Windows does not support add_signal_handler for all signals
            pass

    await stop_event.wait()

    # ── Graceful shutdown ─────────────────────────────────────────────────────
    log.info("bot_stopping")
    await app.updater.stop()
    await app.stop()
    await app.shutdown()
    log.info("bot_stopped")


if __name__ == "__main__":
    asyncio.run(main())
