from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.bot.handlers import files
from app.core.config import Settings
from app.domain.models import Base, ProcessingJob, StoredFile, User


async def _test_session_factory(tmp_path: Path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'bot-tests.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def _message(user_id: int, *, name: str = "report.pdf", size: int = 100):
    return SimpleNamespace(
        from_user=SimpleNamespace(id=user_id),
        chat=SimpleNamespace(type="private", id=user_id),
        document=SimpleNamespace(file_id="telegram-file", file_name=name, file_size=size),
        photo=None,
        answer=AsyncMock(),
    )


@pytest.mark.asyncio
async def test_upload_handler_preflights_stores_and_offers_pdf_actions(
    sample_pdf: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, session_factory = await _test_session_factory(tmp_path)
    settings = Settings(
        temp_root=tmp_path / "scratch",
        storage_root=tmp_path / "stored",
        max_upload_bytes=1_000_000,
        max_pdf_pages=10,
        job_timeout_seconds=30,
    )
    monkeypatch.setattr(files, "SessionFactory", session_factory)
    monkeypatch.setattr(files, "get_settings", lambda: settings)
    monkeypatch.setattr(files, "language_for", AsyncMock(return_value="en"))
    bot = SimpleNamespace(
        get_file=AsyncMock(return_value=SimpleNamespace(file_path="documents/report.pdf")),
        download_file=AsyncMock(
            side_effect=lambda _file_path, destination: Path(destination).write_bytes(
                sample_pdf.read_bytes()
            )
        ),
    )
    message = _message(501)
    try:
        await files.receive_file(message, bot)
        message.answer.assert_awaited_once()
        async with session_factory() as session:
            stored = (await session.execute(select(StoredFile))).scalar_one()
            owner = await session.get(User, 501)
            assert owner is not None
            assert stored.media_type == "application/pdf"
            assert stored.page_count == 1
            stored_path = settings.storage_root / "501" / stored.storage_key
            assert stored_path.is_file()
        markup = message.answer.await_args.kwargs["reply_markup"]
        callbacks = {button.callback_data for row in markup.inline_keyboard for button in row}
        assert f"op:{stored.id}:compress" in callbacks
        assert not list((settings.temp_root / "uploads").glob("upload-*"))
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_upload_handler_rejects_non_pdf_disguised_as_pdf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, session_factory = await _test_session_factory(tmp_path)
    settings = Settings(
        temp_root=tmp_path / "scratch",
        storage_root=tmp_path / "stored",
        max_upload_bytes=1_000_000,
        max_pdf_pages=10,
        job_timeout_seconds=30,
    )
    monkeypatch.setattr(files, "SessionFactory", session_factory)
    monkeypatch.setattr(files, "get_settings", lambda: settings)
    bot = SimpleNamespace(
        get_file=AsyncMock(return_value=SimpleNamespace(file_path="documents/report.pdf")),
        download_file=AsyncMock(
            side_effect=lambda _file_path, destination: Path(destination).write_bytes(
                b"not a real PDF document"
            )
        ),
    )
    message = _message(502)
    try:
        await files.receive_file(message, bot)
        message.answer.assert_awaited_once()
        assert "Unsupported file type" in message.answer.await_args.args[0]
        async with session_factory() as session:
            assert not list((await session.execute(select(StoredFile))).scalars())
        assert not list((settings.temp_root / "uploads").glob("upload-*"))
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_operation_callback_enforces_file_owner_and_enqueues_only_owner_job(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine, session_factory = await _test_session_factory(tmp_path)
    monkeypatch.setattr(files, "SessionFactory", session_factory)
    enqueue = AsyncMock(return_value="job-id")
    monkeypatch.setattr(files, "enqueue_processing", enqueue)
    now = datetime.now(UTC)
    async with session_factory() as session:
        session.add(User(id=600, language="en"))
        await session.flush()
        stored = StoredFile(
            user_id=600,
            storage_key="owned.pdf",
            original_name="owned.pdf",
            media_type="application/pdf",
            size_bytes=100,
            expires_at=now + timedelta(hours=1),
        )
        session.add(stored)
        await session.commit()
        file_id = stored.id

    try:
        unauthorized = SimpleNamespace(
            data=f"op:{file_id}:compress",
            from_user=SimpleNamespace(id=601),
            message=SimpleNamespace(chat=SimpleNamespace(id=601), answer=AsyncMock()),
            answer=AsyncMock(),
        )
        await files.run_operation(unauthorized)
        unauthorized.answer.assert_awaited_once()
        assert unauthorized.answer.await_args.kwargs["show_alert"] is True
        enqueue.assert_not_awaited()

        authorized = SimpleNamespace(
            data=f"op:{file_id}:compress",
            from_user=SimpleNamespace(id=600),
            message=SimpleNamespace(chat=SimpleNamespace(id=600), answer=AsyncMock()),
            answer=AsyncMock(),
        )
        await files.run_operation(authorized)
        enqueue.assert_awaited_once()
        async with session_factory() as session:
            job = (await session.execute(select(ProcessingJob))).scalar_one()
            assert job.user_id == 600
            assert job.operation == "compress"
            assert job.status == "queued"
    finally:
        await engine.dispose()
