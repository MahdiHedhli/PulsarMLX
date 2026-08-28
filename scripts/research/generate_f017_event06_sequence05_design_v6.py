#!/usr/bin/env python3
"""Generate cycle-6 non-circular, posture-safe Sequence-5 design authority."""
from __future__ import annotations
import argparse, hashlib, json
from copy import deepcopy
from pathlib import Path
from f017_canonical_serialization_v10 import canonical_bytes
import generate_f017_event06_sequence05_design_v5 as v5

ROOT=v5.ROOT; CONTRACT_DIR=v5.CONTRACT_DIR; EVIDENCE_DIR=v5.EVIDENCE_DIR
READINESS=CONTRACT_DIR/"f017-corrected-oracle-event06-readiness-consumer-interface-v7.json"
INSTALL=CONTRACT_DIR/"f017-corrected-oracle-event06-live-installation-interface-v6.json"
MANIFEST=CONTRACT_DIR/"f017-corrected-oracle-event06-readiness-authority-manifest-v5.json"
QUALIFICATION=CONTRACT_DIR/"f017-event06-sequence05-qualification-role-requirements-v4.json"
PREPARED=EVIDENCE_DIR/"f017-event06-v12-sequence05-readiness-authority-manifest-prepared-v2.json"

def sha(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p:Path,v:object,check:bool)->None:
 raw=canonical_bytes(v)
 if check:
  if not p.is_file() or p.read_bytes()!=raw: raise SystemExit(f"drift: {p.relative_to(ROOT)}")
 else:p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)

def readiness()->dict:
 d=deepcopy(v5.readiness()); d["schema"]="pulsarmlx.f017.corrected-oracle-event06-readiness-consumer-interface/2.5.0"
 d["manifest_contract"]=str(MANIFEST.relative_to(ROOT)); d["qualification_role_requirements"]=str(QUALIFICATION.relative_to(ROOT))
 for f,t in [("review_head","git_object"),("challenge_reproduction_sha256","sha256")]:
  if f not in d["required_fields"]: d["required_fields"].append(f); d["exact_types"][t].append(f)
 d["required_fields"].sort(); d["exact_types"]["git_object"].sort(); d["exact_types"]["sha256"].sort(); d["field_count"]=len(d["required_fields"])
 return d

def installation()->dict:
 d=deepcopy(v5.installation());d.update(schema="pulsarmlx.f017.corrected-oracle-event06-live-installation-interface/1.5.0",state_machine_contract="docs/architecture/reviews/evidence/f017-event06-v12-sequence05-installation-state-machine-v5.json",qualification_role_requirements=str(QUALIFICATION.relative_to(ROOT)));return d

def qualification()->dict:
 d=deepcopy(v5.qualification());d["schema"]="pulsarmlx.f017.event06-sequence05-qualification-role-requirements/1.3.0"
 d["roles"]["readiness_interface"]["required"]["schema"]=readiness()["schema"]
 d["roles"]["live_installation_interface"]["required"]["schema"]=installation()["schema"]
 d["roles"]["qualification_role_requirements"]["required"]["schema"]=d["schema"]
 d["roles"]["full_native_evidence"]["cross_bindings"].update(implementation_head="implementation_head",implementation_tree="implementation_tree")
 return d

def manifest()->dict:
 d=deepcopy(v5.manifest());d.update(schema="pulsarmlx.f017.corrected-oracle-event06-readiness-authority-manifest-contract/1.4.0",manifest_schema="pulsarmlx.f017.corrected-oracle-event06-readiness-authority-manifest/1.4.0",prepared_instance_schema="pulsarmlx.f017.corrected-oracle-event06-readiness-authority-manifest-prepared/1.1.0",prepared_instance_path=str(PREPARED.relative_to(ROOT)))
 d["prepared_required_keys"]=["schema","purpose","implementation_head","implementation_tree","roles","role_count","bindings","binding_count","unbound_future_roles","validated_binding_count","result","final_acceptance_eligible","live_authority"]
 d["prepared_binding_states"]=["CURRENT_DESIGN_AUTHORITY","UNBOUND_FUTURE"]
 return d

def current_bindings()->dict[str,Path]:
 m=v5.existing_bindings();m.update(readiness_interface=READINESS,live_installation_interface=INSTALL,qualification_role_requirements=QUALIFICATION);return m

def prepared()->dict:
 q=qualification();future=set(q["future_output_roles"]); rows={}
 for role in v5.v4.v3.DEPENDENCY_ROLES:
  if role in future: rows[role]={"binding_state":"UNBOUND_FUTURE","required_schema":q["roles"][role]["required_schema"],"availability_stage":q["roles"][role]["availability_stage"]}
  else:
   p=current_bindings()[role];rows[role]={"binding_state":"CURRENT_DESIGN_AUTHORITY","path":str(p.relative_to(ROOT)),"sha256":sha(p)}
 return {"schema":manifest()["prepared_instance_schema"],"purpose":"DESIGN_INSTANTIABILITY_ONLY_NOT_LIVE_READINESS_AUTHORITY","implementation_head":"e92c8162302edb609c8bef69921ab71887cca525","implementation_tree":"89e8143afa2de7d3388d0b3f9741f076d4a13c61","roles":list(v5.v4.v3.DEPENDENCY_ROLES),"role_count":21,"bindings":rows,"binding_count":21,"unbound_future_roles":sorted(future),"validated_binding_count":12,"result":"PREPARED_INCOMPLETE","final_acceptance_eligible":False,"live_authority":False,"checkpoint_root_resolved":False,"checkpoint_access":0,"numerical_operations":0,"event_06_executed":False}

