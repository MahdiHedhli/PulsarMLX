#!/usr/bin/env python3
"""Generate the cycle-7 design-only repair authority."""
from __future__ import annotations
import argparse, hashlib, json, subprocess
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from f017_canonical_serialization_v10 import canonical_bytes
import generate_f017_event06_sequence05_design_v6 as v6

ROOT=v6.ROOT; C=v6.CONTRACT_DIR; E=v6.EVIDENCE_DIR
READINESS=C/"f017-corrected-oracle-event06-readiness-consumer-interface-v8.json"
INSTALL=C/"f017-corrected-oracle-event06-live-installation-interface-v7.json"
MANIFEST=C/"f017-corrected-oracle-event06-readiness-authority-manifest-v6.json"
QUAL=C/"f017-event06-sequence05-qualification-role-requirements-v5.json"
PROV=C/"f017-independent-review-transport-provenance-v5.json"
SCHEMA_AUTH=C/"f017-event06-sequence05-qualification-schema-authority-v1.json"
NOACCESS=C/"f017-event06-sequence05-no-access-interposition-authority-v1.json"
PREPARED=E/"f017-event06-v12-sequence05-readiness-authority-manifest-prepared-v3.json"
START_HEAD="9ac074e595be354618af9524b436f3cecf9474d9"; START_TREE="21a0ccf436a0e68ceed90e3d6a9d83778238ece5"
ROLES=v6.v5.v4.v3.DEPENDENCY_ROLES

def sha_bytes(b:bytes)->str:return hashlib.sha256(b).hexdigest()
def sha(p:Path)->str:return sha_bytes(p.read_bytes())
def write(p:Path,v:object,check:bool)->None:
 raw=canonical_bytes(v)
 if check:
  if not p.is_file() or p.read_bytes()!=raw:raise SystemExit(f"drift: {p.relative_to(ROOT)}")
 else:p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
def git_bytes(head:str,path:str)->bytes:return subprocess.run(["git","show",f"{head}:{path}"],cwd=ROOT,check=True,capture_output=True).stdout

def readiness():
 d=deepcopy(v6.readiness());d.update(schema="pulsarmlx.f017.corrected-oracle-event06-readiness-consumer-interface/2.6.0",manifest_contract=str(MANIFEST.relative_to(ROOT)),qualification_role_requirements=str(QUAL.relative_to(ROOT)),review_transport_provenance_contract=str(PROV.relative_to(ROOT)));return d
def installation():
 d=deepcopy(v6.installation());d.update(schema="pulsarmlx.f017.corrected-oracle-event06-live-installation-interface/1.6.0",state_machine_contract="docs/architecture/reviews/evidence/f017-event06-v12-sequence05-installation-state-machine-v6.json",qualification_role_requirements=str(QUAL.relative_to(ROOT)));return d
def schema_authority():
 return {"schema":"pulsarmlx.f017.event06-sequence05-qualification-schema-authority/1.0.0","qualification_schema":"pulsarmlx.f017.event06-sequence05-qualification-role-requirements/1.4.0","readiness_schema":readiness()["schema"],"installation_schema":installation()["schema"],"self_reference_permitted":False}
def provenance_contract():
 d=deepcopy(v6.v5.provenance());d.update(schema="pulsarmlx.f017.independent-review-transport-provenance-contract/1.4.0",provider_reported_model_source="provider envelope when present; otherwise requested model plus explicit unavailable attestation",exact_key_census_required=True);return d
