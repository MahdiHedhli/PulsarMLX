"""Host-only controls. Actual evidence is admitted/normalized, never numerically graded here."""
import copy
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import struct
import tempfile
import unittest
import shutil
import sys
from unittest.mock import patch
import zipfile

import retained_admission as admission
import retained_qualify as qualifier
from retained_rational import normalize_token, normalize_exact, frozen_view, grade_compatible, NumericalFailure
from reference import decide_qmm
from exact_gates_v1 import rational


class RationalTests(unittest.TestCase):
    def test_original_failure_preserved(self):
        with self.assertRaisesRegex(ValueError, 'not enough values to unpack'):
            rational('1')

    def test_canonical_integer_and_fraction(self):
        for s in ('0', '-1', '1', '12345678901234567890'):
            with self.subTest(s=s):
                v, changed = normalize_token(s)
                self.assertTrue(changed); self.assertEqual(v, s + '/1')
                self.assertEqual(Fraction(int(s)), rational(v))
        for s in ('0/1', '1/1', '-7/3', '4/5'):
            self.assertEqual(normalize_token(s), (s, False))

    def test_adversarial_syntax_and_types(self):
        bad = [None, True, False, 0, 1, 1.0, [], {}, '', ' 1', '1 ', '1\n', '+1', '-0', '00', '01', '-01',
               '١', '１', '1.0', '1e0', '1/0', '1/-1', '1/+1', '1/01', '1//1', '1/2/3', '2/4', '0/2', '-0/1', '1/' + '9' * 4097]
        for s in bad:
            with self.subTest(s=str(s)[:40]):
                with self.assertRaises(ValueError): normalize_token(s)

    def test_both_fields_and_other_fields_immutable(self):
        value = {'k': 1, 'y_exact': ['0', '-2', '1/3'], 'phi_exact': ['2', '4/3', '0/1'], 'other': {'x': [7]}}
        saved = copy.deepcopy(value); view, census = normalize_exact(value)
        self.assertEqual(value, saved); self.assertEqual(view['other'], value['other'])
        self.assertEqual(view['y_exact'], ['0/1', '-2/1', '1/3']); self.assertEqual(view['phi_exact'], ['2/1', '4/3', '0/1'])
        self.assertEqual(census['y_exact']['converted'], 2)

    def synthetic(self, directory, bits=0x3f800000, shape=None):
        raw = struct.pack('<I', bits); (directory / 'out.f32').write_bytes(raw)
        output = {'id': 'synthetic', 'dtype': 'F32', 'shape': shape or [1, 1], 'file': 'out.f32', 'sha256': hashlib.sha256(raw).hexdigest()}
        report = directory / 'run.json'; report.write_text(json.dumps({'identity': {'fixture_manifest_sha256': 'SYNTHETIC'}, 'outputs': [output]}))
        return report, output

    def test_equivalent_numeric_decisions_and_failures(self):
        with tempfile.TemporaryDirectory(prefix='synthetic-retained-numerics-') as d:
            root = Path(d); report, out = self.synthetic(root)
            exact = {'k': 1, 'y_exact': ['1'], 'phi_exact': ['1']}; normalized, _ = normalize_exact(exact)
            case = {'id': 'synthetic', 'expected': {'families_0_31_2': [{'gamma_n': 1}]}}
            explicit = {'k': 1, 'y_exact': ['1/1'], 'phi_exact': ['1/1']}
            self.assertEqual(decide_qmm(case, normalized, None, {'id': 'synthetic', 'output': out}, root), decide_qmm(case, explicit, None, {'id': 'synthetic', 'output': out}, root))
            view = {'fixture_manifest_sha256': 'SYNTHETIC', 'cases': {'synthetic': {'exact': normalized, 'rust': None, 'gamma_n': 1}}}
            self.assertTrue(grade_compatible(view, report)[0]['gates']['G-QMM-EXACT']['pass'])
            for bits in (0x40000000, 0x7f800000, 0xff800000, 0x7fc00000):
                report, out = self.synthetic(root, bits)
                with self.assertRaises(NumericalFailure): grade_compatible(view, report)
            report, out = self.synthetic(root); (root / 'out.f32').write_bytes(b'bad')
            with self.assertRaises(ValueError): grade_compatible(view, report)

    def test_wrong_cardinality_still_refused(self):
        with tempfile.TemporaryDirectory(prefix='synthetic-retained-count-') as d:
            root = Path(d); report, out = self.synthetic(root)
            view = {'fixture_manifest_sha256': 'SYNTHETIC', 'cases': {'synthetic': {'exact': {'k': 1, 'y_exact': ['1/1', '1/1'], 'phi_exact': ['1/1', '1/1']}, 'rust': None, 'gamma_n': 1}}}
            with self.assertRaises(ValueError): grade_compatible(view, report)


