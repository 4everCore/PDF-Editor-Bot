"""Database helpers for user-owned jobs."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import ProcessingJob, User


async def create_job(
    session: AsyncSession,
    *,
    user_id: int,
    job_id: str,
    operation: str,
    source_file_id: str,
    options: dict[str, Any],
) -> None:
    if await session.get(User, user_id) is None:
        session.add(User(id=user_id))
        await session.flush()
    session.add(
        ProcessingJob(
            id=job_id,
            user_id=user_id,
            source_file_id=source_file_id,
            operation=operation,
            status="queued",
            options=options,
        )
    )
    await session.commit()


async def set_job_status(
    session: AsyncSession, job_id: str, status: str, progress: int = 0
) -> None:
    job = await session.get(ProcessingJob, job_id)
    if job:
        job.status = status
        job.progress = progress
        await session.commit()
