import copy
import random
import tempfile
import unittest
from pathlib import Path
from PIL import Image, ImageDraw
from monitor import routes
from monitor.vision import landmark, locate, changed_fraction
from monitor.windows import key_code


def textured_map(size=(72, 72), seed=7):
    rng = random.Random(seed)
    image = Image.new('RGB', size)
    image.putdata([tuple(rng.randrange(256) for _ in range(3)) for _ in range(size[0]*size[1])])
    return image


class VisionTests(unittest.TestCase):
    def test_recorded_landmark_is_found_after_map_scroll(self):
        world = textured_map((110, 110))
        recorded = world.crop((10, 10, 82, 82))
        patch = landmark(recorded, (36, 36))
        current = world.crop((20, 15, 92, 87))
        # Current player marker is elsewhere; recorded marker is ignored.
        ImageDraw.Draw(patch).rectangle((9, 9, 15, 15), fill='white')
        match = locate(current, patch)
        self.assertIsNotNone(match)
        self.assertEqual((match.x, match.y), (26, 31))

    def test_repeated_landmarks_are_ambiguous(self):
        patch = landmark(textured_map(), (36, 36))
        image = Image.new('RGB', (80, 40), (20, 20, 20))
        image.paste(patch, (2, 4))
        image.paste(patch, (48, 4))
        self.assertIsNone(locate(image, patch))

    def test_missing_landmark_and_featureless_map_fail_closed(self):
        patch = landmark(textured_map(), (36, 36))
        self.assertIsNone(locate(Image.new('RGB', (72, 72)), patch))
        with self.assertRaises(ValueError):
            landmark(Image.new('RGB', (72, 72)), (36, 36))
        with self.assertRaises(ValueError):
            landmark(textured_map(), (4, 4))

    def test_battle_change_detects_creatures_not_small_noise(self):
        baseline = Image.new('RGB', (100, 50), (20, 20, 20))
        current = baseline.copy()
        self.assertEqual(changed_fraction(current, baseline), 0)
        current.putpixel((0, 0), (255, 255, 255))
        self.assertLess(changed_fraction(current, baseline), .02)
        ImageDraw.Draw(current).rectangle((10, 10, 60, 20), fill='white')
        self.assertGreater(changed_fraction(current, baseline), .02)
        with self.assertRaises(ValueError):
            changed_fraction(current, Image.new('RGB', (10, 10)))


class LibraryTests(unittest.TestCase):
    def test_multiple_named_routes_and_images_round_trip(self):
        data = routes.defaults()
        point = {'image': routes.encode_image(landmark(textured_map(), (36, 36)))}
        data['routes'] = {'Rats': [point, point], 'Rotworms': [point]}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'routes.json'
            routes.save(data, path)
            restored = routes.load(path)
            self.assertEqual(restored, data)
            self.assertEqual(list(restored['routes']), ['Rats', 'Rotworms'])
            self.assertEqual(routes.decode_image(point['image']).size, (25, 25))

    def test_invalid_keys_regions_options_and_images(self):
        for key, value in [('heal_key', 'F10'), ('mana_key', 'F8'),
                           ('critical_at', float('nan')), ('key_cooldown', 0),
                           ('heal_key', 'F'), ('battle_change', 2)]:
            with self.subTest(key=key):
                data = routes.defaults()
                data['options'][key] = value
                with self.assertRaises(ValueError):
                    routes.validate(data)
        data = routes.defaults()
        data['routes'] = {'bad': [{'image': routes.encode_image(Image.new('RGB', (20, 20)))}]}
        with self.assertRaises(ValueError):
            routes.validate(data)
        self.assertEqual(key_code('f1'), 0x70)
        self.assertEqual(key_code('F'), ord('F'))
        with self.assertRaises(ValueError):
            key_code('CTRL+F')
