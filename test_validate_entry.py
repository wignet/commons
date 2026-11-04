import base64
import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from validate_entry import validate_entry
from check_changes import check


class EntryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.entry = Path(self.temp.name) / 'activity-status'
        shutil.copytree(Path(__file__).parent / 'scenes' / 'activity-status', self.entry)
        self.addCleanup(self.temp.cleanup)

    def edit_scene(self, change):
        path = self.entry / 'scene.json'
        scene = json.loads(path.read_text())
        change(scene)
        path.write_text(json.dumps(scene))

    def test_valid_scene_compiles(self):
        self.assertEqual(validate_entry(self.entry), 'Activity status')

    def test_external_image_is_refused(self):
        self.edit_scene(lambda s: s.update(assets={'x': {'image_url': 'https://example.com/x'}}))
        with self.assertRaisesRegex(ValueError, 'external'):
            validate_entry(self.entry)

    def test_invalid_scene_is_refused(self):
        self.edit_scene(lambda s: s['on'].update({'event:working': 'run shell'}))
        with self.assertRaises(ValueError):
            validate_entry(self.entry)

    def test_inline_cover_is_refused(self):
        self.edit_scene(lambda s: s.update(cover={'name': 'Demo', 'icon': {'image_base64': 'invalid'}}))
        with self.assertRaisesRegex(ValueError, 'cover.icon'):
            validate_entry(self.entry)

    def test_empty_image_hash_is_refused(self):
        self.edit_scene(lambda s: s.update(assets={'x': {'image_base64': 'YQ==', 'image_sha256': ''}},
                                           pages=[{'page': 1, 'bg': {'image': 'x'}}], on={}))
        with self.assertRaisesRegex(ValueError, 'image_sha256'):
            validate_entry(self.entry)

    def test_remix_provenance_and_attribution(self):
        path = self.entry / 'entry.json'
        meta = json.loads(path.read_text())
        meta.update(license='CC-BY-4.0', attribution='Example author', remixed_from='original@' + 'a' * 40)
        path.write_text(json.dumps(meta))
        self.assertEqual(validate_entry(self.entry), 'Activity status')
        meta.pop('attribution')
        path.write_text(json.dumps(meta))
        with self.assertRaisesRegex(ValueError, 'attribution'):
            validate_entry(self.entry)

    def test_unknown_files_and_symlinks_are_refused(self):
        (self.entry / 'script.py').write_text('print(1)')
        with self.assertRaisesRegex(ValueError, 'only'):
            validate_entry(self.entry)
        (self.entry / 'script.py').unlink()
        (self.entry / 'README.md').unlink()
        (self.entry / 'README.md').symlink_to('/etc/passwd')
        with self.assertRaisesRegex(ValueError, 'symlink'):
            validate_entry(self.entry)

    def test_invalid_image_is_refused(self):
        data = b'not an image'
        self.edit_scene(lambda s: s.update(assets={'x': {'image_base64': base64.b64encode(data).decode(),
                                                         'image_sha256': hashlib.sha256(data).hexdigest()}},
                                           pages=[{'page': 1, 'bg': {'image': 'x'}}], on={}))
        with self.assertRaises(ValueError):
            validate_entry(self.entry)


class ChangeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.git('init', '-q')
        self.git('config', 'user.name', 'Test')
        self.git('config', 'user.email', 'test@example.invalid')
        (self.repo / 'README.md').write_text('trusted')
        self.git('add', '.')
        self.git('commit', '-qm', 'base')
        self.base = self.git('rev-parse', 'HEAD').strip()

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.repo), *args], text=True)

    def commit_entry(self):
        target = self.repo / 'scenes' / 'activity-status'
        target.parent.mkdir(parents=True)
        shutil.copytree(Path(__file__).parent / 'scenes' / 'activity-status', target)
        self.git('add', '.')
        self.git('commit', '-qm', 'entry')

    def test_new_entry_passes(self):
        self.commit_entry()
        check(self.repo, self.base, 'HEAD')

    def test_changes_to_trusted_validator_are_rejected(self):
        self.commit_entry()
        (self.repo / 'validate_entry.py').write_text('print("bypass")')
        self.git('add', '.')
        self.git('commit', '-qm', 'attempt bypass')
        with self.assertRaisesRegex(ValueError, 'only new scene'):
            check(self.repo, self.base, 'HEAD')

if __name__ == '__main__':
    unittest.main()
