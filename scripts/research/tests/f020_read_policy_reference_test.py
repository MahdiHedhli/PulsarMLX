import copy
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import f020_read_policy_reference as ref


class PolicyReference(unittest.TestCase):
    def test_frozen_matrix(self):
        matrix = json.loads(ref.MATRIX.read_bytes())
        for page in (4096,16384):
            population = ref.population(page)
            self.assertEqual(matrix["expected_by_page"][str(page)],population)
            self.assertEqual(len(population),36)
            self.assertEqual(sum(len(row["components"]) for row in population),108)
        self.assertEqual(matrix["controls"],ref.CONTROLS)

    def test_invalid_and_edge(self):
        r = dict(shard="s",begin=4096,len=5)
        with self.assertRaises(ValueError):
            ref.routes([r],{"s":4096},4096,"NoCacheRequested")
        self.assertEqual(ref.routes([r],{"s":4101},4096,"NoCacheRequested")[0]["route"],"buffered-edge-exact")
        with self.assertRaises(ValueError):
            ref.routes([r],{"s":8192},8192,"BufferedRequested")

    def test_real_captures(self):
        roots = os.environ.get("WINDOW_REFERENCE_CAPTURES")
        if not roots:
            self.skipTest("requires host captures")
        rows = [ref.verify(p) for p in roots.split(os.pathsep)]
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0],rows[1])

    def test_reject_crossed_policy_and_fabricated_effects(self):
        roots = os.environ.get("WINDOW_REFERENCE_CAPTURES")
        if not roots:
            self.skipTest("requires host captures")
        rows = [json.loads(l) for l in (Path(roots.split(os.pathsep)[0])/"policy-real.jsonl").read_bytes().splitlines()]
        with tempfile.TemporaryDirectory() as d:
            for field in ("setter","route","copied","physical","original","capacity","ownership"):
                items = copy.deepcopy(rows)
                receipt = items[0][3]
                if field=="setter": receipt["setup"]["slots"][0]["setter"]["argument"] ^= 1
                if field=="route": receipt["components"][0]["route"]="buffered-aligned-window"
                if field=="copied": receipt["effects"][0]["copied"]+=1
                if field=="physical": receipt["physical_bytes"]=0
                if field=="original": receipt["setup"]["slots"][0]["fresh_stamp"][0]^=1
                if field=="capacity": receipt["ledger"]["backing_bytes"]-=1
                if field=="ownership": items[0][5]["released"]+=1
                items[0][4] = len(json.dumps(receipt,separators=(",",":")).encode())
                (Path(d)/"policy-real.jsonl").write_text("".join(json.dumps(x)+"\n" for x in items))
                with self.assertRaises(AssertionError,msg=field):
                    ref.verify(d)
