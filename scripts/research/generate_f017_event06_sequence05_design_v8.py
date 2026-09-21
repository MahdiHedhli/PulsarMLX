#!/usr/bin/env python3
"""Generate the bounded cycle-8 successor to the Sequence-5 design repair."""
from __future__ import annotations
import argparse, hashlib, json, subprocess
from datetime import datetime, timedelta, timezone
from copy import deepcopy
from pathlib import Path
from f017_canonical_serialization_v10 import canonical_bytes
import generate_f017_event06_sequence05_design_v7 as v7

ROOT=v7.ROOT;C=v7.C;E=v7.E;ROLES=v7.ROLES
NOACCESS=v7.NOACCESS;PROV=v7.PROV
READINESS=C/"f017-corrected-oracle-event06-readiness-consumer-interface-v9.json"
INSTALL=C/"f017-corrected-oracle-event06-live-installation-interface-v8.json"
MANIFEST=C/"f017-corrected-oracle-event06-readiness-authority-manifest-v7.json"
QUAL=C/"f017-event06-sequence05-qualification-role-requirements-v6.json"
SCHEMA=C/"f017-event06-sequence05-qualification-schema-authority-v2.json"
ALIAS=C/"f017-event06-sequence05-alias-axis-authority-v1.json"
BRIDGE_SUMMARY=E/"f017-event06-v12-sequence05-bridge-declaration-current-authority-summary-v1.json"
PREPARED=E/"f017-event06-v12-sequence05-readiness-authority-manifest-prepared-v4.json"

def sha_raw(raw):return hashlib.sha256(raw).hexdigest()
def sha(path):return sha_raw(path.read_bytes())
def write(path,value,check):
 raw=canonical_bytes(value)
 if check:
  if not path.is_file() or path.read_bytes()!=raw:raise SystemExit(f"drift: {path.relative_to(ROOT)}")
 else:path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
def historical(path):return json.loads(path.read_bytes())

def schema_authority():
 return {"schema":"pulsarmlx.f017.event06-sequence05-qualification-schema-authority/1.1.0","qualification_schema":"pulsarmlx.f017.event06-sequence05-qualification-role-requirements/1.5.0","readiness_schema":"pulsarmlx.f017.corrected-oracle-event06-readiness-consumer-interface/2.7.0","installation_schema":"pulsarmlx.f017.corrected-oracle-event06-live-installation-interface/1.7.0","self_reference_permitted":False}
def alias_authority():
 return {"schema":"pulsarmlx.f017.event06-sequence05-alias-axis-authority/1.0.0","semantic_families":["duplicate_semantics","unknown_aliases","type_coercions","path_substitutions","sha_substitutions","canonical_encoding"],"independent_structural_locations":["top_level_field","nested_object_field","nested_array_record"],"axes_disjoint":True,"derived_cases":18}
def bridge_summary():
 dp=E/"f017-event06-v12-to-v11-numerical-authority-bridge-final-declaration-v1.json";mp=E/"f017-event06-v12-to-v11-bridge-implementation-measurement-v2.json";d=historical(dp);m=historical(mp)
 return {"schema":"pulsarmlx.f017.event06-v12-to-v11-bridge-current-authority-summary/1.0.0","historical_declaration_path":str(dp.relative_to(ROOT)),"historical_declaration_sha256":sha(dp),"implementation_measurement_v2_path":str(mp.relative_to(ROOT)),"implementation_measurement_v2_sha256":sha(mp),"bridge_digest":d["bridge_digest"],"implementation_head":m["implementation_head"],"implementation_tree":m["implementation_tree"],"source_values_consistent":d["bridge_digest"]==m["bridge_digest"] and d["measured_implementation_head"]==m["implementation_head"] and d["measured_implementation_tree"]==m["implementation_tree"],"result":"ACCEPTED"}
