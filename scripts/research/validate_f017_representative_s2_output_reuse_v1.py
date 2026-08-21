#!/usr/bin/env python3
from __future__ import annotations
import argparse, json
from pathlib import Path
import sys
from f017_representative_expert_ledger_adapter_v1 import current_ledger
from f017_representative_s2_output_reuse_v1 import AUTH, EVIDENCE_PATH, EVIDENCE_SHA, ROOT, load, resolve, sha256_path, validate_authorization, validate_evidence

def validate(path: Path, check_retained: bool = False) -> dict[str, object]:
    document=load(path); validate_authorization(document)
    evidence_path=ROOT/EVIDENCE_PATH
    if sha256_path(evidence_path)!=EVIDENCE_SHA: raise ValueError("EXECUTION_EVIDENCE_SHA")
    validate_evidence(load(evidence_path))
    if current_ledger()!=175: raise ValueError("LEDGER")
    retained=resolve(path) if check_retained else None
    return {"result":"REPRESENTATIVE_S2_OUTPUT_REUSE_AUTHORIZATION_VALID","ledger":175,"checkpoint_reads":0,"shard_opens":0,"new_numerical_events":0,"retained_preflight":retained["result"] if retained else "NOT_REQUESTED"}

if __name__ == "__main__":
    parser=argparse.ArgumentParser(); parser.add_argument("--authorization",type=Path,default=AUTH); parser.add_argument("--check-retained",action="store_true"); args=parser.parse_args()
    try: print(json.dumps(validate(args.authorization,args.check_retained),sort_keys=True))
    except Exception as error: print(json.dumps({"result":"REJECT","error":str(error)},sort_keys=True),file=sys.stderr); raise SystemExit(1)
