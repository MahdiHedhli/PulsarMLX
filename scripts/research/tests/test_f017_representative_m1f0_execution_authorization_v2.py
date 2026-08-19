from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
VALIDATOR = ROOT / "scripts/research/validate_f017_representative_m1f0_execution_authorization_v2.py"
SPEC = importlib.util.spec_from_file_location("f017_auth_v2", VALIDATOR)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class RepresentativeM1F0AuthorizationV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.wrapper = MODULE.load(MODULE.AUTH)
        cls.candidate = MODULE.load(ROOT / cls.wrapper["authorization_candidate"]["path"])
        cls.rehearsal = MODULE.load(ROOT / cls.wrapper["synthetic_rehearsal"]["path"])
        cls.stage = MODULE.load(ROOT / cls.candidate["stage_vocabulary"]["path"])
        cls.historical = MODULE.load(ROOT / cls.candidate["historical_hash_anchor"]["path"])

    def errors(self, mutate) -> list[str]:
        values = [copy.deepcopy(value) for value in (self.wrapper, self.candidate, self.rehearsal, self.stage, self.historical)]
        mutate(*values)
        return MODULE.validate_document(*values)

    def rejected(self, mutate) -> None:
        self.assertTrue(self.errors(mutate), "mutation unexpectedly accepted")

    def test_package_passes_with_bound_files(self) -> None:
        self.assertEqual([], MODULE.validate_paths())

    def test_wrong_authoritative_head(self) -> None:
        self.rejected(lambda w, c, r, s, h: c["authoritative_repository"].update(commit_sha256="0" * 40))

    def test_wrong_boundary(self) -> None:
        self.rejected(lambda w, c, r, s, h: c["semantic_authority"]["representative_boundary_v3"].update(sha256="0" * 64))

    def test_wrong_graph(self) -> None:
        self.rejected(lambda w, c, r, s, h: c["semantic_authority"]["semantic_graph_v2"].update(sha256="0" * 64))

    def test_wrong_epsilon(self) -> None:
        self.rejected(lambda w, c, r, s, h: c["execution_semantics"]["rmsnorm"].update(epsilon_source="f32(1e-6)"))

    def test_wrong_epsilon_dtype(self) -> None:
        self.rejected(lambda w, c, r, s, h: c["execution_semantics"]["rmsnorm"].update(epsilon_dtype="binary64"))

    def test_packed_hash_corruption(self) -> None:
        self.rejected(lambda w, c, r, s, h: c["attention_payload_inventory"][3].update(packed_sha256="0" * 64))

    def test_decoded_hash_corruption(self) -> None:
        self.rejected(lambda w, c, r, s, h: c["attention_payload_inventory"][4].update(decoded_sha256="0" * 64))

    def test_f32_packed_decoded_invariant(self) -> None:
        self.rejected(lambda w, c, r, s, h: c["attention_payload_inventory"][0].update(decoded_sha256="f" * 64))

    def test_retain_before_decode_required(self) -> None:
        self.rejected(lambda w, c, r, s, h: c["read_contract"].update(retain_at_creation_before_decode=False))

    def test_durable_receipt_required(self) -> None:
        self.rejected(lambda w, c, r, s, h: c["read_contract"].update(durable_receipt_before_next_read=False))

    def test_wrong_executor_sha(self) -> None:
        self.rejected(lambda w, c, r, s, h: w["executor"].update(sha256="0" * 64))

    def test_missing_rehearsal_sha(self) -> None:
        self.rejected(lambda w, c, r, s, h: w["synthetic_rehearsal"].pop("sha256"))

    def test_wrong_stage_vocabulary(self) -> None:
        self.rejected(lambda w, c, r, s, h: s["stages"][12].update(name="attention_residual"))

    def test_missing_s0_manifest(self) -> None:
        self.rejected(lambda w, c, r, s, h: c["retained_inputs"][0].pop("private_manifest_sha256"))

    def test_retained_checkpoint_fallback(self) -> None:
        self.rejected(lambda w, c, r, s, h: c["retained_inputs"][2].update(checkpoint_fallback=True))

    def test_q5_decoder_independence_required(self) -> None:
        self.rejected(lambda w, c, r, s, h: c["decoder_bindings"]["Q5_K"].update(independent_kernels=False))

    def test_q8_same_retained_bytes_required(self) -> None:
        self.rejected(lambda w, c, r, s, h: c["decoder_bindings"]["Q8_0"].update(same_retained_bytes=False))

    def test_wrong_actual_read_accounting(self) -> None:
        self.rejected(lambda w, c, r, s, h: r["success_accounting"].update(checkpoint_payload_reads=12))

    def test_missing_banker_binding(self) -> None:
        self.rejected(lambda w, c, r, s, h: r["success_terminal"].pop("journal_sha256"))

    def test_inventory_reorder(self) -> None:
        def mutate(w, c, r, s, h):
            c["attention_payload_inventory"][0], c["attention_payload_inventory"][1] = c["attention_payload_inventory"][1], c["attention_payload_inventory"][0]
        self.rejected(mutate)

    def test_changed_range(self) -> None:
        self.rejected(lambda w, c, r, s, h: c["attention_payload_inventory"][7].update(offset=0))

    def test_wrong_total(self) -> None:
        self.rejected(lambda w, c, r, s, h: c["read_contract"].update(expected_packed_bytes=1))

    def test_more_than_one_open(self) -> None:
        self.rejected(lambda w, c, r, s, h: c["read_contract"].update(maximum_shard_opens=2))

    def test_wrong_ledger(self) -> None:
        self.rejected(lambda w, c, r, s, h: c["ledger_contract"].update(after_success=176))

    def test_missing_partial_failure(self) -> None:
        self.rejected(lambda w, c, r, s, h: c["ledger_contract"].update(partial_failure="continue"))

    def test_direct_dprefix_reuse(self) -> None:
        self.rejected(lambda w, c, r, s, h: c["surface_separation"].update(historical_direct_dprefix_outputs="AUTHORIZED"))

    def test_expert_authorization(self) -> None:
        self.rejected(lambda w, c, r, s, h: w["authorization"].update(expert_execution_authorized=True))

    def test_real_event_authorization(self) -> None:
        self.rejected(lambda w, c, r, s, h: w["authorization"].update(real_event_authorized=True))


if __name__ == "__main__":
    unittest.main()
