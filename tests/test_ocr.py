import io
import shutil

import pytest
from PIL import Image, ImageDraw

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
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_blank_image() -> bytes:
    img = Image.new("RGB", (200, 200), color=(200, 200, 200))
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


# ---------------------------------------------------------------------------
# recognize_pdf — через мок image_to_pdf_or_hocr и render_page
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_recognize_pdf_calls_render_page_doc_mode(monkeypatch):
    """recognize_pdf(b, 'doc') вызывает render_page, затем подаёт JPEG-перекодированную страницу в Tesseract."""
    from unittest.mock import MagicMock

    import services.ocr as ocr

    sentinel_page = Image.new("L", (100, 100), color=200)
    render_mock = MagicMock(return_value=sentinel_page)
    fake_pdf = MagicMock(return_value=b"%PDF-1.4 fake")

    monkeypatch.setattr(ocr, "render_page", render_mock)
    monkeypatch.setattr(ocr.pytesseract, "image_to_pdf_or_hocr", fake_pdf)

    image_bytes = _make_image_with_text("hi")
    result = await ocr.recognize_pdf(image_bytes, "doc")

    render_mock.assert_called_once_with(image_bytes, "doc")
    assert fake_pdf.call_args.kwargs.get("extension") == "pdf"
    # После JPEG-перекодирования в Tesseract уходит новый PIL-объект (не sentinel),
    # но это PIL.Image.Image с форматом JPEG.
    called_image = fake_pdf.call_args.args[0]
    assert isinstance(called_image, Image.Image)
    assert called_image.format == "JPEG"
    assert result == b"%PDF-1.4 fake"


@pytest.mark.asyncio
async def test_recognize_pdf_page_is_jpeg_encoded(monkeypatch):
    """КП-4: страница, поданная в Tesseract, прошла через JPEG-перекодирование (format=JPEG)."""
    from unittest.mock import MagicMock

    import services.ocr as ocr

    page = Image.new("L", (200, 200), color=180)
    monkeypatch.setattr(ocr, "render_page", MagicMock(return_value=page))

    captured: list[Image.Image] = []

    def capture_call(image, **kwargs):
        captured.append(image)
        return b"%PDF-1.4"

    monkeypatch.setattr(ocr.pytesseract, "image_to_pdf_or_hocr", capture_call)

    await ocr.recognize_pdf(_make_image_with_text("hi"), "doc")

    assert len(captured) == 1
    assert captured[0].format == "JPEG", f"Expected JPEG, got {captured[0].format}"


@pytest.mark.asyncio
async def test_recognize_pdf_scan_mode_uses_render_page(monkeypatch):
    """recognize_pdf(b, 'scan') строит страницу через render_page с mode='scan'."""
    from unittest.mock import MagicMock

    import services.ocr as ocr

    sentinel_page = Image.new("L", (100, 100), color=0)
    render_mock = MagicMock(return_value=sentinel_page)
    fake_pdf = MagicMock(return_value=b"%PDF-1.4 scan")

    monkeypatch.setattr(ocr, "render_page", render_mock)
    monkeypatch.setattr(ocr.pytesseract, "image_to_pdf_or_hocr", fake_pdf)

    image_bytes = _make_image_with_text("hi")
    result = await ocr.recognize_pdf(image_bytes, "scan")

    render_mock.assert_called_once_with(image_bytes, "scan")
    assert result == b"%PDF-1.4 scan"


@pytest.mark.asyncio
async def test_recognize_pdf_default_mode_is_doc(monkeypatch):
    """recognize_pdf(b) без mode работает как mode='doc'."""
    from unittest.mock import MagicMock

    import services.ocr as ocr

    sentinel_page = Image.new("L", (100, 100), color=200)
    render_mock = MagicMock(return_value=sentinel_page)
    fake_pdf = MagicMock(return_value=b"%PDF-1.4 doc")

    monkeypatch.setattr(ocr, "render_page", render_mock)
    monkeypatch.setattr(ocr.pytesseract, "image_to_pdf_or_hocr", fake_pdf)

    image_bytes = _make_image_with_text("hi")
    result = await ocr.recognize_pdf(image_bytes)

    render_mock.assert_called_once_with(image_bytes, "doc")
    assert result == b"%PDF-1.4 doc"


