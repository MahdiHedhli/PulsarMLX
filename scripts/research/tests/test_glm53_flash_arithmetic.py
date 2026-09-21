"""MIT. Independent-path comparisons of preregistered fictional inputs."""
from dataclasses import fields, is_dataclass
import copy
import hashlib
import json
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from glm53_flash import candidate, oracle

FIXTURE = Path(__file__).resolve().parents[3] / "fixtures/research/glm53-flash-tiny-v1/arithmetic.json"
EXPECTED_SHA = "bd01af310a0fa30777ddc37254494a10e202002de47a7a1591459689dbfbb5d2"


class ArithmeticTests(unittest.TestCase):
    errors = []

    @classmethod
    def setUpClass(cls):
        data = FIXTURE.read_bytes()
        if hashlib.sha256(data).hexdigest() != EXPECTED_SHA:
            raise ValueError("frozen fixture digest mismatch")
        cls.f = json.loads(data)

    @classmethod
    def tearDownClass(cls):
        print(json.dumps({"comparison": "candidate-vs-independent-oracle-f64",
                          "atol": 1e-12, "rtol": 1e-10, "finite_scalar_comparisons": len(cls.errors),
                          "max_abs": max(cls.errors, default=0.0),
                          "rmse": math.sqrt(sum(e * e for e in cls.errors) / max(1, len(cls.errors))),
                          "fixture_sha256": EXPECTED_SHA}, allow_nan=False))

    def close(self, actual, expected):
        if is_dataclass(expected):
            self.assertEqual([f.name for f in fields(actual)], [f.name for f in fields(expected)])
            for f in fields(expected):
                self.close(getattr(actual, f.name), getattr(expected, f.name))
        elif isinstance(expected, (tuple, list)):
            self.assertEqual(len(actual), len(expected))
            for a, b in zip(actual, expected):
                self.close(a, b)
        elif type(expected) in (int, bool, str):
            self.assertEqual(type(actual), type(expected))
            self.assertEqual(actual, expected)
        else:
            self.assertTrue(math.isfinite(actual) and math.isfinite(expected))
            error = abs(actual - expected)
            self.errors.append(error)
            self.assertLessEqual(error, 1e-12 + 1e-10 * abs(expected))

    def pair(self, name, *args, **kw):
        ref = getattr(oracle, name)(*copy.deepcopy(args), **copy.deepcopy(kw))
        out = getattr(candidate, name)(*copy.deepcopy(args), **copy.deepcopy(kw))
        self.close(out, ref)
        return out

    def test_routing_bias_ids_original_weights(self):
        f = self.f['route']
        out = self.pair('route_tokens', f['logits'], f['bias'], 2, 2.5)
        plain = self.pair('route_tokens', f['logits'], [0] * 4, 2, 2.5)
        self.assertEqual(out.ids, (0, 3))
        self.assertEqual(plain.ids, (3, 2))
        self.close(out.raw_scores, plain.raw_scores)
        self.close(out.weights, tuple(out.raw_scores[i] / sum(out.raw_scores[j] for j in out.ids) * 2.5 for i in out.ids))
        self.close(sum(out.weights), 2.5)
        self.assertGreater(out.corrected_scores[3] - out.corrected_scores[2], 1e-3)
        self.assertGreater(plain.corrected_scores[2] - plain.corrected_scores[1], 1e-3)

    def test_routing_exact_direct_tie(self):
        out = self.pair('route_scores', self.f['route']['tie_scores'], [0] * 4, 2, 2.5)
        self.assertEqual(out.ids, (0, 1))
        self.assertEqual(out.weights, (1.25, 1.25))
        saturated = self.pair('route_tokens', [1000, -1000, 0], [0, 0, 0], 2, 2.5)
        self.assertEqual(saturated.ids, (0, 2))
        self.assertEqual(saturated.raw_scores, (1.0, 0.0, 0.5))
        for mod in (oracle, candidate):
            with self.assertRaises(ValueError):
                mod.route_scores([0, 0], [0, 0], 1, 2.5)

    def kda_args(self, start=0, stop=3, altered=False):
        f = self.f['kda']
        q, v = f['q'][start:stop], f['v'][start:stop]
        if altered:
            q = [[-x for x in row] for row in q]
            v = [[-x for x in row] for row in v]
        return (q, f['k'][start:stop], v, f['a'][start:stop], f['b'][start:stop], f['A_log'], f['dt_bias'])

    def test_kda_empty_and_nonzero_unequal_axes(self):
        empty = self.pair('kda_sequence', *self.kda_args())
        nonzero = self.pair('kda_sequence', *self.kda_args(), state=self.f['kda']['state'])
        self.assertEqual((len(nonzero.state), len(nonzero.state[0])), (2, 3))
        self.assertNotEqual(nonzero.outputs, empty.outputs)
        self.assertEqual(nonzero.position, 3)
        for row in nonzero.decays:
            self.assertTrue(all(math.exp(-5) <= x <= 1 for x in row))
        self.assertTrue(all(0 < x < 1 for x in nonzero.betas))
        f = self.f['kda']
        self.close(nonzero.decays, [[math.exp(-5 / (1 + math.exp(-(a + bias)) )) for a, bias in zip(row, f['dt_bias'])] for row in f['a']])
        self.close(nonzero.betas, [1 / (1 + math.exp(-b)) for b in f['b']])

    def test_kda_prefix_incremental_reset_and_interleaving(self):
        self.pair('kda_sequence', *self.kda_args(altered=True))
        for mod in (oracle, candidate):
            full = mod.kda_sequence(*self.kda_args())
            other = mod.kda_sequence(*self.kda_args(altered=True))
            state_a = state_b = None
            out_a, out_b = [], []
            for i in range(3):
                a = mod.kda_sequence(*self.kda_args(i, i + 1), state=state_a, position=i)
                b = mod.kda_sequence(*self.kda_args(i, i + 1, True), state=state_b, position=i)
                state_a, state_b = a.state, b.state
                out_a.extend(a.outputs); out_b.extend(b.outputs)
            self.close(tuple(out_a), full.outputs); self.close(state_a, full.state)
            self.close(tuple(out_b), other.outputs); self.close(state_b, other.state)
            reset = mod.kda_sequence(*self.kda_args(), state=None, position=0)
            self.assertEqual(reset, full)

    def test_conv_suffix_and_conv_to_kda_boundary(self):
        f = self.f['kda']
        mixed = [q + k + v for q, k, v in zip(f['q'], f['k'], f['v'])]
        full = self.pair('causal_conv_silu', mixed, f['conv'])
        for mod in (oracle, candidate):
            suffix, output = None, []
            for row in mixed:
                result = mod.causal_conv_silu([row], f['conv'], suffix)
                suffix = result.suffix; output.extend(result.outputs)
            self.close(output, full.outputs)
            self.assertEqual(suffix, tuple(map(tuple, mixed[-3:])))
        result = self.pair('kda_sequence', [r[:2] for r in full.outputs], [r[2:4] for r in full.outputs],
                           [r[4:] for r in full.outputs], f['a'], f['b'], 0, f['dt_bias'])
        self.assertEqual(len(result.outputs), 3)

    def test_mhc_nonidentity_collapse_expand(self):
        f = self.f['mhc']
        result = self.pair('mhc_collapse', f['streams'], f['fn'], f['scale'], f['base'])
        self.assertTrue(any(abs(result.comb[i][j]) > 0.01 for i in range(4) for j in range(4) if i != j))
        expanded = candidate.mhc_expand(f['branch'], f['streams'], result.post, result.comb)
        ref_collapse = oracle.mhc_collapse(f['streams'], f['fn'], f['scale'], f['base'])
        self.close(expanded, oracle.mhc_expand(f['branch'], f['streams'], ref_collapse.post, ref_collapse.comb))
        self.assertNotEqual(expanded, tuple(map(tuple, f['streams'])))
        for j in range(4):
            for d in range(3):
                self.close(expanded[j][d], result.post[j] * f['branch'][d] + sum(result.comb[i][j] * f['streams'][i][d] for i in range(4)))

    def test_clamps_below_at_above(self):
        for gate in [-11, -10, -9, 9, 10, 11]:
            for up in [-11, -10, -9, 9, 10, 11]:
                self.pair('clamped_swiglu', [gate], [up])
        for mod in (oracle, candidate):
            self.assertEqual(mod.clamped_swiglu([10], [10]), mod.clamped_swiglu([11], [11]))
            self.assertNotEqual(mod.clamped_swiglu([-10], [1]), mod.clamped_swiglu([-11], [1]))
            self.assertEqual(mod.clamped_swiglu([10], [1]), mod.clamped_swiglu([11], [1]))
            self.assertEqual(mod.clamped_swiglu([1], [10]), mod.clamped_swiglu([1], [11]))
            self.assertEqual(mod.clamped_swiglu([1], [-10]), mod.clamped_swiglu([1], [-11]))

    def test_dense_shared_routed_residual_edges(self):
        f, r = self.f['composition'], self.f['route']
        results = []
        for mod in (oracle, candidate):
            weights = [mod.MlpWeights(**p) for p in f['projections']]
            out = mod.compose_moe_residual(f['x'], f['residual'], r['logits'], r['bias'], weights[:4], weights[4], 2, 2.5)
            results.append(out)
            self.assertEqual(tuple(i for i, _ in out.selected_traces), out.route.ids)
            self.assertEqual(len(out.output), len(f['x']))
            for i, trace in (*out.selected_traces, (4, out.shared_trace)):
                self.close(trace.gate, [sum(w * x for w, x in zip(row, f['x'])) for row in weights[i].gate])
                self.close(trace.up, [sum(w * x for w, x in zip(row, f['x'])) for row in weights[i].up])
                self.close(trace.activated, mod.clamped_swiglu(trace.gate, trace.up))
                self.close(trace.output, [sum(w * x for w, x in zip(row, trace.activated)) for row in weights[i].down])
            for d in range(3):
                self.close(out.routed[d], sum(trace.output[d] * weight for (_, trace), weight in zip(out.selected_traces, out.route.weights)))
                self.close(out.shared[d], out.shared_trace.output[d])
                self.close(out.branch[d], out.routed[d] + out.shared[d])
                self.close(out.output[d], f['residual'][d] + out.branch[d])
            self.assertTrue(any(abs(x) > 1e-6 for x in out.shared))
        self.close(results[1], results[0])

    def sparse_args(self, position=6, n=7, shifted=False):
        f = self.f['sparse']
        valid = [True] * n
        if shifted:
            valid[0] = False
        return (f['keys'][:n], f['gates'][:n], f['ape'], f['query'], f['weights'], valid, position, 4, 2)

    def test_sparse_live_pools_tail_visibility(self):
        for position in [3, 4, 6]:
            out = self.pair('sparse_select', *self.sparse_args(position))
            self.assertFalse(out.bypassed)
            self.assertEqual(len(out.indices), 5)
            self.assertTrue(all(i <= position for i in out.indices))
            live = [i for i in out.indices if i >= 0]
            self.assertEqual(len(live), len(set(live)))
            if position in (4, 6):
                self.assertEqual(out.indices[-1], position)
        self.assertLess(len(live), 7)

    def test_sparse_shifted_origin_invalid_query_and_short_bypass(self):
        out = self.pair('sparse_select', *self.sparse_args(6, shifted=True))
        self.assertNotIn(0, out.indices)
        invalid = self.pair('sparse_select', *self.sparse_args(), current_query_valid=False)
        self.assertEqual(invalid.indices, (-1,) * 5)
        bypass = self.pair('sparse_select', *self.sparse_args(2, 3))
        self.assertTrue(bypass.bypassed)
        self.assertEqual(bypass.indices, ())
        tie = ([[1]] * 4, [[0]] * 4, [[0]] * 2, [[1]], [1], [True] * 4, 3, 2, 2)
        selected = self.pair('sparse_select', *tie, always_tail=False)
        self.assertEqual(selected.indices, (0, 1))
        for mod in (oracle, candidate):
            collision = list(tie); collision[4] = [-1e31]
            with self.assertRaises(ValueError):
                mod.sparse_select(*collision, always_tail=False)
            for mask in ([True, True, False, True, True, True, True], [False] * 7):
                args = list(self.sparse_args()); args[5] = mask
                with self.assertRaises(ValueError):
                    mod.sparse_select(*args)

    def test_nonfinite_input_and_intermediate_rejections(self):
        for mod in (oracle, candidate):
            for bad in [math.nan, math.inf, -math.inf]:
                with self.assertRaises(ValueError):
                    mod.clamped_swiglu([bad], [1])
                with self.assertRaises(ValueError):
                    mod.clamped_swiglu([1], [bad])
                with self.assertRaises(ValueError):
                    mod.route_tokens([bad, 0], [0, 0], 1, 2.5)
                args = list(self.kda_args()); args[5] = bad
                with self.assertRaises(ValueError):
                    mod.kda_sequence(*args)
                h = self.f['mhc']
                for index in range(4):
                    args = copy.deepcopy([h['streams'], h['fn'], h['scale'], h['base']])
                    if index < 2: args[index][0][0] = bad
                    else: args[index][0] = bad
                    with self.assertRaises(ValueError):
                        mod.mhc_collapse(*args)
                collapse = mod.mhc_collapse(h['streams'], h['fn'], h['scale'], h['base'])
                for index in [0, 2, 3]:
                    args = copy.deepcopy([h['branch'], h['streams'], list(collapse.post), [list(row) for row in collapse.comb]])
                    if index == 3: args[index][0][0] = bad
                    else: args[index][0] = bad
                    with self.assertRaises(ValueError):
                        mod.mhc_expand(*args)
                for args in [([[bad]], [[1, 1, 1, 1]]), ([[1]], [[1, bad, 1, 1]])]:
                    with self.assertRaises(ValueError):
                        mod.causal_conv_silu(*args)
                for index in [0, 1, 3, 4]:
                    args = copy.deepcopy(list(self.sparse_args()))
                    if index == 4: args[index][0] = bad
                    else: args[index][0][0] = bad
                    with self.assertRaises(ValueError):
                        mod.sparse_select(*args)
            with self.assertRaises(ValueError):
                mod.clamped_mlp([1e308, 1e308], [[1e308, -1e308]], [[1, 1]], [[1], [1]])

    def test_axis_and_parameter_rejections(self):
        for mod in (oracle, candidate):
            with self.assertRaises(ValueError):
                mod.route_tokens([0] * 9, [0] * 9, 2, 2.5)
            with self.assertRaises(ValueError):
                mod.kda_sequence(*self.kda_args(), state=[[1, 2], [3, 4], [5, 6]])
            with self.assertRaises(ValueError):
                mod.kda_sequence(*self.kda_args(), position=15)
            with self.assertRaises(ValueError):
                mod.causal_conv_silu([[1, 2]], [[1, 1, 1, 1]])
            with self.assertRaises(ValueError):
                mod.compose_moe_residual([1], [0], [0], [0], [object()], object(), 1, 2.5)


if __name__ == '__main__':
    unittest.main(verbosity=2)
