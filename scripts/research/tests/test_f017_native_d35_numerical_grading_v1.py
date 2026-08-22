from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
MODULE=ROOT/"scripts/research/validate_f017_native_d35_numerical_grading_v1.py"
SPEC=importlib.util.spec_from_file_location("grading_validator",MODULE); validator=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(validator)
RESULT=ROOT/"docs/architecture/reviews/evidence/f017-native-d3-5-numerical-grading-result-v1.json"
TERMINAL=ROOT/"docs/architecture/reviews/evidence/f017-native-d3-5-numerical-grading-terminal-v1.json"

class NumericalGradingMutations(unittest.TestCase):
    def setUp(self): self.result=json.loads(RESULT.read_text()); self.terminal=json.loads(TERMINAL.read_text())
    def reject(self,mutation):
        result=copy.deepcopy(self.result); terminal=copy.deepcopy(self.terminal); mutation(result,terminal)
        with tempfile.TemporaryDirectory() as directory:
            rp=Path(directory)/"result.json"; tp=Path(directory)/"terminal.json"; rp.write_text(json.dumps(result)+"\n"); tp.write_text(json.dumps(terminal)+"\n")
            with self.assertRaises(ValueError): validator.validate(rp,tp)
    def test_baseline(self): self.assertEqual(validator.validate()["result"],"PASS")
    def test_mutations(self):
        mutations=[
            lambda r,t:r.__setitem__("unknown",1), lambda r,t:r.__setitem__("grant_sha256","0"*64),
            lambda r,t:r.__setitem__("native_execution_performed",True), lambda r,t:r.__setitem__("original_checkpoint_reads",1),
            lambda r,t:r.__setitem__("historical_payload_ledger_delta",1), lambda r,t:r.__setitem__("pass",False),
            lambda r,t:r["read_receipts"].pop(), lambda r,t:r["read_receipts"][0].__setitem__("consumed_sha256","0"*64),
            lambda r,t:r["read_receipts"][0].__setitem__("original_checkpoint_read",True), lambda r,t:r["stage_metrics"].pop(),
            lambda r,t:r["stage_metrics"][20].__setitem__("metric","post_hoc_metric"), lambda r,t:r["stage_metrics"][20].__setitem__("numeric_pass",False),
            lambda r,t:r["stage_metrics"][20].__setitem__("max_abs_error",r["stage_metrics"][20]["max_per_coordinate_cap"]+1),
            lambda r,t:t.__setitem__("state","TERMINAL_FAILURE"), lambda r,t:t.__setitem__("receipt_count",88),
        ]
        for index,mutation in enumerate(mutations):
            with self.subTest(index=index): self.reject(mutation)

if __name__=="__main__": unittest.main()
