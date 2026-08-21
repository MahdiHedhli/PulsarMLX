from __future__ import annotations
import copy, sys, unittest
from pathlib import Path
SCRIPTS=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(SCRIPTS))
import validate_f017_representative_m1f0_final_closure_declaration_v1 as declaration

class DeclarationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.document=declaration.load(declaration.DECLARATION)
    def test_committed_declaration(self): self.assertEqual(declaration.validate(copy.deepcopy(self.document))["result"],"REPRESENTATIVE_M1F0_FINAL_CLOSURE_DECLARATION_VALID")
    def reject(self, mutate):
        document=copy.deepcopy(self.document); mutate(document)
        with self.assertRaises(declaration.DeclarationError): declaration.validate(document)
    def test_authority_mutations(self):
        for mutation in (lambda d:d["accepted_authority"]["closure_package"].update(sha256="0"*64),lambda d:d["accepted_authority"]["closure_review"].update(sha256="0"*64),lambda d:d["accepted_authority"]["closure_review"].update(verdict="REJECT"),lambda d:d["accepted_authority"]["closure_review"].update(blocking_findings=1)): self.reject(mutation)
    def test_scope_and_nonclaim_mutations(self):
        for mutation in (lambda d:d["scope_proven"].update(s2_concretely_retained=False),lambda d:d["non_claims"].update(full_model_correctness=True),lambda d:d["non_claims"].update(production_serial_f32_equivalence=True),lambda d:d.update(scope_limit="FULL_MODEL")): self.reject(mutation)
    def test_accounting_and_disposition_mutations(self):
        for mutation in (lambda d:d["canonical_authority"].update(final_real_payload_ledger=176),lambda d:d["declaration_phase_accounting"].update(checkpoint_reads=1),lambda d:d["declaration_phase_accounting"].update(s2_constructions=1),lambda d:d["canonical_authority"].update(single_use_authority_disposition="REPLAYABLE")): self.reject(mutation)
    def test_defense_and_later_evidence_mutations(self):
        for mutation in (lambda d:d["defense_in_depth_review_binding"].update(count=0),lambda d:d["defense_in_depth_review_binding"]["findings"][0].update(disposition="BLOCKING"),lambda d:d["later_committed_evidence_audit"].update(contradictory_later_committed_evidence=True),lambda d:d.update(declaration_statement="BLOCKED")): self.reject(mutation)

if __name__=="__main__": unittest.main()
