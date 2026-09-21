"""Focused successor refusal tests. No model data or fixture-authored PASS archive."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1] / 'glm53_flash/router_caller'


def module(name):
    spec = importlib.util.spec_from_file_location('tested_' + name, ROOT / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


guard = module('successor_guard')
entry = module('successor')
supervisor = module('successor_supervisor')
archive = module('rc_archive')


class RefusalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='flash-successor-', dir=Path(tempfile.gettempdir()).resolve())
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_missing_alias_and_escape_are_refused(self):
        target = self.root / 'target'; target.write_bytes(b'known')
        alias = self.root / 'alias'; alias.symlink_to(target)
        owned = self.root / 'owned'; owned.mkdir()
        for path in (alias, self.root / 'absent'):
            with self.subTest(kind=path.name), self.assertRaises((guard.AdmissionError, FileNotFoundError)):
                guard.read(path)
        with self.assertRaises(guard.AdmissionError):
            guard.confined(owned, target)
        for name in ('../escape', '/absolute', 'a//b', './a', 'a\\b'):
            with self.assertRaises(guard.AdmissionError):
                guard.relative(name)

    def test_size_is_checked_before_payload_allocation(self):
        path = self.root / 'large'
        with path.open('wb') as stream:
            stream.truncate(archive.BODY_CAP + 1)
        with mock.patch.object(os, 'fdopen', side_effect=AssertionError('payload opened before size refusal')):
            with self.assertRaisesRegex(archive.ArchiveError, 'READ_SIZE_TYPE'):
                archive.bounded_read(path, archive.BODY_CAP)
            with self.assertRaisesRegex(guard.AdmissionError, 'SIZE_OR_TYPE'):
                guard.read(path, archive.BODY_CAP)

    def test_environment_drift_and_extra_input_are_refused(self):
        env = self.root / 'env'; env.mkdir()
        p = env / 'approved.py'; p.write_bytes(b'approved\n')
        manifest = {'files': [{'path': p.name, 'bytes': p.stat().st_size, 'sha256': guard.sha(p.read_bytes())}]}
        guard.environment_check(env, manifest)
        p.write_bytes(b'modified\n')
        with self.assertRaisesRegex(guard.AdmissionError, 'ENVIRONMENT_DRIFT'):
            guard.environment_check(env, manifest)
        p.write_bytes(b'approved\n'); (env / 'extra.py').write_bytes(b'extra')
        with self.assertRaisesRegex(guard.AdmissionError, 'INVENTORY'):
            guard.environment_check(env, manifest)

    def test_changed_helper_refuses_before_any_execution(self):
        p = self.root / guard.PREFIX / 'successor_harness.py'
        p.parent.mkdir(parents=True)
        raw = b'raise AssertionError("project body executed before identity")\n'
        p.write_bytes(raw)
        manifest = {'source_inputs': [{'path': 'code/' + p.relative_to(self.root).as_posix(),
                                      'bytes': len(raw), 'sha256': '0' * 64}]}
        with self.assertRaisesRegex(ValueError, 'helper identity'):
            entry.load('successor_harness', self.root, manifest)

    def test_duplicate_keys_invalid_utf8_and_nonfinite_refuse(self):
        for raw in (b'{"value":1,"value":2}', b'\xff', b'{"value":NaN}'):
            with self.subTest(raw=raw), self.assertRaises(archive.ArchiveError):
                archive.strict_json(raw)
            with self.assertRaises(guard.AdmissionError):
                guard.parse(raw)
        with self.assertRaisesRegex(archive.ArchiveError, 'INVALID_UTF8'):
            archive.portable_body('producer/stdout.txt', b'\xff')

    def test_private_marker_and_unapproved_field_refuse(self):
        marker = '/' + 'Users' + '/fabricated-successor'
        for name in ('producer/receipt.json', 'inputs/source.py', 'producer/stdout.txt'):
            with self.assertRaisesRegex(archive.ArchiveError, 'UNDECLARED_PRIVATE_LOCATOR'):
                archive.portable_body(name, json.dumps({'nested': {'value': marker}}).encode())
        with self.assertRaisesRegex(archive.ArchiveError, 'UNDECLARED_PRIVATE_LOCATOR'):
            archive.portable_body('producer/prefix.json', json.dumps({'argv': [], 'counter': marker}).encode(),
                                  ((marker, 'role:fabricated'),))

    def test_prefix_commitment_protects_numeric_and_identity_fields(self):
        prefix = {'argv': ['a', '-I', '-B', 'b', '--child', 'c'],
                  'source_inputs': [{'sha256': '1' * 64}], 'counter': 4, 'numeric': [0.25]}
        expected = archive.prefix_protected(prefix)
        allowed = copy.deepcopy(prefix)
        for i in (0, 3, 5): allowed['argv'][i] = 'role:example/new'
        self.assertEqual(archive.prefix_protected(allowed), expected)
        for key, value in [('counter', 5), ('numeric', [0.5]), ('source_inputs', [])]:
            changed = copy.deepcopy(prefix); changed[key] = value
            self.assertNotEqual(archive.prefix_protected(changed), expected)

    def test_malformed_archive_limits_are_truthful_failures(self):
        root = self.root / 'archive'; root.mkdir()
        for row in ({'path': 'x', 'bytes': archive.BODY_CAP + 1, 'parts': []},
                    {'path': 'x', 'bytes': 1, 'parts': [{'path': 'bad', 'bytes': -1}]},
                    {'path': 'x', 'bytes': 1, 'parts': []}):
            (root / 'manifest.json').write_text(json.dumps({'schema': 'router-caller-portable-parts-v1', 'files': [row]}))
            with self.assertRaises(archive.ArchiveError):
                archive.verify_archive(root)
        (root / 'manifest.json').write_bytes(b'{"files":[],"files":[]}')
        with self.assertRaisesRegex(archive.ArchiveError, 'DUPLICATE'):
            archive.verify_archive(root)

    def test_incomplete_or_failed_producer_never_passes(self):
        # Failed fixtures only: the actual successful composition is separately
        # qualified through the production command and portable reader.
        for raw in (b'', b'{', b'{"event":"result","status":"FAIL"}\n',
                    b'{"event":"result","status":"PASS"}\ntruncated trailing data'):
            self.assertFalse(entry.producer_pass(raw, b'', {}, 'case'))
        self.assertFalse(entry.producer_pass(b'\xff', b'', {}, 'matrix'))
        stop, run = self.capture('incomplete', 'print("{",end="",flush=True)')
        self.assertEqual(stop['exit_code'], 0)
        self.assertTrue(stop['capture_complete'] and stop['stop_confirmed'])
        self.assertEqual((run / 'stdout.txt').read_bytes(), b'{')
        self.assertFalse(entry.producer_pass((run / 'stdout.txt').read_bytes(), b'', stop, 'case'))

    def test_omitted_transform_and_extra_logical_member_refuse(self):
        row = {'sha256': 'a' * 64, 'original_sha256': 'b' * 64,
               'bytes': 10, 'original_bytes': 20, 'portable_role_substitution': False, 'transformations': []}
        with self.assertRaisesRegex(archive.ArchiveError, 'TRANSFORMATION_ACCOUNTING'):
            archive.check_transformation_accounting(row)
        files = {'producer/' + n for n in ('prefix.json', 'receipt.json', 'stdout.txt', 'stderr.txt', 'checkpoint.json')}
        files.add('inputs/unlisted')
        with self.assertRaisesRegex(archive.ArchiveError, 'LOGICAL_MEMBER_SET'):
            archive.check_member_set(files, [], False)

    def capture(self, name, body, **limits):
        run = self.root / name; run.mkdir()
        work = run / 'work'; work.mkdir()
        return supervisor.capture([sys.executable, '-I', '-B', '-c', body], run, work, **limits), run

    def test_native_failure_is_reaped_with_complete_distinct_capture(self):
        stop, run = self.capture('failure', 'import sys; print("stdout-known"); print("stderr-known",file=sys.stderr); sys.exit(23)')
        self.assertEqual(stop['exit_code'], 23)
        self.assertTrue(stop['stop_confirmed'] and stop['direct_child_reaped'] and stop['capture_complete'])
        self.assertEqual((run / 'stdout.txt').read_bytes(), b'stdout-known\n')
        self.assertEqual((run / 'stderr.txt').read_bytes(), b'stderr-known\n')
        self.assertFalse(entry.producer_pass((run / 'stdout.txt').read_bytes(), (run / 'stderr.txt').read_bytes(), stop, 'case'))

    def test_timeout_kills_reaps_and_marks_capture_incomplete(self):
        stop, _ = self.capture('timeout', 'import time; time.sleep(10)', seconds=.1)
        self.assertEqual(stop['reason'], 'DEADLINE')
        self.assertTrue(stop['stop_confirmed'] and stop['process_group_absent'])
        self.assertFalse(stop['capture_complete'])

    def test_capture_limit_is_bounded_and_reaped(self):
        stop, run = self.capture('capture', 'import os; os.write(1,b"x"*65536)', capture_cap=1024)
        self.assertEqual(stop['reason'], 'CAPTURE_LIMIT')
        self.assertEqual(sum((run / (n + '.txt')).stat().st_size for n in ('stdout', 'stderr')), 1024)
        self.assertTrue(stop['stop_confirmed'])
        self.assertFalse(stop['capture_complete'])

    def test_denied_group_observation_banks_failure_and_latches(self):
        run = self.root / 'denied-group'; run.mkdir()
        work = run / 'work'; work.mkdir()
        latch = self.root / 'STOP_NUMERICAL.json'
        with mock.patch.object(supervisor, 'group_exists', side_effect=PermissionError(1, 'fabricated denial')):
            with self.assertRaisesRegex(RuntimeError, 'unknown stop'):
                supervisor.capture([sys.executable, '-I', '-B', '-c', 'pass'], run, work, stop_latch=latch)
        stop = json.loads((run / 'stop.json').read_text())
        self.assertTrue(stop['direct_child_reaped'])
        self.assertFalse(stop['stop_confirmed'] or stop['capture_complete'])
        self.assertEqual(stop['reason'], 'STOP_UNCONFIRMED')
        self.assertTrue(latch.is_file())
        self.assertFalse(supervisor.group_exists(stop['pid']))


if __name__ == '__main__':
    unittest.main()
