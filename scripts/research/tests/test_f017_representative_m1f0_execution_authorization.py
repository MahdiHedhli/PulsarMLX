from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
CONTRACT = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-m1f0-execution-authorization-v1.json"
VALIDATOR = ROOT / "scripts/research/validate_f017_representative_m1f0_execution_authorization.py"
SPEC = importlib.util.spec_from_file_location("f017_m1f0_auth_validator", VALIDATOR)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RepresentativeM1F0AuthorizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.document = json.loads(CONTRACT.read_text(encoding="utf-8"))

    def assert_rejected(self, mutate) -> None:
        candidate = copy.deepcopy(self.document)
        mutate(candidate)
        self.assertTrue(MODULE.validate_document(candidate), "mutation unexpectedly accepted")

    def test_authoritative_contract_and_catalog_pass(self) -> None:
        self.assertEqual([], MODULE.validate_document(self.document, ROOT))

    def test_wrong_authoritative_head_rejected(self) -> None:
        self.assert_rejected(lambda d: d["authoritative_repository"].update(commit_sha256="0" * 40))

    def test_wrong_boundary_hash_rejected(self) -> None:
        self.assert_rejected(lambda d: d["semantic_authority"]["representative_boundary_v3"].update(sha256="0" * 64))

    def test_wrong_semantic_graph_hash_rejected(self) -> None:
        self.assert_rejected(lambda d: d["semantic_authority"]["semantic_graph_v2"].update(sha256="0" * 64))

    def test_wrong_epsilon_rejected(self) -> None:
        self.assert_rejected(lambda d: d["execution_semantics"]["rmsnorm"].update(epsilon_source="f32(1e-6)"))

    def test_wrong_epsilon_dtype_rejected(self) -> None:
        self.assert_rejected(lambda d: d["execution_semantics"]["rmsnorm"].update(epsilon_dtype="binary64"))

    def test_wrong_rmsnorm_accumulator_dtype_rejected(self) -> None:
        self.assert_rejected(lambda d: d["execution_semantics"]["rmsnorm"].update(accumulator_dtype="binary64"))

    def test_missing_payload_rejected(self) -> None:
        self.assert_rejected(lambda d: d["attention_payload_inventory"].pop())

    def test_reordered_payload_rejected(self) -> None:
        def mutate(d):
            d["attention_payload_inventory"][0], d["attention_payload_inventory"][1] = d["attention_payload_inventory"][1], d["attention_payload_inventory"][0]
        self.assert_rejected(mutate)

    def test_changed_byte_range_rejected(self) -> None:
        self.assert_rejected(lambda d: d["attention_payload_inventory"][4].update(offset=2004872064))

    def test_wrong_packed_byte_total_rejected(self) -> None:
        self.assert_rejected(lambda d: d["read_contract"].update(expected_packed_bytes=132900863))

    def test_more_than_one_shard_open_rejected(self) -> None:
        self.assert_rejected(lambda d: d["checkpoint_binding"]["shard"].update(maximum_opens=2))

    def test_wrong_start_ledger_rejected(self) -> None:
        self.assert_rejected(lambda d: d["ledger_contract"].update(before=165))

    def test_wrong_success_ledger_rejected(self) -> None:
        self.assert_rejected(lambda d: d["ledger_contract"].update(after_success=176))

    def test_missing_partial_failure_semantics_rejected(self) -> None:
        self.assert_rejected(lambda d: d["ledger_contract"].update(partial_failure="continue"))

    def test_missing_router_reuse_authority_rejected(self) -> None:
        self.assert_rejected(lambda d: d["router_reuse_authorization"]["artifacts"].pop())

    def test_direct_dprefix_output_reuse_rejected(self) -> None:
        self.assert_rejected(lambda d: d["surface_separation"].update(historical_direct_dprefix_route_and_outputs="AUTHORIZED_INPUT"))

    def test_expert_execution_authorization_rejected(self) -> None:
        self.assert_rejected(lambda d: d["authorization"].update(expert_execution_authorized=True))

    def test_checkpoint_reads_outside_inventory_rejected(self) -> None:
        self.assert_rejected(lambda d: d["read_contract"].update(additional_reads=True))

    def test_real_event_authorization_rejected(self) -> None:
        self.assert_rejected(lambda d: d["authorization"].update(real_event_authorized=True))

    def test_route_must_derive_from_new_post_attention_state(self) -> None:
        self.assert_rejected(lambda d: d["surface_separation"].update(representative_route_must_be_computed_from_new_S1=False))


if __name__ == "__main__":
    unittest.main()
