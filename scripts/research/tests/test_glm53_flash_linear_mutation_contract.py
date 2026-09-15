"""Fixed test-only contract for the Flash cache and cross-check mutants."""
import copy
import difflib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import unittest

SOURCE = Path(__file__).resolve().parents[3]
ORACLE = SOURCE / 'scripts/research/glm53_flash/linear_attention/oracle.py'
RECURRENT = SOURCE / 'scripts/research/glm53_flash/recurrent_dispatch/oracle.py'
FIXTURE = SOURCE / 'fixtures/research/glm53-flash-linear-attention-v1/fixtures.json'
EVIDENCE = SOURCE.parent / 'evidence'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


class FixedContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(os.environ['PULSAR_VARIANT_ROOT'])
        cls.oracle = load('variant_oracle', root / 'scripts/research/glm53_flash/linear_attention/oracle.py')
        cls.recurrent = load('pinned_recurrent', root / 'scripts/research/glm53_flash/recurrent_dispatch/oracle.py')
        cls.fixture = json.loads(FIXTURE.read_bytes())
        print(json.dumps({'event': 'module_origins', 'oracle': str(Path(cls.oracle.__file__).resolve()),
                          'recurrent': str(Path(cls.recurrent.__file__).resolve())}), flush=True)

    def reason(self, case, field, expected, message):
        before = copy.deepcopy(case)
        with self.assertRaisesRegex(self.oracle.InputError, '^' + expected + '$', msg=message):
            self.oracle.validate(case)
        self.assertEqual(case, before, message)

    def test_metadata_fixed_expectations(self):
        for base in (self.fixture['cases'][1], self.fixture['cases'][4]):
            B, S = base['B'], base['S']
            for field, prefix, bad, valid in (
                ('initial_lengths', 'ORACLE_INITIAL_LENGTHS', S - 1, (S, S + 1)),
                ('initial_padding', 'ORACLE_INITIAL_PADDING', -1, (0, S - 1, S, S + 1))):
                case = copy.deepcopy(base); del case[field]
                self.reason(case, field, prefix + '_MISSING',
                            'LENGTH_MISSING_GUARANTEE' if field == 'initial_lengths' else 'PADDING_MISSING_GUARANTEE')
                for value in (None, (), 0, [True] * B, [0.5] * B, [float('inf')] * B):
                    case = copy.deepcopy(base); case[field] = value
                    self.reason(case, field, prefix + '_TYPE',
                                'LENGTH_TYPE_GUARANTEE' if field == 'initial_lengths' else 'PADDING_TYPE_GUARANTEE')
                for value in ([], [0] * (B + 1)):
                    case = copy.deepcopy(base); case[field] = value
                    self.reason(case, field, prefix + '_SHAPE', prefix + '_SHAPE_GUARANTEE')
                case = copy.deepcopy(base); case[field] = [bad] * B
                self.reason(case, field, prefix + '_RANGE',
                            'LENGTH_RANGE_GUARANTEE' if field == 'initial_lengths' else 'PADDING_RANGE_GUARANTEE')
                for point in valid:
                    case = copy.deepcopy(base); case[field] = [point] * B; before = copy.deepcopy(case)
                    self.assertEqual(self.oracle.validate(case), (B, S, base['config']['hidden_size'],
                                     base['config']['linear_num_heads'], 32,
                                     base['config']['linear_conv_kernel_dim']),
                                     'PADDING_VALID_BELOW_S_GUARANTEE' if field == 'initial_padding' and point < S else prefix + '_VALID')
                    self.assertEqual(case, before)

    def cross(self, output_ok, state_ok, token, visits_expected, message):
        case = copy.deepcopy(self.fixture['cases'][0]); visits = []
        original = self.oracle.close
        def controlled(actual, expected, atol=None, rtol=None):
            dims = self.oracle.shape(actual)
            if dims == (1, 1, 32): label, result = 'OUTPUT', output_ok
            elif dims == (1, 1, 32, 32): label, result = 'STATE', state_ok
            else: self.fail('UNKNOWN_CROSSCHECK_SIGNATURE:' + repr(dims))
            visits.append({'index': len(visits) + 1, 'label': label, 'shape': list(dims)})
            return result
        self.oracle.close = controlled
        try:
            if token:
                with self.assertRaisesRegex(self.oracle.InputError, '^' + token + '$', msg=message):
                    self.oracle.module_reference(case, self.recurrent)
            else:
                self.oracle.module_reference(case, self.recurrent)
        finally:
            self.oracle.close = original
        self.assertEqual([v['label'] for v in visits], visits_expected, message)
        print(json.dumps({'event': 'close_visits', 'output_ok': output_ok,
                          'state_ok': state_ok, 'visits': visits}), flush=True)

    def test_crosscheck_fixed_expectations(self):
        self.cross(True, True, None, ['OUTPUT', 'STATE'], 'BOTH_TRUE_VISIT_GUARANTEE')
        self.cross(False, True, 'ORACLE_RECURRENCE_CROSSCHECK_OUTPUT', ['OUTPUT'],
                   'OUTPUT_CROSSCHECK_GUARANTEE')
        self.cross(True, False, 'ORACLE_RECURRENCE_CROSSCHECK_STATE', ['OUTPUT', 'STATE'],
                   'STATE_CROSSCHECK_GUARANTEE')


