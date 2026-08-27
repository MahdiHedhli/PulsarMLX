#!/usr/bin/env python3
from __future__ import annotations
import hashlib,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from r001_verify import canonical,domain_hash

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

if __name__=="__main__":unittest.main()
