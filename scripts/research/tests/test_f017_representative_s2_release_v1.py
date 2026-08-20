from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import struct
import sys
import tempfile
import threading
import unittest


ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts/research"
sys.path.insert(0, str(SCRIPTS))

import f017_representative_s2_executor_v1 as executor
import f017_representative_s2_release_wrapper_v1 as wrapper
import f017_representative_s2_terminalizer_v1 as terminalizer
import validate_f017_representative_s2_release_v1 as validator


AUTH = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-s2-construction-authorization-v1.json"
RELEASE = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-s2-single-use-release-v1.json"


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def make_manifest(name: str, raw: bytes, role: str, dtype: str, size: int) -> bytes:
    return (json.dumps({"artifacts":[{"symbolic_path":name,"sha256":hashlib.sha256(raw).hexdigest(),"semantic_role":role,"dtype":dtype,"shape":[6144],"byte_length":size}]},sort_keys=True,separators=(",",":"))+"\n").encode()


class S2ArithmeticTests(unittest.TestCase):
    def test_exact_ties_to_even_and_distinct_from_serial_f32(self) -> None:
        s1 = bytearray(24576); ffn = bytearray(49152)
        struct.pack_into("<f",s1,0,1.0); struct.pack_into("<d",ffn,0,2.0**-24)
        struct.pack_into("<f",s1,4,struct.unpack("<f",bytes.fromhex("0100803f"))[0]); struct.pack_into("<d",ffn,8,2.0**-24)
        struct.pack_into("<f",s1,8,1.0); struct.pack_into("<d",ffn,16,2.0**-24 + 2.0**-52)
        struct.pack_into("<d",ffn,24,2.0**-149)
        out=executor.compose_bytes(bytes(s1),bytes(ffn))
        self.assertEqual(struct.unpack_from("<I",out,0)[0],0x3f800000)
        self.assertEqual(struct.unpack_from("<I",out,4)[0],0x3f800002)
        self.assertEqual(struct.unpack_from("<I",out,8)[0],0x3f800001)
        self.assertEqual(struct.unpack_from("<I",out,12)[0],0x00000001)
        serial=struct.unpack("<f",struct.pack("<f",1.0+struct.unpack("<f",struct.pack("<f",2.0**-24+2.0**-52))[0]))[0]
        self.assertEqual(serial,1.0)
        self.assertNotEqual(struct.unpack_from("<f",out,8)[0],serial)

    def test_bad_geometry_and_nonfinite_rejected(self) -> None:
        with self.assertRaisesRegex(executor.S2Error,"INPUT_GEOMETRY"):
            executor.compose_bytes(b"",b"")
        s1=bytearray(24576); ffn=bytearray(49152); struct.pack_into("<d",ffn,0,math.inf)
        with self.assertRaisesRegex(executor.S2Error,"INPUT_NONFINITE"):
            executor.compose_bytes(bytes(s1),bytes(ffn))


