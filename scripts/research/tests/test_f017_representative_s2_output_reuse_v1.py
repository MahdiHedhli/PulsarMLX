from __future__ import annotations
import copy, math, os, struct, sys, tempfile, unittest
from pathlib import Path
from unittest import mock
SCRIPTS=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(SCRIPTS))
import f017_representative_s2_output_reuse_v1 as reuse

class S2ReuseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.auth=reuse.load(reuse.AUTH); cls.evidence=reuse.load(reuse.ROOT/reuse.EVIDENCE_PATH)
    def test_committed_authorities(self):
        reuse.validate_authorization(copy.deepcopy(self.auth)); reuse.validate_evidence(copy.deepcopy(self.evidence))
    def test_authority_mutations(self):
        cases=[lambda d:d["source_authority"]["execution_evidence"].update(sha256="0"*64),lambda d:d["source_authority"]["single_use_release_v2"].update(sha256="0"*64),lambda d:d["source_authority"]["independent_release_approval"].update(sha256="0"*64),lambda d:d["source_authority"]["arithmetic_contract"].update(sha256="0"*64),lambda d:d["completed_attempt"].update(attempt_id="WRONG"),lambda d:d["completed_attempt"]["terminal"].update(disposition="TERMINAL_FAILURE"),lambda d:d["completed_attempt"]["terminal"].update(output_authority=False)]
        for mutate in cases:
            d=copy.deepcopy(self.auth); mutate(d)
            with self.assertRaises(reuse.ReuseError): reuse.validate_authorization(d)
    def test_artifact_lineage_surface_mutations(self):
        cases=[lambda d:d["retained_s2"].update(sha256="0"*64),lambda d:d["retained_s2"].update(dtype="little-endian-f64"),lambda d:d["retained_s2"].update(shape=[1,6144]),lambda d:d["retained_s2"].update(byte_length=49152),lambda d:d["retained_s2"].update(semantic_surface="PRODUCTION_SERIAL_F32"),lambda d:d["private_manifest"].update(sha256="0"*64),lambda d:d["consumed_lineage"].update(s1_expected_equals_before_equals_consumed_equals_after_sha256="0"*64),lambda d:d["consumed_lineage"].update(ffn_expected_equals_before_equals_consumed_equals_after_sha256="0"*64)]
        for mutate in cases:
            d=copy.deepcopy(self.auth); mutate(d)
            with self.assertRaises(reuse.ReuseError): reuse.validate_authorization(d)
    def test_fallback_and_accounting_mutations(self):
        for key in self.auth["accounting"]:
            if key.startswith("ledger_"): continue
            d=copy.deepcopy(self.auth); d["accounting"][key]=1
            with self.assertRaises(reuse.ReuseError): reuse.validate_authorization(d)
        d=copy.deepcopy(self.auth); d["reproduction_adjudication"]["post_event_reproduction_performed"]=True
        with self.assertRaises(reuse.ReuseError): reuse.validate_authorization(d)
    def test_evidence_mutations(self):
        cases=[lambda d:d.update(result="FAILURE"),lambda d:d["attempt"].update(retry=True),lambda d:d["terminal"].update(disposition="TERMINAL_FAILURE"),lambda d:d["terminal"].update(output_authority=False),lambda d:d["output"].update(sha256="0"*64),lambda d:d["private_manifest"].update(sha256="0"*64),lambda d:d["receipt"].update(sha256="0"*64),lambda d:d["retained_inputs"]["s1"].update(consumed_sha256="0"*64),lambda d:d["accounting"].update(checkpoint_reads=1)]
        for mutate in cases:
            d=copy.deepcopy(self.evidence); mutate(d)
            with self.assertRaises(reuse.ReuseError): reuse.validate_evidence(d)
    def test_output_hash_geometry_and_nonfinite(self):
        good=struct.pack("<6144f",*(0.0 for _ in range(6144))); artifact=copy.deepcopy(self.auth["retained_s2"]); artifact["sha256"]=reuse.sha256(good)
        with mock.patch.object(reuse,"OUTPUT_SHA",reuse.sha256(good)):
            reuse.validate_output(good,artifact)
            with self.assertRaises(reuse.ReuseError): reuse.validate_output(good[:-4],artifact)
        bad=struct.pack("<f",math.nan)+good[4:]; artifact["sha256"]=reuse.sha256(bad)
        with mock.patch.object(reuse,"OUTPUT_SHA",reuse.sha256(bad)):
            with self.assertRaises(reuse.ReuseError): reuse.validate_output(bad,artifact)
    def test_writable_symlink_multilink_truncated(self):
        for case in ("writable","symlink","multilink","truncated"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                root=Path(directory); leaf=root/"x"; leaf.write_bytes(b"\0"*24576); os.chmod(leaf,0o400)
                if case=="writable": os.chmod(leaf,0o600)
                elif case=="symlink": leaf.rename(root/"real"); leaf.symlink_to("real")
                elif case=="multilink": os.link(leaf,root/"alias")
                else: os.chmod(leaf,0o600); leaf.write_bytes(b"\0"*4); os.chmod(leaf,0o400)
                fd=os.open(root,os.O_RDONLY|getattr(os,"O_DIRECTORY",0))
                try:
                    with self.assertRaises((reuse.ReuseError,OSError)): reuse.open_leaf(fd,"x",24576)
                finally: os.close(fd)

if __name__=="__main__": unittest.main()