def qualification():
 d=deepcopy(v6.qualification());d["schema"]=schema_authority()["qualification_schema"]
 d["roles"]["implementation_measurement"]["required"]["schema"]="pulsarmlx.f017.event06-v12-to-v11-bridge-implementation-measurement/1.1.0"
 d["roles"]["readiness_interface"]["required"]["schema"]=readiness()["schema"]
 d["roles"]["live_installation_interface"]["required"]["schema"]=installation()["schema"]
 d["roles"]["qualification_role_requirements"]={"external_schema_authority_path":str(SCHEMA_AUTH.relative_to(ROOT)),"external_schema_authority_sha256":sha_bytes(canonical_bytes(schema_authority())),"required_fields":["schema","role_scope","roles","role_count"]}
 d["roles"]["failure_qualification"]["minimums"]["mutation_cases"]=324
 d["roles"]["challenge_provenance"]["contract"]=str(PROV.relative_to(ROOT));d["roles"]["challenge_provenance"]["required_fields"]=provenance_contract()["required_fields"]
 d["roles"]["review_transport_provenance_contract"]["required"]["schema"]=provenance_contract()["schema"]
 return d
def manifest_contract():
 d=deepcopy(v6.manifest());keys=["schema","purpose","implementation_head","implementation_tree","roles","role_count","bindings","binding_count","unbound_future_roles","validated_binding_count","result","final_acceptance_eligible","live_authority","checkpoint_root_resolved","checkpoint_access","numerical_operations","event_06_executed"]
 d.update(schema="pulsarmlx.f017.corrected-oracle-event06-readiness-authority-manifest-contract/1.5.0",manifest_schema="pulsarmlx.f017.corrected-oracle-event06-readiness-authority-manifest/1.5.0",prepared_instance_schema="pulsarmlx.f017.corrected-oracle-event06-readiness-authority-manifest-prepared/1.2.0",prepared_instance_path=str(PREPARED.relative_to(ROOT)),prepared_required_keys=keys,prepared_unknown_keys_permitted=False,roles_type="closed ordered role-name list; bindings is the closed role-to-binding mapping")
 return d
def noaccess():
 return {"schema":"pulsarmlx.f017.event06-sequence05-no-access-interposition-authority/1.0.0","current_callables":[{"path":"scripts/research/f017_checkpoint_identity_authority_v12.py","symbol":"canonical_candidate"},{"path":"scripts/research/f017_checkpoint_identity_authority_v12.py","symbol":"validate_candidate_bytes"},{"path":"scripts/research/f017_checkpoint_identity_authority_v12.py","symbol":"validate_installed_bytes"}],"planned_boundaries":["checkpoint_root_resolution","checkpoint_hash_stream","tensor_source","numerical_execute","live_root_bank","event_identity_consumption"],"planned_status":"UNBOUND_FUTURE","required_counter":0}
def outcomes():
 pre={"input","readiness","go","plan","identity","candidate","posture","replay"}; post={"receipt","capability","capability_expired","target","write","fsync","readback","partial"};allset=pre|post
 return {k:{"transition":"CANDIDATE->PREPARED_VALIDATION_ONLY" if k in pre else "PREPARED_VALIDATION_ONLY->PRODUCTION_INSTALLED","requires_write":k in post,"terminal":"TERMINAL_FAILURE"} for k in sorted(allset)}
def state_machine():
 d=deepcopy(v6.artifacts()[E/"f017-event06-v12-sequence05-installation-state-machine-v5.json"]);d.update(schema="pulsarmlx.f017.event06-v12-sequence05-installation-state-machine/1.5.0",failure_outcome_edge_mapping=outcomes(),race_mutation_families=["capability_expiry","candidate_replay","exclusive_create","target_identity","write_short","write_error","file_fsync","directory_fsync","readback_identity","concurrent_replacement"],alias_structural_variants=["duplicate_semantic_key","unknown_case_alias","scalar_type_coercion"],supersedes="docs/architecture/reviews/evidence/f017-event06-v12-sequence05-installation-state-machine-v5.json");return d
