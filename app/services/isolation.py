
"""Bounded OS child-process launcher shared by upload preflight and job workers."""

import asyncio
import json
import os
import shutil
import signal
import subprocess  # nosec B404
import sys
import uuid
from pathlib import Path
from typing import Any, cast

from app.core.exceptions import AppError, ProcessingError

PROJECT_ROOT = Path(__file__).resolve().parents[2]


async def run_isolated(
    source: Path,
    destination: Path,
    metadata_path: Path,
    operation: str,
    options: dict[str, Any],
    deadline_seconds: float,
) -> dict[str, Any]:
    """Run a registered operation in a resource-limited process with private scratch space."""
    scratch_dir = destination.parent / f".scratch-{uuid.uuid4().hex}"
    scratch_dir.mkdir(mode=0o700)
    process: asyncio.subprocess.Process | None = None

    try:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "app.workers.run_operation",
            operation,
            str(source),
            str(destination),
            json.dumps(options, ensure_ascii=True, separators=(",", ":")),
            str(metadata_path),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            env={
                **os.environ,
                "HOME": str(scratch_dir),
                "TMPDIR": str(scratch_dir),
                "TEMP": str(scratch_dir),
                "TMP": str(scratch_dir),
                "PYTHONPATH": str(PROJECT_ROOT),
            },
            start_new_session=(os.name != "nt"),
            creationflags=(
                subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
            ),
        )

        try:
            await asyncio.wait_for(process.wait(), timeout=deadline_seconds)
        except TimeoutError as exc:
            await _kill_process_group(process)
            raise ProcessingError(
                "Processing exceeded its time limit.", code="timeout"
            ) from exc

        try:
            payload = json.loads(
                await asyncio.to_thread(metadata_path.read_text, encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError) as exc:
            raise ProcessingError(
                "The processing worker returned an invalid result.",
                code="worker_failed",
            ) from exc

        if not isinstance(payload, dict):
            raise ProcessingError(
                "The processing worker returned an invalid result.",
                code="worker_failed",
            )

        if not payload.get("ok"):
            raise AppError(
                str(payload.get("message", "Processing failed.")),
                code=str(payload.get("code", "processing_failed")),
            )

        if process.returncode != 0:
            raise ProcessingError(
                "The processing worker failed.", code="worker_failed"
            )

        metadata = payload.get("metadata")
        if not isinstance(metadata, dict):
            raise ProcessingError(
                "The processing worker returned invalid metadata.",
                code="worker_failed",
            )

        return cast(dict[str, Any], metadata)

    except asyncio.CancelledError:
        if process is not None:
            await _kill_process_group(process)
        raise

    finally:
        if process is not None and process.returncode is None:
            await _kill_process_group(process)

        try:
            await asyncio.to_thread(metadata_path.unlink, missing_ok=True)
        finally:
            await asyncio.to_thread(shutil.rmtree, scratch_dir)


async def _kill_process_group(process: asyncio.subprocess.Process) -> None:
    if process.returncode is None:
        if os.name == "nt":
            try:
                killer = await asyncio.create_subprocess_exec(
                    "taskkill",
                    "/PID",
                    str(process.pid),
                    "/T",
                    "/F",
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await killer.wait()
            except ProcessLookupError:
                pass
        else:
            killpg = getattr(os, "killpg", None)
            sigkill = getattr(signal, "SIGKILL", None)

            try:
                if killpg is not None and sigkill is not None:
                    killpg(process.pid, sigkill)
                else:
                    process.kill()
            except ProcessLookupError:
                pass

    await process.wait()