import sys
import unittest
from fractions import Fraction as F
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import f020_weighted_native_reference as r
import f020_weighted_native_rational as q


class Rounding(unittest.TestCase):
    def test_thirds_and_canonical_domain(self):
        for x,b in [(F(1,3),0x3eaaaaab),(F(-1,3),0xbeaaaaab),(F(0),0),(F(-1,1<<151),0x80000000)]:
            self.assertEqual(q.rn32(x),b)
            self.assertEqual(q.parse(q.encode(x)),x)
        for s in ["-0/1","+1/1","2/4","1/0","2","01/3","3/01","nan","1/-2","1/"+"9"*2500," "*8000]:
            with self.assertRaises(ValueError):q.parse(s)
        with self.assertRaises(ValueError):q.rn32(1<<8192)

    def test_adjacent_inequalities_ties_and_carry(self):
        for lo in [0,1,2,0x7fffff,0x800000,0x3f800000,0x3f800001,0x3fffffff]:
            a,b=map(r.r1.f32,(lo,lo+1));mid=(a+b)/2;eps=(b-a)/F(3*2**40)
            for value,expected in [(mid-eps,lo),(mid,lo+(lo&1)),(mid+eps,lo+1)]:
                self.assertEqual(q.rn32(value),expected)
                self.assertEqual(q.rn32(-value),expected|(1<<31))
            self.assertEqual(q.rn32(mid),r.dyadic.rounded(0,mid.numerator,1-mid.denominator.bit_length()))
        maximum=r.r1.f32(0x7f7fffff);mid=maximum+2**103
        self.assertEqual(q.rn32(mid-F(1,3)),0x7f7fffff)
        for v in [mid,-mid,mid+F(1,3)]:
            with self.assertRaises(OverflowError):q.rn32(v)

    def test_independent_gates_and_order(self):
        route=((0,r.Q),(1,r.Q),(2,r.H))
        vectors=[(e,[w]*128) for e,w in enumerate([0x4c800000,0xcc800000,r.H])]
        self.assertEqual(r.local_bits(route,vectors),[r.Q]*128)
        self.assertEqual(r.local_bits([route[i] for i in (0,2,1)],[vectors[i] for i in (0,2,1)]),[0]*128)
        for actual,ends,gate in [([r.H]*128,[[0,r.ONE]]*128,"LOCAL_BITS"),([r.Q]*128,[[0,0]]*128,"SOURCE_ENCLOSURE")]:
            with self.assertRaisesRegex(ValueError,gate):r.weighted_gates(route,vectors,actual,ends)
        z=[(0,[0x80000000]*128),(0,[0]*128)]
        self.assertEqual(r.weighted_gates(((0,r.ONE),(0,0)),z,[0]*128,[[0x80000000,0]]*128),[0]*128)

if __name__=="__main__":
    unittest.main()
