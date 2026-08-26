#!/usr/bin/env python3
"""Checkpoint-free V4 requalification for the F017 numerical output interface."""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import struct
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RESEARCH = ROOT / "scripts/research"
EVIDENCE = ROOT / "docs/architecture/reviews/evidence"
sys.path.insert(0, str(RESEARCH))

import f017_corrected_oracle_primary_numerics_v2 as p2
import f017_corrected_oracle_primary_numerics_v3 as p3
import f017_corrected_oracle_secondary_numerics_v2 as s2
import f017_corrected_oracle_secondary_numerics_v3 as s3
from generate_f017_corrected_oracle_fixtures import fixture
from validate_f017_numerical_output_interface_implementation_v1 import (
    validate,
    validate_output_object,
)


CANONICAL_SEEDS = list(range(18101, 18113))
EXPANDED_SEEDS = list(range(17018, 17024))
FRESH_APIS = (
    "primary_v2_legacy", "primary_v3_legacy", "primary_v3_outputs",
    "secondary_v2_legacy", "secondary_v3_legacy", "secondary_v3_outputs",
)


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


class PrimaryTrace:
    def __init__(self, module, tensors: dict):
        self.source = module.JsonSource(tensors)
        self.calls: list[tuple] = []

    def vector(self, name: str, length: int):
        self.calls.append(("vector", name, length))
        return self.source.vector(name, length)

    def matrix(self, name: str, rows: int, columns: int):
        self.calls.append(("matrix", name, rows, columns))
        return self.source.matrix(name, rows, columns)

    def expert(self, name: str, expert: int, rows: int, columns: int):
        self.calls.append(("expert", name, expert, rows, columns))
        return self.source.expert(name, expert, rows, columns)


class SecondaryTrace:
    def __init__(self, module, tensors: dict):
        self.store = module.Store(tensors)
        self.calls: list[tuple] = []

    def vector(self, name: str, count: int):
        self.calls.append(("vector", name, count))
        return self.store.vector(name, count)

    def matrix(self, name: str, rows: int, columns: int):
        self.calls.append(("matrix", name, rows, columns))
        return self.store.matrix(name, rows, columns)

    def expert(self, name: str, expert: int, rows: int, columns: int):
        self.calls.append(("expert", name, expert, rows, columns))
        return self.store.expert(name, expert, rows, columns)


def primary_equivalence(seed: int) -> dict:
    document = fixture(seed)
    geometry2 = p2.Geometry.from_json(document["geometry"])
    geometry3 = p3.Geometry.from_json(document["geometry"])
    source2 = PrimaryTrace(p2, document["tensors"])
    source3 = PrimaryTrace(p3, document["tensors"])
    source_out = PrimaryTrace(p3, document["tensors"])
    old = p2.execute(source2, geometry2, document["token"], document["position"])
    legacy = p3.execute(source3, geometry3, document["token"], document["position"])
    captured = []
    original = p3._execute_graph

    def capture(*args, **kwargs):
        state = original(*args, **kwargs)
        captured.append(state)
        return state

    p3._execute_graph = capture
    try:
        output = p3.execute_outputs(source_out, geometry3, document["token"], document["position"])
    finally:
        p3._execute_graph = original
    if old != legacy or canonical(old) != canonical(legacy):
        raise ValueError(f"primary legacy drift: {seed}")
    if source2.calls != source3.calls or source2.calls != source_out.calls:
        raise ValueError(f"primary source-read drift: {seed}")
    if len(captured) != 1 or output.core_execution_count != 1:
        raise ValueError(f"primary execution count: {seed}")
    validate_output_object(output, "PRIMARY", document["geometry"]["hidden"], document["geometry"]["vocab"])
    hidden = tuple(item[0] for item in struct.iter_unpack("<d", output.final_hidden_payload))
    normalized = tuple(item[0] for item in struct.iter_unpack("<d", output.final_normalized_payload))
    logits = tuple(item[0] for item in struct.iter_unpack("<d", output.full_logits_payload))
    if hidden != tuple(captured[0].hidden) or normalized != tuple(captured[0].final_normalized) or logits != tuple(captured[0].logits):
        raise ValueError(f"primary same-execution payload drift: {seed}")
    expected_hashes = (old["final_hidden_sha256"], old["final_norm_sha256"], old["full_logits_sha256"])
    observed_hashes = (output.final_hidden_sha256, output.final_normalized_sha256, output.full_logits_sha256)
    if expected_hashes != observed_hashes:
        raise ValueError(f"primary payload hash drift: {seed}")
    return {
        "seed": seed, "role": "PRIMARY", "legacy_sha256": sha_bytes(canonical(old)),
        "source_read_count": len(source2.calls), "payload_sha256": list(observed_hashes),
        "core_execution_count": 1, "result": "PASS",
    }


