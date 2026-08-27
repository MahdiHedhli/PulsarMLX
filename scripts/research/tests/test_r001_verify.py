#!/usr/bin/env python3
from __future__ import annotations
import hashlib,json,os,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from r001_verify import CHECKPOINT,EXPECTED_SHARDS,Reader,canonical,descriptor_stat,domain_hash,load_admission

class R001VerifierContract(unittest.TestCase):
    def test_canonical_known_answer(self):
        value={"a":0,"b":"x\\\"","c":[1,True]}
        self.assertEqual(canonical(value),b'{"a":0,"b":"x\\\\\\\"","c":[1,true]}')
        self.assertEqual(hashlib.sha256(canonical(value)).hexdigest(),"1dc821aa6759740ae41a6a3feb610416c797f785dd200bd508a0892173f68304")
    def test_layout_known_answer(self):
        value={"architecture":"glm-dsa","block_bytes":66,"block_elements":256,"dims":[6144,2048,256],"expert_class":"routed","plane_bytes":3244032,"role":"gate","row_bytes":1584,"schema":"pulsarmlx.r001.layout.v1","type_id":16,"type_name":"IQ2_XXS"}
        self.assertEqual(domain_hash(b"PULSARMLX-R001-LAYOUT-V1",value),"765aa7eadd6d8503feebdc5726d19e32703161bb202e207044b9296d5dbecacf")
    def test_reject_noncanonical_domain(self):
        with self.assertRaises(ValueError): canonical({"x":None})
        with self.assertRaises(ValueError): canonical({"x":-1})
        with self.assertRaises(ValueError): canonical({"x":"non-ascii-\u00e9"})
    def test_historical_admission_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/"shard.gguf").write_bytes(b"x")
            admission=root/"admission.json"
            admission.write_text(json.dumps({"set_sha256":CHECKPOINT,"total_bytes":238458632928,"shards":[{"name":"shard.gguf","size":1,"sha256":"00"*32}]}))
            with self.assertRaises(ValueError): load_admission(admission,root)
    def test_authoritative_set_hash_definition(self):
        material="".join(f"{sha}{size}" for _,size,sha in EXPECTED_SHARDS).encode("ascii")
        self.assertEqual(hashlib.sha256(material).hexdigest(),CHECKPOINT)
    def test_replaced_same_size_source_descriptor_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/"source.gguf";replacement=root/"replacement.gguf"
            source.write_bytes(b"GGUF");replacement.write_bytes(b"GGUF")
            fd=os.open(source,os.O_RDONLY)
            try: admitted=descriptor_stat(fd)
            finally: os.close(fd)
            os.replace(replacement,source)
            with self.assertRaises(ValueError): Reader(source,admitted)

if __name__=="__main__":unittest.main()
