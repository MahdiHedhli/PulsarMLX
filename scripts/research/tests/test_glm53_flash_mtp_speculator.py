"""Offline (mlx-free) checks for the MTP speculator's acceptance rule and the linear-state rollback arithmetic.

accept_prefix is the loop's only decision: against a stdlib model it must return the longest matching prefix and the
target's token at the first disagreement (or after a fully accepted block); two mutants (off-by-one, bonus from the
wrong position) must be caught. The rollback slice arithmetic for the conv state is checked on a stdlib model of the
[state(K-1) | mixed(S)] layout: keeping n of S tokens leaves rows [n, n+K-1).
"""
import ast
import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SPEC = ROOT / 'scripts/research/glm53_flash/dogfood/mtp_speculator.py'


def load_accept_prefix(text):
    """Execute only accept_prefix from the runtime file (the module imports mlx at top level)."""
    tree = ast.parse(text)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'accept_prefix')
    ns = {'List': list}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), 'accept_prefix', 'exec'), ns)
    return ns['accept_prefix']


def model_accept(drafts, targets):
    n = 0
    for d, t in zip(drafts, targets):
        if d != t:
            break
        n += 1
    return n, targets[n]


class MTPSpeculatorOffline(unittest.TestCase):
    def test_mlx_not_imported(self):
        self.assertNotIn('mlx', sys.modules)

    def test_accept_prefix_matches_model(self):
        accept = load_accept_prefix(SPEC.read_text()); rng = random.Random(0x20260917F1)
        for _ in range(2000):
            k = rng.randint(1, 5); drafts = [rng.randrange(4) for _ in range(k)]; targets = [rng.randrange(4) for _ in range(k + 1)]
            self.assertEqual(accept(drafts, targets), model_accept(drafts, targets), (drafts, targets))
        with self.assertRaises(ValueError):
            accept([1, 2], [1, 2])

    def test_mutants_killed(self):
        text = SPEC.read_text(); rng = random.Random(0x20260917F2)
        cases = [([rng.randrange(3) for _ in range(k)], [rng.randrange(3) for _ in range(k + 1)]) for k in (1, 2, 3, 4) for _ in range(200)]
        recipes = [('off-by-one', "    while n < k and drafts[n] == targets[n]:\n        n += 1\n    return n, targets[n]\n", "    while n < k and drafts[n] == targets[n]:\n        n += 1\n    return max(0, n - 1), targets[max(0, n - 1)]\n"),
                   ('bonus-wrong-position', "    return n, targets[n]\n", "    return n, targets[min(n + 1, k)]\n")]
        for label, before, after in recipes:
            self.assertEqual(text.count(before), 1, label)
            mutant = load_accept_prefix(text.replace(before, after, 1))
            killed = any(mutant(d, t) != model_accept(d, t) for d, t in cases)
            self.assertTrue(killed, label)

    def test_rollback_conv_slice(self):
        K = 4; state = ['s%d' % i for i in range(K - 1)]
        for S in (1, 2, 3, 4):
            mixed = ['m%d' % i for i in range(S)]; conv_input = state + mixed
            for n in range(0, S + 1):
                expected = (state + mixed[:n])[-(K - 1):]        # the last K-1 rows after consuming n tokens
                self.assertEqual(conv_input[n:n + K - 1], expected, (S, n))


if __name__ == '__main__':
    unittest.main()
