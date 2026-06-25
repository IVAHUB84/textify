import asyncio
import logging
from io import BytesIO

import pytesseract
from PIL import Image

from services import HEAVY_LOCAL_SEMAPHORE
from services.preprocess import preprocess_image, render_page

logger = logging.getLogger(__name__)


_LANG = "rus+eng"
_CONFIG = "--oem 1 --psm 3"
_PAGE_JPEG_QUALITY = 75
_PAGE_DPI = (200, 200)

# Гейт качества OCR. Иконки/UI-элементы (сердечки, значок Wi-Fi, батарея) — это не текст,
# но Tesseract всё равно пытается их «прочитать» и выдаёт мусорные наборы символов.
# Отсекаем по уверенности: учитываем только слова с conf >= _MIN_WORD_CONF и хотя бы двумя
# буквенно-цифровыми символами (одиночные символы — типичный артефакт иконок). Если такого
# уверенного текста почти нет — считаем, что осмысленного текста на картинке нет, и
# возвращаем "" (хендлер покажет «текст не распознан»), не пропуская мусор дальше в LLM.
_MIN_WORD_CONF = 50.0
_MIN_CONFIDENT_ALNUM = 3


def _ocr_candidate(image: object) -> tuple[str, int]:
    """Один проход Tesseract: возвращает (текст из уверенных слов, число буквенно-цифровых
    символов в них). Текст реконструируется из image_to_data по строкам."""
    data = pytesseract.image_to_data(
        image, lang=_LANG, config=_CONFIG, output_type=pytesseract.Output.DICT
    )
    lines: dict[tuple[int, int, int], list[str]] = {}
    confident_alnum = 0
    for i in range(len(data["text"])):
        word = data["text"][i].strip()
        if not word:
            continue
        try:
            conf = float(data["conf"][i])
        except (TypeError, ValueError):
            conf = -1.0
        alnum = sum(ch.isalnum() for ch in word)
        if conf < _MIN_WORD_CONF or alnum < 2:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        lines.setdefault(key, []).append(word)
        confident_alnum += alnum
    text = "\n".join(" ".join(words) for _, words in sorted(lines.items()))
    return text, confident_alnum


def _run_ocr(image_bytes: bytes) -> str:
    # Run OCR on two candidates and keep the stronger one. Preprocessing
    # (deskew/binarize) helps skewed scans but can hurt noisy photos — on such
    # inputs the binarized image may yield empty/garbled text. Recognizing the
    # plain grayscale original as well guarantees we are never worse than the
    # v0.2.0 baseline; we pick the candidate with more confident alphanumeric text.
    candidates: list[tuple[str, int]] = []

    try:
        preprocessed = preprocess_image(image_bytes)
        candidates.append(_ocr_candidate(preprocessed))
    except Exception:
        logger.exception("Preprocessing/OCR failed; relying on original image")

    try:
        original = Image.open(BytesIO(image_bytes)).convert("L")
        candidates.append(_ocr_candidate(original))
    except Exception:
        logger.exception("OCR on original image failed")

    if not candidates:
        return ""

    text, score = max(candidates, key=lambda c: c[1])
    if score < _MIN_CONFIDENT_ALNUM:
        logger.info(
            "OCR output below quality gate (confident alnum=%d); treating as no text",
            score,
        )
        return ""
    return text


async def recognize_text(image_bytes: bytes) -> str:
    async with HEAVY_LOCAL_SEMAPHORE:
        result: str = await asyncio.to_thread(_run_ocr, image_bytes)
    return result


def _run_ocr_pdf(image_bytes: bytes, mode: str = "doc") -> bytes | None:
    """Searchable PDF: очищенная страница + невидимый текстовый слой от Tesseract.

    При сбое рендера деградирует к оригинальному изображению (поведение v1.6.0).
    Если и fallback падает — возвращает None.
    """
    try:
        page = render_page(image_bytes, mode)
        buf = BytesIO()
        # convert("L") — страховка на случай будущего цветного doc-режима; сейчас render_page всегда "L"
        page.convert("L").save(buf, format="JPEG", quality=_PAGE_JPEG_QUALITY, dpi=_PAGE_DPI)
        buf.seek(0)
        jpeg_page = Image.open(buf)
        jpeg_page.load()
        pdf = pytesseract.image_to_pdf_or_hocr(
            jpeg_page, lang=_LANG, config=_CONFIG, extension="pdf"
        )
        if not pdf:
            raise ValueError("empty PDF from Tesseract")
        return bytes(pdf)
    except Exception:
        logger.warning("PDF render failed, falling back to original image", exc_info=True)

    try:
        original = Image.open(BytesIO(image_bytes))
        pdf = pytesseract.image_to_pdf_or_hocr(
            original, lang=_LANG, config=_CONFIG, extension="pdf"
        )
        return bytes(pdf) if pdf else None
    except Exception:
        logger.exception("PDF fallback on original image also failed")
        return None


async def recognize_pdf(image_bytes: bytes, mode: str = "doc") -> bytes | None:
    async with HEAVY_LOCAL_SEMAPHORE:
        return await asyncio.to_thread(_run_ocr_pdf, image_bytes, mode)
