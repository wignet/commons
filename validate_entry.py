#!/usr/bin/env python3
"""Validate one commons entry using a trusted Wignet checkout.

Run with PYTHONPATH pointing to Wignet; never execute files from the entry.
The final dry_run against a physical device is still required.
"""
import argparse
import json
import re
import sys
from pathlib import Path

from backoffice import scenes
from backoffice.publications import PublicationError, acquire

MAX_SCENE_BYTES = 3_000_000
MAX_TEXT_BYTES = 16_384
CAPABILITIES = {'motion', 'touch', 'sound', 'tone', 'power_short', 'i4', 'battery'}
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
    if any(not scenes.INPUT_NAME.fullmatch(x) or x in scenes.RESERVED_INPUTS for x in meta['inputs']):
        fail('invalid input name')
    scene = read_json(path / 'scene.json', MAX_SCENE_BYTES)
    reject_external(scene)
    cover = scene.get('cover') if isinstance(scene, dict) else None
    if isinstance(cover, dict) and 'icon' in cover and not isinstance(cover['icon'], str):
        fail('cover.icon must refer to an asset, not inline image data')
    caps = {'runtime': 2, 'inputs': meta['inputs'], 'gestures': list(scenes.GESTURES),
            'limits': dict(scenes.LIMITS), **{name: name in meta['capabilities'] for name in CAPABILITIES}}
    normalized = scenes.validate(scene, caps, 320, 240)
    images = {}
    for name, asset in normalized['assets'].items():
        if 'from' not in asset:
            if ('image_base64' not in asset or not isinstance(asset.get('image_sha256'), str)
                    or not re.fullmatch(r'[0-9a-f]{64}', asset['image_sha256'])):
                fail(f'asset {name} requires image_base64 and image_sha256')
            images[name] = acquire({key: asset[key] for key in ('image_base64', 'image_sha256')})
    # Compile for one representative RGB device: each target still needs its own dry_run.
    scenes.compile_scene(normalized, images, {'reported_caps': '[]', 'params': '{}'}, 'rgb', 320, 240, 0)
    return meta['name']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('entry', type=Path)
    args = parser.parse_args()
    try:
        print('Valid:', validate_entry(args.entry))
    except (ValueError, OSError, PublicationError) as exc:
        print(f'Invalid entry: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
