#!/usr/bin/env python3
"""Fail-closed validator for committed Q4K-REAL-1 evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


class EvidenceError(ValueError):
    pass


EXPECTED = {
    "attempt_id": "Q4K-REAL-1",
    "execution_config_sha256": "fddffb9359b2cac545afe969d90211f77ca5ef2547057949f75db118522d22da",
    "authorization_binding_sha256": "0a58ca7b1ba3b16c29e7f657b29f48cb9a6ffb4d65377d108a0b20df98dfb865",
    "authorization_amendment_sha256": "62bb1f429fc7c1b0acc2ed7cc88391491758a9e09f62d5745fc991c67e0e502c",
    "checkpoint_set_sha256": "d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee",
    "catalog_sha256": "0f0425106a240c5062acab9fc41b1b2651680c6ad06fe476214f88a8d2a177f0",
    "tensor_map_sha256": "ea0786f0e890af01dc111d355ef64aec1ca4898de5432197258bacccfaecc223",
    "format_contract_sha256": "bbdb296744910dbec5e95496d73df62b1e1b5cae4a9438b41de9962385399305",
    "decoder_sources": [
        ("A_scalar_reference", "1d285e58d5b5c55368191cccb881a56dc78560d7e2541e8d94b5217cd382548d"),
        ("B_spec_transcription", "cfac692461a8772bf7c0d1605b78ab88c43ac593c4431236453e0c8902f51501"),
        ("C_rust_matrix_reference", "c5a3114037a91dee63b5e0c2b7d1d1f2f3b045cb4441c2d5fc6e52b8677ed859"),
    ],
}


def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, child in pairs:
        if key in value:
            raise EvidenceError(f"duplicate key: {key}")
        value[key] = child
    return value


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(), object_pairs_hook=reject_duplicates)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceError(message)


def _validate_evidence_object(value: dict[str, Any]) -> str:
    require(value["schema"] == "pulsarmlx.f017.q4-k-real-byte-qualification-evidence", "schema")
    require(value["schema_version"] == "1.0.0", "schema version")
    attempt = value["attempt"]
    require(attempt["attempt_id"] == EXPECTED["attempt_id"], "attempt id")
    for field in ("authorized", "consumed", "executed", "checkpoint_accessed", "execution_start_recorded"):
        require(attempt[field] is True, f"attempt {field}")
    require(attempt["automatic_retry"] is False, "automatic retry")
    require(attempt["automatic_q6_continuation"] is False, "Q6 continuation")
    require(attempt["automatic_dense_prefix_continuation"] is False, "dense continuation")

    identity = value["identity"]
    require(identity["execution_head"] == "a84e9179dc0ad4b82a695cdbc07373a4311e4589", "execution head")
    for field in (
        "execution_config_sha256", "authorization_binding_sha256", "authorization_amendment_sha256",
        "checkpoint_set_sha256", "catalog_sha256", "tensor_map_sha256", "format_contract_sha256",
    ):
        require(identity[field] == EXPECTED[field], field)
    require(identity["tensor_name"] == "token_embd.weight", "tensor")
    require(identity["shard_ordinal"] == 2, "shard")
    require(identity["offset"] == 535316320, "offset")
    require(identity["packed_length"] == 535265280, "packed length")
    require(identity["gguf_shape"] == [6144, 154880], "shape")
    require(identity["quantization"] == "Q4_K", "quantization")
    require(len(identity["packed_sha256"]) == 64, "packed SHA")

    access = value["access"]
    require(access == {"shard_opens": 1, "positional_reads": 1, "tensor_payloads": 1, "packed_bytes": 535265280}, "access")
    outputs = value["decoder_outputs"]
    require(len(outputs) == 3, "decoder count")
    hashes = []
    for output, (name, source) in zip(outputs, EXPECTED["decoder_sources"], strict=True):
        require(output["name"] == name, "decoder name")
        require(output["source_sha256"] == source, "decoder source")
        require(output["element_count"] == 951582720, "decoded count")
        require(output["logical_shape"] == [154880, 6144], "decoded shape")
        require(output["dtype"] == "f32", "dtype")
        require(output["serialization"] == "canonical_little_endian_ieee754_binary32", "serialization")
        require(output["non_finite_count"] == 0, "non-finite")
        require(len(output["decoded_sha256"]) == 64, "decoded SHA")
        hashes.append(output["decoded_sha256"])
    derived_equal = len(set(hashes)) == 1
    require(value["comparison"]["bitwise_equal"] is derived_equal, "stored equality disagrees with hashes")
    require(value["comparison"]["signed_zero_policy"] == "PRESERVE_AND_COUNT_EXACT_F32_BITS", "signed zero policy")

    isolation = value["isolation"]
    require(isolation["model_compute"] == 0, "model compute")
    require(isolation["mlx_candidate_dispatches"] == 0, "MLX compute")
    require(isolation["additional_payloads"] == 0, "additional payload")
    require(isolation["q6_k_executed"] is False, "Q6 executed")
    require(isolation["dense_prefix_executed"] is False, "dense prefix executed")
    require(isolation["fallback"] is False, "fallback")
    require(value["ledger"] == {"before": 57, "actual_payloads": 1, "after": 58}, "ledger")

    if derived_equal:
        require(attempt["terminal_class"] == "EXACT_REAL_BYTE_QUALIFIED", "terminal class")
        require(value["verdict"] == "EXACT_REAL_BYTE_QUALIFIED", "verdict")
        require(value["comparison"]["first_divergence"] is None, "pass divergence")
        return "EXACT_REAL_BYTE_QUALIFIED"
    require(attempt["terminal_class"] == "DECODER_TRUTH_UNRESOLVED", "divergence class")
    require(value["verdict"] == "DECODER_TRUTH_UNRESOLVED", "divergence verdict")
    require(value["comparison"]["first_divergence"] is not None, "missing divergence")
    return "DECODER_TRUTH_UNRESOLVED"


def validate_evidence_object(value: dict[str, Any]) -> str:
    try:
        return _validate_evidence_object(value)
    except (KeyError, TypeError, IndexError) as error:
        raise EvidenceError(f"missing or malformed evidence field: {error}") from error


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    evidence = args.evidence.resolve(strict=True)
    status = validate_evidence_object(load_json(evidence))
    print(json.dumps({"status": status, "evidence_sha256": sha256(evidence)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
