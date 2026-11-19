import asyncio
import zipfile
from pathlib import Path

import pytest

from app.core.exceptions import AppError, ProcessingError
from app.services.isolation import run_isolated


@pytest.mark.asyncio
async def test_worker_subprocess_executes_and_returns_metadata(
    sample_pdf: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    output = tmp_path / "output.txt"
    meta = tmp_path / "output.meta"
    result = await run_isolated(sample_pdf, output, meta, "extract_text", {}, 30)
    assert result["page_count"] == 1
    assert "project Atlas" in output.read_text()
    assert not meta.exists()


@pytest.mark.asyncio
async def test_pdf_preflight_runs_in_child_and_only_returns_metadata(
    sample_pdf: Path, tmp_path: Path
) -> None:
    output = tmp_path / "probe.txt"
    result = await run_isolated(
        sample_pdf,
        output,
        tmp_path / "probe.meta",
        "inspect",
        {"max_bytes": 1_000_000, "max_pages": 5},
        30,
    )
    assert result["page_count"] == 1
    assert result["media_type"] == "application/pdf"
    assert "project Atlas" not in output.read_text()


@pytest.mark.asyncio
async def test_ooxml_archive_preflight_runs_in_child(tmp_path: Path) -> None:
    source = tmp_path / "arbitrary-name.zip"
    marker = "private spreadsheet contents"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("xl/workbook.xml", f"<workbook>{marker}</workbook>")
    output = tmp_path / "probe.txt"
    result = await run_isolated(
        source,
        output,
        tmp_path / "probe.meta",
        "inspect",
        {"max_bytes": 1_000_000, "max_pages": 5},
        30,
    )
    assert result["media_type"].endswith("spreadsheetml.sheet")
    assert marker not in output.read_text()


@pytest.mark.asyncio
async def test_worker_rejects_unknown_plugin(sample_pdf: Path, tmp_path: Path) -> None:
    with pytest.raises(AppError):
        await run_isolated(sample_pdf, tmp_path / "x.pdf", tmp_path / "x.meta", "import_os", {}, 30)


@pytest.mark.asyncio
async def test_worker_timeout_kills_processor_process_group(
    sample_pdf: Path, tmp_path: Path
) -> None:
    output = tmp_path / "timed-out.txt"
    sidecar = tmp_path / "timed-out.meta"
    with pytest.raises(ProcessingError, match="time limit"):
        await run_isolated(sample_pdf, output, sidecar, "extract_text", {}, 0.001)
    assert not output.exists()
    assert not sidecar.exists()
    scratch_paths = await asyncio.to_thread(lambda: list(tmp_path.glob(".scratch-*")))
    assert not scratch_paths
