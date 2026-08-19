#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
from f017_representative_expert_ledger_adapter_v1 import current_ledger
ROOT=Path(__file__).resolve().parents[2]
DEFAULT=ROOT/"specs/017-rust-native-inference-runtime/contracts/f017-representative-expert-recovery-single-use-release-v1.json"
AUTH=ROOT/"specs/017-rust-native-inference-runtime/contracts/f017-representative-expert-recovery-authorization-v1.json"
PAIR_IDS=[250,10,237,62,73,177,218,28]
PAIR_WEIGHTS=[0.7487501576296707,0.3348627106807668,0.23863270273063697,0.23688715675086147,0.2514906203405492,0.23059957299763345,0.22915341148588297,0.22962366738399842]
class ValidationError(RuntimeError): pass
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p): return json.loads(p.read_text())
def require(c,m):
    if not c: raise ValidationError(m)
def validate(root=ROOT, release=None):
    r=load(release or DEFAULT); a=load(root/AUTH.relative_to(ROOT))
    require(r.get("schema")=="pulsarmlx.f017.representative-expert-recovery-single-use-release","SCHEMA")
    require(r.get("schema_version")=="1.0.0" and r.get("status")=="PREPARED_FOR_INDEPENDENT_APPROVAL","STATUS")
    require(r.get("real_event_authorized") is False and r.get("approval_asserted") is False,"AUTH_GATE")
    b=r["bindings"]; expected={"authorization":sha(root/AUTH.relative_to(ROOT)),"independent_review":"df9b5192cc2df696657b8a8ed47f7417cf6f59aef601adacbd91191734e48142","executor":"7831568ffe451ba8b03827a90618514e682ec4a1170882b3bab4acab3d5452ec","rehearsal":"8d156da25f32c02de1ec8635edcb0ee0bc3be1baa5f72d5fd256697e39d1650f"}
    for k,v in expected.items(): require(b[k]["sha256"]==v and sha(root/b[k]["path"])==v,"BINDING_"+k)
    for k in ("release_wrapper","ledger_adapter","terminalizer"):
        require(sha(root/b[k]["path"])==b[k]["sha256"],"BINDING_"+k)
    require(r["representative_expert_input"]==a["representative_expert_input"],"INPUT")
    require(r["id_weight_pairs"]==a["route_pairs"],"PAIRS")
    require([x["expert_id"] for x in r["id_weight_pairs"]]==PAIR_IDS and [x["routing_weight"] for x in r["id_weight_pairs"]]==PAIR_WEIGHTS,"PAIR_ORDER")
    require(r["retained_payload_inventory"]==a["retained_payload_inventory"] and len(r["retained_payload_inventory"])==24,"INVENTORY")
    require(sum(x["packed_bytes"] for x in r["retained_payload_inventory"])==90439680,"PACKED_BYTES")
    require(r["access_accounting"]=={"starting_ledger":175,"terminal_ledger":175,"checkpoint_reads":0,"shard_opens":0,"new_checkpoint_bytes":0,"retained_payloads":24,"retained_packed_bytes":90439680},"ACCOUNTING")
    require(r["single_use"]=={"attempts":1,"concurrent_invocation":False,"consumed_at":"DURABLE_ATTEMPT_START_BEFORE_EXPERT_COMPUTATION","pre_attempt_failure_unconsumed_only_if_no_expert_computation_and_no_output_authority":True,"retry":False,"resume":False,"second_attempt":False,"interruption_reconciled_by_bound_terminalizer":True},"SINGLE_USE")
    require(r["output_contract"]==a["output_contract"] | {"aggregate_outputs":False,"output_sha256_banked_per_expert":True,"finite_checks_required":True,"input_before_after_identity_required":True},"OUTPUT")
    require(r["stop_boundary"]=="AFTER_EIGHT_INDIVIDUAL_REPRESENTATIVE_EXPERT_OUTPUTS_BEFORE_WEIGHTED_AGGREGATE","STOP")
    require(all(r["prohibitions"].values()) and set(r["prohibitions"])=={"checkpoint_access","shard_open","direct_dprefix_outputs","routed_aggregate","shared_expert","ffn_completion","s2_construction","gpu","retry","resume","second_attempt"},"PROHIBITIONS")
    require(r["preexecution_gates"]["ledger"]==175 and r["preexecution_gates"]["storage_free_bytes"]==3221225472 and r["preexecution_gates"]["all_locally_checkable_before_expert_computation"] is True,"PREFLIGHT")
    require(current_ledger(root)==175,"LEDGER_RUNTIME")
    return "REPRESENTATIVE_EXPERT_RELEASE_VALID"
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--release",type=Path,default=DEFAULT); a=ap.parse_args()
    try: print(validate(ROOT,a.release.resolve()))
    except Exception as e: print("INVALID",e); raise SystemExit(2)
if __name__=="__main__": main()
