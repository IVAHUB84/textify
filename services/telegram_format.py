"""Конвертация Markdown от LLM в безопасный Telegram-HTML.

Telegram не рендерит `####`, `**` и т. п. как Markdown без parse_mode, а MarkdownV2
требует экранирования множества спецсимволов (что ненадёжно для слабой 8B-модели).
Поэтому экранируем спецсимволы HTML сами и переводим ограниченное подмножество
Markdown в теги, которые Telegram поддерживает (`<b>`).
"""
import html
import re

# Заголовок: строка из `#`..`######` + текст (трейлинг-решётки срезаем).
_HEADING_RE = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]+(.+?)[ \t]*#*[ \t]*$")
# Маркер списка в начале строки: -, * или + и пробел.
_BULLET_RE = re.compile(r"^([ \t]*)[-*+][ \t]+")
# Жирный: **текст** или __текст__.
_BOLD_RE = re.compile(r"(\*\*|__)(.+?)\1", re.DOTALL)
# Любые эмфазис-маркеры (для очистки текста заголовка).
_EMPHASIS_RE = re.compile(r"\*\*|__|\*|_")


def _inline(text: str) -> str:
    return _BOLD_RE.sub(lambda m: f"<b>{m.group(2)}</b>", text)


def to_telegram_html(text: str) -> str:
    """Markdown → Telegram-HTML.

    Сначала экранируем `& < >`, затем построчно переводим заголовки в жирный,
    маркеры списка в `•`, инлайновый `**bold**`/`__bold__` в `<b>`. Курсив и прочее
    не трогаем, чтобы не плодить несбалансированные теги.
    """
    escaped = html.escape(text, quote=False)
    out: list[str] = []
    for line in escaped.split("\n"):
        heading = _HEADING_RE.match(line)
        if heading:
            content = _EMPHASIS_RE.sub("", heading.group(1)).strip()
            out.append(f"<b>{content}</b>" if content else "")
            continue
        line = _BULLET_RE.sub(lambda m: f"{m.group(1)}• ", line)
        out.append(_inline(line))
    return "\n".join(out)