def failure_matrix():
 d=deepcopy(v6.v5.artifacts()[E/"f017-event06-v12-sequence05-failure-matrix-v5.json"]);der={"readiness_deletions":86,"readiness_types":86,"acceptance_predicates":34,"alternate_encoding_alias_binding_floor":18,"installation_and_race_floor":100};d.update(schema="pulsarmlx.f017.event06-v12-sequence05-failure-matrix/1.5.0",derivation={**der,"total":sum(der.values())},minimum_mutations=324,alias_family_derivation={"families":["duplicate semantics","unknown aliases","type coercions","path substitutions","SHA substitutions","canonical encoding"],"variants_per_family":3,"total":18},race_family_derivation={"families":state_machine()["race_mutation_families"],"repetitions_per_family":10,"total":100},supersedes="docs/architecture/reviews/evidence/f017-event06-v12-sequence05-failure-matrix-v5.json");return d
def normalized_reviews():
 return {
 E/"f017-event06-v12-sequence05-agy-design-cycle-06-normalized-result.json":{"schema":"pulsarmlx.f017.event06-v12-sequence05-agy-design-result/1.3.0","reviewed_commit":START_HEAD,"reviewed_tree":START_TREE,"blocking_findings":0,"required_findings":0,"unresolved_claims":0,"verdict":"ACCEPT_DESIGN_FOR_IMPLEMENTATION"},
 E/"f017-event06-v12-sequence05-opus-design-cycle-06-normalized-result.json":{"schema":"pulsarmlx.f017.event06-v12-sequence05-opus-design-result/1.3.0","reviewed_commit":START_HEAD,"reviewed_tree":START_TREE,"blocking_findings":3,"required_findings":6,"unresolved_claims":2,"finding_ids":["C6-B1","C6-B2","C6-B3","C6-R1","C6-R2","C6-R3","C6-R4","C6-R5","C6-R6","U1","U2"],"minimum_repair_count":8,"global_verdict":"REJECT"}}
def provenance(tool:str):
 envp=E/f"f017-event06-v12-sequence05-{tool}-design-cycle-06-provider-envelope.json";env=json.loads(envp.read_bytes());req=E/f"f017-event06-v12-sequence05-{tool}-design-cycle-06-request.md";resp=E/f"f017-event06-v12-sequence05-{tool}-design-cycle-06-exact-response.md";norm=E/f"f017-event06-v12-sequence05-{tool}-design-cycle-06-normalized-result.json";norm_value=normalized_reviews()[norm]
 completed=datetime.fromisoformat(("2026-08-28T09:35:22.504+00:00" if tool=="agy" else "2026-08-28T09:43:44.257+00:00"));dur=env.get("duration_seconds") or env["duration_api_ms"]/1000;started=completed-timedelta(seconds=dur)
 if tool=="agy": provider="UNAVAILABLE_FROM_PROVIDER_ENVELOPE";session=f"conversation_id={env['conversation_id']};status={env['status']};duration_seconds={dur};turns={env['num_turns']}";source="AGY_JSON_ENVELOPE_CONVERSATION_ID_STATUS_DURATION_USAGE";requested="gemini-3.1-pro-high";version="1.1.22";command="agy --model gemini-3.1-pro-high --effort high --mode plan --sandbox --output-format json --print <request-bytes>"
 else: provider="claude-opus-5" if "claude-opus-5" in env["modelUsage"] else "UNAVAILABLE";session=f"session_id={env['session_id']};subtype={env['subtype']};terminal_reason={env['terminal_reason']};permission_denials={len(env['permission_denials'])}";source="CLAUDE_JSON_ENVELOPE_SESSION_ID_CANONICAL_MODEL_STATUS_USAGE";requested="claude-opus-5";version="2.1.235";command="claude --model opus --effort high --permission-mode plan --tools Read Grep Glob Bash --no-session-persistence --output-format json --print <request-bytes>"
 return {"schema":"pulsarmlx.f017.independent-review-transport-provenance/1.0.0","tool":tool,"tool_version":version,"transport":"RAW_PROVIDER_ENVELOPE_RECOVERED_FROM_AUTHORIZED_CODEX_SESSION","command":command,"requested_model":requested,"provider_reported_model":provider,"provider_session_metadata":session,"independent_attestation_source":source,"started_at_utc":started.isoformat().replace('+00:00','Z'),"completed_at_utc":completed.isoformat().replace('+00:00','Z'),"exit_status":0,"request_path":str(req.relative_to(ROOT)),"request_sha256":sha(req),"response_path":str(resp.relative_to(ROOT)),"response_sha256":sha(resp),"normalized_result_path":str(norm.relative_to(ROOT)),"normalized_result_sha256":sha_bytes(canonical_bytes(norm_value)),"reviewed_commit":START_HEAD,"credentials_serialized":False,"result":"RECOVERED_EXACT_HISTORICAL_REVIEW"}
