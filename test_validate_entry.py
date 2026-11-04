import base64
import hashlib
import io
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image
from validate_entry import validate_entry, validate_scene
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

    def test_valid_scene_is_accepted(self):
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
        with self.assertRaisesRegex(ValueError, 'cover'):
            validate_entry(self.entry)

    def test_empty_image_hash_is_refused(self):
        self.edit_scene(lambda s: s.update(assets={'x': {'image_base64': 'YQ==', 'image_sha256': '', 'frame': [1, 1]}}))
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
                                                         'image_sha256': hashlib.sha256(data).hexdigest(), 'frame': [1, 1]}}))
        with self.assertRaises(ValueError):
            validate_entry(self.entry)


class SpriteTests(EntryTests):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.entry = Path(self.temp.name) / 'agent-activity-field'
        shutil.copytree(Path(__file__).parent / 'fixtures' / 'agent-activity-field', self.entry)
        self.addCleanup(self.temp.cleanup)

    # EntryTests' assumptions are specific to activity-status, so keep only
    # sprite scenarios in this class.
    def test_valid_scene_is_accepted(self):
        self.assertEqual(validate_entry(self.entry), 'Agent activity field')

    def test_external_image_is_refused(self):
        self.edit_scene(lambda s: s['assets']['robot'].update(image_url='https://example.com/x'))
        with self.assertRaisesRegex(ValueError, 'external'):
            validate_entry(self.entry)

    def test_invalid_scene_is_refused(self):
        self.edit_scene(lambda s: s['on'].update({'event:s1_working': 'run shell'}))
        with self.assertRaisesRegex(ValueError, 'action'):
            validate_entry(self.entry)

    def test_empty_image_hash_is_refused(self):
        self.edit_scene(lambda s: s['assets']['robot'].update(image_sha256=''))
        with self.assertRaisesRegex(ValueError, 'image_sha256'):
            validate_entry(self.entry)

    def test_remix_provenance_and_attribution(self):
        path = self.entry / 'entry.json'
        meta = json.loads(path.read_text())
        meta.update(license='CC-BY-4.0', attribution='Example author', remixed_from='original@' + 'a' * 40)
        path.write_text(json.dumps(meta))
        self.assertEqual(validate_entry(self.entry), 'Agent activity field')

    def test_state_frame_out_of_range_is_refused(self):
        self.edit_scene(lambda s: s['objects'][0]['states']['working'].update(frames=[99]))
        with self.assertRaisesRegex(ValueError, 'frame'):
            validate_entry(self.entry)

    def test_checksum_mismatch_is_refused(self):
        self.edit_scene(lambda s: s['assets']['robot'].update(image_sha256='0' * 64))
        with self.assertRaisesRegex(ValueError, 'checksum'):
            validate_entry(self.entry)

    def test_waiting_pose_contains_a_visible_attention_signal(self):
        scene = json.loads((self.entry / 'scene.json').read_text())
        asset = scene['assets']['robot']
        image = Image.open(io.BytesIO(base64.b64decode(asset['image_base64']))).convert('RGBA')
        fw, fh = asset['frame']
        waiting = scene['objects'][0]['states']['waiting']['frames'][0]
        frame = image.crop((waiting * fw, 0, (waiting + 1) * fw, fh))
        self.assertIn((255, 219, 82, 255), frame.getdata())

    def test_scene_can_be_reduced_to_fewer_slots(self):
        original = (self.entry / 'scene.json').read_text()
        for slots in (1, 4, 8):
            with self.subTest(slots=slots):
                scene = json.loads(original)
                scene['objects'] = [item for item in scene['objects'] if item['id'] <= slots]
                scene['on'] = {key: value for key, value in scene['on'].items()
                               if int(key.removeprefix('event:s').split('_')[0]) <= slots}
                sheets = {item['sheet'] for item in scene['objects']}
                scene['assets'] = {name: item for name, item in scene['assets'].items()
                                   if name in sheets or name == 'robot'}
                validate_scene(scene)

    def test_decompression_bomb_is_refused(self):
        image = Image.new('RGBA', (1500, 1500), '#36b9a6')
        data = io.BytesIO()
        image.save(data, format='PNG')
        payload = data.getvalue()
        self.edit_scene(lambda s: s['assets']['robot'].update(image_base64=base64.b64encode(payload).decode(),
                                                               image_sha256=hashlib.sha256(payload).hexdigest()))
        with self.assertRaisesRegex(ValueError, 'oversized PNG'):
            validate_entry(self.entry)

    def test_derived_source_and_colour_are_verified(self):
        self.edit_scene(lambda s: s['assets']['robot2'].update(map={'#ffffff': '#111111'}))
        with self.assertRaisesRegex(ValueError, 'source colours'):
            validate_entry(self.entry)

    def test_unknown_sprite_state_is_refused(self):
        self.edit_scene(lambda s: s['on'].update({'event:s1_working': 'state 1 missing'}))
        with self.assertRaisesRegex(ValueError, 'action'):
            validate_entry(self.entry)

    def test_tune_requires_declared_capability(self):
        self.edit_scene(lambda s: (s.update(sounds={'beep': {'tune': 'A t120 o5 c8 e8 g4'}}),
                                   s['on'].update({'event:s1_done': 'state 1 done; sound beep'})))
        with self.assertRaisesRegex(ValueError, 'sound capability'):
            validate_entry(self.entry)
        path = self.entry / 'entry.json'
        meta = json.loads(path.read_text())
        meta['capabilities'] = ['sound']
        path.write_text(json.dumps(meta))
        self.assertEqual(validate_entry(self.entry), 'Agent activity field')

    def test_eight_characters_with_twenty_two_frame_sheet_and_sound(self):
        image = Image.new('RGBA', (78 * 22, 66), '#36b9a6')
        out = io.BytesIO()
        image.save(out, format='PNG')
        payload = out.getvalue()
        def change(scene):
            scene['assets']['robot'].update(image_base64=base64.b64encode(payload).decode(),
                                            image_sha256=hashlib.sha256(payload).hexdigest(), frame=[78, 66])
            scene['sounds'] = {'beep': {'tune': 'A t120 o5 c8 e8 g4'}}
            scene['on']['event:s1_done'] += '; sound beep'
        self.edit_scene(change)
        path = self.entry / 'entry.json'
        meta = json.loads(path.read_text())
        meta['capabilities'] = ['sound']
        path.write_text(json.dumps(meta))
        self.assertEqual(validate_entry(self.entry), 'Agent activity field')

    def test_normalized_mml_header_and_uppercase_notes_are_accepted(self):
        self.edit_scene(lambda s: (s.update(sounds={'beep': {'tune': '#MML1\nA T120 O5 C8 E8 G4'}}),
                                   s['on'].update({'event:s1_done': 'state 1 done; sound beep'})))
        path = self.entry / 'entry.json'
        meta = json.loads(path.read_text())
        meta['capabilities'] = ['sound']
        path.write_text(json.dumps(meta))
        self.assertEqual(validate_entry(self.entry), 'Agent activity field')


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

    def test_new_animated_field_passes_the_contribution_check(self):
        target = self.repo / 'scenes' / 'agent-activity-field'
        target.parent.mkdir(parents=True)
        shutil.copytree(Path(__file__).parent / 'fixtures' / 'agent-activity-field', target)
        self.git('add', '.')
        self.git('commit', '-qm', 'animated field')
        check(self.repo, self.base, 'HEAD')

    def test_animated_contribution_with_remote_asset_is_rejected(self):
        target = self.repo / 'scenes' / 'agent-activity-field'
        target.parent.mkdir(parents=True)
        shutil.copytree(Path(__file__).parent / 'fixtures' / 'agent-activity-field', target)
        scene_path = target / 'scene.json'
        scene = json.loads(scene_path.read_text())
        scene['assets']['robot']['image_url'] = 'https://example.com/robot.png'
        scene_path.write_text(json.dumps(scene))
        self.git('add', '.')
        self.git('commit', '-qm', 'invalid animated field')
        with self.assertRaisesRegex(ValueError, 'external'):
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
