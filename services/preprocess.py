from io import BytesIO

import cv2
import numpy as np
from PIL import Image, ImageOps

_MIN_DESKEW_ANGLE = 0.5
_PAGE_MAX_SIDE = 2000
_PAGE_UPSCALE_THRESHOLD = 1000
_PAGE_UPSCALE_TARGET = 1500
_CLAHE_CLIP_LIMIT = 2.0
_CLAHE_TILE_GRID = (8, 8)


def _load_oriented(image_bytes: bytes) -> Image.Image:
    pil_img = Image.open(BytesIO(image_bytes))
    return ImageOps.exif_transpose(pil_img)


def _resize_to_target(arr: np.ndarray, max_side: int = _PAGE_MAX_SIDE) -> np.ndarray:
    h, w = arr.shape[:2]
    current_max = max(h, w)
    if current_max > max_side:
        scale = max_side / current_max
        new_w = max(1, int(round(w * scale)))
        new_h = max(1, int(round(h * scale)))
        return cv2.resize(arr, (new_w, new_h), interpolation=cv2.INTER_AREA)
    if current_max < _PAGE_UPSCALE_THRESHOLD:
        scale = _PAGE_UPSCALE_TARGET / current_max
        new_w = max(1, int(round(w * scale)))
        new_h = max(1, int(round(h * scale)))
        return cv2.resize(arr, (new_w, new_h), interpolation=cv2.INTER_CUBIC)
    return arr


def _skew_angle(binary: np.ndarray) -> float:
    dark_pixels = np.column_stack(np.where(binary < 128))
    if dark_pixels.shape[0] < 10:
        return 0.0
    points = dark_pixels[:, ::-1].astype(np.float32)
    _, _, angle = cv2.minAreaRect(points)
    if angle < -45:
        angle += 90.0
    elif angle > 45:
        angle -= 90.0
    if abs(angle) > 15.0:
        return 0.0
    return angle


def _rotate(arr: np.ndarray, angle: float) -> np.ndarray:
    h, w = arr.shape[:2]
    center = (w / 2.0, h / 2.0)
    rotation_matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(
        arr,
        rotation_matrix,
        (w, h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=255,
    )


def render_page(image_bytes: bytes, mode: str = "doc") -> Image.Image:
    pil_img = _load_oriented(image_bytes)
    arr = np.array(pil_img.convert("L"))
    arr = _resize_to_target(arr)

    if mode == "scan":
        arr = cv2.medianBlur(arr, 3)
        arr = cv2.adaptiveThreshold(
            arr,
            255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            blockSize=31,
            C=10,
        )
        angle = _skew_angle(arr)
        if abs(angle) >= _MIN_DESKEW_ANGLE:
            arr = _rotate(arr, angle)
        return Image.fromarray(arr, mode="L")

    # mode == "doc"
    clahe = cv2.createCLAHE(clipLimit=_CLAHE_CLIP_LIMIT, tileGridSize=_CLAHE_TILE_GRID)
    arr = clahe.apply(arr)

    binary = cv2.adaptiveThreshold(
        arr,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=31,
        C=10,
    )
    angle = _skew_angle(binary)
    if abs(angle) >= _MIN_DESKEW_ANGLE:
        arr = _rotate(arr, angle)
    return Image.fromarray(arr, mode="L")


def preprocess_image(image_bytes: bytes) -> np.ndarray:
    pil_img = _load_oriented(image_bytes)
    pil_img = pil_img.convert("L")
    arr = np.array(pil_img)

    h, w = arr.shape
    max_side = max(h, w)

    if max_side > 2500:
        scale = 2500.0 / max_side
        new_w = max(1, int(round(w * scale)))
        new_h = max(1, int(round(h * scale)))
        arr = cv2.resize(arr, (new_w, new_h), interpolation=cv2.INTER_AREA)
        h, w = arr.shape
        max_side = max(h, w)

    if max_side < 1000:
        scale = 1500.0 / max_side
        new_w = max(1, int(round(w * scale)))
        new_h = max(1, int(round(h * scale)))
        arr = cv2.resize(arr, (new_w, new_h), interpolation=cv2.INTER_CUBIC)

    arr = cv2.medianBlur(arr, 3)

    arr = cv2.adaptiveThreshold(
        arr,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        blockSize=31,
        C=10,
    )

    binary = arr
    angle = _skew_angle(binary)
    arr = _rotate(arr, angle)

    return arr
