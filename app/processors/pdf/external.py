"""Optional OCR/office adapters with bounded time and allowlisted argv."""

import shutil

# Required for the fixed OCR/LibreOffice tools; commands use argv, never a shell.
import subprocess  # nosec B404
from pathlib import Path
from typing import Any

from app.core.exceptions import ProcessingError, ValidationError
from app.domain.operations import Operation
from app.processors.pdf.basic import open_pdf


class OCRPDF(Operation):
    name = "ocr"

    def validate(self, source: Path, options: dict[str, Any]) -> None:
        languages = options.get("languages", "eng")
        if (
            not isinstance(languages, str)
            or not languages
            or len(languages) > 80
            or not all(c.isalnum() or c in "+_" for c in languages)
        ):
            raise ValidationError("Invalid OCR language selection.", code="invalid_option")
        if not shutil.which("ocrmypdf"):
            raise ProcessingError(
                "OCR is not installed on this server. Add OCRmyPDF and "
                "the requested Tesseract language packs.",
                code="ocr_unavailable",
            )
        with open_pdf(source) as doc:
            if doc.page_count > 100:
                raise ValidationError(
                    "OCR is limited to 100 pages per file.", code="ocr_page_limit"
                )

    def execute(self, source: Path, destination: Path, options: dict[str, Any]) -> dict[str, Any]:
        self.validate(source, options)
        args = [
            "ocrmypdf",
            "--skip-text",
            "--jobs",
            "1",
            "--optimize",
            "1",
            "-l",
            options.get("languages", "eng"),
            str(source),
            str(destination),
        ]
        try:
            # Fixed executable, argument array and validated language code; never invoke a shell.
            result = subprocess.run(  # noqa: S603  # nosec B603
                args,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=300,
                env={"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": str(destination.parent)},
            )
        except subprocess.TimeoutExpired as exc:
            destination.unlink(missing_ok=True)
            raise ProcessingError("OCR exceeded its time limit.", code="timeout") from exc
        if result.returncode != 0 or not destination.is_file():
            destination.unlink(missing_ok=True)
            raise ProcessingError(
                "OCR failed. Check that the required Tesseract language packs are installed.",
                code="ocr_failed",
            )
        with open_pdf(destination) as doc:
            return {
                "page_count": doc.page_count,
                "languages": options.get("languages", "eng"),
                "searchable_pdf": True,
            }


class LibreOfficeToPDF(Operation):
    name = "office_to_pdf"

    def validate(self, source: Path, options: dict[str, Any]) -> None:
        if source.suffix.lower() not in {".docx", ".xlsx", ".pptx", ".odt", ".ods", ".odp"}:
            raise ValidationError(
                "Supported office inputs: DOCX, XLSX, PPTX, ODT, ODS, ODP.",
                code="unsupported_type",
            )
        if not shutil.which("libreoffice"):
            raise ProcessingError(
                "Office conversion is unavailable: LibreOffice is not installed.",
                code="converter_unavailable",
            )

    def cleanup_workspace(self, destination: Path) -> None:
        for prefix in ("lo-profile-", "lo-home-", "lo-output-"):
            path = destination.parent / f"{prefix}{destination.stem}"
            if path.is_symlink():
                path.unlink()
            elif path.is_dir():
                shutil.rmtree(path)

    def execute(self, source: Path, destination: Path, options: dict[str, Any]) -> dict[str, Any]:
        self.validate(source, options)
        profile = destination.parent / f"lo-profile-{destination.stem}"
        home = destination.parent / f"lo-home-{destination.stem}"
        work_dir = destination.parent / f"lo-output-{destination.stem}"
        profile.mkdir(mode=0o700)
        home.mkdir(mode=0o700)
        work_dir.mkdir(mode=0o700)
        args = [
            "libreoffice",
            "-env:UserInstallation=" + profile.as_uri(),
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(work_dir),
            str(source),
        ]
        try:
            # Fixed executable and argv, allowlisted suffix, no shell.
            # The worker additionally supplies operating-system resource limits.
            result = subprocess.run(  # noqa: S603  # nosec B603
                args,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=90,
                env={"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": str(home)},
            )
            generated = work_dir / f"{source.stem}.pdf"
            if result.returncode != 0 or not generated.is_file():
                raise ProcessingError(
                    "LibreOffice could not convert this document.",
                    code="conversion_failed",
                )
            if generated != destination:
                generated.replace(destination)
            with open_pdf(destination) as doc:
                return {
                    "page_count": doc.page_count,
                    "layout_note": (
                        "Office conversion is best-effort; complex layouts and fonts may change."
                    ),
                }
        except subprocess.TimeoutExpired as exc:
            destination.unlink(missing_ok=True)
            raise ProcessingError(
                "Office conversion exceeded its time limit.", code="timeout"
            ) from exc
        finally:
            self.cleanup_workspace(destination)
