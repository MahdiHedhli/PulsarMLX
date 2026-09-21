"""Offline (mlx-free) checks for the sanitize research track: the frozen checkpoint fixture recomputes from the
reference; the parameter set has 58 entries with fp32 dtypes for the FP32 suffixes; the dropped keys are the MTP
layer and the 'mtp.' key; the prospective matrix reproduces from the recorded oracle variants; recipes hit their
needles in the stack capsule / the retained DeepSeek-V3.2 text and are refused by the verifiers."""
import ast
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.research.glm53_flash.decoder_ffn import source as ffn_source  # noqa: E402
from scripts.research.glm53_flash.decoder_stack import source as stack_source  # noqa: E402
from scripts.research.glm53_flash.decoder_stack_sanitize import oracle as sanitize_oracle  # noqa: E402

FIXTURE = ROOT / 'fixtures/research/glm53-flash-decoder-stack-sanitize-v1/fixtures.json'
CONTROLS = ROOT / 'scripts/research/glm53_flash/decoder_stack_sanitize/controls.py'
DSV32 = ROOT / 'scripts/research/glm53_flash/decoder_moe/upstream-dsv32-language.txt'


def _recipes():
    tree = ast.parse(CONTROLS.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and getattr(node.targets[0], 'id', None) == 'recipes':
            return [tuple(ast.literal_eval(e)) for e in node.value.elts]
    raise AssertionError('recipes literal not found')


class DecoderStackSanitizeOffline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(FIXTURE.read_bytes()); cls.case = cls.fixture['cases'][0]
        cls.expected = cls.fixture['expected'][cls.case['fixture_id']]
        cls.capsule_raw = (ROOT / stack_source.CAPSULE).read_bytes(); cls.language_raw = (ROOT / ffn_source.LANGUAGE).read_bytes()

    def test_mlx_not_imported(self):
        self.assertNotIn('mlx', sys.modules)

    def test_frozen_expected_recomputes(self):
        got = sanitize_oracle.run(self.case['checkpoint'], self.case['config'])
        self.assertEqual(got['parameters'], self.expected['parameters']); self.assertEqual(got['dropped_keys'], self.expected['dropped_keys'])
        self.assertEqual(len(got['parameters']), 58)
        self.assertEqual(got['dropped_keys'], ['model.layers.2.mlp.gate_proj.weight', 'model.layers.2.self_attn.q_proj.weight', 'model.mtp.embed_tokens.weight'])
        for k, v in got['parameters'].items():
            self.assertEqual(v['dtype'], 'float32', k)
        self.assertEqual([e['dtype'] for e in self.case['checkpoint'] if e['key'].endswith(('A_log', 'dt_bias'))], ['bfloat16', 'bfloat16'])
        self.assertIn('model.layers.0.self_attn.conv1d.weight', got['parameters']); self.assertIn('model.layers.1.self_attn.embed_q.weight', got['parameters'])
        self.assertIn('model.layers.1.mlp.switch_mlp.gate_proj.weight', got['parameters'])

    def test_matrix_prospective_and_recipes(self):
        matrix = self.fixture['expected_kill_matrix']
        self.assertTrue(matrix['frozen_before_tests'] and matrix['prospective_from_oracle_variants'])
        recipes = _recipes()
        self.assertEqual(sorted(r[0] for r in recipes), sorted(matrix['matrix']))
        capsule_text = self.capsule_raw.decode(); oracle_text = Path(sanitize_oracle.__file__).read_text()
        dsv32_text = DSV32.read_text() if DSV32.exists() else None
        for label, target, before, after in recipes:
            self.assertEqual(matrix['matrix'][label], ['KILL'], label)
            if target == 'capsule':
                self.assertEqual(capsule_text.count(before), matrix['needle_counts'][label], label)
                with self.assertRaisesRegex(ValueError, 'DECODER_STACK_(CALLER_TRANSFORM|CLOSURE)'):
                    stack_source.verify_capsule(capsule_text.replace(before, after, 1).encode(), self.language_raw, ffn_source)
            elif dsv32_text is not None:
                self.assertEqual(dsv32_text.count(before), matrix['needle_counts'][label], label)
            v = matrix['oracle_variants'][label]; self.assertEqual(oracle_text.count(v['before']), 1, label)
            ns = {'__name__': 'variant'}; exec(compile(oracle_text.replace(v['before'], v['after']), 'variant:' + label, 'exec'), ns)
            out = ns['run'](self.case['checkpoint'], self.case['config'])['parameters']
            self.assertNotEqual(out, self.expected['parameters'], label)


if __name__ == '__main__':
    unittest.main()
