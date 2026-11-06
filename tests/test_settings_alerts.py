import tempfile
import unittest
from pathlib import Path
from monitor import settings
from monitor.alerts import AlertGate


class SettingsTests(unittest.TestCase):
    def test_round_trip_and_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'nested' / 'settings.json'
            self.assertEqual(settings.load(path), settings.defaults())
            data = settings.defaults()
            data['health']['region'] = [10, 20, 110, 30]
            data['mana']['threshold'] = 12.5
            settings.save(data, path)
            self.assertEqual(settings.load(path), data)

    def test_invalid_saved_data_is_rejected(self):
        for field, value in [('threshold', float('nan')), ('threshold', 101),
                             ('region', [10, 5, 0, 20]), ('color', [999, 0, 0]), ('enabled', 'yes')]:
            with self.subTest(field=field, value=value):
                data = settings.defaults()
                data['health'][field] = value
                with self.assertRaises(ValueError):
                    settings.validate(data)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'settings.json'
            path.write_text('{broken', encoding='utf-8')
            with self.assertRaises(ValueError):
                settings.load(path)


class AlertTests(unittest.TestCase):
    def test_threshold_cooldown_recovery_and_independence(self):
        gate = AlertGate()
        self.assertTrue(gate.due('health', 30, 30, True, 0))
        self.assertFalse(gate.due('health', 20, 30, True, 4.9))
        self.assertTrue(gate.due('mana', 10, 20, True, 4.9))
        self.assertTrue(gate.due('health', 20, 30, True, 5))
        self.assertFalse(gate.due('health', 31, 30, True, 6))
        self.assertTrue(gate.due('health', 29, 30, True, 7))
        self.assertFalse(gate.due('health', 0, 30, False, 8))
