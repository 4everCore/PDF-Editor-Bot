from pathlib import Path

import fitz
import pytest

from app.services.ai import DocumentAssistant


class RecordingProvider:
    def __init__(self) -> None:
        self.system_prompt = ""
        self.user_prompt = ""

    async def answer(self, *, system_prompt: str, user_prompt: str) -> str:
        self.system_prompt = system_prompt
        self.user_prompt = user_prompt
        return "The budget is 1200 EUR [p. 1]."


@pytest.mark.asyncio
async def test_assistant_sends_relevant_excerpt_and_page_number(sample_pdf: Path) -> None:
    provider = RecordingProvider()
    answer = await DocumentAssistant(provider).ask(sample_pdf, "What was the Atlas budget?")
    assert answer.endswith("[p. 1].")
    assert "1200 EUR" in provider.user_prompt
    assert "[Page 1]" in provider.user_prompt
    assert "cite every factual claim" in provider.system_prompt.lower()


def test_scanned_document_gives_no_match_without_inventing_text(tmp_path: Path) -> None:
    path = tmp_path / "scan.pdf"
    document = fitz.open()
    document.new_page()
    document.save(path)
    document.close()
    from app.services.ai import extract_chunks, rank_chunks

    chunks = extract_chunks(path)
    assert chunks == []
    assert rank_chunks("what is the contract date", chunks) == []
