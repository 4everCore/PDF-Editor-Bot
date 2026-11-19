"""Job enqueueing; Telegram handlers only validate/enqueue, never process documents."""

from typing import Any
from uuid import uuid4

from arq import create_pool
from arq.connections import RedisSettings

from app.core.config import get_settings


async def enqueue_processing(
    *,
    user_id: int,
    chat_id: int,
    source_key: str,
    operation: str,
    options: dict[str, Any] | None = None,
    job_id: str | None = None,
) -> str:
    settings = get_settings()
    pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    job_id = job_id or str(uuid4())
    try:
        job = await pool.enqueue_job(
            "process_document",
            job_id,
            user_id,
            chat_id,
            source_key,
            operation,
            options or {},
            _job_id=job_id,
        )
        if job is None:
            raise RuntimeError("Job ID collision; retry the request.")
        return job_id
    finally:
        await pool.aclose()
