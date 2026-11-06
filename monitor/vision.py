"""Small minimap landmark matcher. No game memory or external CV dependency."""
from dataclasses import dataclass
import math
from PIL import Image, ImageChops, ImageStat

PATCH_SIZE = 25


@dataclass(frozen=True)
class Match:
    x: int
    y: int
    error: float


def landmark(image, center):
    """Record map surrounding the player, omitting the moving center marker later."""
    x, y = center
    radius = PATCH_SIZE // 2
    if x - radius < 0 or y - radius < 0 or x + radius >= image.width or y + radius >= image.height:
        raise ValueError('Player center must be at least 13 pixels from the minimap edges.')
    patch = image.convert('RGB').crop((x-radius, y-radius, x+radius+1, y+radius+1))
    if max(ImageStat.Stat(patch, mask=_mask()).stddev) < 12:
        raise ValueError('This map landmark has too little detail. Move to a more distinctive location.')
    return patch


def _mask():
    mask = Image.new('L', (PATCH_SIZE, PATCH_SIZE), 255)
    from PIL import ImageDraw
    ImageDraw.Draw(mask).rectangle((8, 8, 16, 16), fill=0)
    return mask


def locate(image, patch, max_error=18, ambiguity_margin=3):
    """Find a unique matching landmark or return None.

    Search is exhaustive over candidate centers with sparse sampling, followed
    by dense verification of the best candidates. The center 9x9 marker area
    is ignored. Repeated terrain is rejected when distinct locations tie.
    Same zoom/floor/theme is required. All coordinates are image-local.
    """
    image, patch = image.convert('RGB'), patch.convert('RGB')
    if patch.size != (PATCH_SIZE, PATCH_SIZE):
        raise ValueError('Invalid landmark dimensions')
    if max(ImageStat.Stat(patch, mask=_mask()).stddev) < 12:
        return None
    if image.width < PATCH_SIZE or image.height < PATCH_SIZE:
        return None
    samples = [(x, y) for y in range(0, PATCH_SIZE, 4) for x in range(0, PATCH_SIZE, 4)
               if not (8 <= x <= 16 and 8 <= y <= 16)]
    source, target = image.load(), patch.load()
    wanted = [(x, y, target[x, y]) for x, y in samples]
    candidates = []
    # Keep all candidates whose sparse error is plausible, then verify the best 80.
    for top in range(image.height - PATCH_SIZE + 1):
        for left in range(image.width - PATCH_SIZE + 1):
            error = 0
            for x, y, rgb in wanted:
                value = source[left+x, top+y]
                error += sum(abs(a-b) for a, b in zip(value, rgb))
            error /= len(wanted) * 3
            candidates.append((error, left, top))
    candidates.sort()
    verified = []
    mask = _mask()
    for _, left, top in candidates[:80]:
        crop = image.crop((left, top, left+PATCH_SIZE, top+PATCH_SIZE))
        error = sum(ImageStat.Stat(ImageChops.difference(crop, patch), mask=mask).mean) / 3
        verified.append(Match(left+12, top+12, error))
    verified.sort(key=lambda match: match.error)
    if not verified or verified[0].error > max_error:
        return None
    best = verified[0]
    for other in verified[1:]:
        if math.hypot(other.x-best.x, other.y-best.y) > 5:
            if other.error - best.error < ambiguity_margin:
                return None
            break
    return best


def changed_fraction(image, baseline, pixel_difference=35):
    """Fraction of battle-list pixels changed significantly from its empty state."""
    if image.size != baseline.size:
        raise ValueError('Battle-list dimensions changed; select it again.')
    diff = ImageChops.difference(image.convert('RGB'), baseline.convert('RGB'))
    changed = sum(max(pixel) > pixel_difference for pixel in diff.getdata())
    return changed / (image.width * image.height)
