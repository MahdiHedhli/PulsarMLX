import copy
import json
import shutil
import struct
import tempfile
import unittest
from pathlib import Path

from scripts.research import f017_q4_state_q6_authorization as M
from scripts.research.f017_m1f_minus1_dense_prefix_prep import decode_q6_k_independent
from scripts.research.ggml_kquants import dequantize_row_q6_k


ROOT = Path(__file__).resolve().parents[3]


class Q4StateTriadTests(unittest.TestCase):
    def baseline(self):
        return (
            M.load_json(M.Q4_LEDGER_V3),
            M.load_json(M.REAL_LEDGER),
            M.load_json(M.Q4_EVIDENCE),
        )

    def assert_rejected(self, mutate):
        attempt, real, evidence = copy.deepcopy(self.baseline())
        evidence_sha = M.Q4_EVIDENCE_SHA
        present = True
        result = mutate(attempt, real, evidence, evidence_sha, present)
        if result is not None:
            evidence_sha, present = result
        with self.assertRaises(M.ContractError):
            M.validate_q4_triad_objects(attempt, real, evidence if present else None, evidence_sha if present else None)

    def test_banked_state_triad_reconciles(self):
        self.assertEqual("Q4_K STATE TRIAD RECONCILED", M.validate_q4_triad())

    def test_negative_mutation_matrix(self):
        mutations = [
            lambda a, r, e, s, p: a["attempts"][0].update(consumed=False),
            lambda a, r, e, s, p: a["attempts"][0].update(ledger_after=57),
            lambda a, r, e, s, p: ("f" * 64, p),
            lambda a, r, e, s, p: a["attempts"][0].update(terminal_classification="REJECTED"),
            lambda a, r, e, s, p: a["attempts"][0].update(checkpoint_accessed=False),
            lambda a, r, e, s, p: a["attempts"].append(copy.deepcopy(a["attempts"][0])),
            lambda a, r, e, s, p: r["events"].append(copy.deepcopy([x for x in r["events"] if x.get("attempt") == M.Q4_ATTEMPT_ID][0])),
            lambda a, r, e, s, p: a["attempts"][0].update(ledger_after=59),
            lambda a, r, e, s, p: r.update(events=[x for x in r["events"] if x.get("attempt") != M.Q4_ATTEMPT_ID]),
            lambda a, r, e, s, p: (s, False),
        ]
        for index, mutation in enumerate(mutations):
            with self.subTest(index=index):
                self.assert_rejected(mutation)

    def test_real_event_packet_provenance(self):
        claim = {
            "committed_evidence_path": M.Q4_EVIDENCE.relative_to(ROOT).as_posix(),
            "committed_evidence_artifact_sha256": M.Q4_EVIDENCE_SHA,
            "git_commit_containing_evidence": M.Q4_EVIDENCE_COMMIT,
        }
        M.validate_real_event_claim(ROOT, claim)
        claim["committed_evidence_artifact_sha256"] = "0" * 64
        with self.assertRaises(M.ContractError):
            M.validate_real_event_claim(ROOT, claim)


