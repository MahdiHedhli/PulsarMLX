#!/usr/bin/env python3
"""Recover concrete representative M1-F0 route values from retained authority.

This producer has no checkpoint path or provider.  It reuses the accepted
dual-decoder and fixed-order oracle implementations over the nine retained
packed payloads plus the four retained point authorities.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
from typing import Any

import numpy as np

from f017_representative_m1f0_executor import (
    InventoryEntry,
    RetainedSpec,
    canonical_json,
)
from f017_representative_m1f0_executor_v3 import (
    EagerDecoderRegistry,
    OpenRetainedAuthority,
    atomic_bytes,
    sha_file,
)
from prepare_f017_m1f0_real_reference import compose_oracle, strict_matvec


ROOT = Path(__file__).resolve().parents[2]
EXPECTED_EXECUTION_EVIDENCE_SHA256 = "dc53b458fe9c189b4cfbfd83889e7997aa5decba799c421944ac93edb237f190"
EXPECTED_SELECTED_IDS_SHA256 = "a0f2e2b59ebc606c43e17eab8f76a5b14c26b678bef2a9b0207c3f7dd15f164f"
EXPECTED_ROUTING_WEIGHTS_SHA256 = "ff1a7127b418b80dce4e4361e314c16ad50e86484cb1861ad27f6f9ee70b8587"
EXPECTED_ROUTE_SHA256 = "03dc2dfbed65848fdcb649f41f98793ca0f8cdd702c76b55d71c762fc5338103"
EXPECTED_RANKING_SHA256 = "b2de9d7a4fe2701f0cda51f6b95a5396195e0bf0c44924aa6d46b4a899af549d"
EXPECTED_REPRODUCTION_PRODUCER_SHA256 = "b17f1034688f2cf01243d04380151c1ad5c9f321d19a7bc29907a00a10993cc3"


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON_OBJECT_REQUIRED")
    return value


def canonical_stage_hashes(result: dict[str, Any]) -> dict[str, str]:
    stage_hashes = result["stage_hashes"]
    return {
        "input_hidden": stage_hashes["input_hidden"],
        "attention_normalized": stage_hashes["attention_normalized"],
        "query_rank": stage_hashes["query_rank"],
        "query_rank_normalized": stage_hashes["query_rank_normalized"],
        "query_heads": stage_hashes["query_heads"],
        "kv_raw": stage_hashes["kv_raw"],
        "kv_normalized": stage_hashes["kv_normalized"],
        "key_nope": stage_hashes["key_nope"],
        "attention_scores": stage_hashes["attention_scores"],
        "attention_weights": stage_hashes["attention_weights"],
        "value_heads": stage_hashes["value_heads"],
        "attention_output": stage_hashes["attention_output"],
        "post_attention_residual": stage_hashes["attention_residual"],
        "router_normalized": stage_hashes["router_normalized"],
        "router_logits": stage_hashes["router_logits"],
        "router_scores": result["router_scores_sha256"],
        "ranking": result["ranking_sha256"],
        "selected_ids": result["top8_ids_sha256"],
        "routing_weights": result["routing_weights_sha256"],
    }


def recover(
    execution_evidence_path: Path,
    candidate_path: Path,
    retention_root: Path,
    retained_paths: dict[str, Path],
) -> dict[str, Any]:
    if sha_file(execution_evidence_path) != EXPECTED_EXECUTION_EVIDENCE_SHA256:
        raise ValueError("EXECUTION_EVIDENCE_IDENTITY")
    execution = load_object(execution_evidence_path)
    if execution.get("disposition") != "COMPLETE":
        raise ValueError("EXECUTION_NOT_COMPLETE")
    if execution.get("access_accounting", {}).get("ledger_after") != 175:
        raise ValueError("LEDGER_IDENTITY")
    if execution.get("access_accounting", {}).get("checkpoint_rereads") != 0:
        raise ValueError("CHECKPOINT_REREAD")
    if execution.get("access_accounting", {}).get("expert_executions") != 0:
        raise ValueError("EXPERT_EXECUTION")

    reproduction_producer = ROOT / "scripts/research/f017_representative_m1f0_reproduce_from_retention_v1.py"
    if sha_file(reproduction_producer) != EXPECTED_REPRODUCTION_PRODUCER_SHA256:
        raise ValueError("REPRODUCTION_PRODUCER_IDENTITY")

    candidate = load_object(candidate_path)
    decoders = EagerDecoderRegistry().instantiate()
    decoded = {}
    decoded_identities: dict[str, str] = {}
    for item in candidate["attention_payload_inventory"]:
        entry = InventoryEntry(
            item["ordinal"], item["key"], item["offset"], item["packed_bytes"],
            item["quantization"], tuple(item["logical_shape"]), item["packed_sha256"],
            item["decoded_sha256"],
        )
        packed = retention_root / "packed" / f"{entry.ordinal:02d}.bin"
        if not packed.is_file() or sha_file(packed) != entry.packed_sha256:
            raise ValueError("RETAINED_PACKED_IDENTITY")
        pair = decoders[entry.quantization]
        first = pair.a.decode(packed, entry)
        second = pair.b.decode(packed, entry)
        if first.identity != second.identity or first.identity != entry.decoded_sha256:
            raise ValueError("DECODER_DISAGREEMENT")
        if first.canonical_bytes is None:
            raise ValueError("DECODED_BYTES_MISSING")
        if not np.isfinite(np.frombuffer(first.canonical_bytes, dtype="<f4")).all():
            raise ValueError("NONFINITE_DECODED")
        decoded[entry.key] = first
        decoded_identities[entry.key] = first.identity

    authorities: dict[str, OpenRetainedAuthority] = {}
    before = {role: sha_file(path) for role, path in retained_paths.items()}
    try:
        for item in candidate["retained_inputs"]:
            spec = RetainedSpec(
                item["role"], item["key"], item["sha256"], item["dtype"],
                tuple(item["shape"]), item["byte_length"], item.get("private_manifest_sha256"),
            )
            authorities[item["role"]] = OpenRetainedAuthority(retained_paths[item["role"]], spec)
        retained_arrays = {role: authority.array() for role, authority in authorities.items()}
        if not all(np.isfinite(value).all() for value in retained_arrays.values()):
            raise ValueError("NONFINITE_RETAINED")

        tensors: dict[str, np.ndarray] = {}
        for key, tensor in decoded.items():
            tensors[key] = np.frombuffer(tensor.canonical_bytes, dtype="<f4").reshape(tensor.shape)
        tensors["blk.3.ffn_norm.weight"] = retained_arrays["ffn_norm"]
        tensors["blk.3.ffn_gate_inp.weight"] = retained_arrays["router_matrix"]
        tensors["blk.3.exp_probs_b.bias"] = retained_arrays["correction_bias"]
        result = compose_oracle(
            retained_arrays["canonical_s0"],
            lambda name: tensors[name],
            lambda name, values: strict_matvec(tensors[name], values),
            lambda name, head, values: strict_matvec(tensors[name][head], values),
        )
        after = {role: authority.verify_after() for role, authority in authorities.items()}
    finally:
        for authority in authorities.values():
            authority.close()

    stages = canonical_stage_hashes(result)
    if stages != execution["stage_sha256"]:
        raise ValueError("STAGE_IDENTITY")
    selected_ids = [int(value) for value in result["top8_ids"]]
    weights = [float(value) for value in result["routing_weights"]]
    selected_bytes = struct.pack("<8H", *selected_ids)
    weight_bytes = b"".join(struct.pack("<d", value) for value in weights)
    if digest_bytes(selected_bytes) != EXPECTED_SELECTED_IDS_SHA256:
        raise ValueError("SELECTED_IDS_IDENTITY")
    if digest_bytes(weight_bytes) != EXPECTED_ROUTING_WEIGHTS_SHA256:
        raise ValueError("ROUTING_WEIGHTS_IDENTITY")
    if result["ranking_sha256"] != EXPECTED_RANKING_SHA256:
        raise ValueError("RANKING_IDENTITY")
    route_sha256 = digest_bytes(canonical_json({name: stages[name] for name in (
        "ranking", "selected_ids", "routing_weights",
    )}))
    if route_sha256 != EXPECTED_ROUTE_SHA256:
        raise ValueError("ROUTE_IDENTITY")
    if len(set(selected_ids)) != 8 or not all(math.isfinite(value) and value > 0 for value in weights):
        raise ValueError("ROUTE_VALUE_DOMAIN")
    if before != after:
        raise ValueError("RETAINED_AUTHORITY_MUTATION")

    route_pairs = []
    for ordinal, (expert_id, weight) in enumerate(zip(selected_ids, weights, strict=True)):
        route_pairs.append({
            "ordinal": ordinal,
            "expert_id": expert_id,
            "routing_weight": weight,
            "routing_weight_float_hex": weight.hex(),
            "routing_weight_ieee754_le_hex": struct.pack("<d", weight).hex(),
        })
    return {
        "schema": "pulsarmlx.f017.representative-m1f0-retained-route-value-recovery",
        "schema_version": "1.0.0",
        "source": "RETAINED_PAYLOADS_FROM_SINGLE_NINE_READ_REAL_EVENT",
        "execution_evidence_sha256": EXPECTED_EXECUTION_EVIDENCE_SHA256,
        "candidate_sha256": sha_file(candidate_path),
        "accepted_reproduction_producer_sha256": EXPECTED_REPRODUCTION_PRODUCER_SHA256,
        "accepted_oracle_source_sha256": sha_file(ROOT / "scripts/research/prepare_f017_m1f0_real_reference.py"),
        "producer_sha256": sha_file(Path(__file__).resolve()),
        "ledger": 175,
        "checkpoint_rereads": 0,
        "shard_opens": 0,
        "expert_executions": 0,
        "decoded_identities": decoded_identities,
        "retained_authority_before_sha256": before,
        "retained_authority_after_sha256": after,
        "selected_ids": selected_ids,
        "selected_ids_dtype": "uint16_le",
        "selected_ids_shape": [8],
        "selected_ids_bytes_hex": selected_bytes.hex(),
        "selected_ids_sha256": digest_bytes(selected_bytes),
        "routing_weights": weights,
        "routing_weights_dtype": "binary64_le",
        "routing_weights_shape": [8],
        "routing_weights_bytes_hex": weight_bytes.hex(),
        "routing_weights_sha256": digest_bytes(weight_bytes),
        "route_pairs": route_pairs,
        "ranking": {
            "concrete_values_required_for_expert_recovery": False,
            "dtype": "uint16_le",
            "shape": [256],
            "order": "descending router score; expert id ascending tie-break",
            "sha256": result["ranking_sha256"],
            "values_materialized": False,
        },
        "representative_route_sha256": route_sha256,
        "stage_sha256": stages,
        "direct_dprefix_route_used": False,
        "future_expert_recovery_input": "ID_KEYED_SELECTED_IDS_AND_ROUTING_WEIGHTS_IN_ROUTE_ORDER",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execution-evidence", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--retention-root", type=Path, required=True)
    parser.add_argument("--canonical-s0", type=Path, required=True)
    parser.add_argument("--ffn-norm", type=Path, required=True)
    parser.add_argument("--router-matrix", type=Path, required=True)
    parser.add_argument("--correction-bias", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = recover(args.execution_evidence, args.candidate, args.retention_root, {
        "canonical_s0": args.canonical_s0,
        "ffn_norm": args.ffn_norm,
        "router_matrix": args.router_matrix,
        "correction_bias": args.correction_bias,
    })
    atomic_bytes(args.output, canonical_json(result))
    print(json.dumps({
        "result": "EXACT_ROUTE_VALUES_RECOVERED",
        "output_sha256": sha_file(args.output),
        "selected_ids": result["selected_ids"],
        "routing_weights": result["routing_weights"],
        "representative_route_sha256": result["representative_route_sha256"],
        "checkpoint_rereads": 0,
        "shard_opens": 0,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
