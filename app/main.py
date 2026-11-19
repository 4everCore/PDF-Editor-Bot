"""Telegram bot process entry point."""

import asyncio
from pathlib import Path

import structlog
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, ErrorEvent
from sqlalchemy import text

from app.bot.handlers.files import router as files_router
from app.bot.handlers.menu import router as menu_router
from app.bot.middlewares.rate_limit import RateLimitMiddleware
from app.core.config import get_settings
from app.core.database import close_database, engine
from app.core.logging import configure_logging
from app.storage.files import cleanup_temporary_files

log = structlog.get_logger(__name__)


async def report_update_error(event: ErrorEvent) -> bool:
    """Log a redacted error type and notify the user without echoing document data."""
    log.error(
        "telegram_update_failed",
        update_id=event.update.update_id,
        error_type=type(event.exception).__name__,
    )
    try:
        if event.update.message:
            await event.update.message.answer(
                "⚠️ درخواست کامل نشد. دوباره تلاش کنید یا /help را ببینید.\n"
                "The request failed. Please retry or use /help."
            )
        elif event.update.callback_query:
            await event.update.callback_query.answer(
                "The action failed. Please retry.", show_alert=True
            )
    except Exception:
        log.warning("telegram_error_notice_not_delivered", update_id=event.update.update_id)
    return True


async def cleanup_temp_loop(temp_root: Path, age_seconds: int) -> None:
    while True:
        try:
            removed = await asyncio.to_thread(cleanup_temporary_files, temp_root, age_seconds)
            if removed:
                log.info("temporary_files_expired", count=removed)
        except OSError as exc:
            log.warning("temporary_file_cleanup_failed", error_type=type(exc).__name__)
        await asyncio.sleep(3600)


async def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    token = settings.bot_token.get_secret_value()
    if not token:
        raise RuntimeError(
            "BOT_TOKEN is empty. Copy .env.example to .env and set a Telegram bot token."
        )
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    bot = Bot(token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dispatcher = Dispatcher()
    dispatcher.errors.register(report_update_error)
    rate_limiter = RateLimitMiddleware()
    dispatcher.message.middleware(rate_limiter)
    dispatcher.callback_query.middleware(rate_limiter)
    dispatcher.include_router(menu_router)
    dispatcher.include_router(files_router)
    cleanup_task = asyncio.create_task(
        cleanup_temp_loop(settings.temp_root, max(3600, settings.job_timeout_seconds * 2)),
        name="temporary-file-cleanup",
    )
    try:
        await bot.set_my_commands(
            [
                BotCommand(command="start", description="شروع / Start"),
                BotCommand(command="help", description="راهنما / Help"),
                BotCommand(command="menu", description="منوی اصلی / Main menu"),
                BotCommand(command="settings", description="تنظیمات / Settings"),
                BotCommand(command="cancel", description="لغو / Cancel"),
                BotCommand(command="history", description="تاریخچه / History"),
                BotCommand(command="language", description="زبان / Language"),
                BotCommand(command="privacy", description="حریم خصوصی / Privacy"),
                BotCommand(command="about", description="درباره / About"),
            ]
        )
        log.info("bot_started")
        await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
    finally:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
        await rate_limiter.close()
        await bot.session.close()
        await close_database()
        log.info("bot_stopped")


if __name__ == "__main__":
    asyncio.run(run())
