import copy
import json
import tempfile
import unittest
from pathlib import Path

from scripts.research.validate_f017_q6_k_evidence import EvidenceError, load_json, validate_evidence_object
from scripts.research.validate_f017_q6_k_repository_evidence import validate_objects, validate_repository_evidence


ROOT = Path(__file__).resolve().parents[3]
EVIDENCE = ROOT / "docs/architecture/reviews/evidence/f017-q6-k-real-byte-qualification-attempt-1-v1.json"
START = ROOT / "docs/architecture/reviews/evidence/f017-q6-k-real-byte-qualification-attempt-1-execution-start-v1.json"
ATTEMPT = ROOT / "docs/architecture/reviews/evidence/f017-q6-k-attempt-ledger-v2.json"
LEDGER = ROOT / "docs/architecture/reviews/evidence/f017-real-payload-access-ledger-v1.json"


class Q6KRealEvidenceTests(unittest.TestCase):
    def baseline(self):
        return tuple(load_json(path) for path in (START, EVIDENCE, ATTEMPT, LEDGER))

    def test_banked_terminal_evidence_is_exact_and_reconciled(self):
        evidence = load_json(EVIDENCE)
        self.assertEqual("EXACT_REAL_BYTE_QUALIFIED", validate_evidence_object(evidence))
        self.assertEqual("EXACT_REAL_BYTE_QUALIFIED", validate_repository_evidence(ROOT, EVIDENCE))

    def test_cross_artifact_negative_mutations_fail_closed(self):
        mutations = [
            lambda s, e, a, l: e["decoder_outputs"][0].update(decoded_sha256="0" * 64),
            lambda s, e, a, l: e["comparison"].update(bitwise_equal=False),
            lambda s, e, a, l: e["identity"].pop("packed_sha256"),
            lambda s, e, a, l: e["target"].update(offset=1203482465),
            lambda s, e, a, l: e["access"].update(positional_reads=2),
            lambda s, e, a, l: e["ledger"].update(after=58),
            lambda s, e, a, l: a["attempts"][0].update(consumed=False),
            lambda s, e, a, l: a["attempts"][0].update(evidence_sha256="1" * 64),
            lambda s, e, a, l: a["attempts"][0].update(automatic_dense_prefix_continuation=True),
            lambda s, e, a, l: l.update(cumulative_tensor_payloads=58),
            lambda s, e, a, l: l["events"].append(copy.deepcopy(l["events"][-1])),
            lambda s, e, a, l: s.update(checkpoint_accessed=True),
        ]
        for index, mutation in enumerate(mutations):
            with self.subTest(index=index):
                start, evidence, attempt, ledger = copy.deepcopy(self.baseline())
                mutation(start, evidence, attempt, ledger)
                with self.assertRaises(EvidenceError):
                    validate_objects(start, evidence, attempt, ledger)

    def test_duplicate_json_key_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text('{"schema":"x","schema":"y"}')
            with self.assertRaises(EvidenceError):
                load_json(path)

    def test_no_dense_prefix_or_model_compute(self):
        evidence = load_json(EVIDENCE)
        self.assertFalse(evidence["isolation"]["dense_prefix_executed"])
        self.assertEqual(0, evidence["isolation"]["model_compute"])
        self.assertEqual(0, evidence["isolation"]["mlx_candidate_dispatches"])
        self.assertEqual(1, evidence["access"]["tensor_payloads"])


if __name__ == "__main__":
    unittest.main()
