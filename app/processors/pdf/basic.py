"""Core PDF operations implemented with PyMuPDF/pypdf."""

import json
from pathlib import Path
from typing import Any

import pymupdf as fitz
from pypdf import PdfReader, PdfWriter

from app.core.exceptions import ProcessingError, ValidationError
from app.domain.operations import Operation


def open_pdf(source: Path) -> fitz.Document:
    try:
        doc = fitz.open(source)
        if doc.is_encrypted:
            doc.close()
            raise ValidationError(
                "Password-protected PDFs are not supported in this operation.", code="encrypted_pdf"
            )
        return doc
    except ValidationError:
        raise
    except Exception as exc:
        raise ValidationError("The PDF could not be opened.", code="invalid_pdf") from exc


class InspectDocument(Operation):
    """Internal content/container preflight executed only in the limited child process."""

    name = "inspect"
    output_suffix = ".txt"

    def validate(self, source: Path, options: dict[str, Any]) -> None:
        max_bytes = options.get("max_bytes", 20 * 1024 * 1024)
        max_pages = options.get("max_pages", 500)
        if not isinstance(max_bytes, int) or max_bytes < 1:
            raise ValidationError("Invalid file size limit.", code="invalid_option")
        if not isinstance(max_pages, int) or max_pages < 1:
            raise ValidationError("Invalid page limit.", code="invalid_option")

    def execute(self, source: Path, destination: Path, options: dict[str, Any]) -> dict[str, Any]:
        from app.storage.files import inspect_file

        metadata = inspect_file(
            source,
            int(options.get("max_bytes", 20 * 1024 * 1024)),
            int(options.get("max_pages", 500)),
        )
        metadata.pop("sha256", None)
        destination.write_text(json.dumps(metadata), encoding="utf-8")
        return metadata


class ExtractText(Operation):
    name = "extract_text"
    output_suffix = ".txt"

    def validate(self, source: Path, options: dict[str, Any]) -> None:
        open_pdf(source).close()

    def execute(self, source: Path, destination: Path, options: dict[str, Any]) -> dict[str, Any]:
        with open_pdf(source) as doc, destination.open("w", encoding="utf-8", newline="\n") as out:
            for index, page in enumerate(doc, start=1):
                out.write(f"--- Page {index} ---\n{page.get_text(sort=True)}\n")
            count = doc.page_count
        return {"page_count": count, "format": "text"}


class CompressPDF(Operation):
    name = "compress"

    def validate(self, source: Path, options: dict[str, Any]) -> None:
        if options.get("level", "balanced") not in {"low", "balanced", "high"}:
            raise ValidationError(
                "Choose low, balanced, or high compression.", code="invalid_option"
            )
        open_pdf(source).close()

    def execute(self, source: Path, destination: Path, options: dict[str, Any]) -> dict[str, Any]:
        level = options.get("level", "balanced")
        garbage = {"low": 1, "balanced": 3, "high": 4}[level]
        with open_pdf(source) as doc:
            doc.save(
                destination,
                garbage=garbage,
                deflate=True,
                deflate_images=level != "low",
                deflate_fonts=True,
                clean=True,
            )
            pages = doc.page_count
        before, after = source.stat().st_size, destination.stat().st_size
        return {
            "page_count": pages,
            "level": level,
            "input_bytes": before,
            "output_bytes": after,
            "reduction_percent": round((before - after) / before * 100, 1),
            "quality_note": (
                "Compression uses lossless object/stream optimization; "
                "embedded image resolution is not reduced."
            ),
        }


class RotatePDF(Operation):
    name = "rotate"

    def validate(self, source: Path, options: dict[str, Any]) -> None:
        if options.get("degrees") not in {90, 180, 270}:
            raise ValidationError(
                "Rotation must be 90, 180, or 270 degrees.", code="invalid_option"
            )
        open_pdf(source).close()

    def execute(self, source: Path, destination: Path, options: dict[str, Any]) -> dict[str, Any]:
        with open_pdf(source) as doc:
            pages = options.get("pages")
            indices = range(doc.page_count) if pages is None else [int(n) - 1 for n in pages]
            for index in indices:
                if index < 0 or index >= doc.page_count:
                    raise ValidationError(
                        "Page number is outside the document.", code="invalid_page"
                    )
                doc[index].set_rotation((doc[index].rotation + int(options["degrees"])) % 360)
            count = doc.page_count
            doc.save(destination, garbage=3, deflate=True)
        return {"page_count": count, "rotated_degrees": options["degrees"]}