@pytest.mark.asyncio
async def test_recognize_pdf_render_failure_falls_back_to_original(monkeypatch):
    """При исключении в render_page — fallback на оригинал, исключение не пробрасывается."""
    from unittest.mock import MagicMock

    import services.ocr as ocr

    render_mock = MagicMock(side_effect=RuntimeError("render failed"))
    fake_pdf = MagicMock(return_value=b"%PDF-1.4 original")

    monkeypatch.setattr(ocr, "render_page", render_mock)
    monkeypatch.setattr(ocr.pytesseract, "image_to_pdf_or_hocr", fake_pdf)

    image_bytes = _make_image_with_text("hi")
    result = await ocr.recognize_pdf(image_bytes, "doc")

    assert result == b"%PDF-1.4 original"
    # fallback вызывает image_to_pdf_or_hocr с оригиналом (не sentinel)
    called_image = fake_pdf.call_args.args[0]
    assert isinstance(called_image, Image.Image)


@pytest.mark.asyncio
async def test_recognize_pdf_render_failure_logs_degradation(monkeypatch, caplog):
    """Деградация при сбое render_page логируется на уровне WARNING."""
    import logging
    from unittest.mock import MagicMock

    import services.ocr as ocr

    monkeypatch.setattr(ocr, "render_page", MagicMock(side_effect=RuntimeError("boom")))
    monkeypatch.setattr(ocr.pytesseract, "image_to_pdf_or_hocr", MagicMock(return_value=b"%PDF"))

    with caplog.at_level(logging.WARNING, logger="services.ocr"):
        await ocr.recognize_pdf(_make_image_with_text("hi"), "doc")

    assert any("fall" in r.message.lower() or "degrad" in r.message.lower() or "original" in r.message.lower() for r in caplog.records)


@pytest.mark.asyncio
async def test_recognize_pdf_both_fail_returns_none(monkeypatch):
    """Сбой и render_page, и fallback → recognize_pdf возвращает None без проброса."""
    from unittest.mock import MagicMock

    import services.ocr as ocr

    monkeypatch.setattr(ocr, "render_page", MagicMock(side_effect=RuntimeError("render failed")))
    monkeypatch.setattr(
        ocr.pytesseract,
        "image_to_pdf_or_hocr",
        MagicMock(side_effect=RuntimeError("tesseract failed")),
    )

    result = await ocr.recognize_pdf(_make_image_with_text("hi"), "doc")

    assert result is None


@pytest.mark.asyncio
async def test_recognize_pdf_returns_bytes(monkeypatch):
    """recognize_pdf отдаёт байты PDF от pytesseract (мок, без бинаря tesseract)."""
    from unittest.mock import MagicMock

    import services.ocr as ocr

    fake_page = Image.new("L", (100, 100), color=200)
    monkeypatch.setattr(ocr, "render_page", MagicMock(return_value=fake_page))
    fake = MagicMock(return_value=b"%PDF-1.4 fake")
    monkeypatch.setattr(ocr.pytesseract, "image_to_pdf_or_hocr", fake)

    result = await ocr.recognize_pdf(_make_image_with_text("hi"))

    assert result == b"%PDF-1.4 fake"
    assert fake.call_args.kwargs.get("extension") == "pdf"


@pytest.mark.asyncio
async def test_recognize_pdf_returns_none_on_error(monkeypatch):
    """Сбой и render_page, и Tesseract → recognize_pdf возвращает None, исключение не пробрасывается."""
    from unittest.mock import MagicMock

    import services.ocr as ocr

    monkeypatch.setattr(ocr, "render_page", MagicMock(side_effect=RuntimeError("tess failed")))
    boom = MagicMock(side_effect=RuntimeError("tess failed"))
    monkeypatch.setattr(ocr.pytesseract, "image_to_pdf_or_hocr", boom)

    result = await ocr.recognize_pdf(_make_image_with_text("hi"))

    assert result is None
