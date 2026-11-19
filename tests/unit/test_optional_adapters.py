import asyncio
import threading
from pathlib import Path
from types import SimpleNamespace

import pymupdf as fitz
import pytest

from app.core.exceptions import ProcessingError, ValidationError
from app.processors.pdf.external import OCRPDF, LibreOfficeToPDF


def test_ocr_reports_missing_system_dependency(
    sample_pdf: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.processors.pdf.external.shutil.which", lambda _: None)
    with pytest.raises(ProcessingError, match="OCR is not installed"):
        OCRPDF().validate(sample_pdf, {"languages": "eng"})


def test_ocr_subprocess_parallelism_is_bounded(
    sample_pdf: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "searchable.pdf"
    captured: list[str] = []

    def fake_run(args, **kwargs):
        captured.extend(args)
        destination.write_bytes(sample_pdf.read_bytes())
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("app.processors.pdf.external.shutil.which", lambda _: "/usr/bin/ocrmypdf")
    monkeypatch.setattr("app.processors.pdf.external.subprocess.run", fake_run)
    metadata = OCRPDF().execute(sample_pdf, destination, {"languages": "eng"})
    assert captured[captured.index("--jobs") + 1] == "1"
    assert metadata["page_count"] == 1


def test_office_converter_reports_missing_system_dependency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    docx = tmp_path / "source.docx"
    docx.write_bytes(b"not actually opened by this capability check")
    monkeypatch.setattr("app.processors.pdf.external.shutil.which", lambda _: None)
    with pytest.raises(ProcessingError, match="LibreOffice is not installed"):
        LibreOfficeToPDF().validate(docx, {})


def test_ocr_language_option_rejects_command_metacharacters(sample_pdf: Path) -> None:
    with pytest.raises(ValidationError):
        OCRPDF().validate(sample_pdf, {"languages": "eng; touch /tmp/pwned"})


def test_office_cleanup_removes_workdirs_left_by_aborted_child(tmp_path: Path) -> None:
    destination = tmp_path / "result-uuid.pdf"
    converter = LibreOfficeToPDF()
    leftovers = [
        tmp_path / f"{prefix}{destination.stem}"
        for prefix in ("lo-profile-", "lo-home-", "lo-output-")
    ]
    for directory in leftovers:
        directory.mkdir()
        (directory / "partial.tmp").write_text("partial")
    converter.cleanup_workspace(destination)
    assert all(not directory.exists() for directory in leftovers)


@pytest.mark.asyncio
async def test_concurrent_office_conversions_use_separate_output_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "shared-source.docx"
    source.write_bytes(b"not parsed by this mocked converter")
    output_dirs: list[Path] = []
    both_conversions_started = threading.Barrier(2)

    def fake_run(args, **kwargs):
        output_dir = Path(args[args.index("--outdir") + 1])
        output_dirs.append(output_dir)
        both_conversions_started.wait(timeout=5)
        generated = output_dir / f"{source.stem}.pdf"
        doc = fitz.open()
        doc.new_page()
        doc.save(generated)
        doc.close()
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(
        "app.processors.pdf.external.shutil.which", lambda _: "/usr/bin/libreoffice"
    )
    monkeypatch.setattr("app.processors.pdf.external.subprocess.run", fake_run)
    converter = LibreOfficeToPDF()
    first, second = tmp_path / "result-one.pdf", tmp_path / "result-two.pdf"
    await asyncio.gather(
        asyncio.to_thread(converter.execute, source, first, {}),
        asyncio.to_thread(converter.execute, source, second, {}),
    )

    assert output_dirs[0] != output_dirs[1]
    assert not output_dirs[0].exists() and not output_dirs[1].exists()
    for path in (first, second):
        with fitz.open(path) as document:
            assert document.page_count == 1
