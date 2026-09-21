"""Offline (mlx-free) checks for the loading-path track: the fixture's config is groupable and consistent with the graph-15
arrays; the admission's node set and omitted imports are as declared; the structural controls are the recipes in controls.py."""
import ast
import hashlib
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.research.glm53_flash.decoder_load_offload import source as load_source  # noqa: E402
from scripts.research.glm53_flash.decoder_offload import source as offload_source  # noqa: E402
from scripts.research.glm53_flash.decoder_ffn import source as ffn_source  # noqa: E402

FIXTURE = ROOT / 'fixtures/research/glm53-flash-decoder-load-offload-v1/fixtures.json'
CONTROLS = ROOT / 'scripts/research/glm53_flash/decoder_load_offload/controls.py'


class DecoderLoadOffloadOffline(unittest.TestCase):
    def test_mlx_not_imported(self):
        self.assertNotIn('mlx', sys.modules)

    def test_fixture_consistency(self):
        fx = json.loads(FIXTURE.read_bytes()); case = fx['cases'][0]; cfg = case['config']; q = case['expert_config']
        self.assertEqual(cfg['hidden_size'], q['hidden']); self.assertEqual(cfg['moe_intermediate_size'], q['intermediate']); self.assertEqual(cfg['n_routed_experts'], q['num_experts'])
        self.assertEqual(cfg['quantization'], {'group_size': q['group_size'], 'bits': q['bits'], 'mode': 'affine'})
        self.assertEqual(cfg['hidden_size'] % q['group_size'], 0); self.assertEqual(cfg['moe_intermediate_size'] % q['group_size'], 0)
        self.assertEqual(len(case['quantized_experts']['gate']), q['num_experts'])
        self.assertIn('no numeric oracle', fx['scope'])

    def test_admission_static(self):
        offload_raw = (ROOT / offload_source.OFFLOAD).read_bytes(); one_bit_raw = (ROOT / load_source.ONE_BIT).read_bytes()
        self.assertEqual(hashlib.sha256(one_bit_raw).hexdigest(), load_source.ONE_BIT_SHA256)
        nodes, constants, q, patched, contract = load_source.verify(offload_raw, one_bit_raw, ffn_source, offload_source)
        self.assertEqual(sorted(nodes), sorted(load_source.NODES)); self.assertEqual(contract['omitted_function_body_imports'], list(load_source.OMITTED_IMPORTS))
        self.assertFalse(any(isinstance(s, ast.ImportFrom) for s in patched.body))
        with self.assertRaisesRegex(ValueError, 'DECODER_LOAD_OFFLOAD_DIGEST'):
            load_source.verify(offload_raw + b'\n', one_bit_raw, ffn_source, offload_source)

    def test_structural_controls_listed(self):
        fx = json.loads(FIXTURE.read_bytes()); tree = ast.parse(CONTROLS.read_text())
        recipes = next(ast.literal_eval(n.value) for n in ast.walk(tree) if isinstance(n, ast.Assign) and getattr(n.targets[0], 'id', None) == 'recipes')
        self.assertEqual(sorted(r[0] for r in recipes), sorted(fx['structural_controls']))
        text = (ROOT / offload_source.OFFLOAD).read_text()
        for label, before, after in recipes:
            self.assertEqual(text.count(before), 1, label)


if __name__ == '__main__':
    unittest.main()
