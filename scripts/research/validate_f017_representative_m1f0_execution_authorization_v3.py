#!/usr/bin/env python3
"""Independent semantic validator for representative M1-F0 authorization v3."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
AUTH = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-m1f0-execution-authorization-v3.json"
EXPECTED_REVIEW = "5c6a128bc83541c809d0b049e8aad658cbefaf412d48fc9af28e21e37c5c2cf8"
EXPECTED_V1 = "e46874b05d2f5946f5b6c0dc9ac4beeb50628a2ebc28f16d0b8a2fc1284627dc"
EXPECTED_V2 = "459671f5ca4b111f0dc99cbb1958169d2a454321e93d8d156ecd573c3f51da99"
EXPECTED_FAILURE_COUNT = 29
EXPECTED_HEAD = "3df768b94b46e1d2881a88d598e8bd7fcb745072"
EXPECTED_BOUNDARY = "a9dc0d9effb3e52844203a34be587d12f0f7b011fb58d33c5dbdbe5b650deed3"
EXPECTED_GRAPH = "1585dad6b989fd0ac9b231f4e66e4d0129021868d027a3352a7b740707561558"
EXPECTED_EPSILON = "fc92b11223ee174b5f206a45a6d2b50540b4c82ba5d2c2333010947d525646e4"
EXPECTED_STAGE_NAMES = ["input_hidden","attention_normalized","query_rank","query_rank_normalized","query_heads","kv_raw","kv_normalized","key_nope","attention_scores","attention_weights","value_heads","attention_output","post_attention_residual","router_normalized","router_logits","router_scores","ranking","selected_ids","routing_weights"]
EXPECTED_INVENTORY = [
    (0,"blk.3.attn_norm.weight",2008634208,24576,"F32",[6144]),
    (1,"blk.3.attn_q_a.weight",2077864800,8650752,"Q5_K",[2048,6144]),
    (2,"blk.3.attn_q_a_norm.weight",2086515552,8192,"F32",[2048]),
    (3,"blk.3.attn_q_b.weight",2086523744,35651584,"Q8_0",[16384,2048]),
    (4,"blk.3.attn_kv_a_mqa.weight",2004872032,3760128,"Q8_0",[576,6144]),
    (5,"blk.3.attn_kv_a_norm.weight",2008632160,2048,"F32",[512]),
    (6,"blk.3.attn_k_b.weight",1998187360,6684672,"Q8_0",[64,512,192]),
    (7,"blk.3.attn_v_b.weight",2122175328,8912896,"Q8_0",[64,256,512]),
    (8,"blk.3.attn_output.weight",2008658784,69206016,"Q5_K",[6144,16384]),
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError("duplicate key " + key)
        result[key] = value
    return result


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicates)


def validate_document(wrapper: dict[str, Any], candidate: dict[str, Any], reuse: dict[str, Any],
                      preopen: dict[str, Any], reproduction: dict[str, Any], rehearsal: dict[str, Any],
                      review: dict[str, Any], stage: dict[str, Any], historical: dict[str, Any],
                      root: Path | None = None) -> list[str]:
    errors = []
    def req(value: bool, code: str) -> None:
        if not value: errors.append(code)

    req(wrapper.get("schema_version")=="3.0.0" and wrapper.get("status")=="PREPARED_REVIEW_REQUIRED","STATUS")
    req(wrapper.get("authoritative_repository")=={"branch":"feat/017-real-checkpoint-runner","preparation_base_commit":EXPECTED_HEAD},"AUTHORITATIVE_HEAD")
    req(candidate.get("schema_version")=="3.0.0" and candidate.get("status")=="PREPARED_REVIEW_REQUIRED","CANDIDATE_STATUS")
    req(candidate.get("authoritative_repository",{}).get("commit_sha256")==EXPECTED_HEAD,"CANDIDATE_HEAD")
    semantic=candidate.get("semantic_authority",{})
    req(semantic.get("representative_boundary_v3",{}).get("sha256")==EXPECTED_BOUNDARY,"BOUNDARY_HASH")
    req(semantic.get("semantic_graph_v2",{}).get("sha256")==EXPECTED_GRAPH,"SEMANTIC_GRAPH_HASH")
    req(semantic.get("epsilon_adjudication",{}).get("sha256")==EXPECTED_EPSILON,"EPSILON_AUTHORITY")
    req(review.get("verdict")=="REJECT" and wrapper.get("review_authority",{}).get("sha256")==EXPECTED_REVIEW,"REVIEW_AUTHORITY")
    req(candidate.get("review_authority",{}).get("sha256")==EXPECTED_REVIEW,"CANDIDATE_REVIEW")
    event_id=candidate.get("event",{}).get("event_id")
    req(reuse.get("consumer",{}).get("consumer_id")==event_id,"REUSE_CONSUMER_MISMATCH")
    req(reuse.get("consumer",{}).get("aliases")==[] and reuse.get("consumer",{}).get("implicit_scope_inheritance") is False,"REUSE_ALIASES")
    req(candidate.get("router_reuse_authorization",{}).get("consumer_id_must_equal_event_id") is True,"REUSE_GATE")
    req(all(item.get("checkpoint_fallback") is False for item in candidate.get("retained_inputs",[])),"RETAINED_FALLBACK")
    retained=candidate.get("retained_inputs",[])
    req(len(retained)==4 and retained[0].get("private_manifest_sha256")=="a68316207957bc8f804c167b627c208f068d086aed85506c89d87569b992bc60","S0_MANIFEST")

    req(reproduction.get("reproduction_runs")==10,"REPRODUCTION_COUNT")
    req(reproduction.get("required_stage_identity")=="10_OF_10_EXACT" and reproduction.get("required_route_identity")=="10_OF_10_EXACT","REPRODUCTION_IDENTITY")
    req(reproduction.get("checkpoint_rereads")==0 and reproduction.get("additional_shard_opens")==0,"REPRODUCTION_ACCESS")
    req(reproduction.get("minimum_fresh_processes",0)>=2,"REPRODUCTION_PROCESSES")
    req(reproduction.get("finite_checks_all_required_numeric_outputs") is True,"REPRODUCTION_FINITE")
    req(reproduction.get("retained_authority_rehash_before_after") is True and reproduction.get("s0_rehash_before_after") is True,"REPRODUCTION_REHASH")
    req(isinstance(reproduction.get("producer",{}).get("sha256"),str),"REPRODUCTION_PRODUCER")
    rr=rehearsal.get("reproduction",{})
    req(len(rr.get("runs",[]))==10 and rr.get("result")=="10_OF_10_EXACT_STAGE_AND_ROUTE","REHEARSAL_REPRODUCTION")
    req(rr.get("checkpoint_rereads")==0 and rr.get("additional_shard_opens")==0,"REHEARSAL_REPRO_ACCESS")
    req(rr.get("retained_authority_before_sha256")==rr.get("retained_authority_after_sha256"),"REHEARSAL_RETAINED_REHASH")
    req(rr.get("s0_before_sha256")==rr.get("s0_after_sha256"),"REHEARSAL_S0_REHASH")

    req(preopen.get("ordering")=="COMPLETE_BEFORE_ATTEMPT_START_SHARD_OPEN_ORDINAL0_OR_CHECKPOINT_READ","PREOPEN_ORDER")
    ledger_sources=preopen.get("ledger_authorities",[])
    req(len(ledger_sources)==2 and all(x.get("expected")==166 for x in ledger_sources),"LEDGER_AUTHORITY")
    req(preopen.get("retained_authorities",{}).get("rule")=="OPEN_ONCE_LSTAT_FSTAT_EXPECTED_EQUALS_BEFORE_CONSUME_SAME_DESCRIPTOR_BEFORE_EQUALS_AFTER","RETAINED_DESCRIPTOR")
    req(preopen.get("decoder_gate",{}).get("eager_import_before_shard_open") is True,"DECODER_EAGER_IMPORT")
    env=preopen.get("environment",{})
    req(env=={"implementation":"CPython","python_major_minor":[3,14],"numpy":"2.4.5","endianness":"little","threading_contract":"FIXED_ORDER_NO_BLAS_NO_PARALLEL_REDUCTION","reproduction_scope":"SAME_PINNED_PRODUCTION_ENVIRONMENT","cross_platform_libm_identity_claimed":False},"ENVIRONMENT_PIN")
    storage=preopen.get("storage",{})
    req(storage.get("required_free_bytes")==3221225472 and storage.get("method")=="CONSERVATIVE_FREE_SPACE_PRECONDITION","STORAGE_PREFLIGHT")
    req(preopen.get("shard",{}).get("opened_descriptor")=="FSTAT_MUST_EQUAL_PREFLIGHT_OBJECT_ID","SHARD_DESCRIPTOR")

    inventory=candidate.get("attention_payload_inventory",[])
    observed=[(x.get("ordinal"),x.get("key"),x.get("offset"),x.get("packed_bytes"),x.get("quantization"),x.get("logical_shape")) for x in inventory]
    req(observed==EXPECTED_INVENTORY,"INVENTORY")
    packed_anchor={x["symbolic_name"]:x["packed_sha256"] for x in historical.get("tensor_payloads",[])}
    decoded_anchor={x["symbolic_name"]:x["decoded_sha256"] for x in historical.get("decoded_tensors",[])}
    for item in inventory:
        key=item.get("key")
        req(item.get("packed_sha256")==packed_anchor.get(key),"PACKED_SHA:"+str(key))
        req(item.get("decoded_sha256")==decoded_anchor.get(key),"DECODED_SHA:"+str(key))
        if item.get("quantization")=="F32": req(item.get("packed_sha256")==item.get("decoded_sha256"),"F32_IDENTITY:"+str(key))
    req([x.get("name") for x in stage.get("stages",[])]==EXPECTED_STAGE_NAMES,"STAGE_VOCABULARY")
    rms=candidate.get("execution_semantics",{}).get("rmsnorm",{})
    req(rms=={"epsilon_source":"f32(1e-5)","epsilon_exact_decimal":"9.999999747378752e-6","epsilon_bits_hex":"0x3727c5ac","epsilon_dtype":"IEEE-754 binary32","accumulator_dtype":"IEEE-754 binary32"},"RMSNORM")

    read=candidate.get("read_contract",{})
    req(read.get("durably_retain_before_receipt") is True and read.get("durable_receipt_before_next_read") is True,"RETAIN_BEFORE_RECEIPT")
    req(read.get("expected_reads")==9 and read.get("expected_packed_bytes")==132900864 and read.get("maximum_shard_opens")==1,"READ_BUDGET")
    req(all(read.get(x) is False for x in ("fallback_reads","additional_reads","retries","dynamic_discovery")),"EXTRA_READS")
    req(candidate.get("ledger_contract",{}).get("authoritative_reconstruction_required") is True,"LEDGER_RECONSTRUCTION")
    req(candidate.get("ledger_contract",{}).get("partial_failure")=="TERMINAL_NO_RESUME_NO_RETRY_NO_SECOND_ATTEMPT","PARTIAL_FAILURE")
    req(isinstance(candidate.get("crash_terminalizer",{}).get("sha256"),str) and candidate.get("crash_terminalizer",{}).get("resume_authorized") is False,"CRASH_TERMINALIZER")

    req(rehearsal.get("failure_count")==EXPECTED_FAILURE_COUNT and rehearsal.get("exact_failure_count_required")==EXPECTED_FAILURE_COUNT,"FAILURE_COUNT")
    req(len(rehearsal.get("failure_rehearsals",{}))==EXPECTED_FAILURE_COUNT and rehearsal.get("all_failure_rehearsals_pass") is True,"FAILURE_RESULTS")
    required_cases={"retained_preflight_failure","decoder_import_failure","ledger_not_166","insufficient_storage","environment_mismatch","reuse_consumer_mismatch","receipt_before_retention","crash_after_retention_before_receipt","crash_after_receipt_before_journal","restart_terminalizer","direct_dprefix_gate","expert_execution"}
    req(required_cases <= set(rehearsal.get("failure_rehearsals",{})),"REHEARSAL_CASES")
    req(rehearsal.get("production_adapter_real_geometry",{}).get("canonical_names")=="19_OF_19","PRODUCTION_GEOMETRY")
    req(rehearsal.get("decoded_allocation_resource_footprint",{}).get("decoded_bytes")==660113408,"RESOURCE_FOOTPRINT")
    req(rehearsal.get("real_checkpoint_reads")==rehearsal.get("real_shard_opens")==0 and rehearsal.get("real_ledger_after")==166,"REAL_ACCESS")
    req(wrapper.get("authorization",{}).get("real_event_authorized") is False and candidate.get("authorization",{}).get("real_event_authorized") is False,"REAL_EVENT_AUTHORIZED")
    req(wrapper.get("authorization",{}).get("expert_execution_authorized") is False,"EXPERT_AUTHORIZED")
    req(candidate.get("surface_separation",{}).get("historical_direct_dprefix_outputs")=="PROHIBITED_AS_INPUT","DIRECT_DPREFIX")
    req(candidate.get("execution_semantics",{}).get("stop_boundary")=="AFTER_REPRESENTATIVE_ROUTE_BEFORE_ANY_ROUTED_OR_SHARED_EXPERT_EXECUTION","STOP_BOUNDARY")

    if root is not None:
        bindings=[(wrapper.get("authorization_candidate",{}),"CANDIDATE_FILE"),(wrapper.get("executor",{}),"EXECUTOR_FILE"),
                  (wrapper.get("release_wrapper",{}),"RELEASE_WRAPPER_FILE"),(wrapper.get("preopen_preflight",{}),"PREOPEN_FILE"),
                  (wrapper.get("crash_terminalizer",{}),"TERMINALIZER_FILE"),(wrapper.get("reproduction",{}),"REPRODUCTION_FILE"),
                  (wrapper.get("synthetic_rehearsal",{}),"REHEARSAL_FILE"),(wrapper.get("review_authority",{}),"REVIEW_FILE")]
        for binding,code in bindings:
            path=root/str(binding.get("path","")); req(path.is_file() and sha(path)==binding.get("sha256"),code)
        req(sha(root/"specs/017-rust-native-inference-runtime/contracts/f017-representative-m1f0-execution-authorization-v1.json")==EXPECTED_V1,"V1_IMMUTABILITY")
        req(sha(root/"specs/017-rust-native-inference-runtime/contracts/f017-representative-m1f0-execution-authorization-v2.json")==EXPECTED_V2,"V2_IMMUTABILITY")
        for source in ledger_sources:
            path=root/source["path"]; req(path.is_file() and sha(path)==source["sha256"],"LEDGER_SOURCE_FILE")
        for binding,code in ((candidate.get("stage_vocabulary",{}),"STAGE_FILE"),(candidate.get("historical_hash_anchor",{}),"HISTORICAL_FILE"),(candidate.get("router_reuse_authorization",{}),"REUSE_FILE")):
            path=root/str(binding.get("path","")); req(path.is_file() and sha(path)==binding.get("sha256"),code)
    return errors


def validate_paths(root: Path=ROOT, auth_path: Path=AUTH) -> list[str]:
    wrapper=load(auth_path); candidate=load(root/wrapper["authorization_candidate"]["path"])
    reuse=load(root/candidate["router_reuse_authorization"]["path"])
    preopen=load(root/candidate["preopen_preflight"]["path"])
    reproduction=load(root/candidate["reproduction_contract"]["path"])
    rehearsal=load(root/wrapper["synthetic_rehearsal"]["path"])
    review=load(root/wrapper["review_authority"]["path"])
    stage=load(root/candidate["stage_vocabulary"]["path"])
    historical=load(root/candidate["historical_hash_anchor"]["path"])
    return validate_document(wrapper,candidate,reuse,preopen,reproduction,rehearsal,review,stage,historical,root)


def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("--repository-root",type=Path,default=ROOT)
    parser.add_argument("--authorization",type=Path,default=AUTH); args=parser.parse_args()
    errors=validate_paths(args.repository_root.resolve(),args.authorization.resolve())
    print(json.dumps({"result":"FAIL" if errors else "PASS","errors":errors,"checkpoint_reads":0,"shard_opens":0,"ledger":166,"real_event_authorized":False},sort_keys=True))
    return 1 if errors else 0


if __name__=="__main__": raise SystemExit(main())