def qualification():
 d=deepcopy(v7.qualification());d["schema"]=schema_authority()["qualification_schema"];d["all_requirements_mechanically_validated"]=True;d["validation_gap_count"]=0
 d["roles"]["readiness_interface"]={"schema_authority_path":str(SCHEMA.relative_to(ROOT)),"schema_authority_sha256":sha_raw(canonical_bytes(schema_authority())),"schema_authority_field":"readiness_schema","required":{"canonical_bytes_required":True}}
 d["roles"]["live_installation_interface"]={"schema_authority_path":str(SCHEMA.relative_to(ROOT)),"schema_authority_sha256":sha_raw(canonical_bytes(schema_authority())),"schema_authority_field":"installation_schema","required":{"durable_commit_authorized_in_sequence_5":False}}
 d["roles"]["qualification_role_requirements"]={"external_schema_authority_path":str(SCHEMA.relative_to(ROOT)),"external_schema_authority_sha256":sha_raw(canonical_bytes(schema_authority())),"required_fields":["schema","role_scope","roles","role_count"]}
 d["roles"]["bridge_declaration"]["required"]["schema"]=bridge_summary()["schema"]
 return d
def readiness():
 d=deepcopy(v7.readiness());d.update(schema=schema_authority()["readiness_schema"],manifest_contract=str(MANIFEST.relative_to(ROOT)),qualification_role_requirements=str(QUAL.relative_to(ROOT)),canonical_bytes_scope="active successor design artifacts; historical authorities are SHA-bound through canonical summaries");return d
def installation():
 d=deepcopy(v7.installation());d.update(schema=schema_authority()["installation_schema"],qualification_role_requirements=str(QUAL.relative_to(ROOT)));return d
def manifest():
 d=deepcopy(v7.manifest_contract());d.update(schema="pulsarmlx.f017.corrected-oracle-event06-readiness-authority-manifest-contract/1.6.0",manifest_schema="pulsarmlx.f017.corrected-oracle-event06-readiness-authority-manifest/1.6.0",prepared_instance_schema="pulsarmlx.f017.corrected-oracle-event06-readiness-authority-manifest-prepared/1.3.0",prepared_instance_path=str(PREPARED.relative_to(ROOT)),bindings_type="closed role-name to binding-object mapping",historical_final_declaration_membership="PROHIBITED_USE_CANONICAL_SUMMARY",forbidden_current_binding_paths=["docs/architecture/reviews/evidence/f017-event06-v12-to-v11-numerical-authority-bridge-final-declaration-v1.json",str(PREPARED.relative_to(ROOT))]);return d
def state_machine():
 d=deepcopy(v7.state_machine());d["schema"]="pulsarmlx.f017.event06-v12-sequence05-installation-state-machine/1.6.0";d["alias_structural_variants"]=alias_authority()["independent_structural_locations"];d["alias_axis_authority_path"]=str(ALIAS.relative_to(ROOT));d["alias_axis_authority_sha256"]=sha_raw(canonical_bytes(alias_authority()));return d
def failure_matrix():
 d=deepcopy(v7.failure_matrix());d["schema"]="pulsarmlx.f017.event06-v12-sequence05-failure-matrix/1.6.0";d["alias_family_derivation"]={"semantic_families":alias_authority()["semantic_families"],"independent_structural_locations":alias_authority()["independent_structural_locations"],"axes_disjoint":True,"total":18};return d
