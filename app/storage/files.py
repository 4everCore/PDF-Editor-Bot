"""Validated upload inspection and isolated local storage keys."""

import hashlib
import os
import re
import stat
import time
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

import filetype

from app.core.exceptions import AppError, ResourceLimitError, ValidationError

_ALLOWED = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/tiff": ".tiff",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
}
_OFFICE_MARKERS = {
    "word/document.xml": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xl/workbook.xml": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "ppt/presentation.xml": (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    ),
}
_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def safe_filename(name: str, fallback: str = "document") -> str:
    """Discard paths and control characters; filenames are display metadata only."""
    leaf = name.replace("\\", "/").split("/")[-1]
    clean = _NAME_RE.sub("_", leaf).strip("._-")[:120]
    return clean or fallback


def inspect_file(
    path: Path,
    max_bytes: int,
    max_pages: int,
    *,
    deep_pdf_check: bool = True,
    deep_office_check: bool = True,
) -> dict[str, Any]:
    """Check actual file signatures and bounded container structure, not client MIME/name."""
    size = path.stat().st_size
    if size <= 0:
        raise ValidationError("The uploaded file is empty.", code="empty_file")
    if size > max_bytes:
        raise ResourceLimitError(
            f"File exceeds the {max_bytes // (1024 * 1024)} MB upload limit.", code="file_too_large"
        )
    with path.open("rb") as stream:
        signature = stream.read(4)
    kind = filetype.guess(str(path))
    mime = kind.mime if kind else None
    if signature.startswith(b"PK\x03\x04"):
        if not deep_office_check:
            return {
                "media_type": "application/zip",
                "size_bytes": size,
                "sha256": sha256_file(path),
                "deep_inspection_pending": True,
            }
        mime = _inspect_office_archive(path)
    if mime not in _ALLOWED:
        raise ValidationError(
            "Unsupported file type. Upload PDF, JPEG, PNG, TIFF, DOCX, XLSX, or PPTX.",
            code="unsupported_type",
        )
    info: dict[str, Any] = {"media_type": mime, "size_bytes": size, "sha256": sha256_file(path)}
    if mime == "application/pdf":
        if not deep_pdf_check:
            info["page_count"] = None
            info["deep_inspection_pending"] = True
            return info
        import pymupdf as fitz

        try:
            with fitz.open(path) as doc:
                if doc.is_encrypted:
                    raise ValidationError(
                        "This PDF is password-protected. Password support is not "
                        "enabled in this flow.",
                        code="encrypted_pdf",
                    )
                if doc.page_count < 1:
                    raise ValidationError("PDF contains no pages.", code="invalid_pdf")
                if doc.page_count > max_pages:
                    raise ResourceLimitError(
                        f"PDF exceeds the {max_pages} page limit.", code="too_many_pages"
                    )
                info["page_count"] = doc.page_count
        except AppError:
            raise
        except Exception as exc:
            raise ValidationError(
                "The PDF is damaged or cannot be opened.", code="invalid_pdf"
            ) from exc
    return info


def _inspect_office_archive(path: Path) -> str:
    """Recognize macro-free OOXML with bounded archive metadata; never extract archive paths."""
    try:
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > 2000:
                raise ValidationError(
                    "Office archive contains too many entries.", code="archive_limit"
                )
            total_size = 0
            names: set[str] = set()
            for entry in entries:
                name = entry.filename
                pure = PurePosixPath(name)
                mode = entry.external_attr >> 16
                if "\\" in name or pure.is_absolute() or ".." in pure.parts or stat.S_ISLNK(mode):
                    raise ValidationError(
                        "Unsafe path found inside the Office file.", code="unsafe_archive"
                    )
                total_size += entry.file_size
                if entry.file_size > 50 * 1024 * 1024 or total_size > 100 * 1024 * 1024:
                    raise ValidationError(
                        "Office file expands beyond the allowed size.", code="archive_limit"
                    )
                if name in names:
                    raise ValidationError(
                        "Office archive contains duplicate member paths.", code="unsafe_archive"
                    )
                if (entry.file_size and entry.compress_size == 0) or (
                    entry.compress_size and entry.file_size / entry.compress_size > 200
                ):
                    raise ValidationError(
                        "Office file has a suspicious compression ratio.", code="archive_limit"
                    )
                names.add(name)
            if "[Content_Types].xml" not in names:
                raise ValidationError(
                    "Unrecognized ZIP file; expected DOCX, XLSX, or PPTX.", code="unsupported_type"
                )
            # Never decompress archive members in the bot process.
            # LibreOffice validates content in the resource-limited worker.
            for marker, media_type in _OFFICE_MARKERS.items():
                if marker in names:
                    return media_type
            raise ValidationError(
                "Only DOCX, XLSX, and PPTX Office files are supported.", code="unsupported_type"
            )
    except ValidationError:
        raise
    except (zipfile.BadZipFile, OSError, RuntimeError) as exc:
        raise ValidationError(
            "The Office file is damaged or invalid.", code="invalid_archive"
        ) from exc


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cleanup_temporary_files(base_path: Path, older_than_seconds: int) -> int:
    """Remove stale app-owned scratch files only; never traverse symlinks or user folders."""
    base = base_path.resolve()
    private = base / "uploads"
    if private.is_symlink() or not private.is_dir():
        return 0
    resolved = private.resolve()
    if not resolved.is_relative_to(base):
        return 0
    cutoff = time.time() - max(older_than_seconds, 1)
    removed = 0
    with os.scandir(resolved) as entries:
        for entry in entries:
            if not entry.name.startswith(("upload-", "inspect-")):
                continue
            try:
                if entry.is_symlink() or not entry.is_file(follow_symlinks=False):
                    continue
                if entry.stat(follow_symlinks=False).st_mtime < cutoff:
                    Path(entry.path).unlink(missing_ok=True)
                    removed += 1
            except FileNotFoundError:
                continue
    return removed


class LocalStorage:
    """Local file storage. Each user gets a private directory and opaque generated names."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    def path_for(self, user_id: int, key: str) -> Path:
        allowed_suffixes = tuple(_ALLOWED.values()) + (".txt",)
        if not key.endswith(allowed_suffixes) or Path(key).name != key:
            raise ValidationError("Invalid storage reference.", code="invalid_storage_key")
        user_root = (self.root / str(user_id)).resolve()
        path = (user_root / key).resolve()
        if not path.is_relative_to(user_root) or not user_root.is_relative_to(self.root):
            raise ValidationError("Invalid storage reference.", code="invalid_storage_key")
        return path

    def allocate(self, user_id: int, suffix: str = ".pdf") -> tuple[str, Path]:
        if suffix not in set(_ALLOWED.values()) | {".txt", ".png", ".jpg"}:
            suffix = ".pdf"
        key = f"{uuid.uuid4().hex}{suffix}"
        path = self.path_for(user_id, key)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(path.parent, 0o700)
        return key, path
