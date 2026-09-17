"""Offline (mlx-free) checks for the long-sequence linear-attention track: the frozen fixtures recompute from the chunked
composition of the accepted reference; every chunk is <= 5 tokens (the accepted reference's domain is untouched); the
carried caches are fp32-exact; the reference radii stay under the tolerance; the kernel admission default is still 5."""
import json
import struct
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.research.glm53_flash.linear_long import oracle as long_oracle  # noqa: E402

FIXTURE = ROOT / 'fixtures/research/glm53-flash-linear-long-v1/fixtures.json'
SOURCE = ROOT / 'scripts/research/glm53_flash/linear_attention/source.py'


def _fp32_exact(v):
    return all(_fp32_exact(x) for x in v) if isinstance(v, list) else struct.unpack('f', struct.pack('f', v))[0] == v


class LinearLongOffline(unittest.TestCase):
    def test_mlx_not_imported(self):
        self.assertNotIn('mlx', sys.modules)

    def test_frozen_expected_recomputes(self):
        fx = json.loads(FIXTURE.read_bytes())
        self.assertEqual([c['tokens'] for c in fx['cases']], [8, 16, 33, 64])
        for case in fx['cases']:
            exp = fx['expected'][case['fixture_id']]
            self.assertEqual(long_oracle.run(case), exp, case['fixture_id'])
            self.assertTrue(all(len(c['tokens']) <= long_oracle.CHUNK for c in exp['chunks']))
            self.assertTrue(all(_fp32_exact(c['cache0_after']) and _fp32_exact(c['cache1_after']) for c in exp['chunks']))
            self.assertTrue(all(v < 1e-4 for v in exp['maximum_radii_over_chunks'].values()))
            self.assertTrue(all(abs(v) <= 1 for row in case['inputs'] for v in row))

    def test_kernel_admission_default_unchanged(self):
        src = SOURCE.read_text()
        self.assertIn('def kernel_buffers(arguments, input_names, max_sequence=5):', src)
        self.assertIn('def load(context, fixture, mutation=None, max_sequence=5):', src)
        self.assertIn('1<=S<=max_sequence', src)


if __name__ == '__main__':
    unittest.main()
