from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import struct
import tempfile
import unittest
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[3]


def load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


INPUT = load("f017_m1f0_input", "scripts/research/generate_f017_m1f0_input.py")
M1F0 = load("f017_m1f0_admission", "scripts/research/f017_m1f0_admission.py")
SPEC = load("prepare_f017_m1f0", "scripts/research/prepare_f017_m1f0_real_reference.py")


class M1F0AdmissionTests(unittest.TestCase):
    def test_python_rust_spec_decoder_fixtures_are_exact(self):
        import sys

        sys.path.insert(0, str(ROOT / "scripts/research"))
        from ggml_kquants import dequantize_row_q5_k
        from glm52_dense_primitives import _decode_q8_0_row

        q5 = bytearray(((index * 73 + 19) & 255) for index in range(176))
        q5[:4] = bytes.fromhex("0030002c")
        spec_q5 = SPEC.decode_q5_k_spec(bytes(q5))
        project_q5 = np.asarray(dequantize_row_q5_k(bytes(q5)), dtype="<f4")
        self.assertEqual(spec_q5.tobytes(), project_q5.tobytes())
        self.assertEqual(hashlib.sha256(spec_q5.tobytes()).hexdigest(), "6168658f2e27a4650816dd5c3a31a85ac2908045ac7725f2cf79b662e3c478e7")

        q8 = bytearray(((index * 41 + 7) & 255) for index in range(34))
        q8[:2] = bytes.fromhex("0030")
        spec_q8 = SPEC.decode_q8_0_spec(bytes(q8))
        project_q8 = np.asarray(_decode_q8_0_row(bytes(q8), 32), dtype="<f4")
        self.assertEqual(spec_q8.tobytes(), project_q8.tobytes())
        self.assertEqual(hashlib.sha256(spec_q8.tobytes()).hexdigest(), "05ff099941e33b46c92c19002bd1431b3587ce83476f8f1ae364318d89a76c79")
    def test_input_regeneration_is_exact_and_not_historical(self):
        generated = INPUT.document()
        committed = json.loads((ROOT / INPUT.OUTPUT_PATH).read_text())
        self.assertEqual(generated, committed)
        self.assertEqual(generated["state"]["hidden"]["shape"], [6144])
        self.assertEqual(generated["state"]["query_position"]["value"], 0)
        self.assertEqual(generated["state"]["dsa"]["mode"], "range_fill")
        self.assertNotEqual(
            generated["state"]["hidden"]["sha256"],
            "5c3e4ebc2d5909c5e6f556bdc00f50130b705a3fb3fe7150f4f24bf7c81bbb80",
        )
        self.assertEqual(INPUT.package_sha256(generated), generated["package_sha256"])

    def test_attention_router_allowlist_is_exact_and_expert_free(self):
        catalog = ROOT / "docs/research/glm52/raw/f016-c01-catalog-0001.json"
        allowlist = M1F0.build_allowlist(catalog)
        self.assertEqual(len(allowlist), 12)
        self.assertEqual({item["shard_ordinal"] for item in allowlist}, {2})
        self.assertEqual(sum(item["packed_length"] for item in allowlist), 139_217_920)
        self.assertEqual(sum(item["decoded_length"] for item in allowlist), 666_430_464)
        self.assertEqual({item["quantization"] for item in allowlist}, {"F32", "Q5_K", "Q8_0"})
        for item in allowlist:
            self.assertNotIn("exps", item["name"])
            self.assertNotIn("shexp", item["name"])
        M1F0.validate_allowlist(allowlist)

    def test_allowlist_rejects_expert_adjacent_missing_and_wildcard(self):
        catalog = ROOT / "docs/research/glm52/raw/f016-c01-catalog-0001.json"
        allowlist = M1F0.build_allowlist(catalog)
        mutations = []
        extra = copy.deepcopy(allowlist)
        extra.append({**extra[-1], "name": "blk.3.ffn_gate_exps.weight", "role": "expert_gate"})
        mutations.append(extra)
        wrong_layer = copy.deepcopy(allowlist)
        wrong_layer[0]["name"] = wrong_layer[0]["name"].replace("blk.3", "blk.4")
        mutations.append(wrong_layer)
        missing = copy.deepcopy(allowlist[:-1])
        mutations.append(missing)
        wildcard = copy.deepcopy(allowlist)
        wildcard[0]["name"] = "blk.3.*"
        mutations.append(wildcard)
        for mutated in mutations:
            with self.subTest(name=mutated[0]["name"]):
                with self.assertRaises(ValueError):
                    M1F0.validate_allowlist(mutated)

    def test_selection_is_stable_exact_and_canonically_serialized(self):
        probabilities = [0.25] * 256
        scores = [0.0] * 256
        for expert in [15, 177, 233, 41, 166, 26, 10, 152, 9]:
            scores[expert] = 0.75
        selected, weights = M1F0.select_route(probabilities, scores)
        self.assertEqual(selected, [9, 10, 15, 26, 41, 152, 166, 177])
        self.assertEqual(M1F0.id_bytes(selected), struct.pack("<8H", *selected))
        self.assertEqual(len(M1F0.weight_bytes(weights)), 64)
        with self.assertRaises(ValueError):
            M1F0.select_route(probabilities, [float("nan")] + scores[1:])

    def test_synthetic_real_shape_is_deterministic_and_has_zero_expert_access(self):
        fixture = json.loads((ROOT / INPUT.OUTPUT_PATH).read_text())
        result = M1F0.synthetic_qualification(fixture, repeats=10)
        self.assertEqual(result["architecture"]["hidden_width"], 6144)
        self.assertEqual(result["architecture"]["router_expert_count"], 256)
        self.assertEqual(result["repeat_integrity"]["observed"], 10)
        self.assertTrue(result["repeat_integrity"]["all_equal"])
        self.assertEqual(result["isolation"]["expert_tensor_accesses"], 0)
        self.assertEqual(result["isolation"]["expert_dispatches"], 0)
        self.assertEqual(result["isolation"]["conceptual_discoveries"], 1)
        self.assertEqual(len(result["selection"]["selected_ids"]), 8)
        self.assertNotEqual(result["selection"]["selected_ids"], M1F0.HISTORICAL_ROUTE)

    def test_real_shaped_stress_contract_is_frozen_and_deterministic(self):
        fixture = json.loads((ROOT / INPUT.OUTPUT_PATH).read_text())
        result = M1F0.synthetic_stress(fixture)
        self.assertEqual(result["case_count"], 6)
        self.assertEqual(result["status"], "passed")
        self.assertFalse(result["post_observation_retuning"])
        self.assertEqual(result["expert_tensor_accesses"], 0)
        self.assertTrue(all(case["top8_exact"] for case in result["cases"]))

    def test_preflight_is_non_consuming_hash_bound_and_fail_closed(self):
        fixture = json.loads((ROOT / INPUT.OUTPUT_PATH).read_text())
        config = M1F0.build_preparation_config(ROOT, fixture)
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.json"
            config_path.write_bytes(M1F0.canonical_json(config))
            digest = hashlib.sha256(config_path.read_bytes()).hexdigest()
            result = M1F0.preflight(ROOT, config_path, digest)
            self.assertEqual(result["result"], "READY_TO_EXECUTE_M1_F0")
            self.assertEqual(result["checkpoint_payload_reads"], 0)
            self.assertEqual(result["expert_tensor_accesses"], 0)
            self.assertFalse(result["attempt_consumed"])
            mutated = copy.deepcopy(config)
            mutated["attempt"] = 2
            config_path.write_bytes(M1F0.canonical_json(mutated))
            with self.assertRaises(ValueError):
                M1F0.preflight(ROOT, config_path, hashlib.sha256(config_path.read_bytes()).hexdigest())

    def test_historical_route_config_mutation_and_attempt_reuse_fail(self):
        fixture = json.loads((ROOT / INPUT.OUTPUT_PATH).read_text())
        config = M1F0.build_preparation_config(ROOT, fixture)
        cases = []
        historical = copy.deepcopy(config)
        historical["forbidden_historical_route"] = [0] * 8
        cases.append(historical)
        expert = copy.deepcopy(config)
        expert["tensor_allowlist"][0]["name"] = "blk.3.ffn_gate_exps.weight"
        cases.append(expert)
        consumed = copy.deepcopy(config)
        consumed["attempt_state"] = "EXECUTION_STARTED"
        cases.append(consumed)
        stale = copy.deepcopy(config)
        stale["input_state"]["package_sha256"] = "0" * 64
        cases.append(stale)
        wrong_bias = copy.deepcopy(config)
        wrong_bias["tensor_allowlist"][-1]["offset"] += 32
        cases.append(wrong_bias)
        wrong_decoder = copy.deepcopy(config)
        wrong_decoder["tensor_allowlist"][1]["decoder_contract"] = "stale-q5"
        cases.append(wrong_decoder)
        above_budget = copy.deepcopy(config)
        above_budget["access_budget"]["tensor_payloads"] = 13
        cases.append(above_budget)
        for value in cases:
            with self.subTest(keys=list(value)):
                with self.assertRaises(ValueError):
                    M1F0.validate_config(ROOT, value)

    def test_route_artifact_contract_rejects_stale_input_and_expert_evidence(self):
        fixture = json.loads((ROOT / INPUT.OUTPUT_PATH).read_text())
        synthetic = M1F0.synthetic_qualification(fixture, repeats=10)
        route = M1F0.route_artifact_from_synthetic(fixture, synthetic)
        M1F0.validate_route_artifact(route, fixture["package_sha256"])
        stale = copy.deepcopy(route)
        stale["input_package_sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            M1F0.validate_route_artifact(stale, fixture["package_sha256"])
        widened = copy.deepcopy(route)
        widened["expert_computation"] = True
        with self.assertRaises(ValueError):
            M1F0.validate_route_artifact(widened, fixture["package_sha256"])
        substituted = copy.deepcopy(route)
        substituted["top8_ids"] = M1F0.HISTORICAL_ROUTE
        with self.assertRaises(ValueError):
            M1F0.validate_route_artifact(substituted, fixture["package_sha256"])
        inverted = copy.deepcopy(route)
        inverted["top8_ids"] = list(reversed(inverted["top8_ids"]))
        with self.assertRaises(ValueError):
            M1F0.validate_route_artifact(inverted, fixture["package_sha256"])
        weight_drift = copy.deepcopy(route)
        weight_drift["routing_weights"][0] += 1e-15
        with self.assertRaises(ValueError):
            M1F0.validate_route_artifact(weight_drift, fixture["package_sha256"])

    def test_real_preparer_rejects_unissued_authorization_before_private_access(self):
        fixture = json.loads((ROOT / INPUT.OUTPUT_PATH).read_text())
        config = M1F0.build_preparation_config(ROOT, fixture)
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            config_path = temporary / "config.json"
            config_path.write_bytes(M1F0.canonical_json(config))
            digest = hashlib.sha256(config_path.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError, "not authorized"):
                SPEC.prepare(ROOT, config_path, digest, None, None, temporary, temporary / "oracle.json")
            self.assertFalse((temporary / "oracle.json").exists())

    def test_private_package_traversal_and_symlink_escape_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory) / "package"
            package.mkdir()
            outside = Path(directory) / "outside.bin"
            outside.write_bytes(b"x")
            with self.assertRaises(ValueError):
                SPEC._safe_package_file(package, "../outside.bin")
            link = package / "link.bin"
            link.symlink_to(outside)
            with self.assertRaises(ValueError):
                SPEC._safe_package_file(package, "link.bin")


if __name__ == "__main__":
    unittest.main()
