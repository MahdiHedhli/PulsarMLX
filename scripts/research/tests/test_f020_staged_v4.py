"""Public literal controls; no real data or native imports/execution."""
from fractions import Fraction as F
from pathlib import Path
import ast
from dataclasses import replace
import hashlib
import json
import struct
import sys
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from f020_staged_v4 import literals as O
from f020_staged_v4 import numeric as N
from f020_staged_v4 import source as S
from f020_staged_v4 import owner as C
from f020_staged_v4 import mock as M
from f020_staged_v4.protocol import Stage


class LiteralTests(unittest.TestCase):
    def test_independent_rtne(self):
        for v, expected in [(F(1), 0x3f800000), (F(-2), 0xc0000000),
                            (F(1)+F(1, 1 << 24), 0x3f800000),
                            (F(1)+F(3, 1 << 24), 0x3f800002),
                            (F(1, 1 << 150), 0),
                            (F(3, 1 << 150), 2)]:
            self.assertEqual(O.rtne_word(v), expected)

    def test_A02_asymmetry(self):
        for g, u, lo, hi in O.ASYMMETRIC:
            got = N.activation(F(g), F(u))
            self.assertLessEqual(lo, got[0])
            self.assertLessEqual(got[1], hi)
            self.assertLessEqual(lo, O.word_value(O.activation_word(g, u)))
            self.assertLessEqual(O.word_value(O.activation_word(g, u)), hi)
            lane = N.lane(F(g), F(u), F(0), F(0))
            swapped = O.word_value(O.activation_word(u, g))
            self.assertGreater(N.endpoint_error(swapped, lane.h), lane.e)
        self.assertNotEqual(O.activation_word(-2, 3), O.activation_word(3, -2))

    def test_A09_endpoint_not_distance(self):
        ref = (F(0), F(1, 1 << 160))
        self.assertEqual(N.endpoint_error(F(0), ref), F(1, 1 << 160))
        self.assertGreater(N.endpoint_error(F(0), ref), F(1, 1 << 161))

    def test_A05_zero_and_tiny(self):
        z = N.lane(F(0), F(1), F(0), F(0))
        self.assertEqual((z.e, z.h, z.zero), (0, (0, 0), True))
        with self.assertRaisesRegex(N.Refusal, 'nonzero floor'):
            N.lane(F(1, 1 << 20), F(1), F(0), F(0))

    def test_A12_exact_arithmetic_refusals(self):
        for call in [lambda: N.outward(F(0), F(1), 128),
                     lambda: N.interval((F(1), F(0))),
                     lambda: N.interval((F(0), F(1, 3))),
                     lambda: N.interval((F(0), F(1, 1 << 159)), width=True),
                     lambda: N.scale_e(F(1, 7)),
                     lambda: N.integer(1 << 768),
                     lambda: N.bounded(F(1 << 4096)),
                     lambda: N.f32(0x7fc00000)]:
            with self.assertRaises(N.Refusal):
                call()

    def test_original_rectangle_not_candidate(self):
        with self.assertRaisesRegex(N.Refusal, 'rectangle'):
            N.lane(F(16), F(1), F(1, 100), F(0))

    def test_import_independence(self):
        root = Path(N.__file__).parent
        for name, forbidden in [('literals.py', {'numeric', 'source', 'owner'}),
                                ('mock.py', {'numeric', 'source', 'owner'}),
                                ('numeric.py', {'literals', 'mock'}),
                                ('source.py', {'literals', 'mock'}),
                                ('owner.py', {'literals', 'mock'})]:
            tree = ast.parse((root/name).read_text())
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    names = [a.name for a in node.names]
                    if isinstance(node, ast.ImportFrom):
                        names.append(node.module or '')
                    self.assertFalse(any(set(n.split('.')) & forbidden for n in names))

    def test_A01_rectangles_clamps_negative(self):
        for g, u in [(F(10), F(10)), (F(10), F(-10))]:
            lane = N.lane(g, u, F(1), F(1))
            self.assertLessEqual(lane.e, lane.old)
            for dg in (-1, 0, 1):
                for du in (-1, 0, 1):
                    got = O.word_value(O.activation_word(g+dg, u+du))
                    self.assertLessEqual(N.endpoint_error(got, lane.h), lane.e)
        constant = N.lane(F(23, 2), F(2), F(1, 2), F(1, 128))
        self.assertEqual(constant.lg, 0)
        raw = M.packed([O.rtne_word(-15)]*2048)
        self.assertEqual(C.clamp_bits(raw, True), (0xc1700000,)*2048)
        self.assertEqual(C.clamp_bits(raw, False), (0xc1200000,)*2048)

    def test_A03_phi_and_decoder_literal(self):
        # One full-width row; original units but independently authored x.
        row = (struct.pack('<I', 0x76543210)*512,
               struct.pack('<H', 0x3f80)*64, struct.pack('<H', 0xbf80)*64)
        x = tuple(((j % 8)+1)*(1 << 55) for j in range(4096))
        value, budget = S.affine_row(row, x)
        self.assertEqual(value, 67584)
        reversed_row = (struct.pack('<I', 0x01234567)*512, row[1], row[2])
        self.assertEqual(S.affine_row(reversed_row, x)[0], 24576)
        self.assertGreater(abs(value-24576), budget)
        basis = (1 << 55,)+(0,)*4095
        no_bias = (row[0], row[1], bytes(128))
        self.assertEqual(S.affine_row(no_bias, basis)[0], 0)
        self.assertEqual(S.affine_row((reversed_row[0], row[1], bytes(128)), basis)[0], 7)
        cancel = (bytes([0x11])*2048, row[1], row[2])
        x = ((1 << 55), (1 << 55))+(0,)*4094
        value, budget = S.affine_row(cancel, x)
        self.assertEqual(value, 0)
        self.assertEqual(budget, F(273, 2**24-273)*4)
        self.assertNotEqual(budget, 0)  # abs(actual products) mutant.

    def test_A10_absolute_propagation(self):
        # q=0/1, s=-2,b=1 yields weights+1,-1; all remaining E=0.
        row = (bytes([0x10])+bytes(1023), struct.pack('<H', 0xc000)*32,
               struct.pack('<H', 0x3f80)*32)
        hidden = ((N.LATTICE, N.LATTICE+1),)*2048
        e = F(1, 128)
        budgets = ((N.scale_e(e), N.scale_e(e)),)*2+((0, 0),)*2046
        y, d, old = S.contract_row(row, hidden, budgets)
        self.assertEqual(d, 2*e)
        self.assertEqual(old, d)
        self.assertNotEqual(d, abs(e-e))
        self.assertLessEqual(y[0], 2046)
        self.assertGreaterEqual(y[1], 2046)

    def test_A06_down_quantifier_and_lengths(self):
        y = [F(0)]*4096; zero = (F(0),)*4096
        ideal = ((F(0), F(0)),)*4096
        for index in (0, 2048, 4095):
            bad = y.copy(); bad[index] = F(1)
            with self.assertRaisesRegex(N.Refusal, 'local'):
                N.check_down(bad, zero, zero, ideal, zero)
            # Separate predicate unit: generous local budget, inconsistent ideal
            # reference deliberately supplied to this unit, never to the owner.
            targets = list(ideal); targets[index] = (F(4), F(4))
            with self.assertRaisesRegex(N.Refusal, 'ideal'):
                N.check_down(y, zero, (F(1),)*4096, targets, zero)
        for n in (4095, 4097):
            with self.assertRaisesRegex(N.Refusal, 'count'):
                N.check_down([F(0)]*n, zero, zero, ideal, zero)

    def test_A12_hidden_domain_and_resources(self):
        for v in (N.f32(1), F(1, 1 << 33), F(2**33)):
            values = [F(1)]*2048; values[-1] = v
            with self.assertRaisesRegex(N.Refusal, 'floor/magnitude'):
                N.domain(values)
        with self.assertRaisesRegex(N.Refusal, 'row sum'):
            N.domain([F(2**32)]*2048)
        with self.assertRaisesRegex(N.Refusal, 'RSS'):
            C.Resources(clock=lambda: 0, rss=lambda: 256*1024*1024+1).check(True)
        tick = [0]
        resource = C.Resources(clock=lambda: tick[0], rss=lambda: 0)
        tick[0] = 901
        with self.assertRaisesRegex(N.Refusal, 'deadline'):
            resource.check(True)
        with self.assertRaisesRegex(N.Refusal, 'working'):
            resource.reserve(512*1024*1024+1)


