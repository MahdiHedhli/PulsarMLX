#!/usr/bin/env python3
"""Cycle-8 fail-reachable validator for the F017 Sequence-5 design."""
from __future__ import annotations
import argparse, ast, hashlib, json, re, subprocess
from copy import deepcopy
from pathlib import Path
from typing import Callable
from f017_canonical_serialization_v10 import canonical_bytes
import generate_f017_event06_sequence05_design_v8 as design
import validate_f017_event06_sequence05_design_v4 as prior

ROOT=design.ROOT;E=design.E
prior.design=design
Store=prior.Store
def sha(raw):return hashlib.sha256(raw).hexdigest()
def doc(store,path,canonical=True):return store.document(path,canonical=canonical)
def git_raw(head,path):return subprocess.run(["git","show",f"{head}:{path}"],cwd=ROOT,check=True,capture_output=True).stdout
def git_mode(head,path):return subprocess.run(["git","ls-tree",head,"--",path],cwd=ROOT,check=True,capture_output=True,text=True).stdout.split()[0]

def predicate_source_review(store):
 p=E/"f017-event06-v12-sequence05-opus-design-cycle-06-exact-response.md";text=store.raw(p).decode();section=text.split("## Minimum repair set for cycle 7",1)
 items=re.findall(r"(?m)^(\d+)\. (.+)$",section[1] if len(section)==2 else "")
 n=doc(store,E/"f017-event06-v12-sequence05-opus-design-cycle-06-normalized-result.json")
 return len(items)==n["minimum_repair_count"] and [int(i) for i,_ in items]==list(range(1,len(items)+1)) and all(fid in text for fid in n["finding_ids"])
def predicate_measurement(store):
 s=doc(store,design.BRIDGE_SUMMARY);d=doc(store,ROOT/s["historical_declaration_path"],False);m=doc(store,ROOT/s["implementation_measurement_v2_path"],False)
 return s["historical_declaration_sha256"]==sha(store.raw(ROOT/s["historical_declaration_path"])) and s["implementation_measurement_v2_sha256"]==sha(store.raw(ROOT/s["implementation_measurement_v2_path"])) and s["bridge_digest"]==d["bridge_digest"]==m["bridge_digest"] and s["implementation_head"]==d["measured_implementation_head"]==m["implementation_head"] and s["implementation_tree"]==d["measured_implementation_tree"]==m["implementation_tree"] and s["source_values_consistent"]
def predicate_schema_externality(store):
 q=doc(store,design.QUAL);a=doc(store,design.SCHEMA);roles=q["roles"];ap=str(design.SCHEMA.relative_to(ROOT));ash=sha(store.raw(design.SCHEMA));mapping={"readiness_interface":"readiness_schema","live_installation_interface":"installation_schema","qualification_role_requirements":"qualification_schema"}
 return all(roles[r]["schema_authority_path" if r!="qualification_role_requirements" else "external_schema_authority_path"]==ap and roles[r]["schema_authority_sha256" if r!="qualification_role_requirements" else "external_schema_authority_sha256"]==ash for r in mapping) and roles["readiness_interface"]["schema_authority_field"]==mapping["readiness_interface"] and roles["live_installation_interface"]["schema_authority_field"]==mapping["live_installation_interface"] and a["qualification_schema"]==q["schema"] and not a["self_reference_permitted"]
def predicate_failure_arithmetic(store):
 r=doc(store,design.READINESS);m=doc(store,E/"f017-event06-v12-sequence05-failure-matrix-v7.json");a=doc(store,design.ALIAS);sm=doc(store,E/"f017-event06-v12-sequence05-installation-state-machine-v7.json");q=doc(store,design.QUAL)
 deletions=len(r["required_fields"]);types=sum(len(v) for v in r["exact_types"].values());predicates=len(r["exact_predicates"]);aliases=len(a["semantic_families"])*len(a["independent_structural_locations"]);races=len(sm["race_mutation_families"])*m["race_family_derivation"]["repetitions_per_family"];total=deletions+types+predicates+aliases+races
 return len(set(r["required_fields"]))==deletions==r["field_count"]==types and a["axes_disjoint"] and not set(a["semantic_families"])&set(a["independent_structural_locations"]) and m["derivation"]["total"]==m["minimum_mutations"]==total and q["roles"]["failure_qualification"]["minimums"]["mutation_cases"]==total
def predicate_outcomes(store):
 sm=doc(store,E/"f017-event06-v12-sequence05-installation-state-machine-v7.json");fm=doc(store,E/"f017-event06-v12-sequence05-failure-matrix-v7.json");edges={x["from"]+"->"+x["to"]:x["write"] for x in sm["transitions"]};mapping=sm["failure_outcome_edge_mapping"]
 return set(mapping)==set(fm["category_outcomes"]) and len(mapping)==sm["failure_outcome_count"] and all(x["transition"] in edges and x["requires_write"]==edges[x["transition"]] for x in mapping.values())
