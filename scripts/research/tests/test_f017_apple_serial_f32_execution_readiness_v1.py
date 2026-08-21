import copy, json, os, tempfile, unittest
from pathlib import Path
from scripts.research import validate_f017_apple_serial_f32_execution_readiness_v1 as v
from scripts.research import f017_apple_serial_f32_execution_readiness_v1 as package

ROOT=Path(__file__).resolve().parents[3]; C=ROOT/"specs/017-rust-native-inference-runtime/contracts"
def doc(name): return json.loads((C/name).read_text())

class ReadinessMutationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package=doc("f017-apple-production-serial-f32-retained-40-tensor-package-v1.json")
        cls.code=doc("f017-apple-production-serial-f32-code-manifest-v2.json")
        cls.comparison=doc("f017-apple-production-serial-f32-comparison-execution-contract-v1.json")
        cls.routing=doc("f017-apple-production-serial-f32-routing-execution-gates-v1.json")
        cls.determinism=doc("f017-apple-production-serial-f32-determinism-v2.json")
        cls.accounting=doc("f017-apple-production-serial-f32-future-real-event-accounting-v1.json")
        cls.auth=doc("f017-apple-production-serial-f32-future-authorization-schema-v2.json")
        cls.inert=doc("f017-apple-production-serial-f32-inert-go-fixture-v1.json")
    def reject(self, function, baseline, mutations):
        for i,mutation in enumerate(mutations):
            value=copy.deepcopy(baseline); mutation(value)
            with self.subTest(i=i), self.assertRaises(v.ValidationError): function(value)
    def test_package_mutations(self):
        self.reject(v.validate_package_contract,self.package,[lambda d:d["ordered_tensors"].pop(),lambda d:d["ordered_tensors"][0].__setitem__("sha256","0"*64),lambda d:d["ordered_tensors"].reverse(),lambda d:d["consumer_policy"].__setitem__("rehash_actual_bytes",False),lambda d:d["consumer_policy"].__setitem__("no_extra_files",False),lambda d:d["consumer_policy"].__setitem__("non_symlink",False),lambda d:d["assembly"].__setitem__("numerical_transformations",1)])
    def test_code_manifest_mutations(self):
        self.reject(v.validate_code_manifest,self.code,[lambda d:d["artifacts"].__setitem__(slice(None),[r for r in d["artifacts"] if r["path"]!="crates/quant/src/iq_ref.rs"]),lambda d:d["artifacts"].__setitem__(slice(None),[r for r in d["artifacts"] if r["path"]!="crates/quant/src/cpu_dot_tables.rs"]),lambda d:d.__setitem__("execution_code_head","0"*40),lambda d:d["artifacts"][0].__setitem__("sha256","0"*64)])
    def test_comparison_mutations(self):
        self.reject(v.validate_comparison,self.comparison,[lambda d:d.__setitem__("executed",True),lambda d:d["stage_rows"].pop(),lambda d:d["stage_rows"][0].__setitem__("observed_result","BYTE_EQUIVALENT"),lambda d:d["tolerance_policy"].__setitem__("post_hoc_changes",True),lambda d:d["metrics"]["r10_intermediate"].__setitem__("max_abs_error",1.0),lambda d:d["metrics"]["complete_layer_final"].__setitem__("cosine_similarity_min",0.5),lambda d:d["metrics"]["routing_weight_frozen"].__setitem__("membership_exact",False)])
    def test_routing_and_determinism_mutations(self):
        self.reject(v.validate_routing,self.routing,[lambda d:d["ordered_gates"].reverse(),lambda d:d.__setitem__("order_canonicalization",True),lambda d:d.__setitem__("tolerance_cannot_hide_structural_failure",False)])
        self.reject(v.validate_determinism,self.determinism,[lambda d:d.__setitem__("fresh_processes",9),lambda d:d.__setitem__("comparison","NUMERIC_TOLERANCE"),lambda d:d.__setitem__("executed",True),lambda d:d.__setitem__("representative_runs_this_phase",1)])
    def test_accounting_and_authority_mutations(self):
        self.reject(v.validate_accounting,self.accounting,[lambda d:d.__setitem__("ledger_terminal",176),lambda d:d.__setitem__("real_payload_consumption",1),lambda d:d.__setitem__("manual_ledger_increment",True),lambda d:d.__setitem__("result_receipts_master_ledger_same_commit",False)])
        for mutation in [lambda d:d.__setitem__("issued_live_go_tokens",1),lambda d:d.__setitem__("normal_validation_can_generate_live",True),lambda d:d.__setitem__("token_reuse",True)]:
            value=copy.deepcopy(self.auth); mutation(value)
            with self.assertRaises(v.ValidationError): v.validate_authorization(value,self.inert)
    def test_package_root_mutates_on_material_change(self):
        rows=package.derive_descriptors(); base=package.package_root_sha(rows)
        changed=copy.deepcopy(rows); changed[0]["sha256"]="0"*64
        self.assertNotEqual(base,package.package_root_sha(changed))
        changed=copy.deepcopy(rows); changed.reverse()
        self.assertNotEqual(base,package.package_root_sha(changed))

if __name__=="__main__": unittest.main()
