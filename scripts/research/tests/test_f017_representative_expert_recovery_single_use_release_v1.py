from __future__ import annotations
import copy, importlib.util, sys, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]; P=ROOT/"scripts/research/validate_f017_representative_expert_recovery_single_use_release_v1.py"
sys.path.insert(0,str(P.parent))
s=importlib.util.spec_from_file_location("v",P); V=importlib.util.module_from_spec(s); s.loader.exec_module(V)
class ReleaseTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls): cls.base=V.load(V.DEFAULT)
 def reject(self,fn):
  x=copy.deepcopy(self.base); fn(x)
  import tempfile,json
  with tempfile.NamedTemporaryFile("w",suffix=".json") as f:
   json.dump(x,f); f.flush()
   with self.assertRaises(V.ValidationError): V.validate(ROOT,Path(f.name))
 def test_repository(self): self.assertEqual(V.validate(),"REPRESENTATIVE_EXPERT_RELEASE_VALID")
 def test_mutations(self):
  muts=[lambda x:x["bindings"]["authorization"].__setitem__("sha256","0"*64),lambda x:x["bindings"]["executor"].__setitem__("sha256","0"*64),lambda x:x["bindings"]["independent_review"].__setitem__("sha256","0"*64),lambda x:x["representative_expert_input"].__setitem__("sha256","0"*64),lambda x:x["retained_payload_inventory"][0].__setitem__("packed_sha256","0"*64),lambda x:x["id_weight_pairs"].__setitem__(3,x["id_weight_pairs"][4]),lambda x:x["id_weight_pairs"][3].__setitem__("routing_weight",0.0),lambda x:x["access_accounting"].__setitem__("checkpoint_reads",1),lambda x:x["access_accounting"].__setitem__("shard_opens",1),lambda x:x["access_accounting"].__setitem__("starting_ledger",174),lambda x:x["prohibitions"].__setitem__("routed_aggregate",False),lambda x:x["prohibitions"].__setitem__("shared_expert",False),lambda x:x["prohibitions"].__setitem__("direct_dprefix_outputs",False),lambda x:x["single_use"].__setitem__("retry",True),lambda x:x["single_use"].__setitem__("second_attempt",True),lambda x:x.__setitem__("real_event_authorized",True),lambda x:x.__setitem__("approval_asserted",True),lambda x:x.__setitem__("stop_boundary","AFTER_AGGREGATE"),lambda x:x["output_contract"].__setitem__("two_fresh_process_reproductions_required",1)]
  for m in muts:
   with self.subTest(m=m): self.reject(m)
if __name__=="__main__": unittest.main()
