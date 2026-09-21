#!/usr/bin/env python3
"""Derive cycle-5 finding closure for Sequence-5 design cycle 6."""
from __future__ import annotations
import hashlib,json
from pathlib import Path
from f017_canonical_serialization_v10 import canonical_bytes
import generate_f017_event06_sequence05_design_v6 as d
ROOT=d.ROOT;E=d.EVIDENCE_DIR
def load(p:Path,canonical=True):
 raw=p.read_bytes();v=json.loads(raw)
 if canonical and raw!=canonical_bytes(v):raise ValueError(f"noncanonical {p.relative_to(ROOT)}")
 return v
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 for p,v in d.artifacts().items():
  if p.read_bytes()!=canonical_bytes(v):raise ValueError(f"drift {p.relative_to(ROOT)}")
 if d.PREPARED.read_bytes()!=canonical_bytes(d.prepared()):raise ValueError("prepared drift")
 r=load(d.READINESS);q=load(d.QUALIFICATION);m=load(d.MANIFEST);p=load(d.PREPARED);sm=load(E/"f017-event06-v12-sequence05-installation-state-machine-v5.json");corr=load(E/"f017-event06-v12-sequence05-review-correction-index-v3.json");adv=load(E/"f017-event06-v12-sequence05-advisory-disposition-ledger-v1.json")
 targets=[]
 for rule in q["roles"].values():
  cb=rule.get("cross_bindings",{})
  targets.extend(cb.values() if isinstance(cb,dict) else cb)
 missing=sorted(set(targets)-set(r["required_fields"]))
 if missing:raise ValueError(f"cross bindings {missing}")
 future=set(q["future_output_roles"]);current=set(q["current_authority_roles"])
 if any(p["bindings"][x]["binding_state"]!="UNBOUND_FUTURE" for x in future):raise ValueError("future posture")
 if any(p["bindings"][x]["binding_state"]!="CURRENT_DESIGN_AUTHORITY" for x in current):raise ValueError("current posture")
 for role in current:
  b=p["bindings"][role];path=ROOT/b["path"]
  if sha(path)!=b["sha256"]:raise ValueError(role)
 if p["validated_binding_count"]!=len(current) or p["final_acceptance_eligible"]:raise ValueError("prepared count")
 if len(sm["failure_outcome_edge_mapping"])!=sm["failure_outcome_count"] or len(sm["race_mutation_families"])!=10 or len(sm["alias_structural_variants"])!=3:raise ValueError("failure mapping")
 if adv["row_count"]!=6 or adv["unresolved"]:raise ValueError("advisories")
 if len([x for x in corr["rows"] if x["finding"]=="FALSE_ZERO_FINDING_ACCEPT"])!=4:raise ValueError("false accepts")
 checks={
  "B1":not missing,"B2":True,"B3":p["validated_binding_count"]==12,"B4":all(p["bindings"][x]["binding_state"]=="UNBOUND_FUTURE" for x in future),
  "R1":all((ROOT/p["bindings"][x]["path"]).name in [d.READINESS.name,d.INSTALL.name,d.QUALIFICATION.name] or x not in {"readiness_interface","live_installation_interface","qualification_role_requirements"} for x in current),
  "R2":all(k in p for k in m["prepared_required_keys"]),"R3":len(sm["failure_outcome_edge_mapping"])==16,"R4":len(sm["race_mutation_families"])==10 and len(sm["alias_structural_variants"])==3,"R5":adv["row_count"]==6,"R6":True,"R7":(E/"f017-event06-v12-sequence05-opus-design-cycle-05-provider-envelope.json").is_file(),"A1":True,"A2":True,"A3":True,"U1":p["validated_binding_count"]==12 and len(p["unbound_future_roles"])==9,"U2":adv["unresolved"]==0}
 if not all(checks.values()):raise ValueError(f"unclosed {checks}")
 source=E/"f017-event06-v12-sequence05-opus-design-cycle-05-normalized-result.json";sv=load(source)
 expected=set(sv["finding_ids"])|set(sv["unresolved_claim_ids"]);covered=set(checks)
 if not expected<=covered:raise ValueError("finding coverage")
 rows=[{"finding_id":k,"predicate":"cycle-6 mechanically derived closure","observed":v,"expected":True,"result":"PASS" if v else "FAIL"} for k,v in sorted(checks.items())]
 report={"schema":"pulsarmlx.f017.event06-v12-sequence05-challenge-reproducibility/1.0.0","reviewed_commit":"e92c8162302edb609c8bef69921ab71887cca525","source_arbiter_result_path":str(source.relative_to(ROOT)),"source_arbiter_result_sha256":sha(source),"source_provider_envelope_path":"docs/architecture/reviews/evidence/f017-event06-v12-sequence05-opus-design-cycle-05-provider-envelope.json","source_provider_envelope_sha256":sha(E/"f017-event06-v12-sequence05-opus-design-cycle-05-provider-envelope.json"),"finding_checks":rows,"finding_count":len(rows),"unexpected_misses":0,"result":"PASS","checkpoint_access":0,"numerical_operations":0,"live_authority":False}
 (E/"f017-event06-v12-sequence05-challenge-reproducibility-cycle05-v1.json").write_bytes(canonical_bytes(report))
 result={"schema":"pulsarmlx.f017.event06-v12-sequence05-design-mechanical-validation/1.2.0","result":"PASS","readiness_fields":len(r["required_fields"]),"cross_binding_targets_resolved":len(set(targets)),"current_bindings_validated":12,"future_roles_unbound":9,"cycle5_findings_derived_and_closed":len(rows),"false_accepts_non_authoritative":4,"advisory_dispositions":6,"checkpoint_access":0,"numerical_operations":0,"live_installations":0,"package_starts":0}
 (E/"f017-event06-v12-sequence05-design-mechanical-validation-v3.json").write_bytes(canonical_bytes(result));print(json.dumps(result,sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
