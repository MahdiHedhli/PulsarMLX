"""Offline (stdlib) checks of the termination policy (unpruned-persistent G54): terminal ids come from the checkpoint
config and must be control tokens; the matcher stops at the first terminal id and never after it; legacy policy is the
tokenizer eos only; fake-generator streams reproduce the historical fault and the correction; streaming/non-streaming
parity through the shared truncation."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts/research/glm53_flash/dogfood'))
import stop_policy as sp  # noqa: E402

EOT, USER, OBS, ASSIST, THINK_END = 154820, 154827, 154829, 154828, 154842


class FakeTok:
    eos_token_id = EOT
    all_special_ids = [EOT, USER, OBS, ASSIST, THINK_END]
    added_tokens_decoder = {EOT: {'content': '<|endoftext|>'}, USER: {'content': '<|user|>'}, OBS: {'content': '<|observation|>'}, ASSIST: {'content': '<|assistant|>'}, THINK_END: {'content': '</think>'}}
    names = {EOT: '<|endoftext|>', USER: '<|user|>', OBS: '<|observation|>', ASSIST: '<|assistant|>', THINK_END: '</think>', 5: 'hello', 6: 'world', 7: '.'}

    def convert_ids_to_tokens(self, i):
        return self.names.get(i, f'tok{i}')


class FakeCriteria:
    def __init__(self):
        self.eos_token_ids = [EOT]

    def reset(self, ids):
        self.eos_token_ids = list(ids)

    def __call__(self, t):
        return t in self.eos_token_ids


class FakeProcessor:
    def __init__(self):
        self.tokenizer = FakeTok(); self.tokenizer.stopping_criteria = FakeCriteria()


def fake_stream(ids, criteria):
    """mlx-vlm's loop shape: the token is produced, checked, and not yielded when terminal; nothing after it."""
    out = []
    for t in ids:
        if criteria(t):
            return out, 'stop'
        out.append(t)
    return out, 'length'


class StopPolicy(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(); json.dump({'eos_token_id': [EOT, USER, OBS], 'text_config': {}}, open(os.path.join(self.dir, 'config.json'), 'w'))

    def test_mlx_not_imported(self):
        self.assertNotIn('mlx', sys.modules)

    def test_terminal_ids_from_config_and_verification(self):
        pol = sp.build(self.dir, FakeTok())
        self.assertEqual(pol['version'], 'glm5-eos-v1'); self.assertEqual(pol['terminal_ids'], [EOT, USER, OBS]); self.assertEqual(pol['names'][USER], '<|user|>')
        json.dump({'text_config': {'eos_token_id': 154820}}, open(os.path.join(self.dir, 'config.json'), 'w'))
        self.assertEqual(sp.build(self.dir, FakeTok())['terminal_ids'], [EOT])
        json.dump({'eos_token_id': [EOT, 5]}, open(os.path.join(self.dir, 'config.json'), 'w'))
        with self.assertRaisesRegex(ValueError, 'TERMINAL_ID_NOT_SPECIAL'):
            sp.build(self.dir, FakeTok())
        json.dump({}, open(os.path.join(self.dir, 'config.json'), 'w'))
        with self.assertRaisesRegex(ValueError, 'EOS_TOKEN_ID_MISSING'):
            sp.build(self.dir, FakeTok())
        with self.assertRaises(ValueError):
            sp.build(self.dir, FakeTok(), version='nope')

    def test_legacy_policy_is_tokenizer_eos_only(self):
        pol = sp.build(self.dir, FakeTok(), version=sp.LEGACY_VERSION)
        self.assertEqual(pol['terminal_ids'], [EOT])

    def test_apply_installs_into_criteria_and_reads_back(self):
        proc = FakeProcessor(); pol = sp.build(self.dir, FakeTok())
        self.assertEqual(sp.apply(proc, pol)['installed_terminal_ids'], [EOT, USER, OBS])
        self.assertTrue(proc.tokenizer.stopping_criteria(USER))

    def test_fault_reproduced_and_corrected_on_replayed_stream(self):
        # the historical shape: reasoning, </think>, answer, <|user|>, hallucinated continuation, ... (no <|endoftext|>)
        ids = [9, 9, THINK_END, 5, 6, 7, USER, 8, 8, 8, ASSIST, 8, 8]
        legacy = FakeCriteria(); old, old_fin = fake_stream(ids, legacy)
        self.assertEqual(old_fin, 'length'); self.assertIn(USER, old)          # the legacy criteria never stop: the tail is emitted
        crit = FakeCriteria(); sp.apply(FakeProcessor.__new__(FakeProcessor) if False else self._proc(crit), sp.build(self.dir, FakeTok()))
        new, new_fin = fake_stream(ids, crit)
        self.assertEqual((new, new_fin), ([9, 9, THINK_END, 5, 6, 7], 'stop'))
        self.assertEqual(new, sp.StopMatcher([EOT, USER, OBS]).truncate(ids))  # the shared truncation == what the generator emits
        self.assertEqual(new, old[:len(new)], 'pre-stop ids must be identical to the legacy stream prefix')

    def _proc(self, crit):
        p = FakeProcessor(); p.tokenizer.stopping_criteria = crit; return p

    def test_each_terminal_and_edge_cases(self):
        m = sp.StopMatcher([EOT, USER, OBS])
        self.assertEqual(m.truncate([5, EOT, 6]), [5]); self.assertEqual(m.truncate([5, OBS]), [5]); self.assertEqual(m.truncate([USER]), [], 'first-token termination')
        self.assertEqual(m.truncate([5, 6]), [5, 6], 'budget exhaustion: nothing removed'); self.assertEqual(m.truncate([]), [])
        self.assertFalse(m.is_terminal(ASSIST), '<|assistant|> is not a declared terminal id'); self.assertFalse(m.is_terminal(None))
        self.assertEqual(m.truncate([THINK_END, 5, USER, USER, EOT]), [THINK_END, 5], 'nothing is sampled after the first terminal id')

    def test_streaming_and_nonstreaming_share_the_same_prefix(self):
        ids = [1, 2, THINK_END, 3, USER, 4]; crit = FakeCriteria(); sp.apply(self._proc(crit), sp.build(self.dir, FakeTok()))
        streamed, fin = fake_stream(ids, crit); nonstream = sp.StopMatcher(crit.eos_token_ids).truncate(ids)
        self.assertEqual(streamed, nonstream); self.assertEqual(fin, 'stop')


if __name__ == '__main__':
    unittest.main()
