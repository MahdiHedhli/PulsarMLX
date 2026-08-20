from __future__ import annotations

import copy
import json
import math
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock


SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import f017_representative_s1_output_reuse_v1 as reuse


class S1OutputReuseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.authorization = reuse.load(reuse.AUTH)
        evidence_path = reuse.ROOT / cls.authorization["source_authority"]["execution_evidence"]["path"]
        cls.evidence = reuse.load(evidence_path)

    def test_committed_authorization_and_evidence_validate(self) -> None:
        reuse.validate_authorization(copy.deepcopy(self.authorization))
        reuse.validate_evidence(copy.deepcopy(self.evidence))

    def test_authority_identity_mutations_rejected(self) -> None:
        cases = {
            "release": lambda d: d["source_authority"]["single_use_release_v2"].update(sha256="0" * 64),
            "approval": lambda d: d["source_authority"]["independent_release_approval"].update(sha256="0" * 64),
            "authorization": lambda d: d["source_authority"]["materialization_authorization"].update(sha256="0" * 64),
            "evidence": lambda d: d["source_authority"]["execution_evidence"].update(sha256="0" * 64),
            "attempt": lambda d: d["completed_attempt"].update(attempt_id="WRONG"),
            "terminal": lambda d: d["completed_attempt"]["terminal"].update(status="TERMINAL_FAILURE"),
            "output_authority": lambda d: d["completed_attempt"]["terminal"].update(output_authority=False),
        }
        for name, mutate in cases.items():
            with self.subTest(name=name):
                document = copy.deepcopy(self.authorization); mutate(document)
                with self.assertRaises(reuse.ReuseError): reuse.validate_authorization(document)

    def test_lineage_and_output_mutations_rejected(self) -> None:
        cases = {
            "s0": lambda d: d["source_lineage"].update(canonical_s0_sha256="0" * 64),
            "attention": lambda d: d["source_lineage"]["attention_payload_sha256"].update({"blk.3.attn_norm.weight":"0"*64}),
            "consumed_identity": lambda d: d["source_lineage"].update(all_expected_equals_before_equals_consumed_equals_after=False),
            "output_sha": lambda d: d["retained_s1"].update(sha256="0" * 64),
            "dtype": lambda d: d["retained_s1"].update(dtype="little-endian-f64"),
            "shape": lambda d: d["retained_s1"].update(shape=[1,6144]),
            "length": lambda d: d["retained_s1"].update(byte_length=49152),
            "historical_surface": lambda d: d["retained_s1"].update(semantic_role="HISTORICAL_DIRECT_DPREFIX_S1"),
            "manifest": lambda d: d["private_manifest"].update(sha256="0" * 64),
        }
        for name, mutate in cases.items():
            with self.subTest(name=name):
                document = copy.deepcopy(self.authorization); mutate(document)
                with self.assertRaises(reuse.ReuseError): reuse.validate_authorization(document)

    def test_fallback_and_boundary_mutations_rejected(self) -> None:
        cases = {
            "checkpoint": lambda d: d["accounting"].update(checkpoint_reads=1),
            "shard": lambda d: d["accounting"].update(shard_opens=1),
            "attention": lambda d: d["accounting"].update(new_attention_executions=1),
            "rerun": lambda d: d["accounting"].update(s1_release_v2_reruns=1),
            "materialization": lambda d: d["accounting"].update(new_s1_materializations=1),
            "ffn": lambda d: d["accounting"].update(ffn_compositions=1),
            "s2": lambda d: d["accounting"].update(s2_constructions=1),
            "ffn_artifact": lambda d: d["consumer_scope"].update(ffn_artifact_consumption=True),
            "s2_scope": lambda d: d["consumer_scope"].update(s2_construction=True),
            "reproduction": lambda d: d["reproduction_adjudication"].update(additional_post_event_materialization_performed=True),
        }
        for name, mutate in cases.items():
            with self.subTest(name=name):
                document = copy.deepcopy(self.authorization); mutate(document)
                with self.assertRaises(reuse.ReuseError): reuse.validate_authorization(document)

    def test_execution_evidence_mutations_rejected(self) -> None:
        cases = {
            "result": lambda d: d.update(result="FAILURE"),
            "attempt": lambda d: d["attempt"].update(attempt_id="WRONG"),
            "retry": lambda d: d["attempt"].update(retry=True),
            "terminal": lambda d: d["terminal"].update(status="TERMINAL_FAILURE"),
            "authority": lambda d: d["terminal"].update(output_authority=False),
            "output": lambda d: d["retained_output"].update(sha256="0" * 64),
            "manifest": lambda d: d["private_manifest"].update(sha256="0" * 64),
            "receipt": lambda d: d["receipt"].update(sha256="0" * 64),
            "source": lambda d: d["source_lineage"].update(all_expected_equals_before_equals_consumed_equals_after=False),
            "checkpoint": lambda d: d["accounting"].update(checkpoint_reads=1),
            "s2": lambda d: d["accounting"].update(s2_constructions=1),
        }
        for name, mutate in cases.items():
            with self.subTest(name=name):
                document = copy.deepcopy(self.evidence); mutate(document)
                with self.assertRaises(reuse.ReuseError): reuse.validate_evidence(document)

    def artifact(self, raw: bytes) -> dict[str, object]:
        artifact = copy.deepcopy(self.authorization["retained_s1"])
        artifact["sha256"] = reuse.sha256(raw)
        return artifact

    def test_output_geometry_hash_and_nonfinite_rejected(self) -> None:
        good = struct.pack("<6144f", *(0.0 for _ in range(6144)))
        with mock.patch.object(reuse, "OUTPUT_SHA", reuse.sha256(good)):
            reuse.validate_output_bytes(good, self.artifact(good))
            with self.assertRaises(reuse.ReuseError): reuse.validate_output_bytes(good[:-4], self.artifact(good))
        nonfinite = struct.pack("<f", math.nan) + good[4:]
        with mock.patch.object(reuse, "OUTPUT_SHA", reuse.sha256(nonfinite)):
            with self.assertRaises(reuse.ReuseError): reuse.validate_output_bytes(nonfinite, self.artifact(nonfinite))

    def test_writable_symlink_multilink_and_wrong_size_rejected(self) -> None:
        for case in ("writable", "symlink", "multilink", "size"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root=Path(directory); output=root/"representative-s1.f32le"; output.write_bytes(b"\0"*24576); os.chmod(output,0o400)
                if case == "writable": os.chmod(output,0o600)
                elif case == "symlink":
                    real=root/"real.f32le"; output.rename(real); output.symlink_to(real.name)
                elif case == "multilink": os.link(output,root/"alias.f32le")
                else:
                    os.chmod(output,0o600); output.write_bytes(b"\0"*24572); os.chmod(output,0o400)
                root_fd=os.open(root,os.O_RDONLY|getattr(os,"O_DIRECTORY",0))
                try:
                    with self.assertRaises((reuse.ReuseError,OSError)):
                        descriptor,_,_=reuse.open_leaf(root_fd,"representative-s1.f32le",24576); os.close(descriptor)
                finally: os.close(root_fd)

    def test_manifest_mismatch_rejected(self) -> None:
        raw=struct.pack("<6144f",*(0.0 for _ in range(6144))); artifact=self.artifact(raw)
        manifest={"schema":"pulsarmlx.f017.representative-s1-private-manifest","schema_version":"1.0.0","artifact":{"path":"representative-s1.f32le","semantic_role":reuse.STAGE_ROLE,"sha256":"0"*64,"dtype":"little-endian-f32","shape":[6144],"byte_length":24576,"finite":True},"expected_equals_produced_equals_readback":True,"matching_complete_terminal_required":True}
        encoded=(json.dumps(manifest,sort_keys=True,separators=(",",":"))+"\n").encode()
        with mock.patch.object(reuse,"MANIFEST_SHA",reuse.sha256(encoded)):
            with self.assertRaises(reuse.ReuseError): reuse.validate_manifest(encoded,artifact)


if __name__ == "__main__":
    unittest.main()
