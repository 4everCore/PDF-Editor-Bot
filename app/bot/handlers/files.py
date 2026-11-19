"""Bounded document ingestion and owner-checked operation callbacks."""

import asyncio
import os
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import structlog
from aiogram import Bot, F, Router
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select

from app.bot.handlers.menu import language_for
from app.bot.keyboards.main import file_actions
from app.core.config import get_settings
from app.core.database import SessionFactory
from app.core.exceptions import AppError, ValidationError
from app.domain.models import ProcessingJob, StoredFile, User
from app.processors.pdf.registry import get_operation
from app.services.isolation import run_isolated
from app.services.jobs import enqueue_processing
from app.storage.files import LocalStorage, inspect_file, safe_filename

router = Router(name="files")
log = structlog.get_logger(__name__)
_SUFFIX_BY_MIME = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/tiff": ".tiff",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
}
_OFFICE_PREFIX = "application/vnd.openxmlformats-officedocument."
_PUBLIC_OPERATIONS = {
    "compress",
    "extract_text",
    "render_png",
    "ocr",
    "watermark",
    "rotate",
    "image_to_pdf",
    "office_to_pdf",
}


def _storage() -> LocalStorage:
    return LocalStorage(get_settings().storage_root)


def _private_temp_directory(base_path: Path) -> Path:
    """Create a private child directory without changing permissions on shared /tmp."""
    base = base_path.resolve()
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    private = base / "uploads"
    if private.is_symlink():
        raise ValidationError(
            "Temporary storage path must not be a symlink.", code="unsafe_temp_path"
        )
    private.mkdir(mode=0o700, exist_ok=True)
    resolved = private.resolve()
    if not resolved.is_relative_to(base):
        raise ValidationError("Temporary storage path escaped its root.", code="unsafe_temp_path")
    os.chmod(resolved, 0o700)
    return resolved


@router.message(F.document)
@router.message(F.photo)
async def receive_file(message: Message, bot: Bot) -> None:
    user = message.from_user
    if user is None:
        return
    if message.chat.type != "private":
        await message.answer(
            "برای حفظ حریم خصوصی، فایل را در گفت‌وگوی خصوصی ربات ارسال کنید.\n"
            "For privacy, upload documents in a private chat with the bot."
        )
        return
    settings = get_settings()
    if message.document:
        telegram_file_id = message.document.file_id
        original_name = safe_filename(message.document.file_name or "upload.pdf")
        advertised_size = message.document.file_size
    elif message.photo:
        telegram_file_id = message.photo[-1].file_id
        original_name, advertised_size = "telegram-photo.jpg", message.photo[-1].file_size
    else:
        return
    if advertised_size and advertised_size > settings.max_upload_bytes:
        size_mb = settings.max_upload_bytes // (1024 * 1024)
        await message.answer(f"File is larger than the {size_mb} MB limit.")
        return

    temp_path: Path | None = None
    stored_path: Path | None = None
    record_saved = False
    try:
        private_temp = _private_temp_directory(settings.temp_root)
        descriptor, name = tempfile.mkstemp(prefix="upload-", dir=private_temp)
        os.close(descriptor)
        temp_path = Path(name)
        telegram_file = await bot.get_file(telegram_file_id)
        if not telegram_file.file_path:
            raise ValidationError("Telegram file path is missing.", code="download_failed")
        await bot.download_file(telegram_file.file_path, destination=temp_path)
        info = await asyncio.to_thread(
            inspect_file,
            temp_path,
            settings.max_upload_bytes,
            settings.max_pdf_pages,
            deep_pdf_check=False,
            deep_office_check=False,
        )
        if info.get("deep_inspection_pending"):
            probe = private_temp / f"inspect-{uuid.uuid4().hex}.txt"
            sidecar = probe.with_name(probe.name + ".meta")
            try:
                preflight = await run_isolated(
                    temp_path,
                    probe,
                    sidecar,
                    "inspect",
                    {
                        "max_bytes": settings.max_upload_bytes,
                        "max_pages": settings.max_pdf_pages,
                    },
                    settings.job_timeout_seconds,
                )
                info.update(preflight)
                info.pop("deep_inspection_pending", None)
            finally:
                await asyncio.to_thread(probe.unlink, missing_ok=True)
                await asyncio.to_thread(sidecar.unlink, missing_ok=True)
        media_type = str(info["media_type"])
        if media_type not in _SUFFIX_BY_MIME:
            raise ValidationError("Unsupported file type.", code="unsupported_type")
        suffix = _SUFFIX_BY_MIME[media_type]
        storage = _storage()
        key, stored_path = storage.allocate(user.id, suffix)
        os.replace(temp_path, stored_path)
        temp_path = None
        async with SessionFactory() as session:
            user_row = await session.get(User, user.id)
            if user_row is None:
                session.add(User(id=user.id, language=settings.default_language))
                await session.flush()
            file_row = StoredFile(
                user_id=user.id,
                storage_key=key,
                original_name=original_name,
                media_type=media_type,
                size_bytes=info["size_bytes"],
                page_count=info.get("page_count"),
                expires_at=datetime.now(UTC) + timedelta(hours=settings.file_ttl_hours),
            )
            session.add(file_row)
            await session.commit()
            file_id = file_row.id
            record_saved = True

        language = await language_for(user.id)
        page_count = info.get("page_count")
        pages = f" · {page_count} pages" if page_count else ""
        size_kb = int(info["size_bytes"]) // 1024
        await message.answer(
            f"✅ فایل بررسی شد · {size_kb} KB{pages}\nFile inspected. Choose an action:",
            reply_markup=file_actions(
                file_id,
                language,
                media_type == "application/pdf",
                media_type.startswith(_OFFICE_PREFIX),
            ),
        )
    except AppError as exc:
        await message.answer(f"⚠️ {exc.message}")
    except Exception as exc:
        log.exception("upload_failed", user_id=user.id, error_type=type(exc).__name__)
        await message.answer("⚠️ Upload could not be completed. Please try again.")
    finally:
        if temp_path:
            await asyncio.to_thread(temp_path.unlink, missing_ok=True)
        if stored_path and not record_saved:
            await asyncio.to_thread(stored_path.unlink, missing_ok=True)


