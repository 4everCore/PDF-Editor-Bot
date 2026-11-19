from pathlib import Path

import pymupdf as fitz

from app.services.ai import PageChunk, extract_chunks, rank_chunks


def test_retrieval_selects_relevant_page_and_cites_page(sample_pdf: Path) -> None:
    chunks = extract_chunks(sample_pdf)
    ranked = rank_chunks("What was the project Atlas budget?", chunks)
    assert ranked
    assert ranked[0].pages == (1,)
    assert "1200 EUR" in ranked[0].text


def test_retrieval_returns_no_hits_for_unrelated_question() -> None:
    assert rank_chunks("kookaburra", [PageChunk("budget and project details", (4,))]) == []


def test_scanned_pdf_has_no_text_chunks(tmp_path: Path) -> None:
    path = tmp_path / "blank-scan.pdf"
    doc = fitz.open()
    doc.new_page()
    doc.save(path)
    doc.close()
    assert extract_chunks(path) == []
