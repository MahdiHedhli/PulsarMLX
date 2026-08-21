import copy
import json
from pathlib import Path
import unittest

from scripts.research import validate_f017_apple_production_serial_f32_capture_v1 as validator

ROOT = Path(__file__).resolve().parents[3]
CONTRACTS = ROOT / "specs/017-rust-native-inference-runtime/contracts"


def doc(name):
    return json.loads((CONTRACTS / name).read_text())


class MutationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (ROOT / "crates/f017-runner/src/apple_serial_f32.rs").read_text()
        cls.binary = (ROOT / "crates/f017-runner/src/bin/f017-apple-serial-f32-capture.rs").read_text()
        cls.stage = doc("f017-apple-production-serial-f32-stage-manifest-v1.json")
        cls.capture = doc("f017-apple-production-serial-f32-capture-manifest-v1.json")
        cls.rn1 = doc("f017-apple-production-serial-f32-rn1-ownership-v2.json")
        cls.package = doc("f017-apple-production-serial-f32-package-schema-v1.json")

    def assert_stage_rejects(self, mutate):
        value = copy.deepcopy(self.stage); mutate(value)
        with self.assertRaises(validator.ValidationError):
            validator.validate_stage_contract(value, self.source)

    def assert_capture_rejects(self, mutate):
        value = copy.deepcopy(self.capture); mutate(value)
        with self.assertRaises(validator.ValidationError):
            validator.validate_capture_contract(value, validator.rust_stage_ids(self.source))

    def assert_rn1_rejects(self, mutate):
        value = copy.deepcopy(self.rn1); mutate(value)
        with self.assertRaises(validator.ValidationError): validator.validate_rn1_contract(value)

    def test_stage_mutations(self):
        mutations = [
            lambda d: d["stages"].pop(),
            lambda d: d["stages"].append(copy.deepcopy(d["stages"][0])),
            lambda d: d["stages"][2].__setitem__("symbol", "run_r9_exact"),
            lambda d: d["stages"][1].__setitem__("accumulator", "f64"),
            lambda d: d["stages"][26].__setitem__("order", "TREE_REDUCTION"),
            lambda d: d["stages"][26].__setitem__("rounding", "BINARY64"),
            lambda d: d["stages"][32].__setitem__("rounding", "WIDEN_ADD_NARROW"),
            lambda d: d["stages"][33].__setitem__("rounding", "WIDEN_ADD_NARROW"),
            lambda d: d["stages"][0].__setitem__("classification", "UNRESOLVED"),
            lambda d: d["stages"][0].__setitem__("extra", True),
        ]
        for index, mutation in enumerate(mutations):
            with self.subTest(index=index): self.assert_stage_rejects(mutation)

    def test_source_semantic_mutations(self):
        mutations = [
            self.source.replace("for slot in 0..ROUTER_TOP_K", "for slot in (0..ROUTER_TOP_K).rev()"),
            self.source.replace("then_with(|| a.cmp(&b))", "then_with(|| b.cmp(&a))"),
            self.source.replace("pub const ROUTER_TOP_K: usize = 8;", "pub const ROUTER_TOP_K: usize = 7;"),
            self.source.replace("pub const RMS_EPSILON: f32 = 0.00001_f32;", "pub const RMS_EPSILON: f32 = 0.000001_f32;"),
            self.source + "\nuse crate::layer_qualification;\n",
            self.source.replace(".map(|(&a, &b)| add_f32(a, b))", ".map(|(&a, &b)| (a as f64 + b as f64) as f32)", 1),
        ]
        for index, source in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises(validator.ValidationError):
                validator.validate_source_semantics(source, self.binary)

    def test_capture_mutations(self):
        mutations = [
            lambda d: d["stage_ids"].pop(),
            lambda d: d.__setitem__("recomputation", True),
            lambda d: d.__setitem__("arithmetic_mutation", True),
            lambda d: d.__setitem__("serialization", "NATIVE_ENDIAN"),
            lambda d: d.__setitem__("all_required_exactly_once", False),
        ]
        for index, mutation in enumerate(mutations):
            with self.subTest(index=index): self.assert_capture_rejects(mutation)

    def test_rn1_mutations(self):
        mutations = [
            lambda d: d["lock"].__setitem__("mechanism", "CHECK_THEN_CREATE"),
            lambda d: d.__setitem__("cross_invocation_terminalization", True),
            lambda d: d.__setitem__("shared_terminal_as_authority", True),
            lambda d: d["accounting"].__setitem__("terminal_json_sole_authority", True),
            lambda d: d["accounting"].__setitem__("mismatch", "WARN"),
            lambda d: d["artifact_inventory"].__setitem__("orphan_hash", "IGNORED"),
            lambda d: d.__setitem__("retry", True),
            lambda d: d.__setitem__("resume", True),
            lambda d: d.__setitem__("second_invocation", True),
        ]
        for index, mutation in enumerate(mutations):
            with self.subTest(index=index): self.assert_rn1_rejects(mutation)

    def test_package_mutations(self):
        mutations = [
            lambda d: d.__setitem__("package_created", True),
            lambda d: d.__setitem__("live_package_manifest", True),
            lambda d: d["tensor_roles"].pop(),
            lambda d: d["checkpoint_paths"].append("checkpoint"),
            lambda d: d.__setitem__("fallback", True),
            lambda d: d["fixed_graph"].__setitem__("routed_expert_ids", list(reversed(d["fixed_graph"]["routed_expert_ids"]))),
        ]
        for index, mutation in enumerate(mutations):
            value = copy.deepcopy(self.package); mutation(value)
            with self.subTest(index=index), self.assertRaises(validator.ValidationError):
                validator.validate_package_contract(value)

    def test_release_mutations(self):
        baseline = {
            "schema":"pulsarmlx.f017.apple-production-serial-f32-capture-release","schema_version":"2.0.0",
            "real_event_authorized":False,"ledger":{"start":175,"terminal":175},
            "execution_budgets":{**{key:0 for key in ["checkpoint_reads","shard_opens","attention_executions","expert_executions","aggregate_executions","shared_expert_executions","ffn_compositions","s1_materializations","s2_constructions"]},"production_equivalence_executions":1},
            "retry":False,"resume":False,"second_attempt":False,
            "stop_boundary":"AFTER_APPLE_PRODUCTION_SERIAL_F32_CAPTURE_AND_COMPARISON_ONLY","live_go_token_created":False,
        }
        mutations = [
            lambda d: d["ledger"].__setitem__("start", 174),
            lambda d: d["execution_budgets"].__setitem__("checkpoint_reads", 1),
            lambda d: d["execution_budgets"].__setitem__("production_equivalence_executions", 2),
            lambda d: d.__setitem__("real_event_authorized", True),
            lambda d: d.__setitem__("retry", True),
            lambda d: d.__setitem__("live_go_token_created", True),
        ]
        for index, mutation in enumerate(mutations):
            value = copy.deepcopy(baseline); mutation(value)
            with self.subTest(index=index), self.assertRaises(validator.ValidationError):
                validator.validate_release_shape(value)


if __name__ == "__main__": unittest.main()