class HostBoundaryTests(unittest.TestCase):
    def test_output_shape_dtype_length_and_path(self):
        out = {'file': 'output.f32', 'dtype': 'F32', 'shape': [1, 1]}
        admission.output_geometry(out, [1, 1], 'output.f32', 4, True)
        for key, value in [('file', '../output.f32'), ('dtype', 'BF16'), ('shape', [2, 1])]:
            bad = dict(out); bad[key] = value
            with self.assertRaises(ValueError): admission.output_geometry(bad, [1, 1], 'output.f32', 4, True)
        with self.assertRaises(ValueError): admission.output_geometry(out, [1, 1], 'output.f32', 8, True)

    def test_audit_guard_refuses_native_archive_and_network(self):
        for executable in ('adoption-probe', 'adoption-parent', '/archive/grade-rust', 'ssh', 'curl'):
            with self.assertRaises(ValueError): sys.audit('subprocess.Popen', executable, [executable], None, None)
        with self.assertRaises(RuntimeError): sys.audit('ctypes.dlopen', 'libmlx.dylib')
        with self.assertRaises(RuntimeError): sys.audit('import', 'mlx.core', None, [], [], [])

    def test_path_aliases_and_escape(self):
        with tempfile.TemporaryDirectory(prefix='synthetic-retained-path-') as d:
            root = Path(d); (root / 'x').write_text('x'); paths = admission.Paths(root, root, root)
            self.assertEqual(paths.resolve('<CAMPAIGN_ROOT>/inputs/x'), root / 'x')
            for name in ('<NATIVE_PREFIX>/x', '/old/runner/x', '<CAMPAIGN_ROOT>/../x', '<CAMPAIGN_ROOT>//x'):
                with self.subTest(name=name), self.assertRaises((ValueError, FileNotFoundError)): paths.resolve(name)
            (root / 'link').symlink_to(root / 'x')
            with self.assertRaises(ValueError): paths.resolve('<CAMPAIGN_ROOT>/link')

    def test_archive_adversaries(self):
        for name in ('../x', '/x', 'a/../x', 'a\\b'):
            with self.subTest(name=name), self.assertRaises(ValueError): admission.check_members([zipfile.ZipInfo(name)])
        with self.assertRaises(ValueError): admission.check_members([zipfile.ZipInfo('x'), zipfile.ZipInfo('x')])
        symlink = zipfile.ZipInfo('x'); symlink.external_attr = 0o120777 << 16
        with self.assertRaises(ValueError): admission.check_members([symlink])
        huge = zipfile.ZipInfo('x'); huge.file_size = 33554433
        with self.assertRaises(ValueError): admission.check_members([huge])

    def test_original_public_identity_not_interchangeable(self):
        with self.assertRaises(ValueError): admission.original({'x': {'changed': True, 'original_sha256': 'a', 'public_sha256': 'b'}}, 'x')
        self.assertEqual(admission.original({'x': {'changed': False, 'original_sha256': 'a', 'public_sha256': 'a'}}, 'x'), 'a')

    def test_duplicate_json_and_bool_int_refused(self):
        with self.assertRaises(ValueError): admission.parse('{"a":1,"a":2}')
        with self.assertRaises(ValueError): admission.parse('{"a":NaN}')
        with self.assertRaises(ValueError): admission.equal(True, 1, 'typed equality')

    def test_occupied_claim_and_output_refused(self):
        with tempfile.TemporaryDirectory(prefix='synthetic-retained-claim-') as d:
            root = Path(d); receipt = root / 'synthetic-receipt.json'; receipt.write_text('{}')
            fake = {'Q': {'synthetic': True}, 'output': str(root / 'new')}
            intent, out = qualifier.claim(receipt, fake)
            before = intent.read_bytes()
            fake['output'] = str(root / 'different')
            with self.assertRaises(FileExistsError): qualifier.claim(receipt, fake)
            self.assertEqual(intent.read_bytes(), before); self.assertFalse((root / 'different').exists())
            fake['output'] = str(out)
            with self.assertRaises(ValueError): qualifier.claim(receipt, fake)

    def test_native_environment_refused(self):
        for key in qualifier.FORBIDDEN_ENV:
            with patch.dict(os.environ, {key: 'synthetic'}), self.assertRaises(ValueError): qualifier.environment()

    def test_timeout_kills_only_owned_child_and_preserves_attempt(self):
        import subprocess
        class Child:
            pid = 1234
            killed = False
            def poll(self): return 9 if self.killed else None
            def kill(self): self.killed = True
            def wait(self, timeout=None):
                if timeout is not None: raise subprocess.TimeoutExpired('synthetic', timeout)
                return 9
        child = Child()
        with tempfile.TemporaryDirectory(prefix='synthetic-retained-timeout-') as d:
            root = Path(d)
            with patch.object(qualifier.subprocess, 'Popen', return_value=child), self.assertRaises(subprocess.TimeoutExpired):
                qualifier.cpu_child({'sha256': 'synthetic'}, ['synthetic-grader'], root, 0.001)
            self.assertTrue(child.killed)
            self.assertTrue(admission.read(root / 'rust-gates.outcome.json')['owned_child_killed_and_reaped'])
            with self.assertRaises(FileExistsError): qualifier.cpu_child({'sha256': 'synthetic'}, ['synthetic-grader'], root, 1)


