"""Color-based horizontal fill estimation, independent of screen capture and UI."""
import colorsys
from PIL import Image


def fill_percentage(image: Image.Image, color: tuple[int, int, int], tolerance: float = 0.10) -> float:
    """Count columns with >=25% matching pixels; tolerate text and shading.

    Region must contain only the complete horizontal bar interior. Hue matching
    ignores gray/black/white pixels and accepts brightness changes. No matching
    columns means 0%, including an empty bar. This is an estimate, not OCR.
    """
    if image.width < 2 or image.height < 2:
        raise ValueError("Select a region at least 2 by 2 pixels.")
    hue, sat, val = colorsys.rgb_to_hsv(*(c / 255 for c in color))
    if sat < 0.25 or val < 0.15:
        raise ValueError("Choose a saturated, visible bar color.")
    pixels = image.convert("RGB").load()
    filled = 0
    for x in range(image.width):
        matches = 0
        for y in range(image.height):
            h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in pixels[x, y]))
            distance = abs(h - hue)
            if min(distance, 1 - distance) <= tolerance and s >= 0.25 and v >= 0.15:
                matches += 1
        filled += matches / image.height >= 0.25
    return 100.0 * filled / image.width