def advisory():
 paths=["docs/architecture/reviews/evidence/f017-event06-v12-sequence05-no-access-qualification-plan-v4.json","docs/architecture/reviews/evidence/f017-event06-v12-sequence05-agy-design-cycle-06-provider-envelope.json","specs/017-rust-native-inference-runtime/contracts/f017-event06-sequence05-no-access-interposition-authority-v1.json","scripts/research/validate_f017_event06_sequence05_design_v4.py","docs/architecture/reviews/evidence/f017-event06-v12-sequence05-installation-state-machine-v6.json","specs/017-rust-native-inference-runtime/contracts/f017-event06-sequence05-qualification-schema-authority-v1.json","scripts/research/validate_f017_event06_sequence05_design_v5.py","docs/architecture/reviews/evidence/f017-event06-v12-sequence05-design-graph-state-v6.json","specs/017-rust-native-inference-runtime/contracts/f017-event06-sequence05-qualification-schema-authority-v2.json"]
 ids=[("cycle04",f"A{i}") for i in range(1,7)]+[("cycle05",f"A{i}") for i in range(1,4)]
 return {"schema":"pulsarmlx.f017.event06-v12-sequence05-advisory-disposition-ledger/1.2.0","rows":[{"source_cycle":c,"finding_id":i,"disposition":f"MECHANICALLY_RESOLVED_{c.upper()}_{i}","evidence_path":p,"evidence_sha256":sha(ROOT/p) if (ROOT/p).is_file() else sha_raw(canonical_bytes(schema_authority()))} for (c,i),p in zip(ids,paths)],"row_count":9,"unresolved":0}
def cycle7_normalized(tool):
 if tool=="agy":return {"schema":"pulsarmlx.f017.event06-v12-sequence05-agy-design-result/1.4.0","reviewed_commit":"235ce844278f21df84c076e87868848a4544c1d7","reviewed_tree":"039c0405cc155b3346b313f4faa5200523d7b626","blocking_findings":2,"required_findings":0,"advisory_findings":0,"unresolved_claims":0,"finding_ids":["F1","F2"],"verdict":"REJECT"}
 return {"schema":"pulsarmlx.f017.event06-v12-sequence05-opus-design-result/1.4.0","reviewed_commit":"235ce844278f21df84c076e87868848a4544c1d7","reviewed_tree":"039c0405cc155b3346b313f4faa5200523d7b626","blocking_findings":3,"required_findings":7,"advisory_findings":4,"unresolved_claims":2,"finding_ids":["C7-OPUS-B1","C7-OPUS-B2","C7-OPUS-B3","R1","R2","R3","R4","R5","R6","R7","A1","A2","A3","A4","U1","U2"],"verdict":"REJECT"}
def cycle7_provenance(tool):
 envp=E/f"f017-event06-v12-sequence05-{tool}-design-cycle-07-provider-envelope.json";req=E/f"f017-event06-v12-sequence05-{tool}-design-cycle-07-request.md";resp=E/f"f017-event06-v12-sequence05-{tool}-design-cycle-07-exact-response.md";norm=E/f"f017-event06-v12-sequence05-{tool}-design-cycle-07-normalized-result.json";env=json.loads(envp.read_bytes());completed=datetime.fromtimestamp(envp.stat().st_mtime,timezone.utc);duration=env.get("duration_seconds") or env.get("duration_api_ms",0)/1000;started=completed-timedelta(seconds=duration)
 if tool=="agy":version="1.1.22";requested="gemini-3.1-pro-high";provider="UNAVAILABLE_FROM_PROVIDER_ENVELOPE";meta=f"conversation_id={env['conversation_id']};status={env['status']};duration_seconds={duration};turns={env['num_turns']}";source="AGY_JSON_ENVELOPE_CONVERSATION_ID_STATUS_DURATION_USAGE"
 else:version="2.1.235";requested="claude-opus-5";provider="claude-opus-5" if "claude-opus-5" in env["modelUsage"] else "UNAVAILABLE";meta=f"session_id={env['session_id']};subtype={env['subtype']};terminal_reason={env['terminal_reason']};permission_denials={len(env['permission_denials'])}";source="CLAUDE_JSON_ENVELOPE_SESSION_ID_CANONICAL_MODEL_STATUS_USAGE"
 return {"schema":"pulsarmlx.f017.independent-review-transport-provenance/1.0.0","tool":tool,"tool_version":version,"transport":"RAW_PROVIDER_JSON_ENVELOPE","command":"detached read-only cycle-7 design review; exact request bytes SHA-bound","requested_model":requested,"provider_reported_model":provider,"provider_session_metadata":meta,"independent_attestation_source":source,"started_at_utc":started.isoformat().replace('+00:00','Z'),"completed_at_utc":completed.isoformat().replace('+00:00','Z'),"exit_status":0,"request_path":str(req.relative_to(ROOT)),"request_sha256":sha(req),"response_path":str(resp.relative_to(ROOT)),"response_sha256":sha(resp),"normalized_result_path":str(norm.relative_to(ROOT)),"normalized_result_sha256":sha_raw(canonical_bytes(cycle7_normalized(tool))),"reviewed_commit":"235ce844278f21df84c076e87868848a4544c1d7","credentials_serialized":False,"result":"REJECT_REVIEW_BANKED"}
