#!/usr/bin/env python3
"""Check that a PR adds complete new entries only, using trusted validator code."""
import argparse
import subprocess
import sys
from pathlib import Path

from validate_entry import NAME, validate_entry


def check(repo, base, head):
    raw = subprocess.check_output(['git', '-C', str(repo), 'diff', '--name-status', '-z',
                                   '--no-renames', base, head, '--'])
    fields = raw.decode('utf-8').split('\0')
    if fields[-1] != '' or len(fields) % 2 != 1:
        raise ValueError('unexpected git diff output')
    entries = set()
    for status, name in zip(fields[0:-1:2], fields[1:-1:2]):
        parts = name.split('/')
        if (status != 'A' or len(parts) != 3 or parts[0] != 'scenes'
                or not NAME.fullmatch(parts[1])
                or parts[2] not in ('entry.json', 'scene.json', 'README.md')):
            raise ValueError(f'only new scene entry files may be added: {name}')
        entries.add(parts[1])
    if not entries or len(entries) > 5:
        raise ValueError('a PR must add between one and five entries')
    for entry in sorted(entries):
        print('Valid:', validate_entry(repo / 'scenes' / entry))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('repo', type=Path)
    parser.add_argument('base')
    parser.add_argument('head')
    args = parser.parse_args()
    try:
        check(args.repo, args.base, args.head)
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print(f'Invalid PR: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
