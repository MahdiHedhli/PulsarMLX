from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
import unittest
from unittest import mock
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
MODULE=ROOT/"scripts/research/validate_f017_native_d35_comparison_grant_v1.py"
SPEC=importlib.util.spec_from_file_location("grant_validator",MODULE); validator=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(validator)
GRANT=ROOT/"specs/017-rust-native-inference-runtime/contracts/f017-native-d3-5-comparison-read-grant-v1.json"


class GrantMutations(unittest.TestCase):
    def setUp(self): self.doc=json.loads(GRANT.read_text())

    def reject(self, mutate):
        value=copy.deepcopy(self.doc); mutate(value)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"grant.json"; path.write_text(json.dumps(value)+"\n")
            with self.assertRaises((ValueError,FileNotFoundError)):
                validator.validate(path,resolve_executable=False)

    def test_baseline(self): self.assertEqual(validator.validate()["result"],"PASS")
    def test_mutations(self):
        mutations=[
            ("extra",lambda x:x.__setitem__("unknown",1)),
            ("consumer",lambda x:x["consumer"].__setitem__("id","WRONG")),
            ("d0",lambda x:x["authority"].__setitem__("d0_sha256","0"*64)),
            ("evidence",lambda x:x["authority"].__setitem__("d3_5_evidence_sha256","0"*64)),
            ("diagnostic",lambda x:x["authority"].__setitem__("diagnostic_metrics_reusable",True)),
            ("ledger",lambda x:x["authority"].__setitem__("historical_master_terminal",176)),
            ("attempts",lambda x:x["event"].__setitem__("attempts",2)),
            ("retries",lambda x:x["event"].__setitem__("retries",1)),
            ("resume",lambda x:x["event"].__setitem__("resume",True)),
            ("rerun",lambda x:x["event"].__setitem__("numerical_reexecution",True)),
            ("checkpoint",lambda x:x["event"].__setitem__("original_checkpoint_reads",1)),
            ("missing_expected",lambda x:x["expected_reads"].pop()),
            ("operand_sha",lambda x:x["operand_reads"][0].__setitem__("sha256","0"*64)),
            ("capture_path",lambda x:x["capture_reads"][0].__setitem__("path","/tmp/checkpoint/shard.bin")),
            ("capture_commit",lambda x:x["capture_reads"][0].__setitem__("source_commit","f38dc2756bd4949e8883d6afc33b324fe264dd19")),
            ("capture_dtype",lambda x:x["capture_reads"][0].__setitem__("dtype","F64_LE")),
            ("source_authority",lambda x:x["capture_reads"][0].__setitem__("source_authority_sha256","0"*64)),
            ("duplicate_role",lambda x:x["capture_reads"][0].__setitem__("role",x["expected_reads"][0]["role"])),
            ("ids",lambda x:x["route_authority"].__setitem__("selected_ids_hex","00"*16)),
            ("weights",lambda x:x["route_authority"].__setitem__("routing_weights_f64_hex","00"*64)),
            ("ranking",lambda x:x["route_authority"].__setitem__("ranking_sha256","0"*64)),
            ("s0_serialization",lambda x:x["operand_reads"][0].__setitem__("serialization","CANONICAL_F32_LE")),
        ]
        for name,mutation in mutations:
            with self.subTest(mutation=name): self.reject(mutation)

    def test_capture_manifest_hash_is_committed_authority(self):
        original_sha=validator.sha
        def mutate_manifest_hash(path):
            if path.name == "capture-manifest.json": return "0"*64
            return original_sha(path)
        with mock.patch.object(validator,"sha",side_effect=mutate_manifest_hash):
            with self.assertRaisesRegex(ValueError,"capture manifest committed pin"):
                validator.validate(resolve_executable=False)

    def test_grader_uses_exact_d0_oracle_vocabulary_and_all_experts(self):
        source=(ROOT/"crates/f017-native/src/bin/d35_grader.rs").read_text()
        for label in ["RETAINED_CANONICAL_S1","RETAINED_CANONICAL_ROUTER_NORMALIZED","INDEPENDENT_COMPLETE_EXPERT"]:
            self.assertIn(label,source)
        self.assertNotIn("operand_conditioned_matvec_all_eight_experts",source)
        self.assertGreaterEqual(source.count('metric: "operand_conditioned_matvec"'),4)
        self.assertNotIn('oracle:"OPERAND_CONDITIONED_F64"',source)


if __name__=="__main__": unittest.main()
