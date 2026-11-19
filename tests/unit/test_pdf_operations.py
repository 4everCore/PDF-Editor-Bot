from pathlib import Path

import pymupdf as fitz
import pytest
from PIL import Image

from app.core.exceptions import ValidationError
from app.processors.pdf.basic import (
    CompressPDF,
    ExtractPages,
    ExtractText,
    MergePDF,
    RenderPDF,
    RotatePDF,
    WatermarkPDF,
)
from app.processors.pdf.images import ImageToPDF


def run(op, source: Path, dest: Path, options: dict | None = None):
    opts = options or {}
    op.validate(source, opts)
    return op.execute(source, dest, opts)


def test_text_extraction_preserves_content_and_pages(sample_pdf: Path, tmp_path: Path) -> None:
    out = tmp_path / "text.txt"
    result = run(ExtractText(), sample_pdf, out)
    text = out.read_text(encoding="utf-8")
    assert "project Atlas budget 1200 EUR" in text
    assert "Page 1" in text
    assert result["page_count"] == 1


def test_compression_creates_openable_pdf_and_reports_quality(
    sample_pdf: Path, tmp_path: Path
) -> None:
    out = tmp_path / "compressed.pdf"
    result = run(CompressPDF(), sample_pdf, out, {"level": "balanced"})
    with fitz.open(out) as doc:
        assert doc.page_count == 1
        assert "project Atlas" in doc[0].get_text()
    assert result["quality_note"].startswith("Compression uses lossless")
    assert 0 <= result["reduction_percent"] <= 100


@pytest.mark.parametrize("level", ["low", "high"])
def test_compression_other_levels_create_openable_pdfs(
    level: str, sample_pdf: Path, tmp_path: Path
) -> None:
    output = tmp_path / f"compressed-{level}.pdf"
    result = run(CompressPDF(), sample_pdf, output, {"level": level})
    assert result["level"] == level
    with fitz.open(output) as document:
        assert document.page_count == 1
        assert "project Atlas" in document[0].get_text()


def test_compression_rejects_unknown_level(sample_pdf: Path) -> None:
    with pytest.raises(ValidationError):
        CompressPDF().validate(sample_pdf, {"level": "extreme"})


def test_watermark_adds_overlay_without_removing_original(sample_pdf: Path, tmp_path: Path) -> None:
    out = tmp_path / "watermarked.pdf"
    result = run(WatermarkPDF(), sample_pdf, out, {"text": "SAMPLE"})
    with fitz.open(out) as doc:
        text = doc[0].get_text()
    assert "project Atlas" in text
    assert "SAMPLE" in text
    assert result["overlay"] is True


def test_watermark_rejects_text_that_cannot_fit_small_page(tmp_path: Path) -> None:
    source = tmp_path / "small.pdf"
    document = fitz.open()
    document.new_page(width=80, height=80)
    document.save(source)
    document.close()
    with pytest.raises(ValidationError, match="does not fit"):
        WatermarkPDF().execute(source, tmp_path / "small-watermarked.pdf", {"text": "W" * 100})
    assert not (tmp_path / "small-watermarked.pdf").exists()


def test_rotate_pdf_changes_page_rotation(sample_pdf: Path, tmp_path: Path) -> None:
    out = tmp_path / "rotated.pdf"
    run(RotatePDF(), sample_pdf, out, {"degrees": 90})
    with fitz.open(out) as doc:
        assert doc[0].rotation == 90
        assert "project Atlas" in doc[0].get_text()


def test_render_pdf_produces_valid_png(sample_pdf: Path, tmp_path: Path) -> None:
    out = tmp_path / "preview.png"
    data = run(RenderPDF(), sample_pdf, out, {"page": 1})
    with Image.open(out) as image:
        image.verify()
    assert data["width"] > 100


def test_extract_pages_and_reject_out_of_range(sample_pdf: Path, tmp_path: Path) -> None:
    out = tmp_path / "pages.pdf"
    run(ExtractPages(), sample_pdf, out, {"pages": [1]})
    with fitz.open(out) as doc:
        assert doc.page_count == 1
        assert "project Atlas" in doc[0].get_text()
    with pytest.raises(ValidationError):
        ExtractPages().validate(sample_pdf, {"pages": [2]})


def test_merge_two_pdfs(sample_pdf: Path, sample_pdf_2: Path, tmp_path: Path) -> None:
    out = tmp_path / "merged.pdf"
    info = MergePDF().execute(sample_pdf, out, {"sources": [str(sample_pdf), str(sample_pdf_2)]})
    with fitz.open(out) as doc:
        assert doc.page_count == 2
        assert "Atlas" in doc[0].get_text()
        assert "Second source" in doc[1].get_text()
    assert info["source_count"] == 2


def test_merge_requires_more_than_one_source(sample_pdf: Path, tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        MergePDF().execute(sample_pdf, tmp_path / "x.pdf", {"sources": [str(sample_pdf)]})


def test_image_to_pdf_is_valid(sample_png: Path, tmp_path: Path) -> None:
    out = tmp_path / "image.pdf"
    result = run(ImageToPDF(), sample_png, out)
    with fitz.open(out) as doc:
        assert doc.page_count == 1
        assert len(doc[0].get_images()) == 1
    assert result["page_count"] == 1
    assert not Path(str(out) + ".image.pdf").exists()
