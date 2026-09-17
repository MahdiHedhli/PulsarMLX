"""Offline (mlx-free) checks for the quantized-load track: the fixture's quantization block covers exactly the declared modules
with groupable widths; the expected structural sets are consistent; the controls list the structural controls."""
import ast
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / 'fixtures/research/glm53-flash-decoder-quantized-load-v1/fixtures.json'
CONTROLS = ROOT / 'scripts/research/glm53_flash/decoder_quantized_load/controls.py'


class DecoderQuantizedLoadOffline(unittest.TestCase):
    def test_mlx_not_imported(self):
        self.assertNotIn('mlx', sys.modules)

    def test_fixture_consistency(self):
        fx = json.loads(FIXTURE.read_bytes()); case = fx['cases'][0]; exp = fx['expected'][case['fixture_id']]; q = case['config']['quantization']
        per_path = {k: v for k, v in q.items() if isinstance(v, dict)}
        self.assertEqual(sorted(per_path), sorted(exp['quantized_modules_8bit']))
        self.assertTrue(all(v['bits'] == 8 and v['group_size'] in (32, 64) for v in per_path.values()))
        self.assertEqual((q['group_size'], q['bits']), (64, 4))
        self.assertEqual(exp['scales_present_for'], sorted(exp['quantized_modules_8bit'] + exp['quantized_modules_4bit']))
        self.assertEqual(case['kv_b']['group_size'], 32); self.assertIn('revision', fx)
        self.assertIn('no numeric oracle', fx['scope'])

    def test_structural_controls_listed(self):
        fx = json.loads(FIXTURE.read_bytes()); text = CONTROLS.read_text()
        for label in fx['structural_controls']:
            self.assertIn(f"outcomes['{label}']", text, label)


if __name__ == '__main__':
    unittest.main()
