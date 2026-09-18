"""Offline (stdlib) truth table of the dogfood server's speculative preflight (graph 34): greedy only, prompt within the
speculator's one-chunk limit (4095 / 4096 / 4097 at a 4096 limit), no speculator -> ineligible."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts/research/glm53_flash/dogfood'))
import serve_policy  # noqa: E402


class SpeculativePreflight(unittest.TestCase):
    def test_mlx_not_imported(self):
        self.assertNotIn('mlx', sys.modules)

    def test_boundaries(self):
        for n, want in ((0, True), (1, True), (4095, True), (4096, True), (4097, False), (5000, False)):
            ok, why = serve_policy.speculative_eligible(True, 0.0, None, None, n, 4096)
            self.assertEqual(ok, want, (n, why))
            if not want:
                self.assertIn('one-chunk limit 4096', why)
        ok, why = serve_policy.speculative_eligible(True, 0.0, None, None, 512, 512); self.assertTrue(ok)
        ok, why = serve_policy.speculative_eligible(True, 0.0, None, None, 513, 512); self.assertFalse(ok)

    def test_sampling_and_absence(self):
        self.assertFalse(serve_policy.speculative_eligible(False, 0.0, None, None, 10, 4096)[0])
        self.assertFalse(serve_policy.speculative_eligible(True, 0.7, None, None, 10, 4096)[0])
        self.assertFalse(serve_policy.speculative_eligible(True, 0.0, 0.9, None, 10, 4096)[0])
        self.assertFalse(serve_policy.speculative_eligible(True, 0.0, None, 1.1, 10, 4096)[0])
        self.assertTrue(serve_policy.speculative_eligible(True, 0.0, None, None, 10, 4096)[0])
        reasons = {serve_policy.speculative_eligible(*a)[1] for a in ((False, 0.0, None, None, 1, 4096), (True, 0.5, None, None, 1, 4096), (True, 0.0, 0.9, None, 1, 4096), (True, 0.0, None, 1.1, 1, 4096), (True, 0.0, None, None, 9999, 4096))}
        self.assertEqual(len(reasons), 5, 'every ineligibility has its own reason')


if __name__ == '__main__':
    unittest.main()