class Q6AuthorizationTests(unittest.TestCase):
    def test_banked_pre_execution_package_remains_immutable(self):
        expected = {
            M.Q6_HANDOFF: "6430e70980dceeff48515a2f212fddcee495d2fabfc1ecb5c5ad578a64a5d6c2",
            M.Q6_FORMAT: "9e5d15d87b88b9754a5f4b546a110dc1c0659e2c6f62683e12401b8bffb6ff95",
            M.Q6_CONFIG: "215af50497a097f4738df8d75a45ebab86450dc2dbe0fcc5e034fe06b1436dd0",
            M.Q6_BINDING: "8160be060db46ab9c0e74480d9ad5450a4ac8dd28d26397a1d1b7911aea5cd91",
            M.Q6_ATTEMPT: "cc3bb30b0de8480294ab0e5565f80a36e5533a348f954f8a9e1fc985a7521f07",
        }
        for path, digest in expected.items():
            self.assertEqual(digest, M.file_sha256(path), path)
        M.validate_q6_package()

    def test_consumed_event_cannot_preflight_again(self):
        with self.assertRaises(M.ContractError):
            M.canonical_preflight(check_git=False)

    def test_target_and_one_payload_sufficiency(self):
        handoff = M.load_json(M.Q6_HANDOFF)
        self.assertEqual("blk.0.ffn_down.weight", handoff["target"]["tensor_name"])
        self.assertEqual(61_931_520, handoff["target"]["packed_length"])
        self.assertEqual("ONE Q6_K PAYLOAD SUFFICIENT", handoff["one_payload_sufficiency"]["verdict"])
        self.assertFalse(handoff["one_payload_sufficiency"]["tail_path"])
        self.assertEqual(M.CORRECTED_Q6_SHA, handoff["defect_closure"]["corrected_decoder_source_sha256"])

    def test_attempt_is_born_authorized_and_unconsumed(self):
        attempt = M.load_json(M.Q6_ATTEMPT)["attempts"][0]
        self.assertTrue(attempt["authorized"])
        self.assertFalse(attempt["consumed"])
        self.assertFalse(attempt["executed"])
        self.assertFalse(attempt["checkpoint_accessed"])
        self.assertFalse(attempt["automatic_retry"])
        self.assertFalse(attempt["automatic_dense_prefix_continuation"])

    def test_q6_package_mutations_fail_closed(self):
        relative_files = [
            M.Q4_EVIDENCE, M.Q4_LEDGER_V3, M.REAL_LEDGER, M.Q6_DEFECT, M.Q6_FORMAT,
            M.Q6_HANDOFF, M.Q6_CONFIG, M.Q6_BINDING, M.Q6_ATTEMPT, M.Q6_SCHEMA,
            ROOT / "scripts/research/ggml_kquants.py",
        ]
        mutations = [
            (M.Q6_CONFIG, lambda v: v.update(execution_authorized=False)),
            (M.Q6_CONFIG, lambda v: v["target"].update(offset=1_203_482_465)),
            (M.Q6_ATTEMPT, lambda v: v["attempts"][0].update(consumed=True)),
            (M.Q6_ATTEMPT, lambda v: v["attempts"][0].update(automatic_dense_prefix_continuation=True)),
            (M.Q6_BINDING, lambda v: v.update(execution_config_sha256="0" * 64)),
        ]
        for path, mutation in mutations:
            with self.subTest(path=path.name, mutation=mutation):
                with tempfile.TemporaryDirectory() as directory:
                    temp_root = Path(directory)
                    for source in relative_files:
                        destination = temp_root / source.relative_to(ROOT)
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source, destination)
                    target = temp_root / path.relative_to(ROOT)
                    value = M.load_json(target)
                    mutation(value)
                    target.write_bytes(M.canonical_bytes(value))
                    with self.assertRaises(M.ContractError):
                        M.validate_q6_package(temp_root)

    def test_corrected_grouped_and_index_decoders_are_exact(self):
        defect = M.load_json(M.Q6_DEFECT)
        packed = bytes.fromhex(defect["minimized_fixture"]["packed_hex"])
        grouped = dequantize_row_q6_k(packed, 256)
        indexed = decode_q6_k_independent(packed)
        grouped_bytes = struct.pack("<256f", *grouped)
        indexed_bytes = struct.pack("<256f", *indexed)
        self.assertEqual(grouped_bytes, indexed_bytes)
        self.assertEqual(defect["corrected_decoded_sha256"], M.sha256_bytes(grouped_bytes))
        self.assertEqual(grouped[32], -30.0)
        self.assertEqual(indexed[32], -30.0)

    def test_ci_binding_ledger(self):
        value = M.load_json(M.CI_LEDGER)
        M.validate_ci_ledger(value)
        value["bindings"].append(copy.deepcopy(value["bindings"][0]))
        with self.assertRaises(M.ContractError):
            M.validate_ci_ledger(value)

    def test_dense_prefix_load_bearing_artifacts_unchanged(self):
        expected = {
            "docs/architecture/reviews/evidence/f017-m1f-minus1-prompt-token-package-v1.json": "c05ba1cba69535cd17daf9f4326e5e1db25ffafe504c53712aa548f251741dff",
            "docs/architecture/reviews/evidence/f017-m1f-minus1-exact-inventory-v1.json": "eaf54506f5bd45ef41f223224096a253f6fa6c5e2ad3bf94971c18eb09f6b21b",
            "docs/architecture/reviews/evidence/f017-m1f-minus1-residency-admission-v1.json": "56ab1eae69b45f9ae97f98e1d36dfa124e080a6dc82573013cc57782bce1ac76",
            "specs/017-rust-native-inference-runtime/contracts/f017-dense-prefix-numerical-v1.json": "4a9f2f29689b8c20259ebadd46a0038008895ea173bf024b2ab805d35b7aa488",
        }
        for path, digest in expected.items():
            self.assertEqual(digest, M.file_sha256(ROOT / path), path)


if __name__ == "__main__":
    unittest.main()
