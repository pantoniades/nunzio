"""Telegram bot interface for Nunzio workout assistant."""

import logging
import sys
from urllib.parse import urlparse

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from .checkin import run_checkins
from .config import config
from .core import MessageHandler as NunzioHandler
from .database.connection import db_manager
from .database.repository import workout_set_repo

logger = logging.getLogger(__name__)

# How often the check-in job wakes to look for users due a proactive message.
_CHECKIN_INTERVAL_SECONDS = 3600


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
            await update.message.chat.send_action("typing")
            response = await self._handler.process(text, update.effective_user.id)
        except Exception:
            logger.exception("Error processing message from %s", update.effective_user.id)
            response = "Couldn't process that — try again in a sec."

        await update.message.reply_text(response)

    async def _post_init(self, app: Application) -> None:
        await self._handler.initialize()
        if app.job_queue is not None:
            app.job_queue.run_repeating(
                self._checkin_job, interval=_CHECKIN_INTERVAL_SECONDS, first=60
            )
            logger.info("Proactive check-in job scheduled (hourly)")
        else:
            logger.warning(
                "JobQueue unavailable — install python-telegram-bot[job-queue] to "
                "enable proactive check-ins"
            )
        logger.info("Nunzio bot initialized (DB + LLM ready)")

    async def _checkin_recipients(self) -> list[int]:
        """Users eligible for proactive check-ins: the allowlist, or every logged
        user when no allowlist is configured (never the CLI's user_id=0)."""
        if self._allowed_users:
            return list(self._allowed_users)
        async with db_manager.get_session() as session:
            ids = await workout_set_repo.get_distinct_user_ids(session)
        return [uid for uid in ids if uid != 0]

    async def _checkin_job(self, context) -> None:
        try:
            recipients = await self._checkin_recipients()
            if not recipients:
                return
            sent = await run_checkins(context.bot, recipients)
            if sent:
                logger.info("Proactive check-ins sent: %d", sent)
        except Exception:
            logger.exception("Check-in job failed")

    async def _post_shutdown(self, app: Application) -> None:
        await self._handler.close()
        logger.info("Nunzio bot shut down")

    def run(self) -> None:
        if not config.telegram.token:
            logger.error("TELEGRAM__TOKEN not set in .env")
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

        llm_host = urlparse(config.llm.base_url).netloc
        logger.info("Using %s on %s", config.llm.model, llm_host)
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