def repair_ledger():
 source=E/"f017-event06-v12-sequence05-opus-design-cycle-06-exact-response.md";s=sha(source);rows=[
 ("C7-01","derive every finding observation; remove five literal predicates","C6-B1","scripts/research/validate_f017_event06_sequence05_design_v4.py","five derived predicates plus isolated mutations"),
 ("C7-02","rebind measurement v2 and require consistent cross-bound values","C6-B2","docs/architecture/reviews/evidence/f017-event06-v12-to-v11-bridge-implementation-measurement-v2.json","cross-binding consistency proof"),
 ("C7-03","bind a commit/tree containing every current binding and validate with git object bytes","C6-B3,U1","docs/architecture/reviews/evidence/f017-event06-v12-sequence05-readiness-authority-manifest-prepared-v3.json","declared-tree path and SHA proof"),
 ("C7-04","emit exact 21-field provenance and derive provider model from envelope or mark unavailable","C6-R1","specs/017-rust-native-inference-runtime/contracts/f017-independent-review-transport-provenance-v5.json","exact key census and envelope binding"),
 ("C7-05","derive mutation floor 324 from 86+86+34+18+100","C6-R2","docs/architecture/reviews/evidence/f017-event06-v12-sequence05-failure-matrix-v6.json","arithmetic and negative mutation proof"),
 ("C7-06","map all 16 outcomes to real transitions and enforce write consistency","C6-R3","docs/architecture/reviews/evidence/f017-event06-v12-sequence05-installation-state-machine-v6.json","edge existence/write-class mutation proof"),
 ("C7-07","use distinct advisory evidence and reconcile graph/claim counters","C6-R4,U2","docs/architecture/reviews/evidence/f017-event06-v12-sequence05-advisory-disposition-ledger-v2.json","namespace and counter proof"),
 ("C7-08","implement six manifest-validation steps and eliminate qualification self-edge","C6-R5,C6-R6","specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-event06-readiness-authority-manifest-v6.json","exact census, declared-tree, DAG, mutation proof")]
 return {"schema":"pulsarmlx.f017.event06-v12-sequence05-cycle7-repair-ledger/1.0.0","source_response_path":str(source.relative_to(ROOT)),"source_response_sha256":s,"row_count":len(rows),"rows":[{"repair_id":i,"exact_meaning":meaning,"source_finding_ids":ids.split(','),"source_response_path":str(source.relative_to(ROOT)),"source_response_sha256":s,"affected_repository_paths":[path],"required_proof":proof,"repair_commit":"PENDING_BASE_REPAIR_COMMIT","validation_evidence":"PENDING_POST_COMMIT_QUALIFICATION","final_disposition":"OPEN"} for i,meaning,ids,path,proof in rows]}
def advisory_ledger():
 rows=[("cycle04","A1","failure-matrix-v6 arithmetic"),("cycle04","A2","cycle06 raw provider envelopes"),("cycle04","A3","no-access interposition authority"),("cycle04","A4","exclusive output banking validator"),("cycle04","A5","state-machine-v6 outcome edges"),("cycle04","A6","external qualification schema authority"),("cycle05","A1","no-access interposition authority"),("cycle05","A2","graph-state-v6 and claim-ledger-v6"),("cycle05","A3","external qualification schema authority")]
 return {"schema":"pulsarmlx.f017.event06-v12-sequence05-advisory-disposition-ledger/1.1.0","rows":[{"source_cycle":c,"finding_id":f,"disposition":"REPAIR_IMPLEMENTED_PENDING_POST_COMMIT_PROOF","named_evidence":e} for c,f,e in rows],"row_count":len(rows),"unresolved":len(rows)}