def predicate_advisories(store):
 a=doc(store,E/"f017-event06-v12-sequence05-advisory-disposition-ledger-v3.json");rows=a["rows"];ids={(x["source_cycle"],x["finding_id"]) for x in rows};paths=[x["evidence_path"] for x in rows]
 return len(rows)==a["row_count"]==len(ids)==len(set(paths)) and a["unresolved"]==0 and all(sha(store.raw(ROOT/x["evidence_path"]))==x["evidence_sha256"] for x in rows)
def predicate_prepared(store):
 p=doc(store,design.PREPARED);m=doc(store,design.MANIFEST);q=doc(store,design.QUAL);current=set(q["current_authority_roles"]);future=set(q["future_output_roles"]);bindings=p["bindings"]
 if set(p)!=set(m["prepared_required_keys"]) or p["roles"]!=design.ROLES or set(p["roles"])!=current|future or current&future:return False
 if not(p["role_count"]==p["binding_count"]==len(p["roles"])==len(bindings) and p["validated_binding_count"]==len(current)):return False
 if subprocess.run(["git","rev-parse",f'{p["implementation_head"]}^{{tree}}'],cwd=ROOT,check=True,capture_output=True,text=True).stdout.strip()!=p["implementation_tree"]:return False
 forbidden=set(m["forbidden_current_binding_paths"])
 for role in current:
  b=bindings[role];path=b.get("path","");parts=Path(path).parts
  if b.get("binding_state")!="CURRENT_DESIGN_AUTHORITY" or Path(path).is_absolute() or ".." in parts or path in forbidden or git_mode(p["implementation_head"],path)=="120000" or sha(git_raw(p["implementation_head"],path))!=b.get("sha256"):return False
 for role in future:
  if set(bindings[role])!={"binding_state","required_schema","availability_stage"} or bindings[role]["binding_state"]!="UNBOUND_FUTURE":return False
 return p["unbound_future_roles"]==sorted(future) and bindings["bridge_declaration"]["path"]==str(design.BRIDGE_SUMMARY.relative_to(ROOT)) and p["final_acceptance_eligible"] is False
def predicate_qualification(store):
 q=doc(store,design.QUAL);return q["all_requirements_mechanically_validated"] and q["validation_gap_count"]==0 and q["validation_required_before_acceptance"]
def predicate_provenance(store):
 c=doc(store,design.PROV);keys=set(c["required_fields"])
 return len(keys)==len(c["required_fields"]) and all(set(doc(store,E/f"f017-event06-v12-sequence05-{t}-design-cycle-06-provenance-v1.json"))==keys for t in ("agy","opus"))
def predicate_graph(store):
 g6=doc(store,E/"f017-event06-v12-sequence05-design-graph-state-v6.json");c6=doc(store,E/"f017-event06-v12-sequence05-design-claim-ledger-v6.json");s6=doc(store,E/"f017-event06-v12-sequence05-opus-design-cycle-06-normalized-result.json");s5=doc(store,E/"f017-event06-v12-sequence05-opus-design-cycle-05-normalized-result.json")
 return g6["source_blocking_findings"]==s6["blocking_findings"] and g6["source_required_findings"]==s6["required_findings"] and c6["challenged"]==s6["blocking_findings"]+s6["required_findings"] and s5["unresolved_claims"]==2 and s6["unresolved_claims"]==c6["unresolved"]

PREDICATES:dict[str,Callable[[Store],bool]]={"B2":predicate_source_review,"R6":predicate_schema_externality,"A1":lambda s:prior.derive_A1(s)["result"]=="PASS","A2":lambda s:prior.derive_A2(s)["result"]=="PASS","A3":lambda s:prior.derive_A3(s)["result"]=="PASS","measurement":predicate_measurement,"failure_arithmetic":predicate_failure_arithmetic,"outcomes":predicate_outcomes,"advisories":predicate_advisories,"prepared":predicate_prepared,"qualification":predicate_qualification,"provenance":predicate_provenance,"graph":predicate_graph}

def ast_guard():
 modules=[Path(__file__),Path(prior.__file__)];scanned=[]
 for path in modules:
  tree=ast.parse(path.read_text())
  for node in tree.body:
   if isinstance(node,ast.FunctionDef) and (node.name.startswith("predicate_") or node.name in {"derive_B2","derive_R6","derive_A1","derive_A2","derive_A3"}):
    returns=[x for x in ast.walk(node) if isinstance(x,ast.Return)];
    if not returns or any(isinstance(x.value,ast.Constant) and x.value.value is True for x in returns):raise ValueError(f"literal success return {node.name}")
    scanned.append(f"{path.name}:{node.name}")
 return {"scanned":sorted(scanned),"count":len(scanned),"literal_returns":0,"result":"PASS"}