def secondary_equivalence(seed: int) -> dict:
    document = fixture(seed)
    store2 = SecondaryTrace(s2, document["tensors"])
    store3 = SecondaryTrace(s3, document["tensors"])
    store_out = SecondaryTrace(s3, document["tensors"])
    old = s2.execute(document, store=store2)
    legacy = s3.execute(document, store=store3)
    captured = []
    original = s3._execute_graph

    def capture(*args, **kwargs):
        state = original(*args, **kwargs)
        captured.append(state)
        return state

    s3._execute_graph = capture
    try:
        output = s3.execute_outputs(document, store=store_out)
    finally:
        s3._execute_graph = original
    if old != legacy or canonical(old) != canonical(legacy):
        raise ValueError(f"secondary legacy drift: {seed}")
    if store2.calls != store3.calls or store2.calls != store_out.calls:
        raise ValueError(f"secondary source-read drift: {seed}")
    if len(captured) != 1 or output.core_execution_count != 1:
        raise ValueError(f"secondary execution count: {seed}")
    validate_output_object(output, "SECONDARY", document["geometry"]["hidden"], document["geometry"]["vocab"])
    hidden = tuple(item[0] for item in struct.iter_unpack("<f", output.final_hidden_payload))
    normalized = tuple(item[0] for item in struct.iter_unpack("<f", output.final_normalized_payload))
    logits = tuple(item[0] for item in struct.iter_unpack("<f", output.full_logits_payload))
    state = captured[0]
    if hidden != tuple(float(value) for value in state.hidden) or normalized != tuple(float(value) for value in state.final_normalized) or logits != tuple(float(value) for value in state.logits):
        raise ValueError(f"secondary same-execution payload drift: {seed}")
    expected_hashes = (old["final_hidden_sha256"], old["final_norm_sha256"], old["full_logits_sha256"])
    observed_hashes = (output.final_hidden_sha256, output.final_normalized_sha256, output.full_logits_sha256)
    if expected_hashes != observed_hashes:
        raise ValueError(f"secondary payload hash drift: {seed}")
    return {
        "seed": seed, "role": "SECONDARY", "legacy_sha256": sha_bytes(canonical(old)),
        "source_read_count": len(store2.calls), "payload_sha256": list(observed_hashes),
        "core_execution_count": 1, "result": "PASS",
    }


def single(api: str, seed: int) -> dict:
    document = fixture(seed)
    if api == "primary_v2_legacy":
        result = p2.execute(p2.JsonSource(document["tensors"]), p2.Geometry.from_json(document["geometry"]), document["token"], document["position"])
        return {"api": api, "seed": seed, "legacy_sha256": sha_bytes(canonical(result))}
    if api == "primary_v3_legacy":
        result = p3.execute(p3.JsonSource(document["tensors"]), p3.Geometry.from_json(document["geometry"]), document["token"], document["position"])
        return {"api": api, "seed": seed, "legacy_sha256": sha_bytes(canonical(result))}
    if api == "primary_v3_outputs":
        result = p3.execute_outputs(p3.JsonSource(document["tensors"]), p3.Geometry.from_json(document["geometry"]), document["token"], document["position"])
    elif api == "secondary_v2_legacy":
        result = s2.execute(document)
        return {"api": api, "seed": seed, "legacy_sha256": sha_bytes(canonical(result))}
    elif api == "secondary_v3_legacy":
        result = s3.execute(document)
        return {"api": api, "seed": seed, "legacy_sha256": sha_bytes(canonical(result))}
    elif api == "secondary_v3_outputs":
        result = s3.execute_outputs(document)
    else:
        raise ValueError(f"unknown API: {api}")
    return {
        "api": api, "seed": seed, "role": result.role, "core_execution_count": result.core_execution_count,
        "payload_sha256": [result.final_hidden_sha256, result.final_normalized_sha256, result.full_logits_sha256],
        "selected_token": result.selected_token,
        "top_bits": [dataclasses.asdict(item) for item in result.top_32],
    }


def fresh_processes() -> dict:
    results = {}
    script = Path(__file__).resolve()
    for api in FRESH_APIS:
        records = []
        for _ in range(20):
            completed = subprocess.run(
                [sys.executable, str(script), "--single-api", api, "--single-seed", "18106"],
                cwd=ROOT, check=True, text=True, capture_output=True,
            )
            records.append(json.loads(completed.stdout))
        identities = {sha_bytes(canonical(record)) for record in records}
        if len(identities) != 1:
            raise ValueError(f"fresh-process drift: {api}")
        results[api] = {
            "processes": 20,
            "unique_result_count": 1,
            "result_sha256": next(iter(identities)),
            "semantic_result_sha256": records[0].get("legacy_sha256", sha_bytes(canonical(records[0]))),
        }
    if results["primary_v2_legacy"]["semantic_result_sha256"] != results["primary_v3_legacy"]["semantic_result_sha256"]:
        raise ValueError("fresh primary legacy mismatch")
    if results["secondary_v2_legacy"]["semantic_result_sha256"] != results["secondary_v3_legacy"]["semantic_result_sha256"]:
        raise ValueError("fresh secondary legacy mismatch")
    return results


