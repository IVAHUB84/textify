from io import BytesIO

import cv2
import numpy as np
from PIL import Image, ImageOps


def preprocess_image(image_bytes: bytes) -> np.ndarray:
    pil_img = Image.open(BytesIO(image_bytes))

    pil_img = ImageOps.exif_transpose(pil_img)

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

    arr = _deskew(arr)

    return arr


def _deskew(binary: np.ndarray) -> np.ndarray:
    dark_pixels = np.column_stack(np.where(binary < 128))

    if dark_pixels.shape[0] < 10:
        return binary

    points = dark_pixels[:, ::-1].astype(np.float32)
    _, _, angle = cv2.minAreaRect(points)

    if angle < -45:
        angle += 90.0
    elif angle > 45:
        angle -= 90.0

    if abs(angle) > 15.0:
        return binary

    h, w = binary.shape
    center = (w / 2.0, h / 2.0)
    rotation_matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(
        binary,
        rotation_matrix,
        (w, h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=255,
    )
    return rotated
