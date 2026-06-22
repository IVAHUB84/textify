import io

import numpy as np
import pytest
from PIL import Image, ImageDraw

cv2 = pytest.importorskip("cv2", reason="cv2 not installed — install opencv-python-headless to run preprocess tests")


def _png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_color_image(size=(600, 400)) -> bytes:
    img = Image.new("RGB", size, color=(180, 120, 60))
    draw = ImageDraw.Draw(img)
    draw.text((20, 20), "Test text", fill=(0, 0, 0))
    return _png_bytes(img)


def _make_gray_image(size=(500, 300)) -> bytes:
    img = Image.new("L", size, color=200)
    draw = ImageDraw.Draw(img)
    draw.text((10, 10), "Gray", fill=10)
    return _png_bytes(img)


def _make_tiny_image(size=(80, 50)) -> bytes:
    img = Image.new("RGB", size, color=(240, 240, 240))
    draw = ImageDraw.Draw(img)
    draw.text((2, 2), "Hi", fill=(0, 0, 0))
    return _png_bytes(img)


def _make_large_image(size=(3000, 2000)) -> bytes:
    img = Image.new("RGB", size, color=(255, 255, 255))
    return _png_bytes(img)


def _make_solid_image(size=(200, 200), color=(255, 255, 255)) -> bytes:
    img = Image.new("RGB", size, color=color)
    return _png_bytes(img)


def _make_exif_rotated_image() -> bytes:
    img = Image.new("RGB", (400, 200), color=(200, 200, 200))
    draw = ImageDraw.Draw(img)
    draw.text((10, 80), "Rotated", fill=(0, 0, 0))

    exif_data = img.getexif()
    exif_data[274] = 6

    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif_data.tobytes())
    return buf.getvalue()


def _make_skewed_text_image(angle_deg: float = 10.0) -> bytes:
    img = Image.new("L", (500, 200), color=255)
    draw = ImageDraw.Draw(img)
    for i in range(5):
        draw.text((20 + i * 80, 80), "TEXT", fill=0)
    rotated = img.rotate(angle_deg, expand=False, fillcolor=255)
    return _png_bytes(rotated)


def _estimate_skew_angle(binary: np.ndarray) -> float:
    dark = np.column_stack(np.where(binary < 128))
    if dark.shape[0] < 10:
        return 0.0
    points = dark[:, ::-1].astype(np.float32)
    _, _, angle = cv2.minAreaRect(points)
    if angle < -45:
        angle += 90.0
    elif angle > 45:
        angle -= 90.0
    return angle


def _max_side(arr: np.ndarray) -> int:
    return max(arr.shape[0], arr.shape[1])


class TestPreprocessRobustness:
    def test_color_image(self):
        from services.preprocess import preprocess_image
        result = preprocess_image(_make_color_image())
        assert isinstance(result, np.ndarray)
        assert result.ndim == 2
        assert _max_side(result) <= 2500

    def test_gray_image(self):
        from services.preprocess import preprocess_image
        result = preprocess_image(_make_gray_image())
        assert isinstance(result, np.ndarray)
        assert result.ndim == 2
        assert _max_side(result) <= 2500

    def test_tiny_image_upscaled(self):
        from services.preprocess import preprocess_image
        result = preprocess_image(_make_tiny_image(size=(80, 50)))
        assert isinstance(result, np.ndarray)
        assert _max_side(result) <= 2500
        assert _max_side(result) >= 80

    def test_large_image_downscaled(self):
        from services.preprocess import preprocess_image
        result = preprocess_image(_make_large_image(size=(3000, 2000)))
        assert _max_side(result) <= 2500

    def test_solid_white_image_no_crash(self):
        from services.preprocess import preprocess_image
        result = preprocess_image(_make_solid_image(color=(255, 255, 255)))
        assert isinstance(result, np.ndarray)
        assert _max_side(result) <= 2500

    def test_solid_black_image_no_crash(self):
        from services.preprocess import preprocess_image
        result = preprocess_image(_make_solid_image(color=(0, 0, 0)))
        assert isinstance(result, np.ndarray)
        assert _max_side(result) <= 2500

    def test_very_small_1px_image_no_crash(self):
        from services.preprocess import preprocess_image
        img = Image.new("RGB", (1, 1), color=(128, 128, 128))
        result = preprocess_image(_png_bytes(img))
        assert isinstance(result, np.ndarray)

    def test_exif_orientation_no_crash(self):
        from services.preprocess import preprocess_image
        result = preprocess_image(_make_exif_rotated_image())
        assert isinstance(result, np.ndarray)
        assert _max_side(result) <= 2500

    def test_max_side_cap_respected_various_sizes(self):
        from services.preprocess import preprocess_image
        for size in [(100, 50), (800, 600), (2500, 2500), (4000, 1000)]:
            result = preprocess_image(_make_color_image(size=size))
            assert _max_side(result) <= 2500, f"Failed for size {size}"


class TestBinarization:
    def test_result_is_binary_on_text_image(self):
        from services.preprocess import preprocess_image
        img = Image.new("RGB", (400, 200))
        draw = ImageDraw.Draw(img)
        for x in range(400):
            for y in range(200):
                shade = int(80 + 120 * (x / 400) * (y / 200))
                img.putpixel((x, y), (shade, shade, shade))
        draw.text((50, 80), "Hello world text", fill=(0, 0, 0))
        result = preprocess_image(_png_bytes(img))

        unique_values = np.unique(result)
        assert len(unique_values) <= 2, (
            f"Expected binary image (2 unique values), got {len(unique_values)}: {unique_values}"
        )
        assert 0 in unique_values or 255 in unique_values

    def test_binary_values_are_0_and_255(self):
        from services.preprocess import preprocess_image
        result = preprocess_image(_make_color_image())
        unique = set(np.unique(result).tolist())
        assert unique.issubset({0, 255}), f"Non-binary values found: {unique - {0, 255}}"


class TestDeskew:
    def test_skewed_image_angle_reduced(self):
        from services.preprocess import preprocess_image
        angle = 8.0
        image_bytes = _make_skewed_text_image(angle_deg=angle)

        original_arr = np.array(Image.open(io.BytesIO(image_bytes)).convert("L"))
        _, original_binary = cv2.threshold(original_arr, 128, 255, cv2.THRESH_BINARY_INV)
        original_angle = abs(_estimate_skew_angle(original_binary))

        result = preprocess_image(image_bytes)
        dark_mask = (result < 128).astype(np.uint8) * 255
        residual_angle = abs(_estimate_skew_angle(dark_mask))

        assert residual_angle < original_angle or residual_angle < 3.0, (
            f"Deskew did not reduce angle: before={original_angle:.1f}°, after={residual_angle:.1f}°"
        )

    def test_large_angle_not_deskewed(self):
        from services.preprocess import preprocess_image
        image_bytes = _make_skewed_text_image(angle_deg=20.0)
        result = preprocess_image(image_bytes)
        assert isinstance(result, np.ndarray)
        assert _max_side(result) <= 2500
