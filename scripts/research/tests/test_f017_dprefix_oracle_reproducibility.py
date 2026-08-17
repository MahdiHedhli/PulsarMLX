import json
import unittest
from pathlib import Path

from scripts.research.f017_dprefix_oracle_reproducibility import historical_forensics
from scripts.research.f017_dprefix_route_ambiguity import analyze, ambiguity_envelope

ROOT = Path(__file__).resolve().parents[3]


class OracleReproducibilityTests(unittest.TestCase):
    def test_historical_delta_and_inputs(self):
        result = historical_forensics()
        self.assertEqual(result["first_cross_process_oracle_divergence"], "layer_0_attention")
        self.assertEqual(result["real2_real3_layer3_delta"]["differing_elements"], 5080)
        self.assertTrue(result["input_identity"]["packed_40_exact"])
        self.assertTrue(result["input_identity"]["decoded_40_exact"])
        self.assertEqual(result["checkpoint_access"], 0)
        self.assertEqual(result["real_payload_ledger"], 139)

    def test_exact_implementations_match(self):
        roots = [ROOT / ".pulsarmlx-local/dprefix-exact-1" / item for item in ("run-a1", "run-a2", "run-b1", "run-b2")]
        names = ["embedding", "layer_0_attention", "layer_0_output", "layer_1_attention", "layer_1_output", "layer_2_attention", "layer_2_output", "layer_3_entry"]
        for name in names:
            payloads = [(root / f"{name}.f32le").read_bytes() for root in roots]
            self.assertTrue(all(payload == payloads[0] for payload in payloads[1:]), name)

    def test_ambiguity_envelope_covers_observations(self):
        envelope = ambiguity_envelope()
        self.assertTrue(envelope["covers_all_three_states"])
        self.assertEqual(envelope["component_count"], 6144)

    def test_route_proof_fails_closed_without_retained_inputs(self):
        result = analyze()
        self.assertEqual(result["route_insensitivity_disposition"], "ROUTE NOT PROVEN INVARIANT")
        self.assertEqual(result["membership_inequalities_proved"], 0)
        self.assertEqual(result["checkpoint_access"], 0)
        self.assertEqual(result["real_payload_ledger"], 139)

    def test_real_payload_ledger_unchanged(self):
        ledger = json.loads((ROOT / "docs/architecture/reviews/evidence/f017-real-payload-access-ledger-v1.json").read_text())
        self.assertEqual(ledger["cumulative_tensor_payloads"], 139)


if __name__ == "__main__":
    unittest.main()
