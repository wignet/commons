"""Closed, bounded validation of reusable runtime-2 sprite scenes.

This checks the public interchange format without executing contribution
files. Wignet's dry_run is the authoritative device-specific compiler check.
"""
import base64
import binascii
import hashlib
import io
import re
import warnings

from PIL import Image, UnidentifiedImageError

Image.MAX_IMAGE_PIXELS = 2_000_000
NAME = re.compile(r'^[a-z][a-z0-9_]{0,23}$')
EVENT = re.compile(r'^event:[a-z][a-z0-9_]{0,31}$')
COLOR = re.compile(r'^#[a-fA-F0-9]{6}$')
ANCHORS = {'top-left', 'top', 'top-right', 'left', 'center', 'right', 'bottom-left', 'bottom', 'bottom-right'}
MAX_IMAGE_BYTES = 1_000_000


def fail(message):
    raise ValueError(message)


def obj(value, keys, label, required=()):
    if not isinstance(value, dict) or set(value) - set(keys) or set(required) - set(value):
        fail(f'{label}: invalid or missing fields')
    return value


def integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        fail(f'{label}: expected an integer from {low} to {high}')
    return value


def check_name(value, label):
    if not isinstance(value, str) or not NAME.fullmatch(value):
        fail(f'{label}: invalid name')


def place(value, label, area=False):
    allowed = {'anchor', 'x', 'y', 'w', 'h'} if area else {'anchor', 'x', 'y', 'wander'}
    obj(value, allowed, label)
    if 'anchor' in value and (not isinstance(value['anchor'], str) or value['anchor'] not in ANCHORS):
        fail(f'{label}: invalid anchor')
    for key in ('x', 'y'):
        if key in value:
            integer(value[key], -4096, 4096, f'{label}.{key}')
    if area:
        for key in ('w', 'h'):
            integer(value.get(key), 1, 4096, f'{label}.{key}')


