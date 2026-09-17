"""Offline (mlx-free) checks for the PulsarExpertStore track: the fixture recomputes from the LFU model; LFU beats LRU on both
cases; the prospective controls reproduce from the recorded variants; the store file's needles exist."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.research.glm53_flash.decoder_offload import oracle as lru_oracle  # noqa: E402
from scripts.research.glm53_flash.decoder_offload_pulsar import oracle as pulsar_oracle  # noqa: E402
from scripts.research.glm53_flash.decoder_offload_pulsar import generate_fixtures as generator  # noqa: E402

FIXTURE = ROOT / 'fixtures/research/glm53-flash-decoder-offload-pulsar-v1/fixtures.json'
STORE = ROOT / 'scripts/research/glm53_flash/dogfood/pulsar_expert_store.py'


class PulsarStoreOffline(unittest.TestCase):
    def test_mlx_not_imported(self):
        self.assertNotIn('mlx', sys.modules)

    def test_frozen_expected_recomputes_and_beats_lru(self):
        fx = json.loads(FIXTURE.read_bytes())
        for case in fx['cases']:
            exp = fx['expected'][case['fixture_id']]; got = pulsar_oracle.run(case)
            self.assertEqual(got, {k: v for k, v in exp.items() if k in got})
            lru = lru_oracle.run({**case, 'schedule': case['schedule']})
            self.assertEqual(lru['final_stats'], exp['lru_final_stats'])
            self.assertGreater(exp['final_stats']['hits'], lru['final_stats']['hits'])

    def test_controls_prospective(self):
        fx = json.loads(FIXTURE.read_bytes()); matrix = fx['expected_kill_matrix']
        text = Path(pulsar_oracle.__file__).read_text()
        cases = fx['cases']; expected = fx['expected']
        predicted = generator.predicted_cells(cases, expected, {k: (v['before'], v['after']) for k, v in matrix['oracle_variants'].items()}, text)
        self.assertEqual(predicted, matrix['matrix'])
        store = STORE.read_text()
        for needle in ('self._counts[k] *= self.decay', 'self._touch.get(key, 0))', 'self._warm_admitted = self._admit_warm_state()'):
            self.assertEqual(store.count(needle), 1, needle)


if __name__ == '__main__':
    unittest.main()
