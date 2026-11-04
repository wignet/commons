#!/usr/bin/env python3
"""Validate the first, deliberately narrow commons scene format.

Run with Python's standard library; never execute entry files. Wignet's
device-specific dry_run remains necessary before use.
"""
import argparse
import json
import re
import sys
from pathlib import Path

MAX_SCENE_BYTES = 32_768
MAX_TEXT_BYTES = 16_384
CAPABILITIES = set()
NAME = re.compile(r'^[a-z][a-z0-9_-]{0,63}$')


def fail(message):
    raise ValueError(message)


def read_json(path, limit):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        fail(f'{path.name}: missing, symlink or too large')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                fail(f'{path.name}: duplicate key {key}')
            result[key] = value
        return result
    return json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique)


def reject_external(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if key in ('image_url', 'image_file', 'tune_name'):
                fail(f'{key}: external and device-specific sources are not allowed')
            reject_external(item)
    elif isinstance(value, list):
        for item in value:
            reject_external(item)


def validate_entry(path):
    if path.is_symlink() or not path.is_dir() or not NAME.fullmatch(path.name):
        fail('entry must be a real directory with a lowercase slug')
    if {p.name for p in path.iterdir()} != {'entry.json', 'scene.json', 'README.md'}:
        fail('entry must contain only entry.json, scene.json and README.md')
    readme = path / 'README.md'
    if readme.is_symlink() or not readme.is_file() or readme.stat().st_size > MAX_TEXT_BYTES:
        fail('README.md is missing, a symlink or too large')
    readme.read_text(encoding='utf-8')
    meta = read_json(path / 'entry.json', MAX_TEXT_BYTES)
    fields = {'name', 'description', 'use_cases', 'license', 'inputs', 'capabilities'}
    if not isinstance(meta, dict) or not fields <= set(meta) or set(meta) - fields - {'remixed_from', 'attribution'}:
        fail('entry.json must contain the required fields and optional remixed_from and attribution')
    if 'remixed_from' in meta and (not isinstance(meta['remixed_from'], str) or not
            re.fullmatch(r'[a-z][a-z0-9_-]{0,63}@[0-9a-f]{40}', meta['remixed_from'])):
        fail('remixed_from must be an entry slug followed by @ and a full lowercase commit SHA')
    if 'attribution' in meta and (not isinstance(meta['attribution'], str) or not 1 <= len(meta['attribution'].strip()) <= 200):
        fail('attribution must be a nonempty string of at most 200 characters')
    for key, size in [('name', 80), ('description', 300)]:
        if not isinstance(meta[key], str) or not 1 <= len(meta[key].strip()) <= size:
            fail(f'{key} must be a nonempty string of at most {size} characters')
    if meta['license'] not in ('CC0-1.0', 'CC-BY-4.0'):
        fail('license must be CC0-1.0 or CC-BY-4.0')
    if meta['license'] == 'CC-BY-4.0' and 'attribution' not in meta:
        fail('CC-BY-4.0 requires attribution')
    for key, limit in [('inputs', 8), ('capabilities', len(CAPABILITIES)), ('use_cases', 8)]:
        items = meta[key]
        if not isinstance(items, list) or len(items) > limit or any(not isinstance(x, str) for x in items):
            fail(f'{key} must be a bounded list of strings')
        if len(items) != len(set(items)):
            fail(f'{key} contains duplicates')
    if not meta['use_cases'] or any(not NAME.fullmatch(x) for x in meta['use_cases']):
        fail('use_cases must contain lowercase slugs')
    if set(meta['capabilities']) - CAPABILITIES:
        fail('unknown capability')
    if meta['inputs']:
        fail('device buttons are not supported by the initial commons format')
    scene = read_json(path / 'scene.json', MAX_SCENE_BYTES)
    reject_external(scene)
    validate_scene(scene)
    return meta['name']


def validate_scene(scene):
    """A closed subset of runtime 2: text or colour pages and page events."""
    if not isinstance(scene, dict) or set(scene) - {'design', 'pages', 'on', 'start'}:
        fail('scene contains unsupported fields; the initial format supports pages and events only')
    design = scene.get('design')
    if not isinstance(design, list) or len(design) != 2 or any(type(x) is not int or not 16 <= x <= 4096 for x in design):
        fail('design must contain two dimensions between 16 and 4096')
    pages = scene.get('pages')
    if not isinstance(pages, list) or not 1 <= len(pages) <= 8:
        fail('pages must contain 1 to 8 pages')
    numbers = set()
    for page in pages:
        if not isinstance(page, dict) or set(page) != {'page', 'bg'}:
            fail('each page must contain page and bg only')
        number = page['page']
        if type(number) is not int or not 1 <= number <= 99 or number in numbers:
            fail('page numbers must be unique integers from 1 to 99')
        numbers.add(number)
        bg = page['bg']
        if not isinstance(bg, dict) or len(bg) != 1:
            fail('page bg must contain text or color only')
        if 'text' in bg:
            if not isinstance(bg['text'], str) or len(bg['text']) > 1000:
                fail('page text must be at most 1000 characters')
        elif 'color' in bg:
            if not isinstance(bg['color'], str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', bg['color']):
                fail('page color must be #rrggbb')
        else:
            fail('page bg must contain text or color only')
    if 'start' in scene and (type(scene['start']) is not int or scene['start'] not in numbers):
        fail('start must identify a page')
    on = scene.get('on', {})
    if not isinstance(on, dict) or len(on) > 64:
        fail('on must be an object with at most 64 events')
    for event, action in on.items():
        if not re.fullmatch(r'event:[a-z][a-z0-9_]{0,31}', event):
            fail('only named agent events are supported')
        match = re.fullmatch(r'page ([1-9][0-9]?)', action) if isinstance(action, str) else None
        if not match or int(match.group(1)) not in numbers:
            fail('each event must switch to an existing page')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('entry', type=Path)
    args = parser.parse_args()
    try:
        print('Valid:', validate_entry(args.entry))
    except (ValueError, OSError) as exc:
        print(f'Invalid entry: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
