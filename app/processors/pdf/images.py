"""Image document adapter: validated JPEG/PNG/TIFF to single-page PDF."""

from pathlib import Path
from typing import Any

import pymupdf as fitz
from PIL import Image, UnidentifiedImageError

from app.core.exceptions import ProcessingError, ValidationError
from app.domain.operations import Operation


class ImageToPDF(Operation):
    name = "image_to_pdf"

    def cleanup_workspace(self, destination: Path) -> None:
        intermediate = Path(str(destination) + ".image.pdf")
        if intermediate.is_symlink():
            intermediate.unlink()
        else:
            intermediate.unlink(missing_ok=True)

    def validate(self, source: Path, options: dict[str, Any]) -> None:
        try:
            with Image.open(source) as image:
                if image.format not in {"JPEG", "PNG", "TIFF"}:
                    raise ValidationError(
                        "Upload a JPEG, PNG, or TIFF image.", code="unsupported_type"
                    )
                if image.width * image.height > 50_000_000:
                    raise ValidationError(
                        "Image exceeds the 50 megapixel processing limit.", code="image_limit"
                    )
                if getattr(image, "n_frames", 1) != 1:
                    raise ValidationError(
                        "Animated or multi-page images are not supported yet.",
                        code="unsupported_image",
                    )
                image.verify()
        except ValidationError:
            raise
        except (UnidentifiedImageError, OSError) as exc:
            raise ValidationError(
                "The image is damaged or unsupported.", code="invalid_image"
            ) from exc

    def execute(self, source: Path, destination: Path, options: dict[str, Any]) -> dict[str, Any]:
        self.validate(source, options)
        try:
            with Image.open(source) as image:
                rgb = image.convert("RGB")
                width, height = rgb.size
                image_pdf = Path(str(destination) + ".image.pdf")
                rgb.save(image_pdf, format="PDF", resolution=150)
            image_pdf.replace(destination)
            with fitz.open(destination) as doc:
                return {
                    "page_count": doc.page_count,
                    "original_dimensions": f"{width}×{height}",
                    "note": "One uploaded image converted to one PDF page.",
                }
        except Exception as exc:
            destination.unlink(missing_ok=True)
            if isinstance(exc, ValidationError):
                raise
            raise ProcessingError(
                "The image could not be converted to PDF.", code="image_conversion_failed"
            ) from exc
        finally:
            self.cleanup_workspace(destination)