def graph_state():return {"schema":"pulsarmlx.f017.event06-v12-sequence05-design-graph-state/1.5.0","source_review_cycle":6,"source_blocking_findings":3,"source_required_findings":6,"source_unresolved_claims":2,"repair_rows":8,"status":"REPAIR_REQUIRED","running_nodes":0}
def claim_ledger():return {"schema":"pulsarmlx.f017.event06-v12-sequence05-design-claim-ledger/1.5.0","source_review_cycle":6,"challenged":9,"unresolved":2,"supported":0,"status":"REPAIR_REQUIRED"}
def repair_validation_index():
 rows=repair_ledger()["rows"]
 return {"schema":"pulsarmlx.f017.event06-v12-sequence05-cycle7-repair-validation-index/1.0.0","repair_head":"3ce928e53fef9a8e4d2cef06c74a9e11b1b86adb","repair_tree":"8294baba146001f994fe9e2775e724f9caf669a6","source_ledger_path":"docs/architecture/reviews/evidence/f017-event06-v12-sequence05-cycle7-repair-ledger-v1.json","source_ledger_sha256":sha(E/"f017-event06-v12-sequence05-cycle7-repair-ledger-v1.json"),"challenge_reproduction_path":"docs/architecture/reviews/evidence/f017-event06-v12-sequence05-challenge-reproducibility-cycle06-v2.json","challenge_reproduction_sha256":"7a86200b75bdfaaa12b4daef1cd8db337f0aea87d8d004b25f224211d6eb6e7a","mechanical_validation_path":"docs/architecture/reviews/evidence/f017-event06-v12-sequence05-design-mechanical-validation-v4.json","mechanical_validation_sha256":"0aeca25e36c198a6b85a463ccba29bb9ba8251d000993b315453984bbe193565","row_count":len(rows),"rows":[{"repair_id":row["repair_id"],"source_finding_ids":row["source_finding_ids"],"repair_commit":"3ce928e53fef9a8e4d2cef06c74a9e11b1b86adb","validation_evidence":"f017-event06-v12-sequence05-design-mechanical-validation-v4.json","final_disposition":"MECHANICALLY_SUPPORTED_PENDING_INDEPENDENT_REVIEW"} for row in rows],"duplicate_repair_ids":0,"unsupported_closed_dispositions":0,"checkpoint_access":0,"numerical_operations":0,"result":"PASS_PENDING_INDEPENDENT_REVIEW"}
def graph_state_v7():return {"schema":"pulsarmlx.f017.event06-v12-sequence05-design-graph-state/1.6.0","source_review_cycle":6,"cycle7_repair_rows":8,"cycle7_mechanical_repairs_supported":8,"cycle7_review_status":"PENDING","running_nodes":0,"status":"PASS_PENDING_INDEPENDENT_REVIEW"}
def claim_ledger_v7():return {"schema":"pulsarmlx.f017.event06-v12-sequence05-design-claim-ledger/1.6.0","source_review_cycle":6,"source_claims":11,"mechanically_supported":11,"independently_accepted":0,"unresolved":0,"status":"PASS_PENDING_INDEPENDENT_REVIEW"}
def design_artifacts():
 d={READINESS:readiness(),INSTALL:installation(),MANIFEST:manifest_contract(),QUAL:qualification(),PROV:provenance_contract(),SCHEMA_AUTH:schema_authority(),NOACCESS:noaccess(),E/"f017-event06-v12-sequence05-installation-state-machine-v6.json":state_machine(),E/"f017-event06-v12-sequence05-failure-matrix-v6.json":failure_matrix(),E/"f017-event06-v12-sequence05-cycle7-repair-ledger-v1.json":repair_ledger(),E/"f017-event06-v12-sequence05-advisory-disposition-ledger-v2.json":advisory_ledger(),E/"f017-event06-v12-sequence05-design-graph-state-v6.json":graph_state(),E/"f017-event06-v12-sequence05-design-claim-ledger-v6.json":claim_ledger(),E/"f017-event06-v12-sequence05-cycle7-repair-validation-index-v1.json":repair_validation_index(),E/"f017-event06-v12-sequence05-design-graph-state-v7.json":graph_state_v7(),E/"f017-event06-v12-sequence05-design-claim-ledger-v7.json":claim_ledger_v7()};d.update(normalized_reviews());d[E/"f017-event06-v12-sequence05-agy-design-cycle-06-provenance-v1.json"]=provenance("agy");d[E/"f017-event06-v12-sequence05-opus-design-cycle-06-provenance-v1.json"]=provenance("opus");return d