class WatermarkPDF(Operation):
    name = "watermark"

    def validate(self, source: Path, options: dict[str, Any]) -> None:
        text = options.get("text")
        if not isinstance(text, str) or not text.strip() or len(text) > 100:
            raise ValidationError(
                "Watermark text must contain 1–100 characters.", code="invalid_option"
            )
        open_pdf(source).close()

    def execute(self, source: Path, destination: Path, options: dict[str, Any]) -> dict[str, Any]:
        with open_pdf(source) as doc:
            for page in doc:
                rect = page.rect
                remaining = page.insert_textbox(
                    fitz.Rect(
                        rect.width * 0.1, rect.height * 0.4, rect.width * 0.9, rect.height * 0.6
                    ),
                    str(options["text"]),
                    fontsize=32,
                    color=(0.65, 0.65, 0.65),
                    align=1,
                    rotate=0,
                    overlay=True,
                    fill_opacity=0.35,
                )
                if remaining < 0:
                    raise ValidationError(
                        "Watermark text does not fit this page.", code="watermark_too_large"
                    )
            count = doc.page_count
            doc.save(destination, garbage=3, deflate=True)
        return {
            "page_count": count,
            "overlay": True,
            "note": "Watermark added as a visual overlay; original page content remains.",
        }


class RenderPDF(Operation):
    name = "render_png"
    output_suffix = ".png"

    def validate(self, source: Path, options: dict[str, Any]) -> None:
        if int(options.get("page", 1)) < 1:
            raise ValidationError("Page numbers start at 1.", code="invalid_page")
        open_pdf(source).close()

    def execute(self, source: Path, destination: Path, options: dict[str, Any]) -> dict[str, Any]:
        with open_pdf(source) as doc:
            page_no = int(options.get("page", 1))
            if page_no > doc.page_count:
                raise ValidationError("Page number is outside the document.", code="invalid_page")
            page = doc[page_no - 1]
            pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
            pix.save(destination)
            return {
                "page": page_no,
                "page_count": doc.page_count,
                "width": pix.width,
                "height": pix.height,
            }


class ExtractPages(Operation):
    name = "extract_pages"

    def validate(self, source: Path, options: dict[str, Any]) -> None:
        pages = options.get("pages")
        if not isinstance(pages, list) or not pages:
            raise ValidationError("Provide one or more page numbers.", code="invalid_option")
        with open_pdf(source) as doc:
            if any(not isinstance(p, int) or p < 1 or p > doc.page_count for p in pages):
                raise ValidationError(
                    "A requested page number is outside the document.", code="invalid_page"
                )

    def execute(self, source: Path, destination: Path, options: dict[str, Any]) -> dict[str, Any]:
        reader = PdfReader(str(source), strict=True)
        writer = PdfWriter()
        for page in options["pages"]:
            writer.add_page(reader.pages[page - 1])
        with destination.open("wb") as stream:
            writer.write(stream)
        return {"page_count": len(options["pages"])}


class MergePDF(Operation):
    name = "merge"

    def validate(self, source: Path, options: dict[str, Any]) -> None:
        paths = options.get("sources")
        if not isinstance(paths, list) or not 2 <= len(paths) <= 10:
            raise ValidationError(
                "Merge requires between two and ten source PDFs.",
                code="multiple_files_required",
            )
        source_root = source.parent.resolve()
        total_pages = 0
        for item in paths:
            candidate = Path(item)
            if not candidate.is_file() or candidate.resolve().parent != source_root:
                raise ValidationError(
                    "A merge source is missing or outside the user's storage directory.",
                    code="invalid_source",
                )
            with open_pdf(candidate) as doc:
                total_pages += doc.page_count
        if total_pages > 500:
            raise ValidationError("Merged output exceeds the 500 page limit.", code="page_limit")

    def execute(self, source: Path, destination: Path, options: dict[str, Any]) -> dict[str, Any]:
        self.validate(source, options)
        paths = options["sources"]
        writer = PdfWriter()
        try:
            for item in paths:
                path = Path(item)
                if not path.is_file():
                    raise ValidationError("A source PDF is missing.", code="missing_file")
                writer.append(str(path))
            count = len(writer.pages)
            with destination.open("wb") as stream:
                writer.write(stream)
            return {"page_count": count, "source_count": len(paths)}
        except Exception as exc:
            destination.unlink(missing_ok=True)
            if isinstance(exc, ValidationError):
                raise
            raise ProcessingError(
                "One or more PDFs could not be merged.", code="merge_failed"
            ) from exc
        finally:
            writer.close()
