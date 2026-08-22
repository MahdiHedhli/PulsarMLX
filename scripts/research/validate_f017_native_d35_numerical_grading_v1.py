#!/usr/bin/env python3
"""Validate the banked D3.5 numerical result without rereading retained payloads."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
RESULT=ROOT/"docs/architecture/reviews/evidence/f017-native-d3-5-numerical-grading-result-v1.json"
TERMINAL=ROOT/"docs/architecture/reviews/evidence/f017-native-d3-5-numerical-grading-terminal-v1.json"
GRANT=ROOT/"specs/017-rust-native-inference-runtime/contracts/f017-native-d3-5-comparison-read-grant-v1.json"
D0_V1=ROOT/"specs/017-rust-native-inference-runtime/contracts/f017-native-bounded-p1-numeric-acceptance-contract-v1.json"
D0_V2=ROOT/"specs/017-rust-native-inference-runtime/contracts/f017-native-bounded-p1-numeric-acceptance-contract-v2.json"

def no_duplicates(pairs):
    result={}
    for key,value in pairs:
        if key in result: raise ValueError(f"duplicate key: {key}")
        result[key]=value
    return result

def load(path): return json.loads(Path(path).read_text(),object_pairs_hook=no_duplicates)
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def restored_result_sha(path):
    data=Path(path).read_bytes().replace(b"${HOME}/",(str(Path.home())+"/").encode())
    return hashlib.sha256(data).hexdigest()

def validate(result_path=RESULT,terminal_path=TERMINAL):
    result=load(result_path); terminal=load(terminal_path); grant=load(GRANT); d0=load(D0_V1); overlay=load(D0_V2)
    if sha(GRANT)!="340e91aa3f00c91b0275c052307dba1ab0ebef091b3e07f99e4121a4bc1c788f": raise ValueError("grant SHA")
    if sha(D0_V2)!="cc62cdc7550e3a25f55de783e9eb7c68f6cf03d0eafb944a86dc8a2a60007fb9": raise ValueError("D0 SHA")
    if set(result)!={"schema","grant_sha256","d0_sha256","d3_5_evidence_sha256","existing_captures_reused","native_execution_performed","original_checkpoint_reads","historical_payload_ledger_delta","read_receipt_count","read_receipts","stage_metrics","required_ordinal_count","retained_qualification","pass"}: raise ValueError("result key census")
    if set(terminal)!={"schema","event_id","attempt_id","state","result_sha256","receipt_count","original_checkpoint_reads","historical_payload_ledger_delta"}: raise ValueError("terminal key census")
    if result["grant_sha256"]!=sha(GRANT) or result["d0_sha256"]!=sha(D0_V2) or result["d3_5_evidence_sha256"]!="13b1a3a653cf0325f59b0b3b035b7804439a19c000ef8ddf19dad9ecb8316ac8": raise ValueError("authority binding")
    if not result["existing_captures_reused"] or result["native_execution_performed"] or result["original_checkpoint_reads"]!=0 or result["historical_payload_ledger_delta"]!=0: raise ValueError("execution/accounting")
    if result["retained_qualification"]!="MIXED_D0_V2_CLASS/PASS" or result["pass"] is not True: raise ValueError("result verdict")
    reads=grant["expected_reads"]+grant["operand_reads"]+grant["capture_reads"]
    receipts=result["read_receipts"]
    if len(reads)!=89 or result["read_receipt_count"]!=89 or len(receipts)!=89: raise ValueError("receipt census")
    receipt_keys={"ordinal","role","path","expected_sha256","before_sha256","consumed_sha256","after_sha256","byte_count","descriptor_device","descriptor_inode","original_checkpoint_read","original_checkpoint_shard_open"}
    for ordinal,(row,receipt) in enumerate(zip(reads,receipts)):
        if set(receipt)!=receipt_keys or receipt["ordinal"]!=ordinal or receipt["role"]!=row["role"] or receipt["path"]!=row["path"]: raise ValueError("receipt identity")
        if {receipt[key] for key in ["expected_sha256","before_sha256","consumed_sha256","after_sha256"]}!={row["sha256"]}: raise ValueError("EXPECTED/BEFORE/CONSUMED/AFTER")
        if receipt["byte_count"]!=row["byte_count"] or receipt["descriptor_device"]<=0 or receipt["descriptor_inode"]<=0 or receipt["original_checkpoint_read"] or receipt["original_checkpoint_shard_open"]: raise ValueError("receipt accounting")
    effective={row["ordinal"]:row for row in d0["stage_rows"]}
    for override in overlay["stage_overrides"]: effective[override["ordinal"]]=override
    metrics=result["stage_metrics"]
    if len(metrics)!=34 or [row["ordinal"] for row in metrics]!=list(range(34)): raise ValueError("stage census")
    metric_keys={"ordinal","stage_id","class","oracle","metric","max_abs_error","rmse","cosine_similarity","max_per_coordinate_cap","structural_pass","numeric_pass","result"}
    for row in metrics:
        frozen=effective[row["ordinal"]]
        if set(row)!=metric_keys or (row["stage_id"],row["class"],row["oracle"],row["metric"])!=(frozen["id"],frozen["class"],frozen["oracle"],frozen["metric"]): raise ValueError("D0 stage binding")
        if row["structural_pass"] is not True or row["numeric_pass"] is not True or row["result"] in {"FAILED_CONTRACT","FAILED_FROZEN_CONTRACT"}: raise ValueError("stage failure")
        for key in ["max_abs_error","rmse","cosine_similarity","max_per_coordinate_cap"]:
            if row[key] is not None and (isinstance(row[key],bool) or not isinstance(row[key],(int,float)) or not math.isfinite(row[key])): raise ValueError("metric type/nonfinite")
        if row["metric"]=="operand_conditioned_matvec" and (row["max_per_coordinate_cap"] is None or row["max_abs_error"]>row["max_per_coordinate_cap"]): raise ValueError("OCB bound")
    required={ordinal for ordinal,row in effective.items() if row["class"]!="IMPLEMENTATION_SPECIFIC_REPRODUCIBILITY"}
    if result["required_ordinal_count"]!=len(required) or len(required)!=15: raise ValueError("required census")
    if terminal["schema"]!="pulsarmlx.f017.native-d3-5-grading-terminal/1.0.0" or terminal["state"]!="COMPLETE" or terminal["result_sha256"]!=restored_result_sha(result_path) or terminal["receipt_count"]!=89 or terminal["original_checkpoint_reads"]!=0 or terminal["historical_payload_ledger_delta"]!=0: raise ValueError("terminal")
    return {"result":"PASS","normalized_result_sha256":sha(result_path),"restored_machine_result_sha256":restored_result_sha(result_path),"terminal_sha256":sha(terminal_path),"stage_count":34,"receipt_count":89,"original_checkpoint_reads":0,"historical_payload_ledger_delta":0}

def main():
    parser=argparse.ArgumentParser(); parser.add_argument("result",nargs="?",type=Path,default=RESULT); parser.add_argument("--terminal",type=Path,default=TERMINAL); args=parser.parse_args()
    print(json.dumps(validate(args.result,args.terminal),sort_keys=True))

if __name__=="__main__": main()