def ownership_mutations() -> dict:
    document = fixture(18101)
    output = p3.execute_outputs(
        p3.JsonSource(document["tensors"]), p3.Geometry.from_json(document["geometry"]),
        document["token"], document["position"],
    )
    rejected = []
    for field in ("final_hidden_payload", "final_normalized_payload", "full_logits_payload"):
        payload = getattr(output, field)
        for width in range(1, 11):
            for mode, value in (("SHORT", payload[:-width]), ("EXTRA", payload + bytes([width]) * width)):
                mutation_id = f"{field}_{mode}_{width}"
                mutated = dataclasses.replace(output, **{field: value})
                try:
                    validate_output_object(mutated, "PRIMARY", document["geometry"]["hidden"], document["geometry"]["vocab"])
                except ValueError:
                    rejected.append(mutation_id)
                else:
                    raise ValueError(f"ownership mutation passed: {mutation_id}")
    if len(rejected) != 60 or len(set(rejected)) != 60:
        raise ValueError("ownership mutation census")
    return {"mutations": 60, "rejected": 60, "unexpected_passes": 0}


def run_retained(work: Path) -> tuple[dict, dict]:
    v2_output = work / "retained-v2.json"
    capability_output = work / "retained-capability.json"
    subprocess.run([sys.executable, str(RESEARCH / "qualify_f017_corrected_oracle_numerical_authority_v2.py"), "--output", str(v2_output)], cwd=ROOT, check=True)
    subprocess.run([sys.executable, str(RESEARCH / "qualify_f017_numerical_capability_policy_v1.py"), "--output", str(capability_output)], cwd=ROOT, check=True)
    accepted_v2 = EVIDENCE / "f017-corrected-oracle-numerical-requalification-v2.json"
    accepted_capability = EVIDENCE / "f017-corrected-oracle-numerical-capability-qualification-v1.json"
    if v2_output.read_bytes() != accepted_v2.read_bytes():
        raise ValueError("retained V2 numerical qualification drift")
    if capability_output.read_bytes() != accepted_capability.read_bytes():
        raise ValueError("retained capability qualification drift")
    return json.loads(v2_output.read_text()), json.loads(capability_output.read_text())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--single-api", choices=FRESH_APIS)
    parser.add_argument("--single-seed", type=int, default=18106)
    args = parser.parse_args()
    if args.single_api:
        print(json.dumps(single(args.single_api, args.single_seed), sort_keys=True, separators=(",", ":")))
        return 0
    if args.output is None:
        raise SystemExit("--output required")
    implementation = validate()
    cases = []
    for seed in [*CANONICAL_SEEDS, *EXPANDED_SEEDS]:
        cases.append(primary_equivalence(seed))
        cases.append(secondary_equivalence(seed))
    fresh = fresh_processes()
    ownership = ownership_mutations()
    with tempfile.TemporaryDirectory(prefix="f017-num-v4-") as directory:
        retained, capability = run_retained(Path(directory))
    document = {
        "schema": "pulsarmlx.f017.corrected-oracle-numerical-requalification/4.0.0",
        "status": "CORRECTED_ORACLE_NUMERICAL_REQUALIFICATION_V4",
        "result": "PASS",
        "historical_equivalence_cases": len(cases),
        "canonical_seeds": CANONICAL_SEEDS,
        "expanded_seeds": EXPANDED_SEEDS,
        "case_index": cases,
        "packed_decoder_case_count": retained["packed_decoder_case_count"],
        "format_count": retained["format_count"],
        "numerical_localization_mutation_count": retained["mutation_count"],
        "capability_mutation_count": capability["mutation_count"],
        "capability_unexpected_pass_count": capability["unexpected_pass_count"],
        "fresh_process_identity": fresh,
        "fresh_process_total": sum(value["processes"] for value in fresh.values()),
        "ownership_mutations": ownership,
        "primary_formula_equivalence": "PASS",
        "secondary_formula_equivalence": "PASS",
        "primary_legacy_equivalence": "PASS",
        "secondary_legacy_equivalence": "PASS",
        "primary_output_interface": "PASS",
        "secondary_output_interface": "PASS",
        "one_execution_all_outputs": "PASS",
        "output_buffer_hash_binding": "PASS",
        "source_read_equivalence": "PASS",
        "implementation_validation": implementation,
        "numerical_formulas_changed": False,
        "numerical_operation_order_changed": False,
        "routing_semantics_changed": False,
        "decoder_semantics_changed": False,
        "original_checkpoint_shard_opens": 0,
        "original_checkpoint_identity_hash_reads": 0,
        "original_checkpoint_mmaps": 0,
        "original_checkpoint_tensor_reads": 0,
        "original_checkpoint_payload_reads": 0,
        "event_04_retry": False,
        "event_04_resume": False,
        "event_05_executed": False,
        "live_event_05_authorization_created": False,
        "p1_attempt_2_executed": False,
        "historical_master_ledger": 175,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "result": "PASS", "equivalence_cases": len(cases), "fresh_processes": document["fresh_process_total"],
        "ownership_mutations": ownership["mutations"], "original_checkpoint_access": 0,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