def current_bindings():
 return {"implementation_measurement":E/"f017-event06-v12-to-v11-bridge-implementation-measurement-v2.json","scientific_access_contract":C/"f017-corrected-full-checkpoint-oracle-scientific-access-v12.json","checkpoint_identity_authority":C/"f017-corrected-oracle-checkpoint-identity-authority-v12.json","numerical_contract":C/"f017-corrected-full-checkpoint-oracle-numerical-contract-v4.json","result_authority":C/"f017-corrected-oracle-result-authority-v11-v2.json","bridge_declaration":E/"f017-event06-v12-to-v11-numerical-authority-bridge-final-declaration-v1.json","readiness_interface":READINESS,"live_installation_interface":INSTALL,"future_go_capability":C/"f017-corrected-oracle-event06-future-go-capability-v1.json","review_transport_provenance_contract":PROV,"qualification_role_requirements":QUAL,"sequence4_finding_disposition":C/"f017-event06-sequence4-finding-disposition-v1.json"}
def prepared(head:str):
 tree=subprocess.run(["git","rev-parse",f"{head}^{{tree}}"],cwd=ROOT,check=True,capture_output=True,text=True).stdout.strip();q=qualification();future=set(q["future_output_roles"]);bindings={}
 for role in ROLES:
  if role in future:bindings[role]={"binding_state":"UNBOUND_FUTURE","required_schema":q["roles"][role]["required_schema"],"availability_stage":q["roles"][role]["availability_stage"]}
  else:
   path=str(current_bindings()[role].relative_to(ROOT));raw=git_bytes(head,path);bindings[role]={"binding_state":"CURRENT_DESIGN_AUTHORITY","path":path,"sha256":sha_bytes(raw)}
 return {"schema":manifest_contract()["prepared_instance_schema"],"purpose":"DESIGN_INSTANTIABILITY_ONLY_NOT_LIVE_READINESS_AUTHORITY","implementation_head":head,"implementation_tree":tree,"roles":ROLES,"role_count":21,"bindings":bindings,"binding_count":21,"unbound_future_roles":sorted(future),"validated_binding_count":12,"result":"PREPARED_INCOMPLETE","final_acceptance_eligible":False,"live_authority":False,"checkpoint_root_resolved":False,"checkpoint_access":0,"numerical_operations":0,"event_06_executed":False}
def main():
 ap=argparse.ArgumentParser();ap.add_argument("--check",action="store_true");ap.add_argument("--emit-prepared");a=ap.parse_args()
 for p,v in design_artifacts().items():write(p,v,a.check)
 if a.emit_prepared:write(PREPARED,prepared(a.emit_prepared),a.check)
 elif a.check and PREPARED.exists():
  head=json.loads(PREPARED.read_bytes())["implementation_head"];write(PREPARED,prepared(head),True)
 return 0
if __name__=="__main__":raise SystemExit(main())
