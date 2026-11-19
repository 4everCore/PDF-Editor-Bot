import os
import time
import zipfile
from pathlib import Path

import pymupdf as fitz
import pytest
from pypdf import PdfWriter

from app.core.exceptions import ResourceLimitError, ValidationError
from app.storage.files import (
    LocalStorage,
    cleanup_temporary_files,
    inspect_file,
    safe_filename,
)


def test_safe_filename_strips_path_and_controls() -> None:
    assert safe_filename("../../private\u0000report.pdf") == "private_report.pdf"
    assert safe_filename("\\etc\\passwd") == "passwd"
    assert safe_filename("....") == "document"


def test_pdf_detected_by_content_and_has_metadata(sample_pdf: Path) -> None:
    details = inspect_file(sample_pdf, 1_000_000, 10)
    assert details["media_type"] == "application/pdf"
    assert details["page_count"] == 1
    assert len(str(details["sha256"])) == 64


def test_upload_preflight_does_not_parse_pdf_in_bot_process(
    sample_pdf: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden_parse(*args, **kwargs):
        pytest.fail("PDF parser must only run inside the limited child process")

    monkeypatch.setattr("pymupdf.open", forbidden_parse)
    details = inspect_file(sample_pdf, 1_000_000, 10, deep_pdf_check=False)
    assert details["deep_inspection_pending"] is True
    assert details["page_count"] is None


def test_rejects_fake_pdf_and_corrupt_pdf(tmp_path: Path) -> None:
    fake = tmp_path / "fake.pdf"
    fake.write_text("not really a PDF")
    with pytest.raises(ValidationError):
        inspect_file(fake, 1000, 10)
    corrupt = tmp_path / "bad.pdf"
    corrupt.write_bytes(b"%PDF-1.7\\nthis is broken")
    with pytest.raises(ValidationError):
        inspect_file(corrupt, 1000, 10)


def test_rejects_password_protected_pdf(tmp_path: Path) -> None:
    path = tmp_path / "encrypted.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(path, encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="owner", user_pw="secret")
    doc.close()
    with pytest.raises(ValidationError, match="password-protected"):
        inspect_file(path, 100_000, 10)


def test_upload_limit_and_page_limit(sample_pdf: Path) -> None:
    with pytest.raises(ResourceLimitError):
        inspect_file(sample_pdf, 10, 10)
    with pytest.raises(ResourceLimitError):
        inspect_file(sample_pdf, 1_000_000, 0)


def test_rejects_zero_page_pdf(tmp_path: Path) -> None:
    path = tmp_path / "empty-pages.pdf"
    PdfWriter().write(path)
    with pytest.raises(ValidationError):
        inspect_file(path, 10_000, 20)


def test_local_storage_uses_generated_keys_and_rejects_traversal(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path / "storage")
    key, path = storage.allocate(42, ".pdf")
    assert path.parent == (tmp_path / "storage" / "42").resolve()
    assert path.name == key
    with pytest.raises(ValidationError):
        storage.path_for(42, "../secret.pdf")
    with pytest.raises(ValidationError):
        storage.path_for(42, "not-allowed.exe")


def test_storage_keys_are_separated_by_user(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path / "storage")
    key, path = storage.allocate(100, ".pdf")
    assert storage.path_for(200, key) != path
    assert storage.path_for(200, key).parent != path.parent


def test_ooxml_archive_bounded_and_identified(tmp_path: Path) -> None:
    path = tmp_path / "anything.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<document/>")
    details = inspect_file(path, 100_000, 10)
    assert details["media_type"].endswith("wordprocessingml.document")
    assert path.with_suffix(".docx").exists() is False


def test_ooxml_preflight_can_defer_archive_parsing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "sample.docx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<document/>")

    def forbidden_parse(_path: Path) -> str:
        pytest.fail("OOXML archive metadata must only be parsed in the isolated child")

    monkeypatch.setattr("app.storage.files._inspect_office_archive", forbidden_parse)
    details = inspect_file(path, 100_000, 10, deep_office_check=False)
    assert details["media_type"] == "application/zip"
    assert details["deep_inspection_pending"] is True


def test_rejects_traversal_inside_ooxml(tmp_path: Path) -> None:
    path = tmp_path / "evil.docx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "x")
        archive.writestr("word/document.xml", "x")
        archive.writestr("../outside.txt", "x")
    with pytest.raises(ValidationError):
        inspect_file(path, 100_000, 10)


def test_temp_cleanup_only_removes_old_owned_files(tmp_path: Path) -> None:
    root = tmp_path / "tmp"
    private = root / "uploads"
    private.mkdir(parents=True)
    old = private / "upload-old"
    fresh = private / "upload-fresh"
    unrelated = private / "keep-me"
    old.write_text("x")
    fresh.write_text("x")
    unrelated.write_text("x")
    old_time = time.time() - 100
    os.utime(old, (old_time, old_time))
    assert cleanup_temporary_files(root, 50) == 1
    assert not old.exists()
    assert fresh.exists() and unrelated.exists()
