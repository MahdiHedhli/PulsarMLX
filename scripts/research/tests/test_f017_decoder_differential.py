"""glm52-weekend W3: the decoder-differential driver generates valid synthetic blocks for every checkpoint format under the
corrected oracle's independent decoders, and - when the Rust producer is built - the exact loader dispatch matches them
bit-for-bit; the harness negative control (a lane swap) is flagged. Producer-dependent parts skip when the binary is absent."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DRIVER = ROOT / 'scripts/research/f017_decoder_differential_v1.py'
BIN = os.environ.get('F017_DECODER_DIFFERENTIAL_BIN') or shutil.which('f017-native-decoder-differential')


class DecoderDifferential(unittest.TestCase):
    def test_generate_valid_cases_for_every_format(self):
        d = tempfile.mkdtemp(); cases = Path(d) / 'cases.json'
        p = subprocess.run([sys.executable, '-I', '-B', str(DRIVER), 'generate', str(cases), '--seed', '3'], capture_output=True, text=True, timeout=600)
        self.assertEqual(p.returncode, 0, p.stderr[-500:])
        c = json.load(open(cases)); self.assertEqual(len(c['formats']), 11); self.assertEqual(len(c['cases']), 33)
        sys.path.insert(0, str(ROOT / 'scripts/research')); import f017_oracle_primary_decoders as oracle
        for case in c['cases']:
            vals = oracle.decode(case['format'], bytes.fromhex(case['bytes_hex']), case['rows'] * case['columns'])
            self.assertEqual(len(vals), case['rows'] * case['columns'])

    @unittest.skipUnless(BIN, 'f017-native-decoder-differential binary not available')
    def test_producer_matches_oracle(self):
        d = tempfile.mkdtemp(); cases, produced, report = (Path(d) / n for n in ('cases.json', 'produced.json', 'report.json'))
        subprocess.run([sys.executable, '-I', '-B', str(DRIVER), 'generate', str(cases), '--seed', '11'], check=True, timeout=600)
        subprocess.run([BIN, str(cases), str(produced)], check=True, timeout=600)
        p = subprocess.run([sys.executable, '-I', '-B', str(DRIVER), 'compare', str(cases), str(produced), str(report)], capture_output=True, text=True, timeout=600)
        self.assertEqual(p.returncode, 0, p.stdout[-800:]); r = json.load(open(report)); self.assertEqual(r['verdict'], 'PASS'); self.assertTrue(r['negative_control']['flagged'])


if __name__ == '__main__':
    unittest.main()
