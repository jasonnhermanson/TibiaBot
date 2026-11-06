"""Screen-driven hunting state machine. Input adapter and clock are injectable."""
import math
import threading
import time
from .alerts import AlertGate
from .imaging import fill_percentage
from .routes import decode_image
from .vision import changed_fraction, locate


class Hunter:
    def __init__(self, controls, options, bars, minimap, center, battle, baseline, points, clock=time.monotonic, alert=None):
        self.controls = controls
        self.options = dict(options)
        self.bars = bars
        self.minimap, self.center = minimap, center
        self.battle, self.baseline = battle, baseline
        self.points = [decode_image(point['image'], (25, 25)) for point in points]
        if not self.points:
            raise ValueError('Record at least one checkpoint first.')
        self.clock = clock
        self.alert = alert
        self.alert_gate = AlertGate()
        self.input_lock = threading.RLock()
        self.active = True
        self.index = 0
        self.last = {}
        self.status = 'Starting'
        self.combat = False
        self.clear_since = None
        self.travel_time = 0
        self.previous = clock()
        self.last_click = -float('inf')

    def stop(self, reason='Stopped', cancel_walk=True):
        with self.input_lock:
            was_active = self.active
            self.active = False
            self.status = reason
            if was_active and cancel_walk and self.controls.ready():
                try:
                    self.controls.tap('ESC')
                except Exception:
                    pass

    def tap(self, key):
        with self.input_lock:
            if self.active and self.controls.ready():
                self.controls.tap(key)

    def due(self, action, now, cooldown):
        if now - self.last.get(action, -float('inf')) >= cooldown:
            self.last[action] = now
            return True
        return False

    def step(self, shot):
        if not self.active:
            return
        if not self.controls.ready():
            self.stop('Stopped: game lost focus, moved, or closed.', cancel_walk=False)
            return
        now = self.clock()
        elapsed = max(0, now - self.previous)
        self.previous = now
        for region in (self.minimap, self.battle, *(bar['region'] for bar in self.bars.values())):
            if not region or region[0] < 0 or region[1] < 0 or region[2] > shot.width or region[3] > shot.height:
                self.stop('Stopped: screen layout changed; reselect regions.')
                return
        percentages = {name: fill_percentage(shot.crop(bar['region']), tuple(bar['color']))
                       for name, bar in self.bars.items()}
        if self.alert:
            for name, value in percentages.items():
                bar = self.bars[name]
                if self.alert_gate.due(name, value, bar.get('threshold', 0), bar.get('enabled', False), now):
                    self.alert(name)
        options = self.options
        # Health always takes priority; at most one resource key per step.
        if (options['heal_enabled'] and percentages['health'] <= options['heal_at']
            and self.due('heal', now, options['key_cooldown'])):
            self.tap(options['heal_key'])
        elif (options['mana_enabled'] and percentages['mana'] <= options['mana_at']
              and self.due('mana', now, options['key_cooldown'])):
            self.tap(options['mana_key'])
        if percentages['health'] <= options['critical_at']:
            self.stop('Stopped: critical health. Take control manually.')
            return
        occupied = changed_fraction(shot.crop(self.battle), self.baseline) >= options['battle_change']
        if occupied:
            self.clear_since = None
            if not self.combat:
                self.tap('ESC')  # Cancel minimap walking before attacking.
                self.last.pop('target', None)
            self.combat = True
            if self.due('target', now, options['target_interval']):
                self.tap(options['target_key'])
            self.status = f'Fighting near checkpoint {self.index+1}/{len(self.points)}'
            return
        if self.combat:
            if self.clear_since is None:
                self.clear_since = now
            if now - self.clear_since < 1:
                self.status = 'Waiting for battle list to remain empty'
                return
            self.combat = False
            self.last_click = -float('inf')
        self.travel_time += elapsed
        if self.travel_time > options['waypoint_timeout']:
            self.stop('Stopped: checkpoint timed out (blocked path or stuck).')
            return
        # Matching can take time; input must be checked again after it returns.
        match = locate(shot.crop(self.minimap), self.points[self.index])
        if not self.active:
            return
        if not self.controls.ready():
            self.stop('Stopped: game lost focus or moved.', cancel_walk=False)
            return
        if match is None:
            self.stop('Stopped: next checkpoint is not visible or not unique. Move closer; verify map zoom/floor.')
            return
        if math.hypot(match.x-self.center[0], match.y-self.center[1]) <= 3:
            self.index += 1
            self.travel_time = 0
            self.last_click = -float('inf')
            if self.index == len(self.points):
                if options['loop']:
                    self.index = 0
                else:
                    self.stop('Route complete')
                    return
            self.status = f'Checkpoint reached; next {self.index+1}/{len(self.points)}'
            return
        if now - self.last_click >= 2:
            with self.input_lock:
                if self.active:
                    self.controls.click(self.minimap[0]+match.x, self.minimap[1]+match.y)
                    self.last_click = now
        self.status = f'Walking to checkpoint {self.index+1}/{len(self.points)}'
