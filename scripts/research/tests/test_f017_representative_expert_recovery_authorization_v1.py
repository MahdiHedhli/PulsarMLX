from __future__ import annotations

import copy
import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[3]
PATH = ROOT / "scripts/research/validate_f017_representative_expert_recovery_authorization_v1.py"
SPEC = importlib.util.spec_from_file_location("validator", PATH)
V = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(V)


class AuthorizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = V.load(V.AUTH)

    def reject(self, mutation):
        value = copy.deepcopy(self.base); mutation(value)
        with self.assertRaises(V.ValidationError): V.validate(ROOT, value)

    def test_repository(self):
        self.assertEqual(V.validate(ROOT), "REPRESENTATIVE_EXPERT_RECOVERY_AUTHORIZATION_VALID")

    def test_mutations(self):
        mutations = [
            lambda x: x.__setitem__("preparation_base_head", "0"*40),
            lambda x: x.__setitem__("route_value_evidence_sha256", "0"*64),
            lambda x: x["representative_expert_input"].__setitem__("sha256", "0"*64),
            lambda x: x["representative_expert_input"].__setitem__("semantic_role", "DIRECT_DPREFIX"),
            lambda x: x["selected_expert_ids"].__setitem__(3, 73),
            lambda x: x["route_pairs"][3].__setitem__("routing_weight", x["routing_weights"][4]),
            lambda x: x["selected_expert_ids"].__setitem__(7, 250),
            lambda x: x["selected_expert_ids"].pop(),
            lambda x: x["selected_expert_ids"].append(1),
            lambda x: x["retained_payload_inventory"].__setitem__(0, x["retained_payload_inventory"][1]),
            lambda x: x["retained_payload_inventory"][0].__setitem__("offset", 1),
            lambda x: x["retained_payload_inventory"][0].__setitem__("packed_bytes", 1),
            lambda x: x["retained_payload_inventory"].append(copy.deepcopy(x["retained_payload_inventory"][0])),
            lambda x: x["access_accounting"].__setitem__("starting_real_payload_ledger", 174),
            lambda x: x["access_accounting"].__setitem__("successful_terminal_ledger", 176),
            lambda x: x["access_accounting"].__setitem__("new_checkpoint_payload_reads", 1),
            lambda x: x["failure_semantics"].__setitem__("retry", True),
            lambda x: x["failure_semantics"].__setitem__("partial_output_failure_is_terminal", False),
            lambda x: x["computation_contract"].__setitem__("sha256", "0"*64),
            lambda x: x["executor"].__setitem__("sha256", "0"*64),
            lambda x: x.__setitem__("synthetic_rehearsal", None),
            lambda x: x["prohibitions"].__setitem__("historical_direct_dprefix_outputs", False),
            lambda x: x["prohibitions"].__setitem__("routed_aggregate", False),
            lambda x: x["prohibitions"].__setitem__("shared_expert", False),
            lambda x: x["prohibitions"].__setitem__("ffn_completion", False),
            lambda x: x["future_release_token_requirements"].__setitem__("execution_binding_policy", "NONE"),
            lambda x: x["output_contract"].__setitem__("consumer_authority_requires_terminal_complete", False),
            lambda x: x.__setitem__("real_event_authorized", True),
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation): self.reject(mutation)


if __name__ == "__main__": unittest.main()
