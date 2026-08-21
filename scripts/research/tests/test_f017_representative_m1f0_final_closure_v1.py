from __future__ import annotations
import copy, sys, unittest
from pathlib import Path
SCRIPTS=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(SCRIPTS))
import validate_f017_representative_m1f0_final_closure_v1 as closure

class ClosureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.package=closure.load(closure.PACKAGE)
    def test_committed_package(self): self.assertEqual(closure.validate(copy.deepcopy(self.package))["bound_canonical_stages"],10)
    def test_committed_review_spec(self): closure.validate_spec(closure.load(closure.SPEC))
    def reject(self, mutate):
        document=copy.deepcopy(self.package); mutate(document)
        with self.assertRaises(closure.ClosureError): closure.validate(document)
    def test_hash_and_lineage_mutations(self):
        cases=[lambda d:d["canonical_graph"][0].update(sha256="0"*64),lambda d:d["canonical_graph"][1]["stage_sha256"].update(attention_output="0"*64),lambda d:d["canonical_graph"][2].update(sha256="0"*64),lambda d:d["canonical_graph"][4].update(route_sha256="0"*64),lambda d:d["canonical_graph"][4]["ordered_id_weight_pairs"][3].update(expert_id=73),lambda d:d["canonical_graph"][5]["ordered_outputs"][0].update(sha256="0"*64),lambda d:d["canonical_graph"][9].update(sha256="0"*64)]
        for case in cases: self.reject(case)
    def test_arithmetic_and_surface_mutations(self):
        cases=[lambda d:d["canonical_graph"][8].update(formula="serial-f32"),lambda d:d["canonical_graph"][9].update(formula="f32(S1 + FFN)"),lambda d:d["canonical_graph"][6].update(surface="PRODUCTION"),lambda d:d["surface_disposition"].update(production_serial_f32_equivalence_claimed=True),lambda d:d["canonical_graph"][4].update(historical_direct_dprefix_route="SUBSTITUTED")]
        for case in cases: self.reject(case)
    def test_accounting_replay_and_boundary_mutations(self):
        cases=[lambda d:d["accounting_closure"].update(final_ledger=176),lambda d:d["accounting_closure"].update(hidden_checkpoint_rereads=1),lambda d:d["closure_preparation_activity"].update(s2_constructions=1),lambda d:d["single_use_authority_disposition"][0].update(disposition="REPLAYABLE"),lambda d:d["replay_closure"].update(no_live_go_token_can_legitimately_replay_a_completed_stage=False),lambda d:d.update(project_level_m1f0_closure_declared=True),lambda d:d.update(stop_boundary="FINAL_CLOSURE_DECLARED")]
        for case in cases: self.reject(case)

if __name__=="__main__": unittest.main()
