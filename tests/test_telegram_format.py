"""Тесты services/telegram_format.to_telegram_html."""
from services.telegram_format import to_telegram_html


def test_heading_becomes_bold():
    assert to_telegram_html("## Заголовок") == "<b>Заголовок</b>"


def test_all_heading_levels():
    for n in range(1, 7):
        assert to_telegram_html("#" * n + " Тема") == "<b>Тема</b>"


def test_heading_strips_inner_emphasis():
    assert to_telegram_html("### **Итог**") == "<b>Итог</b>"


def test_heading_strips_trailing_hashes():
    assert to_telegram_html("## Тема ##") == "<b>Тема</b>"


def test_bold_double_star():
    assert to_telegram_html("это **важно** тут") == "это <b>важно</b> тут"


def test_bold_double_underscore():
    assert to_telegram_html("это __важно__ тут") == "это <b>важно</b> тут"


def test_bullets_dash_star_plus():
    out = to_telegram_html("- раз\n* два\n+ три")
    assert out == "• раз\n• два\n• три"


def test_bullet_indent_preserved():
    assert to_telegram_html("  - вложенный") == "  • вложенный"


def test_html_special_chars_escaped():
    out = to_telegram_html("a < b & c > d")
    assert "&lt;" in out and "&amp;" in out and "&gt;" in out
    assert "<b>" not in out


def test_emoji_preserved():
    assert to_telegram_html("**📋 Задачи**") == "<b>📋 Задачи</b>"


def test_plain_text_unchanged():
    assert to_telegram_html("Просто текст без разметки.") == "Просто текст без разметки."


def test_horizontal_rule_not_a_bullet():
    # "---" без пробела не должен превратиться в маркер
    assert to_telegram_html("---") == "---"


def test_combined():
    md = "## План\n- **первое** дело\n- второе"
    assert to_telegram_html(md) == "<b>План</b>\n• <b>первое</b> дело\n• второе"
