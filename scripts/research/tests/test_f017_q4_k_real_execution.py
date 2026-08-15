import copy
import json
import tempfile
import unittest
from pathlib import Path

from scripts.research.execute_f017_q4_k_real import (
    EXPECTED,
    canonical_json,
    validate_banked_evidence,
)
from scripts.research.validate_f017_q4_k_evidence import (
    EvidenceError,
    load_json,
    validate_evidence_object,
)
from scripts.research.validate_f017_q4_k_repository_evidence import validate_repository_evidence


ROOT = Path(__file__).resolve().parents[3]


def valid_evidence() -> dict:
    decoded = "a" * 64
    return {
        "schema": "pulsarmlx.f017.q4-k-real-byte-qualification-evidence",
        "schema_version": "1.0.0",
        "attempt": {
            "attempt_id": "Q4K-REAL-1",
            "authorized": True,
            "consumed": True,
            "executed": True,
            "checkpoint_accessed": True,
            "execution_start_recorded": True,
            "terminal_class": "EXACT_REAL_BYTE_QUALIFIED",
            "automatic_retry": False,
            "automatic_q6_continuation": False,
            "automatic_dense_prefix_continuation": False,
        },
        "identity": {
            "execution_head": "a84e9179dc0ad4b82a695cdbc07373a4311e4589",
            "execution_config_sha256": EXPECTED["execution_config_sha256"],
            "authorization_binding_sha256": EXPECTED["authorization_binding_sha256"],
            "authorization_amendment_sha256": EXPECTED["authorization_amendment_sha256"],
            "checkpoint_set_sha256": EXPECTED["checkpoint_set_sha256"],
            "catalog_sha256": EXPECTED["catalog_sha256"],
            "tensor_map_sha256": EXPECTED["tensor_map_sha256"],
            "tensor_name": "token_embd.weight",
            "shard_ordinal": 2,
            "offset": 535316320,
            "packed_length": 535265280,
            "packed_sha256": "b" * 64,
            "gguf_shape": [6144, 154880],
            "quantization": "Q4_K",
            "format_contract_sha256": EXPECTED["format_contract_sha256"],
        },
        "access": {
            "shard_opens": 1,
            "positional_reads": 1,
            "tensor_payloads": 1,
            "packed_bytes": 535265280,
        },
        "decoder_outputs": [
            {
                "name": name,
                "source_sha256": source,
                "decoded_sha256": decoded,
                "element_count": 951582720,
                "logical_shape": [154880, 6144],
                "dtype": "f32",
                "serialization": "canonical_little_endian_ieee754_binary32",
                "non_finite_count": 0,
                "signed_zero_count": 0,
            }
            for name, source in EXPECTED["decoder_sources"]
        ],
        "comparison": {
            "bitwise_equal": True,
            "first_divergence": None,
            "signed_zero_policy": "PRESERVE_AND_COUNT_EXACT_F32_BITS",
        },
        "isolation": {
            "model_compute": 0,
            "mlx_candidate_dispatches": 0,
            "additional_payloads": 0,
            "q6_k_executed": False,
            "dense_prefix_executed": False,
            "fallback": False,
        },
        "ledger": {"before": 57, "actual_payloads": 1, "after": 58},
        "verdict": "EXACT_REAL_BYTE_QUALIFIED",
    }


class Q4KRealEvidenceTests(unittest.TestCase):
    def test_valid_pass_is_derived_from_raw_fields(self):
        evidence = valid_evidence()
        self.assertEqual("EXACT_REAL_BYTE_QUALIFIED", validate_evidence_object(evidence))
        self.assertEqual("EXACT_REAL_BYTE_QUALIFIED", validate_banked_evidence(evidence))

    def test_mutations_fail_closed(self):
        mutations = [
            lambda value: value["decoder_outputs"][0].update(decoded_sha256="c" * 64),
            lambda value: value["comparison"].update(bitwise_equal=False),
            lambda value: value["identity"].pop("packed_sha256"),
            lambda value: value["identity"].update(offset=535316321),
            lambda value: value["access"].update(positional_reads=2),
            lambda value: value["ledger"].update(after=57),
            lambda value: value["attempt"].update(consumed=False),
            lambda value: value["attempt"].update(automatic_q6_continuation=True),
            lambda value: value["identity"].update(execution_config_sha256="d" * 64),
        ]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                candidate = copy.deepcopy(valid_evidence())
                mutation(candidate)
                with self.assertRaises(EvidenceError):
                    validate_evidence_object(candidate)

    def test_duplicate_key_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text('{"schema":"x","schema":"y"}')
            with self.assertRaises(EvidenceError):
                load_json(path)

    def test_canonical_json_is_stable(self):
        evidence = valid_evidence()
        self.assertEqual(canonical_json(evidence), canonical_json(json.loads(canonical_json(evidence))))

    def test_banked_repository_evidence_and_ledgers_reconcile(self):
        evidence = ROOT / "docs/architecture/reviews/evidence/f017-q4-k-real-byte-qualification-attempt-1-v1.json"
        self.assertEqual("EXACT_REAL_BYTE_QUALIFIED", validate_repository_evidence(ROOT, evidence))


if __name__ == "__main__":
    unittest.main()
