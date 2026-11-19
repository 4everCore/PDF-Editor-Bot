"""Per-user Redis fixed-window limiter for Telegram messages and callbacks."""

from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from redis.asyncio import Redis

from app.core.config import get_settings

log = structlog.get_logger(__name__)


class RateLimitMiddleware(BaseMiddleware):
    def __init__(self) -> None:
        self.redis = Redis.from_url(get_settings().redis_url, decode_responses=True)
        self.limit = get_settings().rate_limit_per_minute

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user:
            try:
                key = f"rate:{user.id}"
                count = await self.redis.eval(
                    "local n=redis.call('INCR',KEYS[1]); "
                    "if n==1 then redis.call('EXPIRE',KEYS[1],ARGV[1]); end; "
                    "return n",
                    1,
                    key,
                    60,
                )
                if count > self.limit:
                    message = data.get("event_message")
                    callback = data.get("event_callback_query")
                    if message:
                        await message.answer(
                            "⏳ درخواست‌های زیادی ارسال شده؛ یک دقیقه دیگر تلاش کنید. "
                            "Please slow down and try again in a minute."
                        )
                    elif callback:
                        await callback.answer(
                            "Too many requests. Please wait a minute.", show_alert=True
                        )
                    return None
            except Exception:
                # Explicitly fail open to preserve bot availability during a Redis outage.
                log.warning("rate_limit_redis_unavailable")
        return await handler(event, data)

    async def close(self) -> None:
        await self.redis.aclose()