@unittest.skipUnless(os.environ.get('RUST011_EVIDENCE'), 'explicit verified evidence root required')
class FrozenEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(os.environ['RUST011_EVIDENCE'])
        cls.artifact = cls.root / 'retained-artifact'; cls.inputs = cls.root / 'original-inputs'
        cls.source = Path(os.environ['RUST011_C_SOURCE']); cls.controller = Path(os.environ['RUST011_H_SOURCE'])
        cls.f = admission.read(cls.artifact / 'campaign/freeze.json'); cls.m = admission.read(cls.artifact / 'campaign/m1a/mechanism.json')
        cls.manifest = admission.read(cls.inputs / 'fixtures/manifest.json'); cls.portable = admission.read(cls.inputs / 'portable.json')
        cls.inherited = admission.read(cls.source / 'fixtures/native-composition/manifest.json')
        cls.expected = admission.expected_population(cls.manifest, cls.inherited)
        cls.rows = {r['path']: r for r in admission.read(cls.artifact / 'public-view-manifest.json')['files']}

    def test_actual_reference_census_and_identity(self):
        raw = (self.inputs / 'reference.json').read_bytes(); before = bytes(raw)
        view, census = frozen_view(raw, self.manifest)
        self.assertEqual(raw, before); self.assertEqual(sum(v['converted'] for v in census['totals'].values()), 12288)
        self.assertEqual(sum(v['unchanged'] for v in census['totals'].values()), 37888)
        self.assertEqual(sum(c['rust'] is None for c in view['cases'].values()), 4)
        with self.assertRaises(ValueError): frozen_view(raw + b' ', self.manifest)
        bad = copy.deepcopy(self.manifest); bad['cases'][0]['H'] += 1
        with self.assertRaises(ValueError): frozen_view(raw, bad)

    def test_complete_non_numerical_admission(self):
        value = admission.admit(self.root.parent / 'rust-010/designated-artifact.zip', self.artifact, self.source, self.controller, self.inputs, self.root / 'packed_affine_m1_inputs_v1.json')
        self.assertEqual(len(value['reports']), 52); self.assertEqual(len(value['projections']), 84)
        self.assertEqual(len(value['unavailable_original_controls']), 124)
        self.assertFalse(value['new_native_execution']); self.assertFalse(value['Studio_released'])

    def test_report_population_adversaries(self):
        for mutate in (lambda m: m['reports'].pop(), lambda m: m['reports'].append(m['reports'][0]),
                       lambda m: m['reports'][0].update(report='../run.json'),
                       lambda m: m['reports'][0].update(label='extra')):
            value = copy.deepcopy(self.m); mutate(value)
            with self.assertRaises(ValueError): admission.admit_entries(value, self.expected)

    def test_crossed_control_views(self):
        for key, value in [('source_commit', admission.H), ('source_tree', admission.H_TREE), ('host_role', 'm1-ultra-studio'),
                           ('phase', 'm1b'), ('M1b_released', True), ('raw_policy', 'STUDIO_RETAINED_OBSERVATION'),
                           ('fixture_root', '<UNKNOWN>/fixtures')]:
            with self.subTest(key=key):
                f = copy.deepcopy(self.f); f[key] = value
                with self.assertRaises(ValueError): admission.control_views(self.artifact, self.rows, f, self.m, self.expected, admission.Paths(self.source, self.inputs, self.artifact))
        f = copy.deepcopy(self.f); f['raw_provenance']['run_id'] += 1
        with self.assertRaises(ValueError): admission.control_views(self.artifact, self.rows, f, self.m, self.expected, admission.Paths(self.source, self.inputs, self.artifact))
        f = copy.deepcopy(self.f); f['raw_provenance']['controller_commit'] = admission.C
        with self.assertRaises(ValueError): admission.control_views(self.artifact, self.rows, f, self.m, self.expected, admission.Paths(self.source, self.inputs, self.artifact))

    def report_args(self):
        label = 'group-0-adopted'; p = self.artifact / 'campaign/m1a'
        return [copy.deepcopy(self.f), self.expected, label, admission.read(p / (label + '.config.json')),
                admission.read(p / label / 'run.json'), admission.read(p / (label + '.outcome.json')),
                self.rows['campaign/m1a/' + label + '.config.json']['original_sha256'], self.manifest, self.portable,
                [admission.parse(s) for s in (p / label / 'events.jsonl').read_bytes().splitlines()]]

    def test_report_semantic_adversaries(self):
        mutations = [lambda a: a[3].update(arm='copied'), lambda a: a[3]['sequence'].reverse(),
                     lambda a: a[3].update(source_commit=admission.H), lambda a: a[4].update(config_sha256='0' * 64),
                     lambda a: a[4]['provenance'].update(loaded_images_verified=False),
                     lambda a: a[4]['lifetime'].update(early_free_count=1), lambda a: a[4]['io'].update(overread_bytes=1),
                     lambda a: a[4]['copies'].update(packed_import_bytes=1), lambda a: a[4]['memory'].update(live_working_bound=33554433),
                     lambda a: a[4]['bridge_diagnostic'].update(retirement_complete=0),
                     lambda a: a[4]['adoption'].update(pointer_identity=False), lambda a: a[4].pop('source_binding')]
        # A-B-A reversal is identical; swap the first two instead.
        mutations[1] = lambda a: a[3]['sequence'].__setitem__(slice(0, 2), a[3]['sequence'][0:2][::-1])
        for i, mutate in enumerate(mutations):
            with self.subTest(mutation=i):
                args = self.report_args(); mutate(args)
                with self.assertRaises((ValueError, KeyError)): admission.report_semantics(*args)

    def test_public_config_digest_is_not_original(self):
        args = self.report_args(); args[6] = self.rows['campaign/m1a/group-0-adopted.config.json']['public_sha256']
        with self.assertRaises(ValueError): admission.report_semantics(*args)

    def test_public_payload_missing_extra_and_tampered(self):
        with tempfile.TemporaryDirectory(prefix='synthetic-retained-publication-') as d:
            root = Path(d) / 'copy'; shutil.copytree(self.artifact, root)
            archive = self.root.parent / 'rust-010/designated-artifact.zip'
            extra = root / 'extra.json'; extra.write_text('{}')
            with self.assertRaises(ValueError): admission.publication(archive, root)
            extra.unlink()
            for name in ('campaign/m1a/group-0-copied/run.json', 'campaign/m1a/group-0-copied/output-0.f32', 'campaign/freeze.json', 'public-view-manifest.json'):
                p = root / name; original = p.read_bytes(); p.chmod(0o600); p.write_bytes(original + b' ')
                with self.subTest(name=name), self.assertRaises(ValueError): admission.publication(archive, root)
                p.write_bytes(original)
            p = root / 'campaign/m1a/group-0-copied/run.json'; p.unlink()
            with self.assertRaises(ValueError): admission.publication(archive, root)


if __name__ == '__main__':
    qualifier.guard()
    unittest.main()
