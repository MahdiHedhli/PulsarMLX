"""Offline (mlx-free) checks for the topology track: the frozen fixture's pattern equals the retained upstream config's
(by digest and field), the schedule stays inside the admitted linear kernel domain, and the structural controls are the
recipes in controls.py."""
import ast
import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / 'fixtures/research/glm53-flash-decoder-topology-v1/fixtures.json'
UPSTREAM = ROOT / 'scripts/research/glm53_flash/decoder_topology/upstream-config.json'
CONTROLS = ROOT / 'scripts/research/glm53_flash/decoder_topology/controls.py'


class DecoderTopologyOffline(unittest.TestCase):
    def test_mlx_not_imported(self):
        self.assertNotIn('mlx', sys.modules)

    def test_pattern_equals_retained_config(self):
        fx = json.loads(FIXTURE.read_bytes()); raw = UPSTREAM.read_bytes(); tc = json.loads(raw); tc = tc.get('text_config', tc)
        self.assertEqual(fx['upstream_config_sha256'], hashlib.sha256(raw).hexdigest())
        cfg = fx['cases'][0]['config']
        for k in fx['pattern_keys']:
            if k != 'num_experts_per_tok':
                self.assertEqual(cfg[k], tc[k], k)
        self.assertEqual(cfg['num_hidden_layers'], 45); self.assertEqual(sum(t == 'linear_attention' for t in cfg['layer_types']), 34)
        exp = fx['expected']['topology-45-layers-tiny']
        self.assertEqual(exp['sparse_layers'], [3, 7, 11, 15, 19, 23, 27, 31, 35, 39, 43]); self.assertEqual(len(exp['moe_layers']), 42)
        sched = fx['cases'][0]['schedule']
        self.assertLessEqual(sched['prefill_tokens'], 5); self.assertEqual(len(sched['ids']), sched['prefill_tokens'] + sched['decode_tokens'])
        self.assertTrue(any(v == 'sparse' for v in exp['indexer_regime_by_T'].values()))
        self.assertIn('no numeric reference', fx['scope'])

    def test_structural_controls_listed(self):
        fx = json.loads(FIXTURE.read_bytes()); tree = ast.parse(CONTROLS.read_text())
        recipes = next(ast.literal_eval(n.value) for n in ast.walk(tree) if isinstance(n, ast.Assign) and getattr(n.targets[0], 'id', None) == 'recipes')
        self.assertEqual(sorted(r[0] for r in recipes), sorted(fx['structural_controls']))


if __name__ == '__main__':
    unittest.main()
