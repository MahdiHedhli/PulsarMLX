"""Offline (mlx-free) checks for the Glm5NextMoE research track.

The supervised `successor.py moe` operation is the qualification; this module
only pins what can be checked from the stdlib: the frozen fixture recomputes
from the independent oracle, the retained switch-layer/capsule texts pass their
digest and global-census admission, every frozen mutant recipe hits its needle
exactly as the matrix records and is refused by the capsule verifier, and the
matrix keys equal the recipe labels in `controls.py` (read as text, never
executed here).
"""
import ast
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from scripts.research.glm53_flash.decoder_ffn import source as ffn_source  # noqa: E402
from scripts.research.glm53_flash.decoder_moe import oracle as moe_oracle  # noqa: E402
from scripts.research.glm53_flash.decoder_moe import source as moe_source  # noqa: E402
from scripts.research.glm53_flash.router_caller import rc_oracle  # noqa: E402

FIXTURE = ROOT / 'fixtures/research/glm53-flash-decoder-moe-v1/fixtures.json'
CONTROLS = ROOT / 'scripts/research/glm53_flash/decoder_moe/controls.py'
CELLS = ('KILL', 'INACTIVE', 'WEAK_STRUCTURAL')


def _recipes():
    # The literal `recipes = [...]` list inside test_semantic_mutants, by AST.
    tree = ast.parse(CONTROLS.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and getattr(node.targets[0], 'id', None) == 'recipes':
            return [tuple(ast.literal_eval(e)) for e in node.value.elts]
    raise AssertionError('recipes literal not found')


class DecoderMoEOffline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(FIXTURE.read_bytes())
        cls.capsule_raw = (ROOT / moe_source.CAPSULE).read_bytes()
        cls.language_raw = (ROOT / ffn_source.LANGUAGE).read_bytes()
        cls.switch_raw = (ROOT / moe_source.SWITCH).read_bytes()

    def test_mlx_not_imported(self):
        self.assertNotIn('mlx', sys.modules)
        self.assertNotIn('mlx.core', sys.modules)

    def test_frozen_expected_recomputes(self):
        for case in self.fixture['cases']:
            got = moe_oracle.run(case, rc_oracle.reference)
            self.assertEqual(got, self.fixture['expected'][case['fixture_id']], case['fixture_id'])
            for tok in got['tokens']:
                self.assertGreaterEqual(tok['selection_margin'], 1e-3)

    def test_switch_and_capsule_admission(self):
        nodes, digests = moe_source.verify_switch(self.switch_raw, ffn_source)
        self.assertEqual([n.name for n in nodes], list(moe_source.SWITCH_NODES))
        self.assertEqual(sorted(digests), sorted(moe_source.SWITCH_NODES))
        node, contract = moe_source.verify_capsule(self.capsule_raw, self.language_raw, ffn_source)
        self.assertEqual(node.name, 'source_moe')
        self.assertEqual(contract['digest_scheme'], ffn_source.DIGEST_SCHEME)
        self.assertNotEqual(contract['original_ast_sha256'], contract['capsule_ast_sha256'])

    def test_matrix_is_frozen_and_recipes_match(self):
        matrix = self.fixture['expected_kill_matrix']
        self.assertTrue(matrix['frozen_before_tests'])
        self.assertEqual(matrix['fixtures'], [c['fixture_id'] for c in self.fixture['cases']])
        self.assertEqual(matrix['kill_margin_factor'], 10)
        recipes = _recipes()
        self.assertEqual([r[0] for r in recipes], list(matrix['matrix']))
        self.assertEqual(set(matrix['matrix']), set(matrix['needle_counts']))
        self.assertEqual(set(matrix['matrix']), set(matrix['reasoning']))
        text = self.capsule_raw.decode()
        for label, before, after in recipes:
            cells = matrix['matrix'][label]
            self.assertEqual(len(cells), len(self.fixture['cases']), label)
            self.assertTrue(all(c in CELLS for c in cells), label)
            self.assertEqual(text.count(before), matrix['needle_counts'][label], label)
            mutated = text.replace(before, after, 1).encode()
            self.assertNotEqual(mutated, self.capsule_raw, label)
            with self.assertRaisesRegex(ValueError, 'DECODER_MOE_(CALLER_TRANSFORM|CLOSURE)'):
                moe_source.verify_capsule(mutated, self.language_raw, ffn_source)

    def test_tampered_texts_are_refused(self):
        with self.assertRaisesRegex(ValueError, 'DECODER_MOE_SWITCH_DIGEST'):
            moe_source.verify_switch(self.switch_raw + b'\n', ffn_source)
        with self.assertRaisesRegex(ValueError, 'DECODER_MOE_UPSTREAM_DIGEST'):
            moe_source.verify_capsule(self.capsule_raw, self.language_raw + b'\n', ffn_source)


if __name__ == '__main__':
    unittest.main()
