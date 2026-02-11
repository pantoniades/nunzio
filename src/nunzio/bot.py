"""Telegram bot interface for Nunzio workout assistant."""

import asyncio
import logging
import sys

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from .config import config
from .core import MessageHandler as NunzioHandler

logger = logging.getLogger(__name__)


class NunzioBot:
    """Telegram bot that routes messages through the shared message handler."""

    def __init__(self) -> None:
        self._handler = NunzioHandler(verbose=False)
        self._allowed_users: set[int] = set()
        if config.telegram.allowed_user_ids:
            self._allowed_users = set(config.telegram.allowed_user_ids)

    def _is_allowed(self, user_id: int | None) -> bool:
        if not self._allowed_users:
            return True  # no restriction configured
        return user_id in self._allowed_users

    async def _on_start(self, update: Update, _) -> None:
        if update.effective_user and not self._is_allowed(update.effective_user.id):
            return
        await update.message.reply_text(
            "Nunzio here. Tell me what you did or ask me anything about training."
        )

    async def _on_message(self, update: Update, _) -> None:
        if not update.message or not update.message.text:
            return
        if update.effective_user and not self._is_allowed(update.effective_user.id):
            return

        text = update.message.text.strip()
        if not text:
            return

        try:
            response = await self._handler.process(text)
        except Exception:
            logger.exception("Error processing message from %s", update.effective_user.id)
            response = "Couldn't process that — try again in a sec."

        await update.message.reply_text(response)

    async def _post_init(self, app: Application) -> None:
        await self._handler.initialize()
        logger.info("Nunzio bot initialized (DB + LLM ready)")

    async def _post_shutdown(self, app: Application) -> None:
        await self._handler.close()
        logger.info("Nunzio bot shut down")

    def run(self) -> None:
        if not config.telegram.token:
            print("TELEGRAM__TOKEN not set in .env")
            sys.exit(1)

        app = (
            Application.builder()
            .token(config.telegram.token)
            .post_init(self._post_init)
            .post_shutdown(self._post_shutdown)
            .build()
        )

        app.add_handler(CommandHandler("start", self._on_start))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._on_message))

        logger.info("Starting Nunzio bot (polling)...")
        app.run_polling()


def main() -> None:
    logging.basicConfig(
        level=config.logging.level,
        format=config.logging.format,
    )
    bot = NunzioBot()
    bot.run()


if __name__ == "__main__":
    main()
