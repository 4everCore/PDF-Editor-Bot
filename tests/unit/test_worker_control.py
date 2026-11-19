import asyncio

import pytest

from app.workers import worker


@pytest.mark.asyncio
async def test_cancel_while_waiting_for_worker_slot_persists_cancelled_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    states: list[tuple[str, str, str]] = []

    async def record_state(job_id: str, status: str, code: str) -> None:
        states.append((job_id, status, code))

    monkeypatch.setattr(worker, "_set_job_state", record_state)
    semaphore = asyncio.Semaphore(0)

    async def wait_for_slot() -> None:
        async with worker._job_slot(semaphore, "job-1"):
            raise AssertionError("a zero-capacity semaphore must not be acquired")

    task = asyncio.create_task(wait_for_slot())
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert states == [("job-1", "cancelled", "cancelled")]
    assert semaphore._value == 0


@pytest.mark.asyncio
async def test_worker_slot_is_released_after_operation_error() -> None:
    semaphore = asyncio.Semaphore(1)
    with pytest.raises(RuntimeError, match="operation failed"):
        async with worker._job_slot(semaphore, "job-2"):
            assert semaphore._value == 0
            raise RuntimeError("operation failed")
    assert semaphore._value == 1
