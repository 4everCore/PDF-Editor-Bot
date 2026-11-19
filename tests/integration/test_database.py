from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.domain.models import Base, ProcessingJob, StoredFile, User
from app.workers.worker import expired_files_statement


@pytest.mark.asyncio
async def test_schema_create_and_user_job_relationship() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        Session = async_sessionmaker(engine, expire_on_commit=False)
        async with Session() as session:
            user = User(id=123456, language="fa")
            session.add(user)
            await session.flush()
            job = ProcessingJob(user_id=user.id, operation="compress", status="queued", options={})
            session.add(job)
            await session.commit()
            assert job.id
            assert await session.get(User, 123456) is not None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_expiration_does_not_remove_source_used_by_active_job() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        Session = async_sessionmaker(engine, expire_on_commit=False)
        now = datetime.now(UTC)
        async with Session() as session:
            session.add(User(id=789, language="en"))
            await session.flush()
            active_file = StoredFile(
                user_id=789,
                storage_key="active.pdf",
                original_name="active.pdf",
                media_type="application/pdf",
                size_bytes=10,
                expires_at=now - timedelta(minutes=1),
            )
            idle_file = StoredFile(
                user_id=789,
                storage_key="idle.pdf",
                original_name="idle.pdf",
                media_type="application/pdf",
                size_bytes=10,
                expires_at=now - timedelta(minutes=1),
            )
            session.add_all([active_file, idle_file])
            await session.flush()
            session.add(
                ProcessingJob(
                    user_id=789,
                    source_file_id=active_file.id,
                    operation="compress",
                    status="running",
                    options={},
                )
            )
            await session.commit()
            result = await session.execute(expired_files_statement(now))
            expired_keys = {file.storage_key for file in result.scalars()}
            assert expired_keys == {"idle.pdf"}
    finally:
        await engine.dispose()
