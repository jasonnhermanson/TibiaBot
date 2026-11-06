import unittest
from PIL import Image, ImageDraw
from monitor.imaging import fill_percentage


class FillTests(unittest.TestCase):
    def bar(self, percent, color=(200, 30, 30)):
        image = Image.new('RGB', (200, 20), (25, 25, 25))
        if percent:
            ImageDraw.Draw(image).rectangle((0, 0, percent * 2 - 1, 19), fill=color)
        return image

    def test_empty_partial_and_full(self):
        for percent in (0, 1, 25, 50, 73, 100):
            with self.subTest(percent=percent):
                self.assertEqual(fill_percentage(self.bar(percent), (220, 40, 40)), percent)

    def test_blue_mana_and_wrong_color(self):
        image = self.bar(64, (30, 65, 210))
        self.assertEqual(fill_percentage(image, (40, 80, 220)), 64)
        self.assertEqual(fill_percentage(image, (220, 40, 40)), 0)

    def test_gradient_with_white_text_occlusion(self):
        image = self.bar(0)
        draw = ImageDraw.Draw(image)
        for x in range(140):
            draw.line((x, 0, x, 19), fill=(80 + x, 15, 20))
        # White text-like marks obscure half the vertical pixels in some columns.
        draw.rectangle((35, 5, 100, 14), fill='white')
        self.assertEqual(fill_percentage(image, (220, 40, 40)), 70)

    def test_sparse_noise_does_not_inflate_fill(self):
        image = self.bar(30)
        for x in range(60, 200):
            image.putpixel((x, x % 20), (255, 0, 0))
        self.assertEqual(fill_percentage(image, (220, 40, 40)), 30)

    def test_red_hue_wraparound_and_rgba(self):
        self.assertEqual(fill_percentage(self.bar(45, (220, 0, 20)).convert('RGBA'), (220, 20, 0)), 45)

    def test_reject_tiny_region_and_gray_target(self):
        for image, color in [(Image.new('RGB', (1, 20)), (255, 0, 0)),
                             (self.bar(50), (120, 120, 120))]:
            with self.assertRaises(ValueError):
                fill_percentage(image, color)
