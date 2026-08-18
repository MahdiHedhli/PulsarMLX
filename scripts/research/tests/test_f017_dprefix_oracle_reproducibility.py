import json
import unittest
from pathlib import Path

from scripts.research.f017_dprefix_oracle_reproducibility import historical_forensics
from scripts.research.f017_dprefix_route_ambiguity import analyze, ambiguity_envelope

ROOT = Path(__file__).resolve().parents[3]
PUBLIC = ROOT / "docs/architecture/reviews/evidence"
PRIVATE_EXACT = ROOT / ".pulsarmlx-local/dprefix-exact-1"
PRIVATE_PACKED_MANIFEST = ROOT / ".pulsarmlx-local/dprefix-real-2/material/packed/manifest.json"


def public_evidence(name: str):
    return json.loads((PUBLIC / name).read_text())


class OracleReproducibilityTests(unittest.TestCase):
    def test_historical_delta_and_inputs(self):
        result = (
            historical_forensics()
            if PRIVATE_PACKED_MANIFEST.is_file()
            else public_evidence("f017-dprefix-oracle-cross-process-forensics-v1.json")
        )
        self.assertEqual(result["first_cross_process_oracle_divergence"], "layer_0_attention")
        self.assertEqual(result["real2_real3_layer3_delta"]["differing_elements"], 5080)
        self.assertTrue(result["input_identity"]["packed_40_exact"])
        self.assertTrue(result["input_identity"]["decoded_40_exact"])
        self.assertEqual(result["checkpoint_access"], 0)
        self.assertEqual(result["real_payload_ledger"], 139)

    def test_exact_implementations_match(self):
        roots = [PRIVATE_EXACT / item for item in ("run-a1", "run-a2", "run-b1", "run-b2")]
        if all(root.is_dir() for root in roots):
            names = ["embedding", "layer_0_attention", "layer_0_output", "layer_1_attention", "layer_1_output", "layer_2_attention", "layer_2_output", "layer_3_entry"]
            for name in names:
                payloads = [(root / f"{name}.f32le").read_bytes() for root in roots]
                self.assertTrue(all(payload == payloads[0] for payload in payloads[1:]), name)
            return
        result = public_evidence("f017-dprefix-exact1-descriptor-v1.json")
        self.assertEqual(result["reproduction"]["result"], "DPREFIX-EXACT-1 BITWISE SELF-REPRODUCIBLE")
        self.assertEqual(result["reproduction"]["fresh_process_count"], 4)
        self.assertEqual(len(result["stage_sha256"]), 8)

    def test_ambiguity_envelope_covers_observations(self):
        envelope = (
            ambiguity_envelope()
            if (PRIVATE_EXACT / "run-a1/layer_3_entry.f32le").is_file()
            else public_evidence("f017-dprefix-route-ambiguity-proof-v1.json")["ambiguity_set"]
        )
        self.assertTrue(envelope["covers_all_three_states"])
        self.assertEqual(envelope["component_count"], 6144)

    def test_route_proof_fails_closed_without_retained_inputs(self):
        result = (
            analyze()
            if (PRIVATE_EXACT / "run-a1/layer_3_entry.f32le").is_file()
            else public_evidence("f017-dprefix-route-ambiguity-proof-v1.json")
        )
        self.assertEqual(result["route_insensitivity_disposition"], "ROUTE NOT PROVEN INVARIANT")
        self.assertEqual(result["membership_inequalities_proved"], 0)
        self.assertEqual(result["checkpoint_access"], 0)
        self.assertEqual(result["real_payload_ledger"], 139)

    def test_real_payload_ledger_unchanged(self):
        ledger = json.loads((ROOT / "docs/architecture/reviews/evidence/f017-real-payload-access-ledger-v1.json").read_text())
        real2 = next(item for item in ledger["events"] if item["attempt"] == "DPREFIX-REAL-2")
        self.assertEqual(real2["cumulative_tensor_payloads_after_event"], 139)
        self.assertEqual(ledger["cumulative_tensor_payloads"], 166)


if __name__ == "__main__":
    unittest.main()
