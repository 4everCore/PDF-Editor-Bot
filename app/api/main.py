"""Small optional FastAPI health service; no document content is exposed."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from redis.asyncio import Redis
from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import engine

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.redis = Redis.from_url(settings.redis_url)
    yield
    await app.state.redis.aclose()
    await engine.dispose()


app = FastAPI(
    title="PDF Assistant internal API",
    version="0.1.0",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)


@app.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
async def ready() -> dict[str, str]:
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        await app.state.redis.ping()
    except Exception as exc:
        raise HTTPException(status_code=503, detail="A required service is unavailable") from exc
    return {"status": "ready"}
