from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.bot.handlers import menu
from app.bot.keyboards.main import LABELS, file_actions, language_keyboard, main_menu


def test_main_menu_has_persian_and_english_categories() -> None:
    assert len(main_menu("fa").keyboard) == 6
    assert "📄 ابزارهای PDF" in main_menu("fa").keyboard[0][0].text
    assert "PDF Tools" in main_menu("en").keyboard[0][0].text


def test_file_actions_are_scoped_and_real() -> None:
    markup = file_actions("a-valid-uuid", "en")
    callbacks = [button.callback_data for row in markup.inline_keyboard for button in row]
    assert callbacks
    assert all(callback.startswith("op:a-valid-uuid:") for callback in callbacks)
    assert "op:a-valid-uuid:compress" in callbacks
    assert "op:a-valid-uuid:extract_text" in callbacks
    assert "op:a-valid-uuid:rotate" in callbacks


def test_office_upload_has_conversion_action() -> None:
    markup = file_actions("id", "fa", is_pdf=False, is_office=True)
    assert markup.inline_keyboard[0][0].callback_data == "op:id:office_to_pdf"


def test_language_switch_has_both_languages() -> None:
    keys = [button.callback_data for row in language_keyboard().inline_keyboard for button in row]
    assert keys == ["lang:fa", "lang:en"]


@pytest.mark.asyncio
async def test_every_main_menu_button_has_a_specific_response() -> None:
    for label in set(LABELS["fa"] + LABELS["en"]):
        message = SimpleNamespace(text=label, answer=AsyncMock())
        await menu.menu_action(message)
        message.answer.assert_awaited_once()
        assert "Use /help" not in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_start_responds_with_saved_language_keyboard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(menu, "language_for", AsyncMock(return_value="en"))
    message = SimpleNamespace(
        from_user=SimpleNamespace(id=42),
        answer=AsyncMock(),
    )
    await menu.start(message)
    message.answer.assert_awaited_once()
    assert message.answer.await_args.kwargs["reply_markup"] == main_menu("en")
