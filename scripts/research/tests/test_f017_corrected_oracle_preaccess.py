from __future__ import annotations
import hashlib,json,os,struct,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest import mock

ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/"scripts/research"))
from f017_oracle_primary_decoders import decode
from qualify_f017_quantization_matrix_v1 import FORMATS,independent_decode,synthetic_block
from generate_f017_corrected_oracle_fixtures import fixture
from f017_corrected_oracle_primary import Geometry,JsonSource,StreamingCatalogSource,execute as primary
from f017_corrected_oracle_secondary import CatalogStore,execute as secondary
from execute_f017_corrected_oracle_event import access_census,graph_tensor_names

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
 def test_named_packed_mutations_are_real_and_banked(self):
  with tempfile.TemporaryDirectory() as directory:
   output=Path(directory)/"qualification.json"
   subprocess.run([sys.executable,str(ROOT/"scripts/research/qualify_f017_corrected_oracles.py"),"--output",str(output)],check=True,cwd=ROOT,capture_output=True)
   result=json.loads(output.read_text());self.assertEqual(result["packed_decoder_case_count"],44)
   mutations={item["id"]:item for item in result["mutations"]}
   self.assertEqual(mutations["Q6_K_PACKED_LANE"]["test_kind"],"PACKED_BLOCK_BIT_MUTATION")
   self.assertEqual(mutations["IQ3_XXS_PACKED_LANE"]["test_kind"],"PACKED_BLOCK_BIT_MUTATION")
   self.assertEqual(mutations["QUANT_TYPE_ID"]["test_kind"],"DISPATCH_GEOMETRY_REJECTION")
   self.assertEqual(mutations["PACKED_TENSOR_OFFSET"]["test_kind"],"ENCODED_BYTE_OFFSET_SHIFT")
   for mutation in ("ROUTE_BIAS_ORDER","ROUTE_WEIGHT_PLACEMENT","WRONG_EXPERT","ACCUMULATION_PRECISION"):
    self.assertEqual(mutations[mutation]["test_kind"],"EXECUTED_GRAPH_SEMANTIC_MUTATION")
    self.assertTrue(mutations[mutation]["changed_fields"])
 def test_scientific_consumers_are_explicitly_namespaced(self):
  coordinator=(ROOT/"scripts/research/execute_f017_corrected_oracle_event.py").read_text()
  self.assertIn('root/f"{consumer}-access-events"',coordinator)
  self.assertIn('("primary",ROOT/',coordinator)
  self.assertIn('("secondary",ROOT/',coordinator)
 def test_bound_geometry_contract_is_directly_parseable(self):
  path=ROOT/"specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-geometry-v1.json"
  geometry=Geometry.from_json(json.loads(path.read_text()))
  self.assertEqual(geometry.layers,79);self.assertEqual(geometry.heads,64)
 def test_graph_access_census_is_1410_tensors_on_five_payload_shards(self):
  geometry=json.loads((ROOT/"specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-geometry-v1.json").read_text())
  catalog=json.loads((ROOT/"docs/research/glm52/raw/f016-c01-catalog-0001.json").read_text())
  names=graph_tensor_names(geometry);records={item["name"]:item for item in catalog["tensors"]}
  self.assertEqual(len(names),1410);self.assertEqual(len(set(records)-names),399)
  shards={records[name]["file"] for name in names};self.assertEqual(len(shards),5)
  self.assertNotIn("GLM-5.2-UD-IQ2_XXS-00001-of-00006.gguf",shards)
 def test_synthetic_multishard_target_readers_exercise_offsets_experts_and_journals(self):
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);checkpoint=root/"checkpoint";checkpoint.mkdir()
   shard_a=checkpoint/"synthetic-a.gguf";shard_b=checkpoint/"synthetic-b.gguf"
   shard_a.write_bytes(struct.pack("<8f",*range(8)))
   expert_values=[float(index) for index in range(64*2*4)];shard_b.write_bytes(struct.pack(f"<{len(expert_values)}f",*expert_values))
   tensors=[{"name":"m.weight","type":"F32","type_id":0,"dims":[4,2],"file":shard_a.name,"data_offset_abs":0},
            {"name":"e.weight","type":"F32","type_id":0,"dims":[4,2,64],"file":shard_b.name,"data_offset_abs":0}]
   catalog=root/"catalog.json";catalog.write_text(json.dumps({"tensors":tensors},sort_keys=True)+"\n")
   digest=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
   shards=[{"filename":path.name,"size_bytes":path.stat().st_size,"sha256":digest(path)} for path in (shard_a,shard_b)]
   auth={"schema":"pulsarmlx.f017.corrected-full-checkpoint-oracle-access-authorization/1.0.0","state":"AUTHORIZED","live":True,
         "authorization_id":"F017-SYNTHETIC-TARGET-READER","attempts":1,"retries":0,"resume":False,
         "consumers":["INDEPENDENT_CPU_REFERENCE","INDEPENDENT_ACCELERATED_CROSS_CHECK"],"checkpoint_root":str(checkpoint.resolve()),
         "checkpoint_catalog_sha256":digest(catalog),"primary_sha256":digest(ROOT/"scripts/research/f017_corrected_oracle_primary.py"),
         "secondary_sha256":digest(ROOT/"scripts/research/f017_corrected_oracle_secondary.py"),"shards":shards}
   auth_path=root/"authorization.json";auth_path.write_text(json.dumps(auth,sort_keys=True)+"\n")
   identity=root/"identity.json";identity.write_text(json.dumps({"authorization_id":auth["authorization_id"],"result":"PASS","shards":shards},sort_keys=True)+"\n")
   for consumer,constructor in (("primary",StreamingCatalogSource),("secondary",CatalogStore)):
    events=root/f"{consumer}-events"
    with mock.patch.dict(os.environ,{"F017_ORACLE_CHECKPOINT_IDENTITY":str(identity),"F017_ORACLE_ACCESS_EVENT_DIR":str(events)}):
     source=constructor(auth_path,catalog,checkpoint)
     try:
      self.assertEqual([float(v) for v in source.matrix("m.weight",2,4).row(1)],[4.0,5.0,6.0,7.0])
      expert=source.expert("e.weight",63,2,4)
      self.assertEqual([float(v) for v in expert.row(1)],[float(v) for v in range(508,512)])
     finally: source.close()
    journal=[json.loads(path.read_text()) for path in sorted(events.glob("*.json"))]
    self.assertEqual([item["sequence"] for item in journal],list(range(len(journal))))
    self.assertEqual(journal[0]["kind"],"CHECKPOINT_IDENTITY_EVIDENCE_READ_ATTEMPT")
    self.assertEqual(journal[1]["kind"],"CHECKPOINT_IDENTITY_EVIDENCE_READ_RESULT")
    self.assertEqual({item["tensor_name"] for item in journal if item["kind"]=="TENSOR_RESOLUTION"},{"m.weight","e.weight"})
 def test_synthetic_multishard_full_graph_target_readers_and_census(self):
  document=fixture(18102);geometry=document["geometry"];tensors=document["tensors"]
  dimensions={"token_embd.weight":[geometry["hidden"],geometry["vocab"]],"output_norm.weight":[geometry["hidden"]],"output.weight":[geometry["hidden"],geometry["vocab"]]}
  qdim=geometry["qk_nope"]+geometry["qk_rope"]
  for layer in range(geometry["layers"]):
   prefix=f"blk.{layer}"
   dimensions.update({f"{prefix}.attn_norm.weight":[geometry["hidden"]],f"{prefix}.attn_q_a.weight":[geometry["hidden"],geometry["q_rank"]],
    f"{prefix}.attn_q_a_norm.weight":[geometry["q_rank"]],f"{prefix}.attn_q_b.weight":[geometry["q_rank"],geometry["heads"]*qdim],
    f"{prefix}.attn_kv_a_mqa.weight":[geometry["hidden"],geometry["kv_rank"]+geometry["qk_rope"]],f"{prefix}.attn_kv_a_norm.weight":[geometry["kv_rank"]],
    f"{prefix}.attn_k_b.weight":[geometry["qk_nope"],geometry["kv_rank"],geometry["heads"]],f"{prefix}.attn_v_b.weight":[geometry["kv_rank"],geometry["value_dim"],geometry["heads"]],
    f"{prefix}.attn_output.weight":[geometry["heads"]*geometry["value_dim"],geometry["hidden"]],f"{prefix}.ffn_norm.weight":[geometry["hidden"]]})
   if layer<geometry["dense_layers"]:
    dimensions.update({f"{prefix}.ffn_gate.weight":[geometry["hidden"],geometry["dense_ffn"]],f"{prefix}.ffn_up.weight":[geometry["hidden"],geometry["dense_ffn"]],f"{prefix}.ffn_down.weight":[geometry["dense_ffn"],geometry["hidden"]]})
   else:
    dimensions.update({f"{prefix}.ffn_gate_inp.weight":[geometry["hidden"],geometry["experts"]],f"{prefix}.exp_probs_b.bias":[geometry["experts"]],
     f"{prefix}.ffn_gate_exps.weight":[geometry["hidden"],geometry["expert_ffn"],geometry["experts"]],f"{prefix}.ffn_up_exps.weight":[geometry["hidden"],geometry["expert_ffn"],geometry["experts"]],
     f"{prefix}.ffn_down_exps.weight":[geometry["expert_ffn"],geometry["hidden"],geometry["experts"]],f"{prefix}.ffn_gate_shexp.weight":[geometry["hidden"],geometry["expert_ffn"]],
     f"{prefix}.ffn_up_shexp.weight":[geometry["hidden"],geometry["expert_ffn"]],f"{prefix}.ffn_down_shexp.weight":[geometry["expert_ffn"],geometry["hidden"]]})
  grouped={}
  for key,value in tensors.items():
   base,separator,ordinal=key.partition("#");grouped.setdefault(base,[]).append((int(ordinal) if separator else 0,value))
  with tempfile.TemporaryDirectory() as directory:
   root=Path(directory);checkpoint=root/"checkpoint";checkpoint.mkdir();payloads={"synthetic-a.gguf":bytearray(),"synthetic-b.gguf":bytearray()};records=[]
   for index,name in enumerate(sorted(dimensions)):
    values=[value for _,part in sorted(grouped[name]) for value in part];encoded=struct.pack(f"<{len(values)}f",*values);shard=tuple(payloads)[index%2];offset=len(payloads[shard]);payloads[shard].extend(encoded)
    records.append({"name":name,"type":"F32","type_id":0,"dims":dimensions[name],"file":shard,"data_offset_abs":offset})
   for name,payload in payloads.items(): (checkpoint/name).write_bytes(payload)
   catalog=root/"catalog.json";catalog.write_text(json.dumps({"tensors":records},sort_keys=True)+"\n");digest=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
   shards=[{"filename":name,"size_bytes":len(payload),"sha256":digest(checkpoint/name)} for name,payload in payloads.items()]
   auth={"schema":"pulsarmlx.f017.corrected-full-checkpoint-oracle-access-authorization/1.0.0","state":"AUTHORIZED","live":True,"authorization_id":"F017-SYNTHETIC-FULL-GRAPH-READER",
    "attempts":1,"retries":0,"resume":False,"consumers":["INDEPENDENT_CPU_REFERENCE","INDEPENDENT_ACCELERATED_CROSS_CHECK"],"checkpoint_root":str(checkpoint.resolve()),
    "checkpoint_catalog_sha256":digest(catalog),"primary_sha256":digest(ROOT/"scripts/research/f017_corrected_oracle_primary.py"),"secondary_sha256":digest(ROOT/"scripts/research/f017_corrected_oracle_secondary.py"),"shards":shards}
   auth_path=root/"authorization.json";auth_path.write_text(json.dumps(auth,sort_keys=True)+"\n");identity=root/"identity.json";identity.write_text(json.dumps({"authorization_id":auth["authorization_id"],"result":"PASS","shards":shards},sort_keys=True)+"\n")
   results=[]
   for consumer,constructor in (("primary",StreamingCatalogSource),("secondary",CatalogStore)):
    events=root/f"{consumer}-access-events"
    with mock.patch.dict(os.environ,{"F017_ORACLE_CHECKPOINT_IDENTITY":str(identity),"F017_ORACLE_ACCESS_EVENT_DIR":str(events)}):
     source=constructor(auth_path,catalog,checkpoint)
     try:
      results.append(primary(source,Geometry.from_json(geometry),document["token"],document["position"]) if consumer=="primary" else secondary({"geometry":geometry,"token":document["token"],"position":document["position"]},False,source))
     finally: source.close()
   self.assertEqual(results[0]["selected_token"],results[1]["selected_token"])
   census=access_census(root,auth,catalog,geometry);self.assertEqual(census["graph_tensor_count"],len(dimensions));self.assertEqual(census["declared_non_access_tensor_count"],0)
   self.assertEqual(census["graph_payload_shards"],sorted(payloads))
if __name__=="__main__": unittest.main()