class AuthorityMutationTests(unittest.TestCase):
    def test_authorization_mutations_rejected(self) -> None:
        base=load(AUTH)
        mutations=[]
        for path,value in [
            (("bindings","s1_reuse_authorization","sha256"),"0"*64),
            (("bindings","ffn_reuse_authorization","sha256"),"0"*64),
            (("inputs","s1","sha256"),"0"*64),
            (("inputs","ffn","sha256"),"0"*64),
            (("inputs","s1","dtype"),"little-endian-f64"),
            (("inputs","ffn","dtype"),"little-endian-f32"),
            (("arithmetic","formula"),"S2=f32(S1)+f32(FFN)"),
            (("arithmetic","surface"),"PRODUCTION_SERIAL_F32"),
            (("accounting","checkpoint_reads"),1),
            (("accounting","shard_opens"),1),
            (("accounting","s1_materializations"),1),
            (("accounting","ffn_compositions"),1),
            (("accounting","future_s2_constructions"),2),
            (("fallbacks","checkpoint_access"),True),
            (("fallbacks","s1_reconstruction"),True),
            (("fallbacks","ffn_recomputation"),True),
            (("stop_boundary",),"AFTER_S2_AND_LATER"),
        ]:
            doc=copy.deepcopy(base); cursor=doc
            for key in path[:-1]: cursor=cursor[key]
            cursor[path[-1]]=value; mutations.append(doc)
        for index,doc in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises(validator.ValidationError):
                validator.validate_authorization(doc,repo=False)

    def test_release_mutations_rejected(self) -> None:
        base=load(RELEASE)
        changes=[
            ("real_event_authorized",True),("status","AUTHORIZED"),("stop_boundary","AFTER_S2_AND_S3"),
        ]
        for key,value in changes:
            doc=copy.deepcopy(base); doc[key]=value
            with self.subTest(key=key),self.assertRaises(validator.ValidationError): validator.validate_release(doc,repo=False)
        nested=[("numerical_surface","addition","f32 addition"),("numerical_surface","fma",True),("numerical_surface","production_equivalence","PROVEN"),("single_use","retry",True),("single_use","second_attempt",True),("operands","s1",{}),("operands","ffn",{}),("input_preflight","same_validated_descriptor_consumed",False),("output_banking","dtype","little-endian-f64"),("output_banking","overwrite",True),("runtime","arithmetic_backend","NUMPY_VECTOR"),("future_approval","release_review_and_reviewed_head_enforced",False),("accounting","checkpoint_reads",1),("accounting","ffn_compositions",1),("accounting","future_s2_constructions",2),("prohibitions","s1_reconstruction",False),("prohibitions","ffn_recomputation",False)]
        for section,key,value in nested:
            doc=copy.deepcopy(base); doc[section][key]=value
            with self.subTest(section=section,key=key),self.assertRaises(validator.ValidationError): validator.validate_release(doc,repo=False)


class FileAndDurabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name); os.chmod(self.root,0o700)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def create_operand(self, dtype: str) -> tuple[dict,Path]:
        name="operand.f32le" if dtype.endswith("f32") else "operand.f64le"; size=24576 if dtype.endswith("f32") else 49152
        raw=b"\0"*size; role="SYNTHETIC_S1" if dtype.endswith("f32") else "SYNTHETIC_FFN"; manifest_name=f"manifest-{dtype[-3:]}.json"
        (self.root/name).write_bytes(raw); os.chmod(self.root/name,0o400)
        manifest=make_manifest(name,raw,role,dtype,size); (self.root/manifest_name).write_bytes(manifest); os.chmod(self.root/manifest_name,0o400)
        return {"manifest":{"relative_path":manifest_name,"sha256":hashlib.sha256(manifest).hexdigest(),"byte_length":len(manifest)},"artifact":{"relative_path":name,"sha256":hashlib.sha256(raw).hexdigest(),"semantic_role":role,"dtype":dtype,"shape":[6144],"byte_length":size}},self.root/name

    def test_open_once_and_file_policy(self) -> None:
        spec,path=self.create_operand("little-endian-f32"); opened=executor.OpenOperand(self.root,spec)
        try:
            identity=opened.verify_after(); self.assertEqual(len(set(identity.values())),1)
        finally: opened.close()
        os.chmod(path,0o600)
        with self.assertRaisesRegex(executor.S2Error,"READ_ONLY"): executor.OpenOperand(self.root,spec)

    def test_symlink_and_multi_link_rejected(self) -> None:
        spec,path=self.create_operand("little-endian-f32")
        alias=self.root/"alias"; os.link(path,alias)
        with self.assertRaisesRegex(executor.S2Error,"SINGLE_LINK"): executor.OpenOperand(self.root,spec)
        alias.unlink(); path.unlink(); os.symlink("target",path)
        with self.assertRaises(OSError): executor.OpenOperand(self.root,spec)

    def test_manifest_and_truncation_rejected(self) -> None:
        spec,path=self.create_operand("little-endian-f32")
        spec["manifest"]["sha256"]="0"*64
        with self.assertRaisesRegex(executor.S2Error,"MANIFEST_SHA"): executor.OpenOperand(self.root,spec)
        spec,_=self.create_operand("little-endian-f64")
        operand=self.root/spec["artifact"]["relative_path"]; os.chmod(operand,0o600); operand.write_bytes(b"\0"*8); os.chmod(operand,0o400)
        with self.assertRaisesRegex(executor.S2Error,"BYTE_LENGTH"): executor.OpenOperand(self.root,spec)

    def test_descriptor_relative_no_replace_publication(self) -> None:
        fd=wrapper.open_directory(self.root,exact_mode=0o700)
        try:
            first=wrapper.publish(fd,"artifact.bin",b"payload")
            self.assertEqual(first,hashlib.sha256(b"payload").hexdigest())
            with self.assertRaisesRegex(wrapper.ReleaseError,"PREEXISTING_DESTINATION"):
                wrapper.publish(fd,"artifact.bin",b"other")
        finally: os.close(fd)

    def test_concurrent_attempt_race_has_one_winner(self) -> None:
        target=self.root/"attempt-state"; outcomes=[]; barrier=threading.Barrier(2)
        def contender() -> None:
            barrier.wait()
            try: os.mkdir(target,0o700); outcomes.append("WIN")
            except FileExistsError: outcomes.append("LOSE")
        threads=[threading.Thread(target=contender) for _ in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join()
        self.assertCountEqual(outcomes,["WIN","LOSE"])

    def test_terminalizer_reconstructs_complete_and_rejects_partial_authority(self) -> None:
        release=self.root/"release.json"; release.write_text("{}")
        state=self.root/"state"; state.mkdir(); os.chmod(state,0o700)
        output=self.root/"representative-s2.f32le"; manifest=self.root/"representative-s2-private-manifest-v1.json"
        output.write_bytes(b"\0"*24576); out_sha=hashlib.sha256(output.read_bytes()).hexdigest()
        manifest.write_bytes(wrapper.canonical(wrapper.output_manifest(out_sha)))
        attempt={"event_id":wrapper.EVENT_ID,"release_id":wrapper.RELEASE_ID,"attempt_id":wrapper.ATTEMPT_ID,"release_sha256":hashlib.sha256(release.read_bytes()).hexdigest()}
        (state/"attempt-start.json").write_text(json.dumps(attempt))
        (state/"s2-start.json").write_text(json.dumps({"s2_constructions":1,"accounting_semantics":"DURABLE_START_COUNTS_ONE_S2_CONSTRUCTION_REGARDLESS_OF_OUTCOME"}))
        manifest_sha=hashlib.sha256(manifest.read_bytes()).hexdigest()
        receipt={"output_sha256":out_sha,"output_manifest_sha256":manifest_sha,"s1_materializations":0,"ffn_compositions":0,"s2_constructions":1}
        (state/"s2-execution-receipt.json").write_text(json.dumps(receipt)); receipt_sha=hashlib.sha256((state/"s2-execution-receipt.json").read_bytes()).hexdigest()
        terminal={"disposition":"COMPLETE","output_authority":True,"output_sha256":out_sha,"output_manifest_sha256":manifest_sha,"execution_receipt_sha256":receipt_sha,"s2_constructions":1,"retry":False,"resume":False,"second_attempt":False}
        (state/"terminal.json").write_text(json.dumps(terminal))
        result=terminalizer.reconcile(state,output,manifest,release); self.assertTrue(result["output_authority"])
        terminal["output_sha256"]="0"*64; (state/"terminal.json").write_text(json.dumps(terminal))
        with self.assertRaises(terminalizer.ReconciliationError): terminalizer.reconcile(state,output,manifest,release)


if __name__=="__main__": unittest.main()