def evaluate(store):return {k:f(store) for k,f in PREDICATES.items()}
def mutate(store,path,change,canonical=True):
 if canonical is None:
  overrides=dict(store.overrides);overrides[str(path.relative_to(ROOT))]=change(store.raw(path));return Store(overrides)
 d=doc(store,path,canonical);change(d);return store.changed(path,d)
def mutations(base):
 cases=[
 ("B2",E/"f017-event06-v12-sequence05-opus-design-cycle-06-normalized-result.json",lambda d:d.__setitem__("minimum_repair_count",7),True),
 ("R6",design.QUAL,lambda d:d["roles"]["readiness_interface"].__setitem__("schema_authority_field","installation_schema"),True),
 ("A1",ROOT/"scripts/research/f017_checkpoint_identity_authority_v12.py",lambda raw:raw.replace(b"def canonical_candidate",b"def unavailable_candidate",1),None),
 ("A2",E/"f017-event06-v12-sequence05-design-claim-ledger-v6.json",lambda d:d.__setitem__("source_review_cycle",5),True),
 ("A3",design.PREPARED,lambda d:d["bindings"]["readiness_interface"].update(deepcopy(d["bindings"]["live_installation_interface"])),True),
 ("measurement",design.BRIDGE_SUMMARY,lambda d:d.__setitem__("bridge_digest","0"*64),True),
 ("failure_arithmetic",design.READINESS,lambda d:d["required_fields"].pop(),True),
 ("outcomes",E/"f017-event06-v12-sequence05-installation-state-machine-v7.json",lambda d:d["failure_outcome_edge_mapping"]["write"].__setitem__("transition","CANDIDATE->PREPARED_VALIDATION_ONLY"),True),
 ("advisories",E/"f017-event06-v12-sequence05-advisory-disposition-ledger-v3.json",lambda d:d["rows"][1].__setitem__("evidence_path",d["rows"][0]["evidence_path"]),True),
 ("prepared",design.PREPARED,lambda d:d["bindings"]["bridge_declaration"].__setitem__("path","docs/architecture/reviews/evidence/f017-event06-v12-to-v11-numerical-authority-bridge-final-declaration-v1.json"),True),
 ("qualification",design.QUAL,lambda d:d.__setitem__("validation_gap_count",1),True),
 ("provenance",E/"f017-event06-v12-sequence05-opus-design-cycle-06-provenance-v1.json",lambda d:d.pop("command"),True),
 ("graph",E/"f017-event06-v12-sequence05-opus-design-cycle-05-normalized-result.json",lambda d:d.__setitem__("unresolved_claims",3),True)]
 baseline=evaluate(base);rows=[]
 for index,(target,path,change,canonical) in enumerate(cases,1):
  values=evaluate(mutate(base,path,change,canonical));changed={k for k in values if values[k]!=baseline[k]};rows.append({"mutation_id":f"C8-M{index:02d}","target":target,"changed_predicates":sorted(changed),"isolated":changed=={target} and not values[target],"result":"PASS" if changed=={target} and not values[target] else "FAIL"})
 return rows
def report(store):
 values=evaluate(store);ms=mutations(store);head=subprocess.run(["git","rev-parse","HEAD"],cwd=ROOT,check=True,capture_output=True,text=True).stdout.strip();tree=subprocess.run(["git","rev-parse","HEAD^{tree}"],cwd=ROOT,check=True,capture_output=True,text=True).stdout.strip();ok=all(values.values()) and all(x["result"]=="PASS" for x in ms)
 return {"schema":"pulsarmlx.f017.event06-v12-sequence05-design-mechanical-validation/1.4.0","reviewed_commit":head,"reviewed_tree":tree,"predicate_results":values,"predicate_count":len(values),"predicate_passes":sum(values.values()),"ast_guard":ast_guard(),"mutations":ms,"mutation_count":len(ms),"mutation_rejections":sum(x["result"]=="PASS" for x in ms),"checkpoint_root_resolved":False,"checkpoint_access":0,"numerical_operations":0,"live_authority":False,"result":"PASS" if ok else "FAIL"}
def main():
 ap=argparse.ArgumentParser();ap.add_argument("--output",type=Path);ap.add_argument("--inject-a2-failure",action="store_true");a=ap.parse_args();store=Store({})
 if a.inject_a2_failure:
  p=E/"f017-event06-v12-sequence05-design-claim-ledger-v6.json";store=mutate(store,p,lambda d:d.__setitem__("source_review_cycle",5))
 r=report(store)
 if a.output:
  with a.output.open("xb") as f:f.write(canonical_bytes(r))
 print(json.dumps(r,sort_keys=True));return 0 if r["result"]=="PASS" else 1
if __name__=="__main__":raise SystemExit(main())
