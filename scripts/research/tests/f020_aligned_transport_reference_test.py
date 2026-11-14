import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import f020_aligned_transport_reference as ref


class WindowOracle(unittest.TestCase):
    def test_independent_population_and_freeze(self):
        cases = list(ref.corpus())
        self.assertEqual(len(set(cases)), 6161)
        self.assertEqual(sum(a < 4096 for a, *_ in cases), 5489)
        self.assertEqual(len(cases) - 5489, 672)
        self.assertEqual(ref.freeze(), json.loads(ref.FROZEN.read_bytes()))

    def test_minimal_in_file_cover_or_whole_edge(self):
        for a, length, offset, n in ref.corpus():
            result = ref.geometry(a, length, offset, n)
            if not n or offset+n > length:
                self.assertEqual(result, ["empty"] if not n else ["out-of-file"])
                continue
            kind,start,size,delta=result
            self.assertEqual(start+delta,offset)
            self.assertLessEqual(start+size,length)
            self.assertLessEqual(delta+n,size)
            if kind == "buffered-edge-exact":
                self.assertEqual((start,size,delta),(offset,n,0))
                self.assertLess(length//a*a,offset+n)
            else:
                self.assertEqual((start%a,size%a),(0,0))
                self.assertLess(delta,a)
                self.assertLess(start+size-(offset+n),a)

    def test_named_limits_include_uint64_native_and_budget(self):
        rows = {r[0]:r[-1] for r in ref.named_records()}
        self.assertEqual(rows["rounded-overflow"],["round-overflow"])
        self.assertEqual(rows["high-offset-small-native"],["buffered-aligned-window",1<<45,4096,0])
        self.assertEqual(rows["maximum-backing"],["backing",33603581])
        self.assertEqual(rows["control-at-cap"],["reservation",33603581+65536])
        self.assertEqual(rows["one-byte-short"],["budget"])

    def test_observed_comparisons_when_host_exports_supplied(self):
        import os
        roots = os.environ.get("WINDOW_REFERENCE_CAPTURES")
        if not roots:
            self.skipTest("requires captured debug/release host observations")
        rows = [ref.verify_capture(directory) for directory in roots.split(os.pathsep)]
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0], rows[1])
        self.assertEqual(sum(r[-1]["roles"] for r in rows[0]), 72)