@router.callback_query(F.data.startswith("op:"))
async def run_operation(query: CallbackQuery) -> None:
    parts = (query.data or "").split(":")
    if len(parts) != 3:
        await query.answer("Invalid action", show_alert=True)
        return
    _, file_id, operation_name = parts
    if operation_name not in _PUBLIC_OPERATIONS:
        await query.answer("Unsupported operation", show_alert=True)
        return
    try:
        get_operation(operation_name)
    except ValueError:
        await query.answer("Unsupported operation", show_alert=True)
        return

    async with SessionFactory() as session:
        result = await session.execute(
            select(StoredFile).where(
                StoredFile.id == file_id,
                StoredFile.user_id == query.from_user.id,
                StoredFile.expires_at > datetime.now(UTC),
            )
        )
        source_file = result.scalar_one_or_none()
        if source_file is None:
            await query.answer(
                "فایل پیدا نشد یا منقضی شده است / File expired or unavailable",
                show_alert=True,
            )
            return
        media_type = source_file.media_type
        is_pdf = media_type == "application/pdf"
        is_image = media_type.startswith("image/")
        is_office = media_type.startswith(_OFFICE_PREFIX)
        if (
            (operation_name == "image_to_pdf" and not is_image)
            or (operation_name == "office_to_pdf" and not is_office)
            or (operation_name not in {"image_to_pdf", "office_to_pdf"} and not is_pdf)
        ):
            await query.answer(
                "این عملیات برای نوع فایل مناسب نیست / Incompatible file type",
                show_alert=True,
            )
            return
        options: dict[str, Any] = {}
        if operation_name == "compress":
            options = {"level": "balanced"}
        elif operation_name == "render_png":
            options = {"page": 1}
        elif operation_name == "watermark":
            options = {"text": "SAMPLE"}
        elif operation_name == "rotate":
            options = {"degrees": 90}
        job_id = str(uuid.uuid4())
        session.add(
            ProcessingJob(
                id=job_id,
                user_id=query.from_user.id,
                source_file_id=source_file.id,
                operation=operation_name,
                status="queued",
                options=options,
            )
        )
        await session.commit()
        source_key = source_file.storage_key

    await query.answer("در صف پردازش / Added to processing queue")
    response_message = query.message if isinstance(query.message, Message) else None
    chat_id = response_message.chat.id if response_message else query.from_user.id
    try:
        await enqueue_processing(
            user_id=query.from_user.id,
            chat_id=chat_id,
            source_key=source_key,
            operation=operation_name,
            options=options,
            job_id=job_id,
        )
        if query.message:
            await query.message.answer(
                "⏳ در حال پردازش… نتیجه در همین گفت‌وگو ارسال می‌شود.\n"
                "Processing in the background. The result will be sent here."
            )
    except Exception as exc:
        log.exception(
            "job_enqueue_failed", user_id=query.from_user.id, error_type=type(exc).__name__
        )
        async with SessionFactory() as session:
            job = await session.get(ProcessingJob, job_id)
            if job:
                job.status, job.error_code = "failed", "queue_unavailable"
                await session.commit()
        if query.message:
            await query.message.answer(
                "صف پردازش در دسترس نیست. کمی بعد دوباره تلاش کنید.\n"
                "Processing queue is unavailable; please retry shortly."
            )