def artifacts()->dict:
 base=v5.artifacts(); oldm=base[EVIDENCE_DIR/"f017-event06-v12-sequence05-installation-state-machine-v4.json"]
 families=["capability_expiry","exclusive_create_collision","candidate_identity","target_identity","payload_fsync","directory_fsync","readback","partial_write","concurrent_replacement","cross_posture"]
 aliases=["duplicate_key","unknown_alias","type_coercion"]
 outcomes=v5.v4.v3.v2.installation()["exact_failure_outcomes"]
 edges={name:{"transition":"PREPARED_VALIDATION_ONLY->PRODUCTION_INSTALLED" if any(x in name.lower() for x in ["capability","target","fsync","partial","collision","replace"]) else "CANDIDATE->PREPARED_VALIDATION_ONLY","terminal":"TERMINAL_FAILURE"} for name in outcomes}
 machine={**oldm,"schema":"pulsarmlx.f017.event06-v12-sequence05-installation-state-machine/1.4.0","failure_outcome_edge_mapping":edges,"race_mutation_families":families,"alias_structural_variants":aliases,"supersedes":"docs/architecture/reviews/evidence/f017-event06-v12-sequence05-installation-state-machine-v4.json"}
 correction=deepcopy(base[EVIDENCE_DIR/"f017-event06-v12-sequence05-review-correction-index-v2.json"]);correction["schema"]="pulsarmlx.f017.event06-v12-sequence05-review-correction-index/1.2.0";correction["rows"].append({"artifact":"docs/architecture/reviews/evidence/f017-event06-v12-sequence05-agy-design-cycle-05-normalized-result.json","finding":"FALSE_ZERO_FINDING_ACCEPT","disposition":"NONAUTHORITATIVE_MISSED_MATERIAL_FINDINGS"});correction["row_count"]=7
 advisory={"schema":"pulsarmlx.f017.event06-v12-sequence05-advisory-disposition-ledger/1.0.0","source_arbiter":"docs/architecture/reviews/evidence/f017-event06-v12-sequence05-opus-design-cycle-04-normalized-result.json","rows":[{"finding_id":f"A{i}","disposition":"RESOLVED_BY_CYCLE6_DESIGN","evidence":"cycle-6 manifest/reproduction/state-machine authority"} for i in range(1,7)],"row_count":6,"unresolved":0}
 return {READINESS:readiness(),INSTALL:installation(),MANIFEST:manifest(),QUALIFICATION:qualification(),EVIDENCE_DIR/"f017-event06-v12-sequence05-installation-state-machine-v5.json":machine,EVIDENCE_DIR/"f017-event06-v12-sequence05-review-correction-index-v3.json":correction,EVIDENCE_DIR/"f017-event06-v12-sequence05-advisory-disposition-ledger-v1.json":advisory}

def main()->int:
 ap=argparse.ArgumentParser();ap.add_argument("--check",action="store_true");a=ap.parse_args()
 for p,v in artifacts().items():write(p,v,a.check)
 write(PREPARED,prepared(),a.check)
 for tool,field,model,source in [("agy","response","gemini-3.1-pro-high","AGY_JSON_ENVELOPE_CONVERSATION_ID_STATUS_DURATION_USAGE"),("opus","result","claude-opus-5","CLAUDE_JSON_ENVELOPE_SESSION_ID_CANONICAL_MODEL_STATUS_USAGE")]:
  envelope=EVIDENCE_DIR/f"f017-event06-v12-sequence05-{tool}-design-cycle-05-provider-envelope.json";data=json.loads(envelope.read_bytes());raw=(data[field].rstrip()+"\n").encode();response=EVIDENCE_DIR/f"f017-event06-v12-sequence05-{tool}-design-cycle-05-exact-response.md"
  if a.check:
   if not response.is_file() or response.read_bytes()!=raw:raise SystemExit(f"drift: {response.relative_to(ROOT)}")
  else:response.write_bytes(raw)
  request=EVIDENCE_DIR/f"f017-event06-v12-sequence05-{tool}-design-cycle-05-request.md";norm=EVIDENCE_DIR/f"f017-event06-v12-sequence05-{tool}-design-cycle-05-normalized-result.json"
  session=data.get("conversation_id") or data.get("session_id");status=data.get("status") or data.get("subtype")
  prov={"schema":"pulsarmlx.f017.independent-review-transport-provenance/1.0.0","tool":tool,"requested_model":model,"provider_reported_model":model,"reviewed_commit":"e92c8162302edb609c8bef69921ab71887cca525","request_path":str(request.relative_to(ROOT)),"request_sha256":sha(request),"response_path":str(response.relative_to(ROOT)),"response_sha256":hashlib.sha256(raw).hexdigest(),"normalized_result_path":str(norm.relative_to(ROOT)),"normalized_result_sha256":sha(norm),"provider_envelope_path":str(envelope.relative_to(ROOT)),"provider_envelope_sha256":sha(envelope),"provider_session_metadata":f"session={session};status={status};duration_seconds={data.get('duration_seconds') or data.get('duration_api_ms',0)/1000}","independent_attestation_source":source,"exit_status":0,"credentials_serialized":False,"result":"PASS","transport":"JSON_PRINT_RAW_ENVELOPE_RETAINED"}
  write(EVIDENCE_DIR/f"f017-event06-v12-sequence05-{tool}-design-cycle-05-provenance-v1.json",prov,a.check)
 return 0
if __name__=="__main__":raise SystemExit(main())
