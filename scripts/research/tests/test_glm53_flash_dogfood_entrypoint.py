"""Offline checks of the dogfood entrypoint's pure helpers (no mlx, no weights)."""
import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.research.glm53_flash.dogfood import run_offload  # noqa: E402


class DogfoodEntrypoint(unittest.TestCase):
    def test_mlx_not_imported(self):
        self.assertNotIn('mlx', sys.modules)

    def test_budget_rule(self):
        self.assertAlmostEqual(run_offload.expert_budget_gb(128), 0.8 * 0.75 * 128 - 18, places=6)
        self.assertEqual(run_offload.expert_budget_gb(16), 0.0)

    def test_eager_ffn_applied_only_to_patched_layers(self):
        class OffloadedSwitchGLU:  # name is what the helper keys on
            store = 'S'
        L = lambda switch: types.SimpleNamespace(mlp=types.SimpleNamespace(switch_mlp=switch), compile_ffn=True, _ffn_c='compiled')
        lm = types.SimpleNamespace(model=types.SimpleNamespace(layers=[L(object()), L(OffloadedSwitchGLU()), types.SimpleNamespace(mlp=object(), compile_ffn=True, _ffn_c='c')]))
        self.assertEqual(run_offload.apply_eager_ffn_on_patched_layers(lm), 1)
        self.assertEqual([getattr(l, 'compile_ffn') for l in lm.model.layers], [True, False, True])
        self.assertEqual(run_offload.find_store(lm), 'S')


if __name__ == '__main__':
    unittest.main()
