"""Stdlib cache admission controls; no model, MLX import or candidate outputs."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import types
import unittest

ROOT = Path(__file__).resolve().parents[3]
CACHE = ROOT / 'scripts/research/glm53_flash/cache_lifecycle'
FIXTURE = ROOT / 'fixtures/research/glm53-flash-cache-lifecycle-v1/fixtures.json'


def load(path):
    spec = importlib.util.spec_from_file_location('cache_contract_' + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CacheContract(unittest.TestCase):
    def setUp(self):
        self.fixture = json.loads(FIXTURE.read_bytes())

    def context(self, replacements):
        return types.SimpleNamespace(roots={'code': ROOT, 'upstream': ROOT},
                                     read_verified=lambda p: replacements[p] if p in replacements else p.read_bytes())

    def test_repinned_changed_class_still_fails_original_ast(self):
        raw = (CACHE / 'capsule.py').read_bytes()
        changed = raw.replace(b'return self.cache[idx]', b'return self.cache[0]')
        self.assertNotEqual(changed, raw)
        provenance = json.loads((CACHE / 'provenance.json').read_bytes())
        provenance['capsule_sha256'] = hashlib.sha256(changed).hexdigest()
        pbytes = json.dumps(provenance).encode()
        fixture = copy.deepcopy(self.fixture)
        fixture['cache_capsule_sha256'] = hashlib.sha256(changed).hexdigest()
        fixture['cache_provenance_sha256'] = hashlib.sha256(pbytes).hexdigest()
        context = self.context({CACHE / 'capsule.py': changed, CACHE / 'provenance.json': pbytes})
        with self.assertRaisesRegex(ValueError, '^CACHE_SOURCE_AST_OR_SPAN$'):
            load(CACHE / 'source.py').load(context, fixture)

    def test_unrepinned_source_is_rejected_before_import(self):
        context = self.context({CACHE / 'capsule.py': (CACHE / 'capsule.py').read_bytes() + b'\n'})
        with self.assertRaisesRegex(ValueError, '^CACHE_SOURCE_BINDING$'):
            load(CACHE / 'source.py').load(context, self.fixture)

    def test_frozen_expectations_and_domain(self):
        self.assertEqual(hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
                         'b26a06902aae5786a99ec49cc1b69f6d6843b05c9a16a5a96fe7674fa142ec3f')
        self.assertEqual({case['K'] for case in self.fixture['cases']}, {2, 3, 4})
        for case in self.fixture['cases']:
            self.assertGreater(case['K'], 1)
            self.assertLessEqual(case['T'], 7)
            for chunks in case['partitions']:
                self.assertEqual(sum(chunks), case['T'])
                self.assertTrue(all(type(x) is int and x > 0 for x in chunks))
        self.assertEqual(self.fixture['cache_expectations']['advance']['lengths_after'], [5, 3])

    def test_cache_producer_requires_exact_checks(self):
        entry = load(ROOT / 'scripts/research/glm53_flash/router_caller/successor.py')
        ids = ['test_batch_lifecycle_composition', 'test_cache_bookkeeping_composition',
               'test_cache_construction_alias_and_errors', 'test_classifier',
               'test_interleaved_new_cache', 'test_mutations', 'test_partitions',
               'test_research_refusal_and_callee_failure']
        result = {'event': 'result', 'status': 'PASS', 'tests_run': 8, 'test_ids': ids,
                  'skips': 0, 'failures': 0, 'errors': 0}
        def accepted(value):
            stdout = (json.dumps(value) + '\n').encode()
            stderr = b''
            stop = {'exit_code': 0, 'stop_confirmed': True, 'capture_complete': True,
                    'direct_child_reaped': True, 'process_group_absent': True, 'reason': None,
                    'outputs': {name: {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
                                for name, raw in [('stdout', stdout), ('stderr', stderr)]}}
            return entry.producer_pass(stdout, stderr, stop, 'cache')
        self.assertTrue(accepted(result))
        for replacement in [ids[:-1], ids[::-1], ['unrelated'] * 8]:
            self.assertFalse(accepted(dict(result, test_ids=replacement)))
        self.assertFalse(accepted(dict(result, tests_run=True)))
        self.assertFalse(accepted(dict(result, skips=1)))


if __name__ == '__main__':
    unittest.main()
