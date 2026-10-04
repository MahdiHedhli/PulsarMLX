"""Host-only formula, encoding and independent analytic checks."""
from fractions import Fraction as F
from pathlib import Path
import struct
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import f020_selected_fixtures_v2 as fixture
import f020_selected_proof_v2 as proof
import f020_selected_r1_v2 as r1


class SelectedV2(unittest.TestCase):
    def test_input_group_bias_observability(self):
        raw = fixture.input_bytes()
        x = [F(v[0]) for v in struct.iter_unpack('<f',raw)]
        self.assertEqual(len(raw), 16384)
        self.assertEqual(x, proof.input_exact())
        self.assertEqual(sum(x), 2)
        for j in range(0,4096,64):
            self.assertEqual(sum(x[j:j+64]), F(1,32))

    def test_rejected_v1_cancellation_is_not_reintroduced(self):
        self.assertEqual(sum((-1)**j.bit_count() for j in range(64)),0)
        self.assertNotEqual(sum(proof.input_exact()[:64]),0)

    def test_original_packed_rows_independently(self):
        x = proof.input_exact()
        for case, sign in [('A',1),('B',-1)]:
            for ri, role in enumerate(('gate','up','down')):
                for row in range(16):
                    packed, scales, biases = fixture.row_bytes(case,role,row)
                    k = 2048 if role=='down' else 4096
                    self.assertEqual(len(packed), k//2)
                    self.assertEqual(len(scales), k//32)
                    self.assertEqual(len(biases), k//32)
                    def decode_bf(raw):
                        return F(struct.unpack('<f', b'\0\0'+raw)[0])
                    s,b = decode_bf(scales[:2]),decode_bf(biases[:2])
                    total = F(0)
                    for j in range(k):
                        # Byte nibble unpack independent of generator U32 packing.
                        q = (packed[j//2] >> (4*(j%2))) & 15
                        self.assertEqual(q,(j+row+ri)%16)
                        total += x[j]*(s*q+b)
                    if role!='down':
                        self.assertEqual(total,fixture.TARGETS[case][row%4][ri])

    def test_analytic_domains_and_mutations(self):
        report = proof.prove()
        self.assertEqual(report['status'],'PASS')
        self.assertEqual(set(report['cases']),{'A','B'})

    def test_non_bf16_formula_refused(self):
        with self.assertRaises(ValueError):
            fixture.bf16(6-15/128)

    def test_generation_shape_refusals(self):
        for args in [('C','gate',0),('A','other',0),('A','gate',2048)]:
            with self.assertRaises(ValueError):
                fixture.row_bytes(*args)


class StreamedR1(unittest.TestCase):
    def test_units_exact_and_refusals(self):
        for val in (0., -0., 2**-32, -3/4096, 2**32):
            word=struct.unpack('<I',struct.pack('<f',val))[0]
            self.assertEqual(F(r1.units(word),2**55),F(val))
        for word in (1, 0x7f800000, 0x7fc00000, 0x2f000000):
            with self.assertRaises(ValueError):
                r1.units(word)

    def test_streamed_affine_against_scalar_original_bytes(self):
        # One full-width row; a host oracle test, not a native observation.
        packed,sraw,braw=fixture.row_bytes('B','up',3)
        s=r1.units(struct.unpack_from('<H',sraw)[0],True)
        b=r1.units(struct.unpack_from('<H',braw)[0],True)
        class OneRow:
            n,k=1,4096
            def groups(self,row):
                for i in range(64):
                    yield i,memoryview(packed)[i*32:(i+1)*32],s,b
        raw=fixture.input_bytes()
        x=r1.original_input(raw,4096)
        exact,bounds=r1.affine(OneRow(),x)
        oracle=F(0); phi=F(0)
        for j in range(4096):
            word=struct.unpack_from('<I',packed,(j//8)*4)[0]
            q=(word>>(4*(j%8)))&15
            v=F(x[j],2**55)
            sv,bv=F(s,2**39),F(b,2**39)
            oracle+=v*(sv*q+bv)
            phi+=abs(v)*(abs(sv)*q+abs(bv))
        self.assertEqual(exact,[oracle])
        self.assertEqual(bounds,[proof.gamma(4096)*phi])

    def test_down_integer_enclosure_negative_weights(self):
        class OneRow:
            n,k=1,2048
            def groups(self,row):
                for i in range(32):
                    yield i,bytes(range(32)), -(1<<27),1<<26
        h=[(F(j-4,8),F(j-4,8)+F(1,2**256)) for j in range(2048)]
        bh=[F(1,128)]*2048
        ys,bs=r1.ideal_down(OneRow(),h,bh)
        lo=hi=pb=F(0)
        for group,packed,s,b in OneRow().groups(0):
            for j in range(64):
                w=F(s*r1.code(packed,j)+b,2**39)
                a,c=h[group*64+j]
                lo+=min(a*w,c*w);hi+=max(a*w,c*w);pb+=abs(w)/128
        self.assertLessEqual(ys[0][0],lo)
        self.assertGreaterEqual(ys[0][1],hi)
        self.assertLessEqual(ys[0][1]-ys[0][0],hi-lo+F(2,2**256))
        self.assertEqual(bs,[pb])

    def test_real_pre_admission_tiny_hidden_refuses(self):
        with self.assertRaisesRegex(ValueError,'down nonzero floor'):
            r1.hidden_admission([F(1,2**20)],[F(1)],[F(0)],[F(0)])

    def test_exact_zero_exception(self):
        self.assertEqual(r1.hidden_admission([F(0)],[F(1)],[F(0)],[F(0)]),
                         ([(F(0),F(0))],[F(0)]))


if __name__=='__main__':
    unittest.main()
