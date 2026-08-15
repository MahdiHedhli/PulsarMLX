import copy
import hashlib
import json
import unittest
from pathlib import Path

from scripts.research.validate_f017_q4_k_authorization import (
    READY_STATUS,
    AuthorizationError,
    load_package,
    validate_documents,
)


ROOT = Path(__file__).resolve().parents[3]


def sha(path: str) -> str:
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


class Q4KAuthorizationAmendmentTests(unittest.TestCase):
    def setUp(self):
        self.docs = load_package(ROOT)

    def assert_rejected(self, mutation):
        docs = copy.deepcopy(self.docs)
        mutation(docs)
        with self.assertRaises(AuthorizationError):
            validate_documents(docs)

    def test_canonical_preflight_is_ready_and_zero_read(self):
        result = validate_documents(self.docs)
        self.assertEqual(READY_STATUS, result)
        self.assertEqual(57, self.docs["ledger"]["cumulative_tensor_payloads"])
        self.assertEqual(0, self.docs["amendment"]["real_checkpoint_access"])
        self.assertFalse(self.docs["attempt"]["attempts"][0]["consumed"])

    def test_missing_attempt_fails(self):
        self.assert_rejected(lambda d: d["attempt"].update(attempts=[]))

    def test_unauthorized_attempt_fails(self):
        self.assert_rejected(lambda d: d["attempt"]["attempts"][0].update(authorized=False))

    def test_consumed_attempt_fails(self):
        self.assert_rejected(lambda d: d["attempt"]["attempts"][0].update(consumed=True))

    def test_wrong_attempt_id_fails(self):
        self.assert_rejected(lambda d: d["attempt"]["attempts"][0].update(attempt_id="Q4K-REAL-2"))

    def test_binding_or_config_mismatch_fails(self):
        self.assert_rejected(lambda d: d["binding"].update(execution_config_sha256="0" * 64))

    def test_wrong_ledger_before_fails(self):
        self.assert_rejected(lambda d: d["attempt"]["attempts"][0].update(ledger_before=58))

    def test_retry_or_chaining_fails(self):
        for key in ("automatic_retry", "automatic_q6_continuation", "automatic_dense_prefix_continuation"):
            with self.subTest(key=key):
                self.assert_rejected(lambda d, key=key: d["attempt"]["attempts"][0].update({key: True}))

    def test_post_amendment_config_mutation_fails(self):
        self.assert_rejected(lambda d: d["config"]["target"].update(offset=535316321))

    def test_historical_not_executed_evidence_is_immutable(self):
        self.assertEqual(
            "c29feb1479771bd8353d8382429dca656657f9cb18b51a53a4c1ad4eab9b678b",
            sha("docs/architecture/reviews/evidence/f017-q4-k-real-byte-qualification-attempt-1-not-executed-v1.json"),
        )
        self.assertEqual(
            "087b1a2fa652fadaa8e35c802030293bb00c7bd1d79c7d365a89cb2149260f59",
            sha("docs/architecture/reviews/f017-q4-k-real-byte-qualification-not-executed-review.md"),
        )

    def test_v1_controls_and_numerical_surface_are_immutable(self):
        self.assertEqual("bcb3bc2b7fca752d17555fd1c1efe8d77691102f742e66483b8f42a81a35b27b", sha("docs/architecture/reviews/evidence/f017-q4-k-execution-config-v1.json"))
        self.assertEqual("c3eea6693831c7821ae5973890754543b1be8e8f79a85674d3439c176c41ebb9", sha("docs/architecture/reviews/evidence/f017-q4-k-authorization-binding-v1.json"))
        self.assertEqual("d4c069b4afba82715d3351b87a459345dd89e25566cba73f42c1fc75c6118e51", sha("docs/architecture/reviews/evidence/f017-q4-k-real-byte-qualification-handoff-v1.json"))
        self.assertEqual("c78736cba193e82fb5110cad4e636f909d0ef4c0ece70726d601c6c033835034", sha("specs/017-rust-native-inference-runtime/contracts/f017-q4-k-evidence-v1.schema.json"))

    def test_public_authorization_artifacts_are_path_safe(self):
        for name in ("amendment", "config", "binding", "attempt"):
            rendered = json.dumps(self.docs[name], sort_keys=True)
            self.assertNotIn("/Users/", rendered)
            self.assertNotIn("file://", rendered)


if __name__ == "__main__":
    unittest.main()
