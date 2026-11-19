from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.types import TelegramObject

from app.bot.middlewares.rate_limit import RateLimitMiddleware


class FakeRedis:
    def __init__(self, result: int) -> None:
        self.result = result
        self.script: str | None = None
        self.key: str | None = None

    async def eval(self, script: str, numkeys: int, key: str, ttl: int) -> int:
        assert numkeys == 1 and ttl == 60
        self.script, self.key = script, key
        return self.result

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_rate_limit_uses_atomic_ttl_and_blocks_over_limit() -> None:
    middleware = RateLimitMiddleware()
    fake_redis = FakeRedis(result=999)
    middleware.redis = fake_redis  # type: ignore[assignment]
    middleware.limit = 5
    message = SimpleNamespace(answer=AsyncMock())
    handler = AsyncMock(return_value="should not run")
    result = await middleware(
        handler,
        TelegramObject(),
        {"event_from_user": SimpleNamespace(id=77), "event_message": message},
    )
    assert result is None
    handler.assert_not_awaited()
    message.answer.assert_awaited_once()
    assert fake_redis.key == "rate:77"
    assert "EXPIRE" in (fake_redis.script or "")