def changed(raw, index, word):
    return raw[:index*4]+struct.pack('<I', word)+raw[index*4+4:]


class StagedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = S.Original.synthetic(*M.public_source('A'))
        cls.serial = 0

    def make_owner(self):
        type(self).serial += 1
        return C.Owner(self.original, 'unit-'+str(self.serial))

    def run_fault(self, callback, counts, pattern=None):
        owner = self.make_owner()
        backend = M.Backend(mutate=callback)
        with self.assertRaises(N.Refusal) as error:
            owner.run(backend)
        if pattern:
            self.assertIn(pattern, str(error.exception))
        self.assertEqual(tuple(backend.calls), counts)
        self.assertEqual(owner.state, 'TERMINAL')
        self.assertEqual(sum(json.loads(r)['state'] == 'TERMINAL' for r in owner.receipts), 1)
        with self.assertRaisesRegex(N.Refusal, 'replay'):
            owner.run(backend)
        self.assertEqual(tuple(backend.calls), counts)

    def test_A04_A07_no_intrinsic_assumption(self):
        def mutation(stage, r):
            if stage == 'activation':
                raw = r.buffers[0]
                v = O.word_value(struct.unpack_from('<I', raw)[0])+F(1, 1024)
                return replace(r, buffers=(changed(raw, 0, O.rtne_word(v)),))
            return r
        self.run_fault(mutation, O.COUNTS['hidden'], 'activation bound')

    def test_A06_gate_up_all_lanes(self):
        for role in (0, 1):
            for index in (1023, 2047):
                def mutation(stage, r):
                    if stage == 'gu':
                        outputs = list(r.buffers)
                        outputs[role] = changed(outputs[role], index, O.rtne_word(15))
                        return replace(r, buffers=tuple(outputs))
                    return r
                self.run_fault(mutation, O.COUNTS['gu'], 'GU exact')

    def test_A06_hidden_clamp_lengths(self):
        def bad_clamp(stage, r):
            return replace(r, clamp_gate=r.clamp_gate[:-1]+(0,)) if stage == 'activation' else r
        self.run_fault(bad_clamp, O.COUNTS['hidden'], 'clamp')
        for index in (1023, 2047):
            def mutation(stage, r):
                return replace(r, buffers=(changed(r.buffers[0], index, 1),)) if stage == 'activation' else r
            self.run_fault(mutation, O.COUNTS['hidden'])
        for word in (O.rtne_word(F(1, 2**33)), O.rtne_word(2**33)):
            def mutation(stage, r):
                return replace(r, buffers=(changed(r.buffers[0], 2047, word),)) if stage == 'activation' else r
            self.run_fault(mutation, O.COUNTS['hidden'])
        for stage, counts in [('gu', O.COUNTS['gu']), ('activation', O.COUNTS['hidden']), ('down', O.COUNTS['down'])]:
            for extra in (False, True):
                def mutation(current, r):
                    if current == stage:
                        raw = r.buffers[0]+bytes(4) if extra else r.buffers[0][:-4]
                        return replace(r, buffers=(raw,)+r.buffers[1:])
                    return r
                self.run_fault(mutation, counts, 'length')
        for extra in (False, True):
            def up_length(stage, r):
                if stage == 'gu':
                    raw = r.buffers[1]+bytes(4) if extra else r.buffers[1][:-4]
                    return replace(r, buffers=(r.buffers[0], raw))
                return r
            self.run_fault(up_length, O.COUNTS['gu'], 'length')
            for field in ('clamp_gate', 'clamp_up'):
                def clamp_length(stage, r):
                    if stage == 'activation':
                        vector = getattr(r, field)
                        return replace(r, **{field: vector+(0,) if extra else vector[:-1]})
                    return r
                self.run_fault(clamp_length, O.COUNTS['hidden'], 'clamp')

    def test_A06_down_output_mutants(self):
        for index in (2048, 4095):
            def mutation(stage, r):
                return replace(r, buffers=(changed(r.buffers[0], index, O.rtne_word(2**30)),)) if stage == 'down' else r
            self.run_fault(mutation, O.COUNTS['down'], 'down local')

    def test_A08_E_D_digest_mutants(self):
        for field, indices in [('lanes', (0, 1023, 2047)), ('propagation', (0, 2048, 4095))]:
            for index in indices:
                owner = self.make_owner()
                def mutation(stage, r):
                    if stage == 'gu':
                        vals = list(getattr(owner.certificate, field))
                        vals[index] = replace(vals[index], e=vals[index].old) if field == 'lanes' else vals[index]+1
                        owner.certificate = replace(owner.certificate, **{field: tuple(vals)})
                    return r
                backend = M.Backend(mutate=mutation)
                with self.assertRaisesRegex(N.Refusal, 'certificate'):
                    owner.run(backend)
                self.assertEqual(tuple(backend.calls), O.COUNTS['gu'])

    def test_A11_reentry_buffer_receipts_replay(self):
        for mode in ('reentry', 'buffer', 'receipt', 'mutable', 'exception'):
            owner = self.make_owner()
            backend = M.Backend()
            def mutation(stage, r):
                if stage == 'activation':
                    if mode == 'reentry':
                        owner.run(backend)
                    elif mode == 'buffer':
                        owner.buffers = (bytes(8192),)+owner.buffers[1:]
                    elif mode == 'receipt':
                        owner.receipts = (b'{}',)
                    elif mode == 'mutable':
                        return replace(r, buffers=(bytearray(r.buffers[0]),))
                    else:
                        raise RuntimeError('public injected fault')
                return r
            backend.mutate = mutation
            start = time.monotonic()
            with self.assertRaises(N.Refusal):
                owner.run(backend)
            self.assertLess(time.monotonic()-start, 30)
            self.assertEqual(tuple(backend.calls), O.COUNTS['hidden'])
            another = C.Owner(self.original, owner.attempt)
            with self.assertRaisesRegex(N.Refusal, 'duplicate'):
                another.run(M.Backend())

    def test_A12_backend_resource_faults(self):
        for i, cap in enumerate((64*1024*1024, 64*1024*1024, 1024*1024*1024)):
            def mutation(stage, r):
                if stage == 'gu':
                    m = [0, 0, 0]; m[i] = cap+1
                    return replace(r, resources=tuple(m))
                return r
            self.run_fault(mutation, O.COUNTS['gu'], 'resource')

    def test_A12_original_hash_mutations(self):
        o = self.original
        e = json.loads(o.descriptor)
        for i in range(9):
            parts = list(o.parts); parts[i] = bytes([parts[i][0]^255])+parts[i][1:]
            with self.assertRaisesRegex(N.Refusal, 'component hash'):
                S.Original.synthetic(o.header, tuple(parts), e, o.x)
        with self.assertRaisesRegex(N.Refusal, 'input identity'):
            S.Original.synthetic(o.header, o.parts, e, bytes(len(o.x)))

    def test_A07P_propagation_is_required(self):
        owner = self.make_owner(); backend = M.Backend(perturb=True)
        owner.run(backend)
        self.assertEqual(tuple(backend.calls), O.COUNTS['success'])
        self.assertIs(backend.hidden_input, owner.buffers[2])
        h = C.words(owner.buffers[2], 2048)[1]
        for index, (gw, uw) in O.PERTURBED.items():
            lane = owner.certificate.lanes[index]
            self.assertLess(abs(O.word_value(gw)-lane.g), lane.bg)
            self.assertLess(abs(O.word_value(uw)-lane.u), lane.bu)
            error = N.endpoint_error(h[index], lane.h)
            self.assertGreater(error, lane.a)
            self.assertLessEqual(error, lane.e)
            lower, upper = (F(1, 2**16), F(1, 2**14)) if index == 0 else (F(1, 2**13), F(1, 2**12))
            # Independent rounded-oracle differences bracketed by public literals.
            oracle_difference = abs(h[index]-O.word_value(O.activation_word(lane.g, lane.u)))
            self.assertLess(lower, oracle_difference)
            self.assertLess(oracle_difference, upper)
        check = N.check_hidden
        for mutant in ('omit-P', 'Lg-zero'):
            def wrong(h, local, lanes):
                bad = tuple(replace(v, e=v.a if mutant == 'omit-P' else v.e-v.lg*v.bg) for v in lanes)
                return check(h, local, bad)
            owner = self.make_owner(); backend = M.Backend(perturb=True)
            with patch.object(N, 'check_hidden', wrong):
                with self.assertRaisesRegex(N.Refusal, 'ideal hidden'):
                    owner.run(backend)
            self.assertEqual(tuple(backend.calls), O.COUNTS['hidden'])

    def test_A08_binding_and_stage_identity(self):
        for field in ('source', 'build', 'checker', 'proof', 'profile', 'contract'):
            owner = self.make_owner()
            def mutation(stage, r):
                if stage == 'gu':
                    d = dict(owner.identity); d[field] = 'wrong'
                    owner.identity = tuple(sorted(d.items()))
                return r
            backend = M.Backend(mutate=mutation)
            with self.assertRaisesRegex(N.Refusal, 'changed'):
                owner.run(backend)
            self.assertEqual(tuple(backend.calls), O.COUNTS['gu'])
        def mutation(stage, r):
            return replace(r, input_digests=('0'*64,)) if stage == 'gu' else r
        self.run_fault(mutation, O.COUNTS['gu'], 'input/family')
        owner = self.make_owner()
        def attempt_mutation(stage, r):
            owner.attempt = 'substituted-attempt'
            return r
        backend = M.Backend(mutate=attempt_mutation)
        with self.assertRaisesRegex(N.Refusal, 'attempt identity'):
            owner.run(backend)
        self.assertEqual(tuple(backend.calls), O.COUNTS['gu'])

    def test_A11_cleanup_failure_and_pre_refusal(self):
        class CleanupFault(M.Backend):
            def cleanup(self):
                super().cleanup()
                return (1, 0, 0)
        owner = self.make_owner(); backend = CleanupFault()
        with self.assertRaisesRegex(N.Refusal, 'cleanup'):
            owner.run(backend)
        self.assertEqual(tuple(backend.calls), O.COUNTS['success'])
        owner = C.Owner(self.original, 'rss-pre-refusal', C.Resources(rss=lambda: 2**30))
        backend = M.Backend()
        with self.assertRaisesRegex(N.Refusal, 'RSS'):
            owner.run(backend)
        self.assertEqual(tuple(backend.calls), O.COUNTS['pre'])

    def test_A03_cache_includes_metadata(self):
        row = self.original.row(0, 0)
        x = tuple(int(v*(1 << 55)) for v in M.values(self.original.x))
        first = S.affine_row(row, x)[0]
        other = (row[0], row[1], struct.pack('<H', 0x3f80)*64)
        second = S.affine_row(other, x)[0]
        self.assertEqual(first, 1)
        self.assertEqual(second, F(47, 16))
        class TwoMetadata:
            def row(self, role, r):
                return row if r == 0 else other
        rows = S.Rows(TwoMetadata(), lambda: None)
        out = rows.apply(0, 'literal-x', lambda data: S.affine_row(data, x), 'literal')
        self.assertEqual(out[0][0], first)
        self.assertEqual(out[1][0], second)
        self.assertEqual(rows.stats['literal'], {'hits': 2046, 'misses': 2})

    def test_A05_source_exact_zero(self):
        original = S.Original.synthetic(*M.public_source('A', zero_row=2047))
        owner = C.Owner(original, 'public-source-zero'); backend = M.Backend()
        owner.run(backend)
        lane = owner.certificate.lanes[-1]
        self.assertEqual((lane.g, lane.bg, lane.e, lane.h), (0, 0, 0, (0, 0)))
        self.assertEqual(C.words(owner.buffers[2], 2048)[1][-1], 0)
        self.assertEqual(tuple(backend.calls), O.COUNTS['success'])

        def signed_zero(stage, r):
            if stage == 'gu':
                return replace(r, buffers=(changed(r.buffers[0], 2047, 0x80000000), r.buffers[1]))
            if stage == 'activation':
                return replace(r, buffers=(changed(r.buffers[0], 2047, 0x80000000),))
            return r
        owner = C.Owner(original, 'public-source-negative-zero')
        backend = M.Backend(mutate=signed_zero)
        owner.run(backend)
        self.assertEqual(C.words(owner.buffers[2], 2048)[0][-1], 0x80000000)
        self.assertEqual(tuple(backend.calls), O.COUNTS['success'])

        for word in (0x00000001, 0x80000001, 0x00800000):
            def nonzero(stage, r):
                return replace(r, buffers=(changed(r.buffers[0], 2047, word),)) if stage == 'activation' else r
            owner = C.Owner(original, 'zero-hidden-mutant-'+str(word))
            backend = M.Backend(mutate=nonzero)
            with self.assertRaisesRegex(N.Refusal, 'ideal hidden bound'):
                owner.run(backend)
            self.assertEqual(tuple(backend.calls), O.COUNTS['hidden'])
            self.assertEqual(sum(json.loads(r)['state'] == 'TERMINAL' for r in owner.receipts), 1)
            with self.assertRaisesRegex(N.Refusal, 'replay'):
                owner.run(backend)
            self.assertEqual(tuple(backend.calls), O.COUNTS['hidden'])

    def test_A05_tiny_original_positive_phi_refuses(self):
        row_bytes = M.fixtures.row_bytes
        def tiny(case, role, row):
            w, scales, bias = row_bytes(case, role, row)
            if row == 0 and role in ('gate', 'up'):
                # Literal BF16 2^-21 and 1/2, independent of checker encoding.
                return w, bytes(len(scales)), struct.pack('<H', 0x3500 if role == 'gate' else 0x3f00)*64
            return w, scales, bias
        with patch.object(M.fixtures, 'row_bytes', tiny):
            original = S.Original.synthetic(*M.public_source('A'))
        owner = C.Owner(original, 'tiny-original-positive-phi')
        backend = M.Backend()
        with self.assertRaisesRegex(N.Refusal, 'prospective down nonzero floor'):
            owner.run(backend)
        self.assertEqual(tuple(backend.calls), O.COUNTS['pre'])
        self.assertEqual(sum(json.loads(r)['state'] == 'TERMINAL' for r in owner.receipts), 1)
        with self.assertRaisesRegex(N.Refusal, 'replay'):
            owner.run(backend)

    def test_A02_integrated_swap_A_B(self):
        for case in ('A', 'B'):
            original = self.original if case == 'A' else S.Original.synthetic(*M.public_source('B'))
            owner = C.Owner(original, 'swap-'+case)
            def mutate(stage, r):
                return replace(r, buffers=r.buffers[::-1]) if stage == 'gu' else r
            backend = M.Backend(mutate=mutate)
            with self.assertRaisesRegex(N.Refusal, 'GU exact bound'):
                owner.run(backend)
            self.assertEqual(tuple(backend.calls), O.COUNTS['gu'])
            self.assertEqual(sum(json.loads(r)['state'] == 'TERMINAL' for r in owner.receipts), 1)
            with self.assertRaisesRegex(N.Refusal, 'replay'):
                owner.run(backend)

    def test_A11_state_and_swallowed_reentry(self):
        for mode in ('state', 'swallow'):
            owner = self.make_owner(); backend = M.Backend()
            def mutate(stage, r):
                if stage == 'gu':
                    if mode == 'state':
                        owner.state = 'DOWN_CHECKED'
                    else:
                        try:
                            owner.run(backend)
                        except N.Refusal:
                            pass
                return r
            backend.mutate = mutate
            with self.assertRaisesRegex(N.Refusal, 'state'):
                owner.run(backend)
            self.assertEqual(tuple(backend.calls), O.COUNTS['gu'])
            self.assertEqual(sum(json.loads(r)['state'] == 'TERMINAL' for r in owner.receipts), 1)

    def test_A12_infinity_and_invalid_samples(self):
        for stage, counts in [('gu', O.COUNTS['gu']), ('activation', O.COUNTS['hidden']), ('down', O.COUNTS['down'])]:
            for word in (0x7f800000, 0xff800000, 0x7fc00000):
                def mutate(current, r):
                    return replace(r, buffers=(changed(r.buffers[0], 0, word),)+r.buffers[1:]) if current == stage else r
                self.run_fault(mutate, counts, 'nonfinite')
        for sample in ((0, 0), (-1, 0, 0), (True, 0, 0), ('0', 0, 0), [0, 0, 0]):
            def mutate(stage, r):
                return replace(r, resources=sample) if stage == 'gu' else r
            self.run_fault(mutate, O.COUNTS['gu'], 'resource sample type')
        for sample in (None, True, '0', .5):
            with self.assertRaisesRegex(N.Refusal, 'RSS'):
                C.Resources(clock=lambda: 0, rss=lambda: sample).check(True)
        for sample in (None, True, 'bad', float('inf'), float('nan')):
            tick = [0]
            r = C.Resources(clock=lambda: tick[0], rss=lambda: 0)
            tick[0] = sample
            with self.assertRaisesRegex(N.Refusal, 'clock'):
                r.check(True)

    def test_A12_periodic_reference_and_local_down_refusal(self):
        apply = S.Rows.apply
        for target, counts in [('gate', O.COUNTS['pre']), ('local_down', O.COUNTS['hidden'])]:
            for failure in ('deadline', 'RSS'):
                phase = ['idle']; seen = [0]; tick = [0.0]; rss = [0]
                class RowTrip(C.Resources):
                    def check(self, force=False):
                        if phase[0] == target:
                            seen[0] += 1
                            tick[0] += .101
                            if seen[0] == 101:
                                if failure == 'deadline':
                                    tick[0] = 901
                                else:
                                    rss[0] = 256*1024*1024+1
                        return super().check(force)
                resource = RowTrip(clock=lambda: tick[0], rss=lambda: rss[0])
                def observe(rows, role, operand, call, label):
                    phase[0] = label
                    return apply(rows, role, operand, call, label)
                type(self).serial += 1
                owner = C.Owner(self.original, 'periodic-'+str(self.serial), resource)
                backend = M.Backend()
                with patch.object(S.Rows, 'apply', observe):
                    with self.assertRaisesRegex(N.Refusal, failure):
                        owner.run(backend)
                self.assertEqual(seen[0], 101)
                self.assertEqual(tuple(backend.calls), counts)
                self.assertEqual(sum(json.loads(r)['state'] == 'TERMINAL' for r in owner.receipts), 1)



if __name__ == '__main__':
    unittest.main()
