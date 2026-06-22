from handlers.commands import HELP_TEXT
from handlers.image import NO_TEXT_MESSAGE


def test_help_text_contains_file_hint():
    hint_keywords = ("файл", "документ", "пережима", "пережим")
    assert any(kw in HELP_TEXT.lower() for kw in hint_keywords), (
        f"HELP_TEXT should contain a hint to send image as file/document, got: {HELP_TEXT!r}"
    )


def test_no_text_message_contains_file_hint():
    hint_keywords = ("файл", "документ", "пережима", "пережим")
    assert any(kw in NO_TEXT_MESSAGE.lower() for kw in hint_keywords), (
        f"NO_TEXT_MESSAGE should contain a hint to send image as file/document, got: {NO_TEXT_MESSAGE!r}"
    )


def test_no_text_message_still_mentions_not_recognized():
    assert "не распознан" in NO_TEXT_MESSAGE.lower(), (
        "NO_TEXT_MESSAGE should still say text was not recognized"
    )
