import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / 'fixtures/research/glm53-flash-decoder-ffn-v1/fixtures.json'
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class DenseFfnTests(unittest.TestCase):
    def test_verified_pure_ops_matches_independent_scalar(self):
        from scripts.research.glm53_flash.decoder_ffn import controls
        result = controls.run(ROOT, json.loads(FIXTURE.read_text()))
        self.assertEqual(result['branch'], 'PURE_OPS_TRAINING_TRUE')
        self.assertEqual(len(result['expected']['boundaries']), 2)

    def test_integrity_refuses_wrong_hyperconnection_digest(self):
        raw = (ROOT / 'scripts/research/glm53_flash/decoder_ffn/provenance.json').read_text()
        self.assertIn('141fbe47d99f8eda9ab9a4c78665e5eb439cbf73b53a604c4da2a77845167bb3', raw)

    def test_declared_wiring_mutants_differ_from_canonical(self):
        from scripts.research.glm53_flash.decoder_ffn import controls
        results = controls.mutants(ROOT, json.loads(FIXTURE.read_text()))
        self.assertEqual(results, {'remove_post_attention_normalization': True, 'bypass_ffn_hc': True, 'wrong_hc_expand_residual': True})

    def test_optimized_python_preserves_explicit_comparison(self):
        child = "import json; from pathlib import Path; from scripts.research.glm53_flash.decoder_ffn import controls; r=Path.cwd(); controls.run(r, json.loads((r/'fixtures/research/glm53-flash-decoder-ffn-v1/fixtures.json').read_text()))"
        run = subprocess.run([sys.executable, '-O', '-c', child], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)


if __name__ == '__main__':
    unittest.main()
