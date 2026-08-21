import copy, json, os, tempfile, unittest
from pathlib import Path
from unittest import mock
from scripts.research import validate_f017_apple_serial_f32_execution_readiness_v1 as v
from scripts.research import f017_apple_serial_f32_execution_readiness_v1 as package
from scripts.research import f017_apple_serial_f32_equivalence_wrapper_v3 as wrapper

ROOT=Path(__file__).resolve().parents[3]; C=ROOT/"specs/017-rust-native-inference-runtime/contracts"
def doc(name): return json.loads((C/name).read_text())

class ReadinessMutationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package=doc("f017-apple-production-serial-f32-retained-40-tensor-package-v1.json")
        cls.code=doc("f017-apple-production-serial-f32-code-manifest-v4.json")
        cls.comparison=doc("f017-apple-production-serial-f32-comparison-execution-contract-v1.json")
        cls.routing=doc("f017-apple-production-serial-f32-routing-execution-gates-v1.json")
        cls.determinism=doc("f017-apple-production-serial-f32-determinism-v2.json")
        cls.accounting=doc("f017-apple-production-serial-f32-future-real-event-accounting-v1.json")
        cls.auth=doc("f017-apple-production-serial-f32-future-authorization-schema-v4.json")
        cls.inert=doc("f017-apple-production-serial-f32-inert-go-fixture-v3.json")
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

    def test_all_authority_scope_fields_are_enforced(self):
        release=doc("f017-apple-production-serial-f32-equivalence-single-use-release-v5.json")
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); release_path=root/"release.json"; review_path=root/"review.json"; approval_path=root/"approval.json"; token_path=root/"token.json"
            release["machine_local_paths"]["capture_root"]="/fixed/capture"
            release["canonical_readiness_review_path"]="review.json"
            release_path.write_text(json.dumps(release,sort_keys=True,separators=(",", ":"))+"\n")
            reviewed_head="1"*40
            review={"schema":"pulsarmlx.f017.apple-production-serial-f32-execution-readiness-independent-review","schema_version":"1.0.0","reviewer_model":"claude-fable-5","reviewed_head":reviewed_head,"verdict":"ACCEPT"}
            review_path.write_text(json.dumps(review,sort_keys=True,separators=(",", ":"))+"\n")
            approval={key:None for key in release["approval_schema_fields"]}
            approval.update({"schema":"pulsarmlx.f017.apple-production-serial-f32-equivalence-independent-approval","schema_version":"1.0.0","event_id":release["event_id"],"release_id":release["release_id"],"attempt_id":release["attempt_id"],"release_sha256":wrapper.sha(release_path),"readiness_head":reviewed_head,"execution_code_head":release["execution_code_head"],"native_executable_sha256":release["native_executable_sha256"],"code_manifest_sha256":release["code_manifest"]["sha256"],"runtime_binding_sha256":release["runtime_binding"]["sha256"],"package_root_sha256":release["package_root_sha256"],"package_manifest_sha256":release["package_census_sha256"],"stage_manifest_sha256":release["stage_manifest_sha256"],"capture_manifest_sha256":release["capture_manifest_sha256"],"comparison_contract_sha256":release["comparison_contract_sha256"],"determinism_contract_sha256":release["determinism_contract_sha256"],"wrapper_sha256":release["wrapper_sha256"],"terminalizer_sha256":release["terminalizer_sha256"],"reviewed_head":reviewed_head,"readiness_review_path":"review.json","readiness_review_sha256":wrapper.sha(review_path),"reviewer_model":"claude-fable-5","verdict":"ACCEPT","approval_statement":wrapper.APPROVAL_STATEMENT,"approval_does_not_execute":True,"approval_is_not_token":True,"human_approval_identity":"TEST_HUMAN","real_event_authorized":True,"ledger":175,"stop_boundary":release["stop_boundary"]})
            approval_path.write_text(json.dumps(approval,sort_keys=True,separators=(",", ":"))+"\n")
            token={key:None for key in release["go_token_schema_fields"]}
            for key in ("event_id","release_id","attempt_id","execution_code_head","native_executable_sha256","package_root_sha256","stage_manifest_sha256","capture_manifest_sha256","comparison_contract_sha256","determinism_contract_sha256","wrapper_sha256","terminalizer_sha256"):
                token[key]=release[key]
            token.update({"schema":"pulsarmlx.f017.apple-production-serial-f32-live-go","schema_version":"1.0.0","release_sha256":wrapper.sha(release_path),"approval_sha256":wrapper.sha(approval_path),"readiness_head":reviewed_head,"code_manifest_sha256":release["code_manifest"]["sha256"],"runtime_binding_sha256":release["runtime_binding"]["sha256"],"package_manifest_sha256":release["package_census_sha256"],"expected_starting_ledger":175,"allowed_real_payload_consumption":0,"allowed_attempt_count":1,"retries":0,"resume":False,"checkpoint_reads":0,"checkpoint_fallback":"PROHIBITED","allowed_stage_range":"input_hidden..production_s2","allowed_output_root":"/fixed/capture","human_approval_identity":"TEST_HUMAN","disposition":"GO_EXECUTE_ONCE_NO_RETRY","real_event_authorized":True})
            token_path.write_text(json.dumps(token,sort_keys=True,separators=(",", ":"))+"\n")
            with mock.patch.object(wrapper,"REPO",root):
                wrapper.validate_authority(release_path,release,approval_path,token_path)
                for field,bad in (("checkpoint_reads",999),("checkpoint_fallback","ALLOWED"),("allowed_stage_range","EVERYTHING"),("allowed_output_root","/tmp/evil"),("allowed_real_payload_consumption",99),("expected_starting_ledger",176),("readiness_head","0"*40)):
                    changed=copy.deepcopy(token); changed[field]=bad
                    token_path.write_text(json.dumps(changed,sort_keys=True,separators=(",", ":"))+"\n")
                    with self.subTest(field=field), self.assertRaises(wrapper.GateError): wrapper.validate_authority(release_path,release,approval_path,token_path)
                token_path.write_text(json.dumps(token,sort_keys=True,separators=(",", ":"))+"\n")
                for field,bad in (("schema","EVIL"),("schema_version","9.9.9")):
                    changed=copy.deepcopy(token); changed[field]=bad
                    token_path.write_text(json.dumps(changed,sort_keys=True,separators=(",", ":"))+"\n")
                    with self.subTest(field=field), self.assertRaises(wrapper.GateError): wrapper.validate_authority(release_path,release,approval_path,token_path)
                token_path.write_text(json.dumps(token,sort_keys=True,separators=(",", ":"))+"\n")
                changed_review=copy.deepcopy(review); changed_review["schema"]="pulsarmlx.f017.apple-production-serial-f32-capture-independent-review"
                review_path.write_text(json.dumps(changed_review,sort_keys=True,separators=(",", ":"))+"\n")
                changed_approval=copy.deepcopy(approval); changed_approval["readiness_review_sha256"]=wrapper.sha(review_path)
                approval_path.write_text(json.dumps(changed_approval,sort_keys=True,separators=(",", ":"))+"\n")
                changed_token=copy.deepcopy(token); changed_token["approval_sha256"]=wrapper.sha(approval_path)
                token_path.write_text(json.dumps(changed_token,sort_keys=True,separators=(",", ":"))+"\n")
                with self.assertRaisesRegex(wrapper.GateError,"READINESS_REVIEW_SCHEMA"):
                    wrapper.validate_authority(release_path,release,approval_path,token_path)

    def test_success_terminalization_rejects_any_payload_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); (root/"payload-receipts").mkdir()
            owner={"invocation_id":"inv","attempt_id":"attempt"}
            (root/"owner.json").write_text(json.dumps(owner,sort_keys=True,separators=(",", ":"))+"\n")
            (root/"payload-receipts"/"unexpected.json").write_text("{}\n")
            with self.assertRaisesRegex(wrapper.GateError,"RETAINED_ONLY_EVENT_HAS_PAYLOAD_RECEIPTS"):
                wrapper.terminalize_owned_success_v3(root,root/"capture","inv",wrapper.sha(root/"owner.json"))

if __name__=="__main__": unittest.main()