class Matrix(unittest.TestCase):
    MUTANTS = {
        'range': ('value < minimum', 'False', 'LENGTH_RANGE_GUARANTEE'),
        'bool': ('type(value) is not int', 'not isinstance(value, int)', 'LENGTH_TYPE_GUARANTEE'),
        'wrong-field': ("('initial_lengths', S, 'ORACLE_INITIAL_LENGTHS')", "('initial_padding', S, 'ORACLE_INITIAL_LENGTHS')", 'LENGTH_MISSING_GUARANTEE'),
        'padding-bound': ("('initial_padding', 0, 'ORACLE_INITIAL_PADDING')", "('initial_padding', S, 'ORACLE_INITIAL_PADDING')", 'PADDING_VALID_BELOW_S_GUARANTEE'),
        'drop-output': ("if not close(mapping(recur_y, lambda x:x.v), accepted_y, 1e-14, 1e-13):", "if False and not close(mapping(recur_y, lambda x:x.v), accepted_y, 1e-14, 1e-13):", 'OUTPUT_CROSSCHECK_GUARANTEE'),
        'drop-state': ("if not close(mapping(state, lambda x:x.v), accepted_state, 1e-14, 1e-13):", "if False and not close(mapping(state, lambda x:x.v), accepted_state, 1e-14, 1e-13):", 'STATE_CROSSCHECK_GUARANTEE')}

    def run_child(self, variant, mode, root):
        outdir = EVIDENCE / 'matrix' / variant / mode; outdir.mkdir(parents=True, exist_ok=True)
        argv = [sys.executable] + (['-O'] if mode == 'optimized' else []) + [str(Path(__file__).resolve())]
        env = dict(os.environ, PULSAR_VARIANT_ROOT=str(root), PULSAR_INNER='1')
        started = time.time(); process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                                           text=True, env=env, start_new_session=True)
        timed_out = False
        try: stdout, stderr = process.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            timed_out = True; os.killpg(process.pid, signal.SIGTERM)
            try: stdout, stderr = process.communicate(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL); stdout, stderr = process.communicate()
        (outdir / 'stdout.txt').write_text(stdout); (outdir / 'stderr.txt').write_text(stderr)
        record = {'argv': argv, 'elapsed': time.time() - started, 'exit': process.returncode,
                  'timeout': timed_out, 'stdout_sha256': hashlib.sha256(stdout.encode()).hexdigest(),
                  'stderr_sha256': hashlib.sha256(stderr.encode()).hexdigest()}
        (outdir / 'result.json').write_text(json.dumps(record, sort_keys=True, indent=2) + '\n')
        return record, stdout, stderr

    def test_fourteen_cells_and_canaries(self):
        raw = ORACLE.read_text(); roots = {'canonical': SOURCE}
        temp = EVIDENCE / 'temp'; temp.mkdir(parents=True, exist_ok=True)
        for name, (before, after, guarantee) in self.MUTANTS.items():
            self.assertEqual(raw.count(before), 1, name + '_SINGLE_SITE')
            root = temp / name; target = root / 'scripts/research/glm53_flash/linear_attention'; target.mkdir(parents=True, exist_ok=True)
            recurrent = root / 'scripts/research/glm53_flash/recurrent_dispatch'; recurrent.mkdir(parents=True, exist_ok=True)
            changed = raw.replace(before, after); (target / 'oracle.py').write_text(changed); shutil.copy2(RECURRENT, recurrent / 'oracle.py')
            patch = ''.join(difflib.unified_diff(raw.splitlines(True), changed.splitlines(True), fromfile='oracle.py', tofile=name + '/oracle.py'))
            (EVIDENCE / 'matrix' / name).mkdir(parents=True, exist_ok=True); (EVIDENCE / 'matrix' / name / 'mutation.patch').write_text(patch)
            roots[name] = root
        for name, root in roots.items():
            for mode in ('normal', 'optimized'):
                record, stdout, stderr = self.run_child(name, mode, root)
                self.assertFalse(record['timeout'], name + ':' + mode + ':TIMEOUT')
                if name == 'canonical': self.assertEqual(record['exit'], 0, stdout + stderr)
                else:
                    self.assertNotEqual(record['exit'], 0, name + ':' + mode + ':SURVIVOR')
                    self.assertIn(self.MUTANTS[name][2], stderr, name + ':' + mode + ':WRONG_KILL')
        for mode, optimized, expected_assert in (('normal', False, 1), ('optimized', True, 0)):
            args = [sys.executable] + (['-O'] if optimized else []) + ['-c', 'assert False']
            self.assertEqual(subprocess.run(args, timeout=30).returncode, expected_assert)
            args[-1] = "import unittest;unittest.TestCase().fail('OPT_CANARY')"
            self.assertNotEqual(subprocess.run(args, timeout=30).returncode, 0)


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(FixedContract if os.environ.get('PULSAR_INNER') else Matrix)
    raise SystemExit(0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1)
