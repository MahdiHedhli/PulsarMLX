import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import f020_weighted_mlp_reference as ref


class Reference(unittest.TestCase):
    def test_ties_normal_subnormal_and_carry(self):
        for a, b, expected in [
            (0x3f800000,0x33800000,0x3f800000), (0x3f800001,0x33800000,0x3f800002),
            (0x3fffffff,0x33800000,0x40000000), (0x007fffff,1,0x00800000),
            (0x00800000,0x80000001,0x007fffff), (0x7f7fffff,0,0x7f7fffff),
            (0x80000000,0x80000000,0x80000000), (1,0x80000001,0)]:
            self.assertEqual(ref.add(a,b), expected)
        self.assertEqual(ref.multiply(1,0x3f000000), 0)
        self.assertEqual(ref.multiply(3,0x3f000000), 2)
        self.assertEqual(ref.multiply(0x80000001,0),0x80000000)
        with self.assertRaises(OverflowError):
            ref.add(0x7f7fffff,0x7f7fffff)

    def test_order_and_two_rounding_points(self):
        def run(pairs):
            result = 0
            for w, x in pairs:
                result = ref.add(result, ref.multiply(w,x))
            return result
        a,b,c = (0x3e800000,0x4c800000),(0x3e800000,0xcc800000),(0x3f000000,0x3f000000)
        self.assertEqual(run([a,b,c]), 0x3e800000)
        self.assertEqual(run([a,c,b]), 0)
        self.assertNotEqual(run([a,b,c]), run([(c[0],a[1]),b,(a[0],c[1])]))
        self.assertEqual(run([(0x3e800000,0xc0400000),(0x3f400000,0x3f800001)]),0x34000000)

    def test_reject_malformed_or_oversized_inputs(self):
        import tempfile
        base = json.loads(ref.bounded(ref.FIXTURE / "routes.json"))
        for field, value in [("lanes", 128.0), ("routes", []), ("routes", [base["routes"][2]]*5),
                             ("routes", [[None]]), ("routes", [[[-1,0]]]),
                             ("routes", [[[0,0x80000000]]]), ("patterns", {})]:
            with self.assertRaises(ValueError):
                ref.report(dict(base, **{field: value}))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "oversized"
            with path.open("wb") as output:
                output.truncate((1 << 20) + 1)
            with self.assertRaises(ValueError):
                ref.bounded(path)

    def test_invalid_words_and_fixed_golden(self):
        for value in [False,-1,1 << 32,0x7fc00001,0xff800000,"0"]:
            with self.assertRaises(ValueError):
                ref.decode(value)
        expected=json.loads(ref.bounded(ref.FIXTURE / "expected.json"))
        self.assertEqual(expected,ref.report())
        plans=json.loads(ref.bounded(ref.FIXTURE / "routes.json"))["routes"]
        self.assertEqual(plans[3][0],plans[3][2])
        self.assertEqual(plans[4][1],[2,0])


if __name__ == "__main__":
    unittest.main()
