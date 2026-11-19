"""Arq worker. Every document transformation runs in a time/resource-limited child process."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from aiogram import Bot
from aiogram.types import FSInputFile
from arq import cron
from arq.connections import RedisSettings
from sqlalchemy import exists, select
from sqlalchemy.sql import Select

from app.core.config import get_settings
from app.core.database import SessionFactory
from app.core.exceptions import AppError
from app.domain.models import JobResult, ProcessingJob, StoredFile
from app.processors.pdf.registry import get_operation
from app.services.isolation import run_isolated as _run_isolated
from app.storage.files import LocalStorage

log = structlog.get_logger(__name__)
Context = dict[str, Any]


async def startup(ctx: Context) -> None:
    settings = get_settings()
    ctx["storage"] = LocalStorage(settings.storage_root)
    token = settings.bot_token.get_secret_value()
    if not token:
        raise RuntimeError("BOT_TOKEN is required to start a Telegram worker")
    ctx["bot"] = Bot(token)
    ctx["semaphore"] = asyncio.Semaphore(settings.max_concurrent_jobs)


async def shutdown(ctx: Context) -> None:
    await ctx["bot"].session.close()


@asynccontextmanager
async def _job_slot(semaphore: asyncio.Semaphore, job_id: str) -> AsyncIterator[None]:
    """Acquire capacity and persist cancellation even if abort arrives while queued locally."""
    try:
        await semaphore.acquire()
    except asyncio.CancelledError:
        await _set_job_state(job_id, "cancelled", "cancelled")
        log.info("job_cancelled_before_slot", job_id=job_id)
        raise
    try:
        yield
    finally:
        semaphore.release()


async def process_document(
    ctx: Context,
    job_id: str,
    user_id: int,
    chat_id: int,
    source_key: str,
    operation_name: str,
    options: dict[str, Any],
) -> dict[str, str]:
    settings = get_settings()
    storage: LocalStorage = ctx["storage"]
    bot: Bot = ctx["bot"]
    source = storage.path_for(user_id, source_key)
    if not await asyncio.to_thread(source.is_file):
        await _mark_failed(job_id, "missing_file")
        await bot.send_message(
            chat_id, "فایل اصلی پیدا نشد. /start\nOriginal file is no longer available."
        )
        return {"status": "missing"}
    try:
        plugin = get_operation(operation_name)
    except ValueError:
        await _mark_failed(job_id, "unknown_operation")
        return {"status": "failed", "code": "unknown_operation"}

    async with _job_slot(ctx["semaphore"], job_id):
        output_key, output = storage.allocate(user_id, plugin.output_suffix)
        metadata_path = output.with_name(output.name + ".meta")
        try:
            async with SessionFactory() as session:
                job = await session.get(ProcessingJob, job_id)
                if job:
                    job.status = "running"
                    await session.commit()
            metadata = await _run_isolated(
                source, output, metadata_path, operation_name, options, settings.job_timeout_seconds
            )
            output_size = await asyncio.to_thread(lambda: output.stat().st_size)
            if output_size > 49 * 1024 * 1024:
                raise AppError(
                    "The result is too large to send through Telegram (49 MB limit).",
                    code="result_too_large",
                )
            report_lines: list[str] = []
            if "input_bytes" in metadata and "output_bytes" in metadata:
                change = float(metadata.get("reduction_percent", 0))
                direction = "smaller" if change >= 0 else "larger"
                report_lines.append(
                    f"Size: {_format_size(int(metadata['input_bytes']))} → "
                    f"{_format_size(int(metadata['output_bytes']))} "
                    f"({abs(change):.1f}% {direction})"
                )
            report_lines.extend(
                f"{key}: {value}"
                for key, value in metadata.items()
                if key in {"page_count", "level", "quality_note", "overlay", "note", "languages"}
            )
            report = "\n".join(report_lines)
            caption = f"✅ تمام شد | Done — {operation_name}\n{report}"[:1024]
            await bot.send_document(
                chat_id,
                FSInputFile(output, filename=f"result{plugin.output_suffix}"),
                caption=caption,
            )
            async with SessionFactory() as session:
                job = await session.get(ProcessingJob, job_id)
                if job:
                    job.status, job.progress = "completed", 100
                    session.add(
                        JobResult(
                            job_id=job_id,
                            storage_key=output_key,
                            filename=f"result{plugin.output_suffix}",
                            size_bytes=output_size,
                            metadata_json=metadata,
                        )
                    )
                    session.add(
                        StoredFile(
                            user_id=user_id,
                            storage_key=output_key,
                            original_name=f"result{plugin.output_suffix}",
                            media_type=_mime_for_suffix(plugin.output_suffix),
                            size_bytes=output_size,
                            page_count=metadata.get("page_count"),
                            expires_at=datetime.now(UTC) + timedelta(hours=settings.file_ttl_hours),
                        )
                    )
                await session.commit()
            log.info("job_completed", job_id=job_id, user_id=user_id, operation=operation_name)
            return {"status": "completed"}
        except asyncio.CancelledError:
            await asyncio.to_thread(output.unlink, missing_ok=True)
            await _set_job_state(job_id, "cancelled", "cancelled")
            log.info("job_cancelled", job_id=job_id, user_id=user_id)
            raise
        except Exception as exc:
            await asyncio.to_thread(output.unlink, missing_ok=True)
            code = exc.code if isinstance(exc, AppError) else "processing_failed"
            message = (
                exc.message
                if isinstance(exc, AppError)
                else "This document could not be processed. Please try another file."
            )
            await _mark_failed(job_id, code)
            log.warning("job_failed", job_id=job_id, operation=operation_name, code=code)
            try:
                await bot.send_message(
                    chat_id, f"⚠️ عملیات انجام نشد: {message}\nOperation failed: {message}"
                )
            except Exception:
                log.warning("failure_notice_not_delivered", job_id=job_id)
            return {"status": "failed", "code": code}
        finally:
            try:
                await asyncio.to_thread(plugin.cleanup_workspace, output)
            finally:
                await asyncio.to_thread(metadata_path.unlink, missing_ok=True)


def _format_size(size_bytes: int) -> str:
    value = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def _mime_for_suffix(suffix: str) -> str:
    return {
        ".pdf": "application/pdf",
        ".txt": "text/plain",
        ".png": "image/png",
        ".jpg": "image/jpeg",
    }.get(suffix, "application/octet-stream")


async def _mark_failed(job_id: str, code: str) -> None:
    await _set_job_state(job_id, "failed", code)


async def _set_job_state(job_id: str, status: str, code: str) -> None:
    async with SessionFactory() as session:
        job = await session.get(ProcessingJob, job_id)
        if job:
            job.status, job.error_code = status, code
            await session.commit()


def expired_files_statement(now: datetime) -> Select[StoredFile]:
    """Select expired files only when no job can still be using the source."""
    active_job = exists().where(
        ProcessingJob.source_file_id == StoredFile.id,
        ProcessingJob.status.in_(("queued", "running", "cancelling")),
    )
    return select(StoredFile).where(StoredFile.expires_at < now, ~active_job)


async def expire_files(ctx: Context) -> int:
    """Delete expired storage objects when no queued or running job references them."""
    now = datetime.now(UTC)
    removed = 0
    async with SessionFactory() as session:
        result = await session.execute(expired_files_statement(now))
        rows = list(result.scalars())
        for row in rows:
            path = ctx["storage"].path_for(row.user_id, row.storage_key)
            await asyncio.to_thread(path.unlink, missing_ok=True)
            await session.delete(row)
            removed += 1
        await session.commit()
    return removed


class WorkerSettings:
    functions = [process_document]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 4
    job_timeout = 360
    keep_result = 3600
    cron_jobs: list[Any] = [cron(expire_files, minute={0})]
