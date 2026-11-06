import unittest
from unittest.mock import patch
from PIL import Image, ImageDraw
from monitor.hunting import Hunter
from monitor.routes import defaults, encode_image
from monitor.vision import Match, landmark
from test_routes_vision import textured_map


class Controls:
    def __init__(self):
        self.focus = True
        self.actions = []
    def ready(self):
        return self.focus
    def tap(self, key):
        self.actions.append(('key', key))
    def click(self, x, y):
        self.actions.append(('click', x, y))


class HuntingTests(unittest.TestCase):
    def setUp(self):
        self.controls = Controls()
        self.now = 0
        self.options = defaults()['options']
        self.options['loop'] = False
        self.bars = {'health': {'region': [0, 0, 100, 10], 'color': [220, 40, 40]},
                     'mana': {'region': [0, 10, 100, 20], 'color': [40, 80, 220]}}
        self.shot = Image.new('RGB', (140, 140), (20, 20, 20))
        draw = ImageDraw.Draw(self.shot)
        draw.rectangle((0, 0, 99, 9), fill=(220, 40, 40))
        draw.rectangle((0, 10, 99, 19), fill=(40, 80, 220))
        self.baseline = self.shot.crop((0, 100, 100, 125))
        self.point = {'image': encode_image(landmark(textured_map(), (36, 36)))}

    def hunter(self, points=None):
        return Hunter(self.controls, self.options, self.bars, [0, 25, 72, 97], [36, 36],
                      [0, 100, 100, 125], self.baseline, points or [self.point], clock=lambda: self.now)

    def low(self, name, percent):
        region = self.bars[name]['region']
        draw = ImageDraw.Draw(self.shot)
        draw.rectangle((0, region[1], 99, region[3]-1), fill=(20, 20, 20))
        if percent:
            draw.rectangle((0, region[1], percent-1, region[3]-1), fill=tuple(self.bars[name]['color']))

    @patch('monitor.hunting.locate', return_value=Match(50, 36, 0))
    def test_walk_then_reach_and_complete(self, _):
        hunter = self.hunter()
        hunter.step(self.shot)
        self.assertEqual(self.controls.actions, [('click', 50, 61)])
        self.now = 1
        hunter.step(self.shot)
        self.assertEqual(len(self.controls.actions), 1)
        with patch('monitor.hunting.locate', return_value=Match(36, 36, 0)):
            hunter.step(self.shot)
        self.assertFalse(hunter.active)
        self.assertEqual(hunter.status, 'Route complete')

    @patch('monitor.hunting.locate', return_value=Match(36, 36, 0))
    def test_loop_returns_to_first_waypoint(self, _):
        self.options['loop'] = True
        hunter = self.hunter([self.point, self.point])
        hunter.step(self.shot)
        self.assertEqual(hunter.index, 1)
        hunter.step(self.shot)
        self.assertEqual(hunter.index, 0)
        self.assertTrue(hunter.active)

    @patch('monitor.hunting.locate', return_value=Match(50, 36, 0))
    def test_combat_cancels_travel_targets_and_waits_for_clear(self, _):
        hunter = self.hunter()
        occupied = self.shot.copy()
        ImageDraw.Draw(occupied).rectangle((10, 105, 90, 115), fill='white')
        hunter.step(occupied)
        self.assertEqual(self.controls.actions, [('key', 'ESC'), ('key', 'F')])
        self.now = 2
        hunter.step(occupied)
        self.assertEqual(len(self.controls.actions), 2)
        self.now = 5
        hunter.step(occupied)
        self.assertEqual(self.controls.actions[-1], ('key', 'F'))
        self.now = 6
        hunter.step(self.shot)
        self.assertNotEqual(self.controls.actions[-1][0], 'click')
        self.now = 7.1
        hunter.step(self.shot)
        self.assertEqual(self.controls.actions[-1][0], 'click')

    @patch('monitor.hunting.locate', return_value=Match(50, 36, 0))
    def test_health_priority_cooldown_and_critical_stop(self, _):
        self.options.update(heal_enabled=True, mana_enabled=True)
        self.low('health', 40)
        self.low('mana', 10)
        hunter = self.hunter()
        hunter.step(self.shot)
        self.assertEqual(self.controls.actions[0], ('key', 'F1'))
        self.now = .5
        hunter.step(self.shot)
        self.assertIn(('key', 'F2'), self.controls.actions)
        self.now = 2.1
        self.low('health', 10)
        hunter.step(self.shot)
        self.assertFalse(hunter.active)
        self.assertIn('critical', hunter.status)
        self.assertEqual(self.controls.actions[-2:], [('key', 'F1'), ('key', 'ESC')])

    def test_disabled_healing_never_sends_resource_keys(self):
        self.low('health', 40)
        self.low('mana', 10)
        hunter = self.hunter()
        with patch('monitor.hunting.locate', return_value=Match(50, 36, 0)):
            hunter.step(self.shot)
        self.assertFalse(any(action in self.controls.actions for action in [('key', 'F1'), ('key', 'F2')]))

    def test_missing_landmark_focus_loss_and_timeout_stop(self):
        hunter = self.hunter()
        with patch('monitor.hunting.locate', return_value=None):
            hunter.step(self.shot)
        self.assertFalse(hunter.active)
        self.assertFalse(any(a[0] == 'click' for a in self.controls.actions))
        self.controls.actions.clear()
        hunter = self.hunter()
        self.controls.focus = False
        hunter.step(self.shot)
        self.assertFalse(hunter.active)
        self.assertEqual(self.controls.actions, [])
        self.controls.focus = True
        hunter = self.hunter()
        self.now = 46
        hunter.step(self.shot)
        self.assertIn('timed out', hunter.status)
        self.assertFalse(hunter.active)

    def test_stop_or_focus_loss_during_matching_prevents_click(self):
        for lose_focus in (False, True):
            with self.subTest(lose_focus=lose_focus):
                self.controls = Controls()
                hunter = self.hunter()
                def match(*args):
                    if lose_focus:
                        self.controls.focus = False
                    else:
                        hunter.stop('F10')
                    return Match(50, 36, 0)
                with patch('monitor.hunting.locate', side_effect=match):
                    hunter.step(self.shot)
                self.assertFalse(any(action[0] == 'click' for action in self.controls.actions))

    def test_actual_scrolling_map_drives_two_checkpoint_route(self):
        world = textured_map((110, 110))
        points = [{'image': encode_image(landmark(world, center))}
                  for center in [(46, 46), (56, 46)]]
        hunter = self.hunter(points)
        self.shot.paste(world.crop((0, 0, 72, 72)), (0, 25))
        hunter.step(self.shot)
        self.assertEqual(self.controls.actions[-1], ('click', 46, 71))
        self.now = 2
        self.shot.paste(world.crop((10, 10, 82, 82)), (0, 25))
        hunter.step(self.shot)
        self.assertEqual(hunter.index, 1)
        hunter.step(self.shot)
        self.assertEqual(self.controls.actions[-1], ('click', 46, 61))
        self.now = 4
        self.shot.paste(world.crop((20, 10, 92, 82)), (0, 25))
        hunter.step(self.shot)
        self.assertEqual(hunter.status, 'Route complete')
        self.assertFalse(hunter.active)

    @patch('monitor.hunting.locate', return_value=Match(50, 36, 0))
    def test_existing_sound_alert_settings_apply_during_hunt(self, _):
        self.bars['mana'].update(enabled=True, threshold=20)
        self.low('mana', 10)
        alerts = []
        hunter = self.hunter()
        hunter.alert = alerts.append
        hunter.step(self.shot)
        self.now = 1
        hunter.step(self.shot)
        self.assertEqual(alerts, ['mana'])
        self.now = 5
        hunter.step(self.shot)
        self.assertEqual(alerts, ['mana', 'mana'])
