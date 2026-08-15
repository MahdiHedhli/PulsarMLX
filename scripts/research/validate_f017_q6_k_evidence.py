#!/usr/bin/env python3
"""Fail-closed validator for Q6K-REAL-1 terminal evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


class EvidenceError(ValueError):
    pass


EXPECTED = {
    "attempt_id": "Q6K-REAL-1",
    "execution_head": "44d6ecfe188774f4dc420f02083f1c7cc072d58e",
    "execution_config_sha256": "215af50497a097f4738df8d75a45ebab86450dc2dbe0fcc5e034fe06b1436dd0",
    "authorization_binding_sha256": "8160be060db46ab9c0e74480d9ad5450a4ac8dd28d26397a1d1b7911aea5cd91",
    "handoff_v3_sha256": "6430e70980dceeff48515a2f212fddcee495d2fabfc1ecb5c5ad578a64a5d6c2",
    "format_contract_sha256": "9e5d15d87b88b9754a5f4b546a110dc1c0659e2c6f62683e12401b8bffb6ff95",
    "defect_evidence_sha256": "b6bf1f3f1ea751250bdeedd79beacfebd5da09e98a1540b3e866de283286e8ba",
    "corrected_decoder_sha256": "1d285e58d5b5c55368191cccb881a56dc78560d7e2541e8d94b5217cd382548d",
    "checkpoint_set_sha256": "d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee",
    "catalog_sha256": "0f0425106a240c5062acab9fc41b1b2651680c6ad06fe476214f88a8d2a177f0",
    "tensor_map_sha256": "ea0786f0e890af01dc111d355ef64aec1ca4898de5432197258bacccfaecc223",
    "decoder_sources": [
        ("A_corrected_python_grouped", "1d285e58d5b5c55368191cccb881a56dc78560d7e2541e8d94b5217cd382548d"),
        ("B_python_index_driven_spec", "cfac692461a8772bf7c0d1605b78ab88c43ac593c4431236453e0c8902f51501"),
        ("C_rust_reference", "a4d308ef1aa874865e668002a8911d8247247dd490e301018f730aeb06ab35fd"),
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


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceError(message)


def _validate(value: dict[str, Any]) -> str:
    require(value["schema"] == "pulsarmlx.f017.q6-k-real-byte-qualification-evidence", "schema")
    require(value["schema_version"] == "1.0.0", "schema version")
    attempt = value["attempt"]
    require(attempt["attempt_id"] == EXPECTED["attempt_id"], "attempt id")
    for field in ("authorized", "consumed", "executed", "checkpoint_accessed", "execution_start_recorded"):
        require(attempt[field] is True, f"attempt {field}")
    require(attempt["automatic_retry"] is False, "automatic retry")
    require(attempt["automatic_dense_prefix_continuation"] is False, "dense continuation")

    identity = value["identity"]
    for field in (
        "execution_head", "execution_config_sha256", "authorization_binding_sha256",
        "handoff_v3_sha256", "checkpoint_set_sha256", "catalog_sha256",
        "tensor_map_sha256", "format_contract_sha256",
    ):
        require(identity[field] == EXPECTED[field], field)
    require(identity["corrected_decoder_source_sha256"] == EXPECTED["corrected_decoder_sha256"], "corrected decoder")
    require(identity["defect_evidence_sha256"] == EXPECTED["defect_evidence_sha256"], "defect evidence")
    require(identity["tensor_name"] == "blk.0.ffn_down.weight", "tensor")
    require(identity["shard_ordinal"] == 2, "shard")
    require(identity["offset"] == 1203482464, "offset")
    require(identity["packed_length"] == 61931520, "packed length")
    require(identity["gguf_shape"] == [12288, 6144], "GGUF shape")
    require(identity["logical_shape"] == [6144, 12288], "logical shape")
    require(identity["quantization"] == "Q6_K", "quantization")
    require(len(identity["packed_sha256"]) == 64, "packed SHA")
    require(identity["upstream"] == {
        "repository": "https://github.com/ggml-org/llama.cpp",
        "commit": "a94d563ed801d1da1b8c2432946de07d0231bb3d",
        "tree": "df5ef3120316710a104d702115d446ac30d385f2",
        "path": "ggml/src/ggml-quants.c",
        "file_sha256": "07143d7068936ae46b3c528b2f3d4bbb666e74d88992165716174d243573965d",
        "function": "dequantize_row_q6_K",
    }, "upstream identity")
    for digest in identity["execution_tooling"].values():
        if isinstance(digest, str) and digest not in ("3.13.13", "2.4.5"):
            require(len(digest) == 64, "execution tooling hash")

    target = value["target"]
    require(target["tensor_name"] == "blk.0.ffn_down.weight", "target tensor")
    require(target["shard_ordinal"] == 2 and target["offset"] == 1203482464, "target range")
    require(target["packed_length"] == 61931520, "target length")
    require(target["logical_shape"] == [6144, 12288], "target shape")
    require(target["gguf_shape"] == [12288, 6144], "target GGUF shape")
    require(target["quantization"] == "Q6_K", "target quantization")
    require(target["block_arithmetic"] == {
        "elements": 75497472,
        "elements_per_block": 256,
        "blocks": 294912,
        "packed_bytes_per_block": 210,
        "packed_row_width": 10080,
    }, "block arithmetic")
    require(value["access"] == {
        "shard_opens": 1,
        "positional_reads": 1,
        "tensor_payloads": 1,
        "packed_bytes": 61931520,
    }, "access budget")

    outputs = value["decoder_outputs"]
    require(len(outputs) == 3, "decoder count")
    hashes: list[str] = []
    signed_zero_counts: list[int] = []
    for output, (name, source) in zip(outputs, EXPECTED["decoder_sources"], strict=True):
        require(output["name"] == name, "decoder name")
        require(output["source_sha256"] == source, "decoder source")
        require(output["element_count"] == 75497472, "element count")
        require(output["logical_shape"] == [6144, 12288], "output shape")
        require(output["dtype"] == "f32", "output dtype")
        require(output["serialization"] == "canonical_little_endian_ieee754_binary32", "serialization")
        require(output["non_finite_count"] == 0, "non-finite output")
        require(len(output["decoded_sha256"]) == 64, "decoded SHA")
        hashes.append(output["decoded_sha256"])
        signed_zero_counts.append(output["signed_zero_count"])
    derived_equal = len(set(hashes)) == 1
    require(value["comparison"]["bitwise_equal"] is derived_equal, "stored equality disagrees with hashes")
    require(value["comparison"]["derived_from_decoded_hashes"] is True, "hash derivation")
    require(value["comparison"]["signed_zero_policy"] == "PRESERVE_AND_COUNT_EXACT_F32_BITS", "signed zero policy")
    require(len(set(signed_zero_counts)) == 1, "signed-zero count disagreement")
    require(value["isolation"] == {
        "model_compute": 0,
        "mlx_candidate_dispatches": 0,
        "additional_payloads": 0,
        "dense_prefix_executed": False,
        "fallback": False,
    }, "isolation")
    require(value["ledger"] == {"before": 58, "actual_payloads": 1, "after": 59}, "ledger")
    closure = value["defect_closure"]
    require(closure["defect_id"] == "F017-Q6K-LANE-ORDER-001", "defect id")
    require(closure["defect_evidence_sha256"] == EXPECTED["defect_evidence_sha256"], "closure evidence")
    require(closure["corrected_decoder_sha256"] == EXPECTED["corrected_decoder_sha256"], "closure decoder")
    require(closure["real_byte_side_closed"] is derived_equal, "closure status")
    if derived_equal:
        require(attempt["terminal_class"] == "EXACT_REAL_BYTE_QUALIFIED", "terminal class")
        require(value["verdict"] == "EXACT_REAL_BYTE_QUALIFIED", "verdict")
        require(value["comparison"]["first_divergence"] is None, "pass divergence")
        return "EXACT_REAL_BYTE_QUALIFIED"
    require(attempt["terminal_class"] == "Q6_K_DECODER_TRUTH_UNRESOLVED", "divergence class")
    require(value["verdict"] == "Q6_K_DECODER_TRUTH_UNRESOLVED", "divergence verdict")
    require(value["comparison"]["first_divergence"] is not None, "missing divergence")
    return "Q6_K_DECODER_TRUTH_UNRESOLVED"


def validate_evidence_object(value: dict[str, Any]) -> str:
    try:
        return _validate(value)
    except (KeyError, TypeError, IndexError) as error:
        raise EvidenceError(f"missing or malformed evidence field: {error}") from error


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
