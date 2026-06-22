import asyncio
import inspect
import io
import shutil
from unittest.mock import patch

import pytest
from PIL import Image


def _png_bytes(size=(200, 100), color=(255, 255, 255)) -> bytes:
    img = Image.new("RGB", size, color=color)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _tesseract_available() -> bool:
    if shutil.which("tesseract") is None:
        return False
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


TESSERACT_SKIP = pytest.mark.skipif(
    not _tesseract_available(),
    reason="tesseract binary not found — install tesseract-ocr with rus+eng data to run OCR tests",
)


def test_recognize_text_exists_and_is_coroutine():
    from services.ocr import recognize_text
    assert inspect.iscoroutinefunction(recognize_text), "recognize_text must be async"


def test_recognize_text_accepts_bytes_returns_str_annotation():
    from services.ocr import recognize_text
    hints = recognize_text.__annotations__
    assert hints.get("return") is str or str(hints.get("return")) == "str"


def test_ocr_module_does_not_import_aiogram():
    import services.ocr as ocr_module
    module_source = inspect.getsource(ocr_module)
    assert "aiogram" not in module_source, "services/ocr.py must not import aiogram"


@pytest.mark.asyncio
async def test_oem1_psm3_and_lang_used():
    from services import ocr
    with patch("pytesseract.image_to_string", return_value="mocked") as mock_ts:
        await ocr.recognize_text(_png_bytes())
        assert mock_ts.called
        call_kwargs = mock_ts.call_args
        config_arg = call_kwargs.kwargs.get("config") or (
            call_kwargs.args[2] if len(call_kwargs.args) > 2 else ""
        )
        lang_arg = call_kwargs.kwargs.get("lang") or (
            call_kwargs.args[1] if len(call_kwargs.args) > 1 else ""
        )
        assert "--oem 1" in config_arg, f"--oem 1 not in config: {config_arg!r}"
        assert "--psm 3" in config_arg, f"--psm 3 not in config: {config_arg!r}"
        assert lang_arg == "rus+eng", f"lang must be 'rus+eng', got: {lang_arg!r}"


@pytest.mark.asyncio
async def test_fallback_on_preprocess_exception():
    with patch("services.ocr.preprocess_image", side_effect=RuntimeError("preprocess boom")):
        with patch("pytesseract.image_to_string", return_value="fallback result") as mock_ts:
            from services import ocr
            result = await ocr.recognize_text(_png_bytes())
            assert result == "fallback result", "Should return fallback OCR result"
            assert mock_ts.called, "Tesseract should still be called on fallback path"


@pytest.mark.asyncio
async def test_fallback_does_not_raise():
    with patch("services.ocr.preprocess_image", side_effect=ValueError("bad image")):
        with patch("pytesseract.image_to_string", return_value=""):
            from services import ocr
            result = await ocr.recognize_text(_png_bytes())
            assert isinstance(result, str)


@pytest.mark.asyncio
async def test_best_of_both_picks_original_when_preprocessed_worse():
    """Регрессия v0.4.0: на шумных фото предобработка может дать пусто/мусор.
    Должен вернуться более содержательный кандидат (исходное изображение)."""
    with patch("services.ocr.preprocess_image", return_value=object()):
        # порядок вызовов: 1) предобработанное (слабое), 2) исходное (сильное)
        with patch("pytesseract.image_to_string", side_effect=["", "Hello World 123"]):
            from services import ocr
            result = await ocr.recognize_text(_png_bytes())
            assert result == "Hello World 123"


@pytest.mark.asyncio
async def test_best_of_both_keeps_preprocessed_when_better():
    """Выигрыш предобработки (например, deskew) сохраняется, если она лучше."""
    with patch("services.ocr.preprocess_image", return_value=object()):
        with patch("pytesseract.image_to_string", side_effect=["Hello World 123", "ll Wld"]):
            from services import ocr
            result = await ocr.recognize_text(_png_bytes())
            assert result == "Hello World 123"


@pytest.mark.asyncio
async def test_corrupt_bytes_returns_str_never_raises():
    """recognize_text must return str and not raise on completely invalid image data."""
    from services import ocr
    result = await ocr.recognize_text(b"not an image")
    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_recognize_text_returns_str():
    with patch("pytesseract.image_to_string", return_value="hello"):
        from services import ocr
        result = await ocr.recognize_text(_png_bytes())
        assert isinstance(result, str)


@TESSERACT_SKIP
@pytest.mark.asyncio
async def test_ocr_fallback_with_real_tesseract():
    from services import ocr
    with patch("services.ocr.preprocess_image", side_effect=RuntimeError("forced failure")):
        result = await ocr.recognize_text(_png_bytes())
        assert isinstance(result, str), "recognize_text must return str even when preprocess fails"
