#!/usr/bin/env python3
"""Generate deterministic checkpoint-free rehearsal evidence for repaired v2."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path

import numpy as np

from f017_representative_m1f0_validation_executor import (
    CANONICAL_STAGES, ExecutionError, RepresentativeExecutor, SyntheticComputationStage,
    SyntheticDecoderPair, SyntheticRetainedInputs, SyntheticShardProvider,
    canonical_json, canonicalize_oracle_output, sha_file,
)
from prepare_f017_m1f0_real_reference import synthetic_real_shaped_oracle


ROOT = Path(__file__).resolve().parents[2]
AUTH = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-m1f0-execution-authorization-v2.json"
EXECUTOR = ROOT / "scripts/research/f017_representative_m1f0_validation_executor.py"
VOCABULARY = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-m1f0-stage-vocabulary-v1.json"


def run(output: Path) -> dict:
    authorization = json.loads(AUTH.read_text())
    inventory = authorization["attention_payload_inventory"]
    cases: dict[str, object] = {}
    with tempfile.TemporaryDirectory() as directory:
        base = Path(directory)
        provider = SyntheticShardProvider(inventory)
        success = RepresentativeExecutor(authorization, provider, SyntheticDecoderPair(), SyntheticRetainedInputs(), SyntheticComputationStage(), base / "success", synthetic=True).execute()
        cases["success"] = success.__dict__
        cases["retention_implies_receipt_recoverability"] = all((base / "success" / "retained-packed" / f"{i:02d}.bin").is_file() for i in range(9))

        short_provider = SyntheticShardProvider(inventory, short_read=4)
        cases["short_read"] = RepresentativeExecutor(authorization, short_provider, SyntheticDecoderPair(), SyntheticRetainedInputs(), SyntheticComputationStage(), base / "short", synthetic=True).execute().__dict__
        disagreement_provider = SyntheticShardProvider(inventory)
        cases["decoder_disagreement"] = RepresentativeExecutor(authorization, disagreement_provider, SyntheticDecoderPair(2), SyntheticRetainedInputs(), SyntheticComputationStage(), base / "disagree", synthetic=True).execute().__dict__
        vocabulary_provider = SyntheticShardProvider(inventory)
        cases["wrong_vocabulary"] = RepresentativeExecutor(authorization, vocabulary_provider, SyntheticDecoderPair(), SyntheticRetainedInputs(), SyntheticComputationStage(True), base / "vocabulary", synthetic=True).execute().__dict__

        retained_provider = SyntheticShardProvider(inventory)
        try:
            RepresentativeExecutor(authorization, retained_provider, SyntheticDecoderPair(), SyntheticRetainedInputs(True), SyntheticComputationStage(), base / "retained", synthetic=True).execute()
        except ExecutionError as exc:
            cases["retained_preopen_failure"] = {"reason": exc.code, "opens": retained_provider.open_count, "reads": retained_provider.read_count}

    hidden = np.asarray([((index * 17) % 257 - 128) / 128.0 for index in range(6144)], dtype=np.float32)
    production_vocabulary = canonicalize_oracle_output(synthetic_real_shaped_oracle(hidden))
    cases["production_adapter_real_geometry"] = {"stage_count": len(production_vocabulary), "stage_names": sorted(production_vocabulary), "all_distinct": len(set(production_vocabulary.values())) == len(CANONICAL_STAGES)}
    evidence = {
        "schema":"pulsarmlx.f017.autonomous-loop-rehearsal","schema_version":"1.0.0","cycle":1,
        "authorization_id":authorization["authorization_id"],"executor_sha256":sha_file(EXECUTOR),
        "stage_vocabulary_sha256":sha_file(VOCABULARY),"synthetic":True,
        "real_geometry":{"reads":9,"packed_bytes":132900864,"decoded_element_count":165028352,"retained_router_bytes":6317056,"canonical_s0_bytes":24576},
        "cases":cases,"checkpoint_reads":0,"shard_opens":0,"real_ledger_delta":0,
        "result":"PASS" if cases["success"]["terminal"] == "COMPLETE" and cases["production_adapter_real_geometry"]["stage_count"] == 18 else "FAIL",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(canonical_json(evidence))
    return evidence


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    evidence=run(args.output)
    print(hashlib.sha256(canonical_json(evidence)).hexdigest())
    return 0 if evidence["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