def image_data(item, label):
    encoded, digest = item.get('image_base64'), item.get('image_sha256')
    if not isinstance(encoded, str) or len(encoded) > MAX_IMAGE_BYTES * 2:
        fail(f'{label}: invalid or oversized base64 image')
    if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest):
        fail(f'{label}: image_sha256 must be a lowercase SHA-256')
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        fail(f'{label}: invalid base64 image')
    if not data or len(data) > MAX_IMAGE_BYTES or hashlib.sha256(data).hexdigest() != digest:
        fail(f'{label}: image is too large or checksum does not match')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                if image.format != 'PNG' or getattr(image, 'n_frames', 1) != 1:
                    fail(f'{label}: only single-frame PNG sprite sheets are supported')
                image.load()
                return image.convert('RGBA')
    except (OSError, SyntaxError, ValueError, UnidentifiedImageError,
            Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        fail(f'{label}: invalid or oversized PNG ({exc})')


def validate_assets(raw):
    if not isinstance(raw, dict) or len(raw) > 12:
        fail('assets: expected at most 12 assets')
    assets = {}
    total_pixels = 0
    for name, item in raw.items():
        check_name(name, 'asset')
        obj(item, {'image_base64', 'image_sha256', 'frame', 'pixel', 'from', 'map'}, f'assets.{name}')
        if 'from' in item:
            if set(item) != {'from', 'map'}:
                fail(f'assets.{name}: a colour variant needs only from and map')
            check_name(item['from'], f'assets.{name}.from')
            mapping = item['map']
            if not isinstance(mapping, dict) or not 1 <= len(mapping) <= 12:
                fail(f'assets.{name}.map: expected 1 to 12 colours')
            if any(not isinstance(k, str) or not isinstance(v, str) or not COLOR.fullmatch(k) or
                   not COLOR.fullmatch(v) for k, v in mapping.items()):
                fail(f'assets.{name}.map: colours must be #rrggbb')
            assets[name] = {'from': item['from'], 'map': mapping}
            continue
        if set(item) - {'image_base64', 'image_sha256', 'frame', 'pixel'}:
            fail(f'assets.{name}: invalid fields')
        frame = item.get('frame')
        if not isinstance(frame, list) or len(frame) != 2:
            fail(f'assets.{name}.frame: expected [width, height]')
        fw, fh = [integer(x, 1, 128, f'assets.{name}.frame') for x in frame]
        if 'pixel' in item and type(item['pixel']) is not bool:
            fail(f'assets.{name}.pixel: expected true or false')
        image = image_data(item, f'assets.{name}')
        total_pixels += image.width * image.height
        if total_pixels > 2_000_000:
            fail('assets: decoded sprite sheets exceed the total pixel limit')
        if image.width % fw or image.height % fh or not 1 <= (image.width // fw) * (image.height // fh) <= 64:
            fail(f'assets.{name}: sprite sheet must contain 1 to 64 complete frames')
        # Wignet compares colours in RGB565; transparent pixels do not count.
        colours = {((r & 248) << 8) | ((g & 252) << 3) | (b >> 3)
                   for r, g, b, a in image.getdata() if a}
        assets[name] = {'frame': frame, 'frames': (image.width // fw) * (image.height // fh), 'colours': colours}
    for name, item in assets.items():
        if 'from' not in item:
            continue
        source = assets.get(item['from'])
        if source is None or 'from' in source:
            fail(f'assets.{name}.from: source must be a direct sprite sheet')
        converted = []
        for colour in item['map']:
            rgb = tuple(int(colour[i:i + 2], 16) for i in (1, 3, 5))
            converted.append(((rgb[0] & 248) << 8) | ((rgb[1] & 252) << 3) | (rgb[2] >> 3))
        if len(converted) != len(set(converted)) or any(c not in source['colours'] for c in converted):
            fail(f'assets.{name}.map: source colours must exist and be distinct in RGB565')
        item.update(frame=source['frame'], frames=source['frames'])
    return assets


def validate_objects(raw, assets, pages):
    if not isinstance(raw, list) or len(raw) > 16:
        fail('objects: expected at most 16 objects')
    result = {}
    for item in raw:
        obj(item, {'page', 'id', 'obj', 'sheet', 'anchor', 'x', 'y', 'hidden', 'states', 'state', 'do',
                   'portrait', 'landscape'}, 'sprite', {'page', 'id', 'obj', 'sheet', 'states'})
        identifier = integer(item['id'], 1, 99, 'sprite.id')
        if identifier in result or type(item['page']) is not int or item['page'] not in pages or item['obj'] != 'sprite':
            fail('sprite: duplicate id, unknown page or unsupported object type')
        sheet = assets.get(item['sheet']) if isinstance(item['sheet'], str) else None
        if sheet is None:
            fail('sprite.sheet: unknown asset')
        place({k: item[k] for k in ('anchor', 'x', 'y') if k in item}, 'sprite')
        if 'hidden' in item and type(item['hidden']) is not bool:
            fail('sprite.hidden must be true or false')
        states = item['states']
        if not isinstance(states, dict) or not 1 <= len(states) <= 16:
            fail('sprite.states: expected 1 to 16 states')
        for name, state in states.items():
            check_name(name, 'sprite state')
            obj(state, {'frames', 'ms', 'for', 'then'}, 'sprite state', {'frames'})
            frames = state['frames']
            if not isinstance(frames, list) or not 1 <= len(frames) <= 32:
                fail('sprite state: expected 1 to 32 frames')
            for frame in frames:
                integer(frame, 0, sheet['frames'] - 1, 'sprite state frame')
            integer(state.get('ms', 200), 20, 10000, 'sprite state ms')
            if 'for' in state:
                integer(state['for'], 100, 600000, 'sprite state for')
                if not isinstance(state.get('then'), str) or state['then'] not in states:
                    fail('sprite state then must name a state')
            elif 'then' in state:
                fail('sprite state then requires for')
        if 'state' in item and (not isinstance(item['state'], str) or item['state'] not in states):
            fail('sprite.state must name a state')
        do = item.get('do')
        if do is not None:
            obj(do, {'wander', 'speed', 'avoid'}, 'sprite.do', {'wander'})
            place(do['wander'], 'sprite.do.wander', area=True)
            if 'speed' in do:
                integer(do['speed'], 1, 400, 'sprite.do.speed')
            if 'avoid' in do:
                avoid = do['avoid']
                if avoid is not True:
                    if not isinstance(avoid, list) or len(avoid) != 4 or any(type(x) is not int for x in avoid):
                        fail('sprite.do.avoid: expected true or a frame rectangle')
                    x, y, w, h = avoid
                    if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > sheet['frame'][0] or y + h > sheet['frame'][1]:
                        fail('sprite.do.avoid must fit the frame')
        for shape in ('portrait', 'landscape'):
            if shape in item:
                place(item[shape], f'sprite.{shape}')
                if 'wander' in item[shape]:
                    if do is None:
                        fail(f'sprite.{shape}.wander needs do.wander')
                    if not isinstance(item[shape]['wander'], dict):
                        fail(f'sprite.{shape}.wander must be an object')
                    combined = {**do['wander'], **item[shape]['wander']}
                    place(combined, f'sprite.{shape}.wander', area=True)
        result[identifier] = item
    return result


def validate_actions(on, pages, objects, sounds):
    if not isinstance(on, dict) or len(on) > 64:
        fail('on: expected at most 64 events')
    for event, actions in on.items():
        if not EVENT.fullmatch(event) or not isinstance(actions, str):
            fail('on: expected named agent events with action strings')
        parts = [part.strip() for part in actions.split(';') if part.strip()]
        if not 1 <= len(parts) <= 4:
            fail('on: each event must have 1 to 4 actions')
        for part in parts:
            tokens = part.split()
            op, args = tokens[0], tokens[1:]
            if op == 'page' and len(args) == 1 and (args[0] in ('next', 'prev') or
                    (args[0].isdigit() and int(args[0]) in pages)):
                continue
            if op == 'sound' and len(args) == 1 and args[0] in sounds:
                continue
            if op == 'end' and not args:
                continue
            if not args or not args[0].isdigit() or int(args[0]) not in objects:
                fail(f'on: invalid action {part!r}')
            sprite = objects[int(args[0])]
            if op == 'state' and len(args) == 2 and args[1] in sprite['states']:
                continue
            if op == 'wander' and len(args) == 2 and args[1] in ('on', 'off') and 'do' in sprite:
                continue
            if op in ('show', 'hide') and len(args) == 1:
                continue
            if op == 'move' and len(args) in (3, 4):
                if len(args) == 4 and args[1] not in ANCHORS:
                    fail(f'on: invalid move anchor in {part!r}')
                if all(re.fullmatch(r'-?[0-9]{1,4}', x) and abs(int(x)) <= 4096 for x in args[-2:]):
                    continue
            fail(f'on: invalid or unsupported action {part!r}')
