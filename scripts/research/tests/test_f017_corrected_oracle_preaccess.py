from __future__ import annotations
import json,sys,tempfile,unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/"scripts/research"))
from f017_oracle_primary_decoders import decode
from qualify_f017_quantization_matrix_v1 import FORMATS,independent_decode,synthetic_block
from generate_f017_corrected_oracle_fixtures import fixture
from f017_corrected_oracle_primary import Geometry,JsonSource,execute as primary
from f017_corrected_oracle_secondary import execute as secondary

class CorrectedOraclePreaccess(unittest.TestCase):
 def test_all_eleven_primary_decoders_agree_with_separate_diagnostic_path(self):
  for index,(fmt,(_,columns,_)) in enumerate(FORMATS.items()):
   for mode in ("zero","pattern","subnormal","max_finite"):
    raw=synthetic_block(fmt,mode,19000+index)
    left=decode(fmt,raw,columns);right=independent_decode(fmt,raw,columns)
    self.assertEqual(len(left),columns,fmt)
    self.assertEqual([float(x).hex() for x in left],[float(x).hex() for x in right],f"{fmt}:{mode}")
 def test_oracles_agree_on_predeclared_full_graph_cases(self):
  for seed in (18101,18103,18104,18106,18112):
   doc=fixture(seed);a=primary(JsonSource(doc["tensors"]),Geometry.from_json(doc["geometry"]),doc["token"],doc["position"]);b=secondary(doc)
   self.assertEqual(a["selected_token"],b["selected_token"])
   self.assertEqual([x["selected_expert_ids"] for x in a["layers"]],[x["selected_expert_ids"] for x in b["layers"]])
 def test_target_literals_are_quarantined(self):
  for name in ("f017_corrected_oracle_primary.py","f017_corrected_oracle_secondary.py","f017_oracle_primary_decoders.py"):
   text=(ROOT/"scripts/research"/name).read_text();self.assertNotIn(str(21600+15),text);self.assertNotIn(str(17300+51),text)
 def test_inert_authority_cannot_enter_target_reader(self):
  from f017_corrected_oracle_primary import StreamingCatalogSource
  inert=ROOT/"specs/017-rust-native-inference-runtime/fixtures/f017-corrected-full-checkpoint-oracle-inert-authorization-v1.json"
  catalog=ROOT/"docs/research/glm52/raw/f016-c01-catalog-0001.json"
  with self.assertRaises(ValueError): StreamingCatalogSource(inert,catalog,ROOT)
if __name__=="__main__": unittest.main()
