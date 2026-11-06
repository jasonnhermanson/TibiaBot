"""Validated per-user route library with embedded PNG landmarks."""
import base64
from io import BytesIO
import json
import math
from PIL import Image
from .settings import settings_path
from .vision import PATCH_SIZE


def encode_image(image):
    buffer = BytesIO()
    image.convert('RGB').save(buffer, format='PNG')
    return base64.b64encode(buffer.getvalue()).decode('ascii')


def decode_image(encoded, size=None):
    if not isinstance(encoded, str) or len(encoded) > 2_000_000:
        raise ValueError('Invalid or oversized saved image')
    with Image.open(BytesIO(base64.b64decode(encoded, validate=True))) as image:
        if image.width > 600 or image.height > 600 or (size and image.size != size):
            raise ValueError('Invalid saved image size')
        return image.convert('RGB')


def defaults():
    return {'version': 1, 'game_rect': None, 'minimap': None, 'center': None, 'battle': None,
            'empty_battle': None, 'routes': {},
            'options': {'target_key': 'F', 'heal_key': 'F1', 'mana_key': 'F2',
                        'heal_enabled': False, 'mana_enabled': False,
                        'heal_at': 45, 'mana_at': 30, 'critical_at': 15,
                        'key_cooldown': 2, 'target_interval': 5,
                        'battle_change': 0.02, 'waypoint_timeout': 45, 'loop': True}}


def validate(data):
    from .windows import key_code
    if data['version'] != 1:
        raise ValueError('Unsupported route library version')
    rect = data.get('game_rect')
    if rect is not None and (not isinstance(rect, list) or len(rect) != 4
                             or any(type(v) is not int for v in rect)
                             or rect[2] <= rect[0] or rect[3] <= rect[1]):
        raise ValueError('Invalid saved game-window layout')
    for name in ('minimap', 'battle'):
        region = data[name]
        if region is not None:
            if (not isinstance(region, list) or len(region) != 4
                or any(type(v) is not int for v in region)
                or region[0] < 0 or region[1] < 0
                or not 25 <= region[2]-region[0] <= 600
                or not 25 <= region[3]-region[1] <= 600):
                raise ValueError('Select regions between 25 and 600 pixels on each side.')
    if data['center'] is not None:
        center, region = data['center'], data['minimap']
        if (not region or not isinstance(center, list) or len(center) != 2
            or any(type(v) is not int for v in center)
            or not 12 <= center[0] < region[2]-region[0]-12
            or not 12 <= center[1] < region[3]-region[1]-12):
            raise ValueError('Player center must be inside the minimap, away from its edges.')
    if data['empty_battle'] is not None:
        region = data['battle']
        if region is None:
            raise ValueError('Missing battle region')
        decode_image(data['empty_battle'], (region[2]-region[0], region[3]-region[1]))
    routes = data['routes']
    if not isinstance(routes, dict) or len(routes) > 100:
        raise ValueError('At most 100 routes are supported')
    for name, points in routes.items():
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
            raise ValueError('Route name must contain 1–80 characters')
        if not isinstance(points, list) or len(points) > 500:
            raise ValueError('At most 500 checkpoints per route')
        for point in points:
            decode_image(point['image'], (PATCH_SIZE, PATCH_SIZE))
    options = data['options']
    codes = []
    for field in ('target_key', 'heal_key', 'mana_key'):
        code = key_code(options[field])
        if code in (key_code('F8'), key_code('F10'), key_code('ESC')):
            raise ValueError('F8, F10 and ESC are reserved for recording/stopping.')
        codes.append(code)
    if len(set(codes)) != 3:
        raise ValueError('Target, healing and mana keys must differ.')
    for field in ('heal_enabled', 'mana_enabled', 'loop'):
        if type(options[field]) is not bool:
            raise ValueError('Invalid toggle')
    limits = {'heal_at': (0, 100), 'mana_at': (0, 100), 'critical_at': (0, 100),
              'key_cooldown': (0.5, 30), 'target_interval': (1, 30),
              'battle_change': (0.001, 0.5), 'waypoint_timeout': (5, 300)}
    for field, (low, high) in limits.items():
        value = options[field]
        if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f'{field} must be between {low} and {high}')
    return data


def load(path=None):
    path = path or settings_path().with_name('routes.json')
    if not path.exists():
        return defaults()
    if path.stat().st_size > 20_000_000:
        raise ValueError('Route library is too large')
    return validate(json.loads(path.read_text(encoding='utf-8')))


def save(data, path=None):
    validate(data)
    path = path or settings_path().with_name('routes.json')
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, indent=2), encoding='utf-8')
    temporary.replace(path)