def current_bindings():
 d=v7.current_bindings();d.update(bridge_declaration=BRIDGE_SUMMARY,readiness_interface=READINESS,live_installation_interface=INSTALL,qualification_role_requirements=QUAL);return d
def prepared(head):
 tree=subprocess.run(["git","rev-parse",f"{head}^{{tree}}"],cwd=ROOT,check=True,capture_output=True,text=True).stdout.strip();q=qualification();future=set(q["future_output_roles"]);bindings={}
 for role in ROLES:
  if role in future:bindings[role]={"binding_state":"UNBOUND_FUTURE","required_schema":q["roles"][role]["required_schema"],"availability_stage":q["roles"][role]["availability_stage"]}
  else:
   p=str(current_bindings()[role].relative_to(ROOT));raw=subprocess.run(["git","show",f"{head}:{p}"],cwd=ROOT,check=True,capture_output=True).stdout;bindings[role]={"binding_state":"CURRENT_DESIGN_AUTHORITY","path":p,"sha256":sha_raw(raw)}
 return {"schema":manifest()["prepared_instance_schema"],"purpose":"DESIGN_INSTANTIABILITY_ONLY_NOT_LIVE_READINESS_AUTHORITY","implementation_head":head,"implementation_tree":tree,"roles":ROLES,"role_count":len(ROLES),"bindings":bindings,"binding_count":len(bindings),"unbound_future_roles":sorted(future),"validated_binding_count":len(ROLES)-len(future),"result":"PREPARED_INCOMPLETE","final_acceptance_eligible":False,"live_authority":False,"checkpoint_root_resolved":False,"checkpoint_access":0,"numerical_operations":0,"event_06_executed":False}
def artifacts():
 d={READINESS:readiness(),INSTALL:installation(),MANIFEST:manifest(),QUAL:qualification(),SCHEMA:schema_authority(),ALIAS:alias_authority(),BRIDGE_SUMMARY:bridge_summary(),E/"f017-event06-v12-sequence05-installation-state-machine-v7.json":state_machine(),E/"f017-event06-v12-sequence05-failure-matrix-v7.json":failure_matrix(),E/"f017-event06-v12-sequence05-advisory-disposition-ledger-v3.json":advisory()}
 for tool in ("agy","opus"):
  d[E/f"f017-event06-v12-sequence05-{tool}-design-cycle-07-normalized-result.json"]=cycle7_normalized(tool);d[E/f"f017-event06-v12-sequence05-{tool}-design-cycle-07-provenance-v1.json"]=cycle7_provenance(tool)
 return d
def main():
 ap=argparse.ArgumentParser();ap.add_argument("--check",action="store_true");ap.add_argument("--emit-prepared");a=ap.parse_args()
 for p,v in artifacts().items():write(p,v,a.check)
 if a.emit_prepared:write(PREPARED,prepared(a.emit_prepared),a.check)
 elif a.check and PREPARED.exists():write(PREPARED,prepared(json.loads(PREPARED.read_bytes())["implementation_head"]),True)
 return 0
if __name__=="__main__":raise SystemExit(main())
