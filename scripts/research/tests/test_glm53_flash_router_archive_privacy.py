"""Fabricated markers only: narrow archive redaction and producer bindings."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'glm53_flash/router_caller'))
import rc_archive as archive

def encoded(value):
    return (json.dumps(value, indent=2) + '\n').encode()

class RedactionTests(unittest.TestCase):
    def setUp(self):
        self.home = '/' + 'Users' + '/' + 'fabricated-operator'
        self.other = '/' + 'home' + '/' + 'fabricated-other'
        self.roots = ((self.home, 'role:operator-home'),)
        self.value = {'argv': [self.home + '/python', '-I', '-B', self.home + '/runner.py',
                               '--phase', self.home + '/phase'],
                      'source_inputs': [{'path': 'source/a.py', 'sha256': 'a' * 64, 'bytes': 3}],
                      'nested': {'claims': ['PARTIAL'], 'counters': [0, 4],
                                 'numeric': [[0.5, -2.0]], 'dtype': 'float32'},
                      'ticket': {'input_digest': 'b' * 64, 'nonce': 'synthetic'}}

    def test_only_declared_complete_path_operands_change(self):
        original = encoded(self.value)
        body, changes = archive.portable_body('producer/prefix.json', original, self.roots)
        expected = copy.deepcopy(self.value)
        for i in (0, 3, 5):
            expected['argv'][i] = 'role:operator-home' + expected['argv'][i][len(self.home):]
        self.assertEqual(json.loads(body), expected)
        self.assertEqual([x['field'] for x in changes], [['argv', 0], ['argv', 3], ['argv', 5]])
        self.assertEqual(encoded(self.value), original)
        self.assertNotEqual(archive.sha(body), archive.sha(original))
        self.assertEqual(archive.REDACTION_FIELDS, (('argv', 0), ('argv', 3), ('argv', 5)))

    def test_already_sanitized_and_nonmatching_bytes_preserved(self):
        raw = b'{ "argv": ["role:operator-home/python", "safe nonmatching text"] }\n'
        self.assertEqual(archive.portable_body('producer/prefix.json', raw, self.roots), (raw, []))
        raw = b'unchanged source and numeric evidence\n'
        self.assertEqual(archive.portable_body('inputs/source.py', raw, self.roots), (raw, []))

    def test_protected_fields_and_nested_containers_refuse_locators(self):
        clean = json.loads(archive.portable_body('producer/prefix.json', encoded(self.value), self.roots)[0])
        for key in ('source_inputs', 'claims', 'counters', 'receipt', 'numerical_values'):
            with self.subTest(key=key):
                bad = copy.deepcopy(clean)
                bad['nested'][key] = [{'path': self.home + '/protected'}]
                with self.assertRaisesRegex(archive.ArchiveError, 'UNDECLARED_PRIVATE_LOCATOR'):
                    archive.portable_body('producer/prefix.json', encoded(bad), self.roots)

    def test_embedded_unbound_and_other_home_locators_refused(self):
        for value in ('prefix ' + self.home + '/python', self.home + '-other/python',
                      self.other + '/python', 'C:' + '\\Users\\' + 'fabricated\\python'):
            with self.subTest(kind=value.split('/')[0]):
                with self.assertRaisesRegex(archive.ArchiveError, 'UNDECLARED_PRIVATE_LOCATOR'):
                    archive.portable_body('producer/prefix.json', encoded({'argv': [value]}), self.roots)
        with self.assertRaisesRegex(archive.ArchiveError, 'UNDECLARED_PRIVATE_LOCATOR'):
            archive.portable_body('producer/prefix.json', encoded({self.other: 1}), self.roots)

    def test_source_and_receipt_are_never_rewritten(self):
        for name in ('inputs/source.py', 'producer/receipt.json', 'producer/stdout.txt'):
            with self.subTest(name=name):
                with self.assertRaisesRegex(archive.ArchiveError, 'UNDECLARED_PRIVATE_LOCATOR'):
                    archive.portable_body(name, encoded({'path': self.home + '/private'}), self.roots)

    def test_case_variants_refused_without_silent_normalization(self):
        for home in (self.home.upper(), self.other.upper()):
            with self.assertRaisesRegex(archive.ArchiveError, 'UNDECLARED_PRIVATE_LOCATOR'):
                archive.portable_body('producer/prefix.json', encoded({'argv': [home + '/python']}), self.roots)

    def test_json_escaped_protected_strings_refused(self):
        raw = encoded({'nested': [{'path': self.other + '/private'}]}).replace(b'/', b'\\u002f')
        for name in ('producer/receipt.json', 'producer/stdout.txt', 'inputs/source.json'):
            with self.subTest(name=name):
                with self.assertRaisesRegex(archive.ArchiveError, 'UNDECLARED_PRIVATE_LOCATOR'):
                    archive.portable_body(name, raw, self.roots)

    def test_invalid_policy_and_duplicate_keys_refused(self):
        for roots in ((('/', 'role:root'),), (('/synthetic/../escape', 'role:root'),),
                      ((self.home, 'plain replacement'),), self.roots + self.roots):
            with self.subTest(roots_count=len(roots)):
                with self.assertRaises(archive.ArchiveError):
                    archive.portable_body('producer/prefix.json', b'{}', roots)
        with self.assertRaisesRegex(archive.ArchiveError, 'DUPLICATE_KEY'):
            archive.portable_body('producer/prefix.json', b'{"argv":[],"argv":[]}')

    def test_redaction_has_no_home_or_filesystem_discovery(self):
        with mock.patch.object(Path, 'home', side_effect=AssertionError('host lookup forbidden')):
            with mock.patch.object(Path, 'read_bytes', side_effect=AssertionError('host read forbidden')):
                body, _ = archive.portable_body('producer/prefix.json', encoded(self.value), self.roots)
        self.assertNotIn(self.home.encode(), body)

    def test_pack_readback_preserves_originals_and_rejects_tampered_part(self):
        parent = Path(tempfile.gettempdir()).resolve(strict=True)
        with tempfile.TemporaryDirectory(prefix='router-archive-', dir=parent) as temp:
            root = Path(temp); phase = root / 'phase'; run = phase / 'runs' / 'synthetic'
            run.mkdir(parents=True); checkpoints = phase / 'evidence/checkpoints'; checkpoints.mkdir(parents=True)
            source = root / 'synthetic-input.json'; source.write_bytes(b'{"numeric":[0.25,2],"claim":"synthetic"}\n')
            rows = [{'path': source.name, 'bytes': source.stat().st_size, 'sha256': archive.sha(source.read_bytes())}]
            generation = archive.sha(json.dumps(rows, sort_keys=True, separators=(',', ':')).encode())
            prefix = {'argv': [str(root / 'python'), '-I', '-B', str(root / 'runner.py'), '--phase', str(phase)],
                      'source_inputs': rows, 'ticket': {'input_digest': generation}}
            stdout = b'{"event":"result","status":"PASS","synthetic_archive_fixture":true}\n'
            receipt = {'status': 'PASS', 'run': 'synthetic', 'input_manifest_sha256': generation,
                       'termination': {'stop_confirmed': True}, 'counters': {'attempted_bytes': 32},
                       'outputs': {'stdout': {'sha256': archive.sha(stdout)}, 'stderr': {'sha256': archive.sha(b'')}}}
            for name, raw in [('prefix.json', encoded(prefix)), ('receipt.json', encoded(receipt)),
                              ('stdout.txt', stdout), ('stderr.txt', b'')]:
                (run / name).write_bytes(raw)
            (checkpoints / (generation + '.json')).write_bytes(encoded({'generation': generation, 'files': rows}))
            originals = {p: p.read_bytes() for p in (*run.iterdir(), source)}
            def confined(base, path):
                path = Path(path)
                if path.resolve() != path or not path.is_relative_to(base):
                    raise AssertionError('synthetic test path escape')
                return path
            guard = types.SimpleNamespace(admit_phase=lambda p: p, confined=confined,
                                          resolve_input=lambda row: root / row['path'])
            target = phase / 'archive'
            with mock.patch.dict(sys.modules, {'rc_guard': guard}):
                result = archive.pack_run(phase, 'synthetic', target)
            self.assertEqual(result['logical_files'], 6)
            self.assertEqual({p: p.read_bytes() for p in originals}, originals)
            manifest = json.loads((target / 'manifest.json').read_text())
            self.assertEqual([r['path'] for r in manifest['files'] if r['portable_role_substitution']], ['producer/prefix.json'])
            prefix_row = next(r for r in manifest['files'] if r['path'] == 'producer/prefix.json')
            self.assertEqual(prefix_row['original_sha256'], archive.sha(encoded(prefix)))
            part = target / prefix_row['parts'][0]['path']
            data = bytearray(part.read_bytes()); data[0] ^= 1; part.write_bytes(data)
            with self.assertRaisesRegex(archive.ArchiveError, 'PART_DIGEST_SIZE'):
                archive.verify_archive(target)

if __name__ == '__main__':
    unittest.main()
