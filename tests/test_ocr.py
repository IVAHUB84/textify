import shutil

import pytest
from PIL import Image, ImageDraw, ImageFont

pytesseract = pytest.importorskip("pytesseract")


def _tesseract_available() -> bool:
    if shutil.which("tesseract") is None:
        return False
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


TESSERACT_SKIP = pytest.mark.skipif(
    not _tesseract_available(),
    reason="tesseract binary not found — install tesseract-ocr with rus+eng data to run OCR tests",
)


def _make_image_with_text(text: str) -> bytes:
    img = Image.new("RGB", (400, 100), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((10, 30), text, fill=(0, 0, 0))
    import io
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_blank_image() -> bytes:
    img = Image.new("RGB", (200, 200), color=(200, 200, 200))
    import io
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@TESSERACT_SKIP
@pytest.mark.asyncio
async def test_ocr_returns_text_from_image():
    """Т-1: OCR на изображении с текстом возвращает непустую строку с ожидаемыми словами."""
    from services.ocr import recognize_text

    image_bytes = _make_image_with_text("Hello world")
    result = await recognize_text(image_bytes)
    assert result.strip(), "OCR вернул пустую строку для изображения с текстом"
    assert "Hello" in result or "hello" in result.lower() or "world" in result.lower()


@TESSERACT_SKIP
@pytest.mark.asyncio
async def test_ocr_empty_result_on_blank_image():
    """Т-2: OCR на однотонном фоне без текста возвращает пустой/пробельный результат без исключения."""
    from services.ocr import recognize_text

    image_bytes = _make_blank_image()
    result = await recognize_text(image_bytes)
    assert isinstance(result, str), "recognize_text должна возвращать str"
    assert not result.strip(), f"Ожидали пустой результат, получили: {result!r}"
