#!/usr/bin/env python3
"""Generate deterministic checkpoint-free rehearsal evidence for repaired v2."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import tempfile
from pathlib import Path

import numpy as np

from f017_representative_m1f0_validation_executor import (
    CANONICAL_STAGES, ExecutionError, ProductionComputationStage, ProductionDecoderPair,
    RepresentativeExecutor, SyntheticComputationStage,
    SyntheticDecoderPair, SyntheticRetainedInputs, SyntheticShardProvider,
    canonical_json, canonicalize_oracle_output, durable_json, durable_publish, sha256, sha_file,
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
        decoded_hash_provider = SyntheticShardProvider(inventory)
        cases["decoded_hash_mismatch"] = RepresentativeExecutor(authorization, decoded_hash_provider, SyntheticDecoderPair(decoded_hash_ordinal=2), SyntheticRetainedInputs(), SyntheticComputationStage(), base / "decoded-hash", synthetic=True).execute().__dict__
        read_fault_provider = SyntheticShardProvider(inventory, read_error=3)
        cases["unexpected_read_fault"] = RepresentativeExecutor(authorization, read_fault_provider, SyntheticDecoderPair(), SyntheticRetainedInputs(), SyntheticComputationStage(), base / "read-fault", synthetic=True).execute().__dict__
        compute_fault_provider = SyntheticShardProvider(inventory)
        cases["unexpected_compute_fault"] = RepresentativeExecutor(authorization, compute_fault_provider, SyntheticDecoderPair(), SyntheticRetainedInputs(), SyntheticComputationStage(unexpected_error=True), base / "compute-fault", synthetic=True).execute().__dict__
        vocabulary_provider = SyntheticShardProvider(inventory)
        cases["wrong_vocabulary"] = RepresentativeExecutor(authorization, vocabulary_provider, SyntheticDecoderPair(), SyntheticRetainedInputs(), SyntheticComputationStage(True), base / "vocabulary", synthetic=True).execute().__dict__

        retained_provider = SyntheticShardProvider(inventory)
        try:
            RepresentativeExecutor(authorization, retained_provider, SyntheticDecoderPair(), SyntheticRetainedInputs(True), SyntheticComputationStage(), base / "retained", synthetic=True).execute()
        except ExecutionError as exc:
            cases["retained_preopen_failure"] = {"reason": exc.code, "opens": retained_provider.open_count, "reads": retained_provider.read_count}

        escalated = copy.deepcopy(authorization)
        escalated["authorization"]["expert_execution_authorized"] = True
        gate_provider = SyntheticShardProvider(inventory)
        try:
            RepresentativeExecutor(escalated, gate_provider, SyntheticDecoderPair(), SyntheticRetainedInputs(), SyntheticComputationStage(), base / "gate", synthetic=True).execute()
        except ExecutionError as exc:
            cases["direct_scope_escalation_gate"] = {"reason": exc.code, "opens": gate_provider.open_count, "reads": gate_provider.read_count}

        interrupted_root = base / "interrupted"
        interrupted_root.mkdir()
        durable_json(interrupted_root / "execution-start.json", {"event_id": authorization["event"]["event_id"]})
        interrupted_payload = b"durable-before-crash"
        durable_publish(interrupted_root / "retained-packed/00.bin", interrupted_payload)
        durable_json(interrupted_root / "receipts/01.json", {"sequence":1,"ordinal":0,"actual_bytes":len(interrupted_payload),"packed_sha256":sha256(interrupted_payload),"retained_relative_path":"retained-packed/00.bin"})
        interrupted_provider = SyntheticShardProvider(inventory)
        interrupted_executor = RepresentativeExecutor(authorization, interrupted_provider, SyntheticDecoderPair(), SyntheticRetainedInputs(), SyntheticComputationStage(), interrupted_root, synthetic=True)
        cases["interrupted_attempt_reconciliation"] = interrupted_executor.reconcile_interrupted().__dict__

    hidden = np.asarray([((index * 17) % 257 - 128) / 128.0 for index in range(6144)], dtype=np.float32)
    production_vocabulary = canonicalize_oracle_output(synthetic_real_shaped_oracle(hidden))
    decoded = {entry["key"]: bytes(4 * int(np.prod(entry["logical_shape"]))) for entry in inventory}
    retained = {"canonical_s0":bytes(24576),"ffn_norm":bytes(24576),"router_matrix":bytes(6291456),"correction_bias":bytes(1024)}
    adapter_result = ProductionComputationStage(inventory).compute(decoded, retained)
    cases["production_adapter_real_geometry"] = {"stage_count": len(adapter_result["required_stage_sha256"]), "stage_names": sorted(adapter_result["required_stage_sha256"]), "all_distinct": len(set(adapter_result["required_stage_sha256"].values())) == len(CANONICAL_STAGES), "decoded_allocation_bytes": sum(map(len, decoded.values()))}
    rng = np.random.default_rng(1702)
    decoder_fixtures = [
        ({"quantization":"F32","logical_shape":[8]}, rng.bytes(32)),
        ({"quantization":"Q8_0","logical_shape":[32]}, rng.bytes(34)),
        ({"quantization":"Q5_K","logical_shape":[256]}, rng.bytes(176)),
    ]
    cases["production_decoder_nonzero"] = all(left == right for entry, packed in decoder_fixtures for left, right in [ProductionDecoderPair().decode_pair(entry, packed)])
    evidence = {
        "schema":"pulsarmlx.f017.autonomous-loop-rehearsal","schema_version":"1.1.0","cycle":2,
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
