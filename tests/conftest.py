from pathlib import Path

import pymupdf as fitz
import pytest
from PIL import Image


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    path = tmp_path / "sample.pdf"
    doc = fitz.open()
    page = doc.new_page(width=612, height=792)
    page.insert_text((72, 100), "Release plan Q3: project Atlas budget 1200 EUR.")
    page.insert_text((72, 130), "This paragraph contains searchable text for extraction tests.")
    doc.save(path)
    doc.close()
    return path


@pytest.fixture
def sample_pdf_2(tmp_path: Path) -> Path:
    path = tmp_path / "sample-two.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Second source document.")
    doc.save(path)
    doc.close()
    return path


@pytest.fixture
def sample_png(tmp_path: Path) -> Path:
    path = tmp_path / "sample.png"
    Image.new("RGB", (140, 90), color=(30, 120, 200)).save(path)
    return path
