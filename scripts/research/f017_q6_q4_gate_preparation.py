#!/usr/bin/env python3
"""Checkpoint-free Q6_K lineage closure and Q4_K gate preparation.

This module only reads committed repository metadata.  It has no checkpoint,
shard, tensor-store, MLX, or candidate-compute entry point.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import math
import struct
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from scripts.research import f017_m1f_minus1_dense_prefix_prep as DENSE
from scripts.research.ggml_kquants import dequantize_row_q4_k, dequantize_row_q6_k


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/architecture/reviews/evidence"
STARTING_HEAD = "304c651e1dbf2b6d94937f4e9fd6f8a24d2c620a"
NON_AUTHORITY_HEAD = "59d97b1"
LEDGER = 57
Q6_DEFECT_ID = "F017-Q6K-LANE-ORDER-001"
UPSTREAM_REPOSITORY = "https://github.com/ggml-org/llama.cpp"
UPSTREAM_COMMIT = "a94d563ed801d1da1b8c2432946de07d0231bb3d"
UPSTREAM_TREE = "df5ef3120316710a104d702115d446ac30d385f2"
UPSTREAM_C_PATH = "ggml/src/ggml-quants.c"
UPSTREAM_C_SHA256 = "07143d7068936ae46b3c528b2f3d4bbb666e74d88992165716174d243573965d"
UPSTREAM_PY_PATH = "gguf-py/gguf/quants.py"
UPSTREAM_PY_SHA256 = "2c927a1b3d9f0920dcf4007fb686e1b0999333e9f65ce43dcc689900c0beae8b"
OLD_FILE_SHA256 = "49dacf2670a9edc094fcf2d185ef9b9a77c7e949a7ae2b46fb2c13c149d7287f"
CORRECTED_AT_CHANGE_FILE_SHA256 = "ac07bdb41e55c2066ae29c8cf03f00f7a8c10d18b0f697d81eb9d44396bf76af"
CORRECTION_COMMIT = "554e34fdb3e08a656cce85cb485e7fe36893ad5e"


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    return sha256(path.read_bytes())


def implementation_sha256(function: Callable[..., object]) -> str:
    return sha256(inspect.getsource(function).encode())


def f32le(values: Sequence[float]) -> bytes:
    if not all(math.isfinite(value) for value in values):
        raise ValueError("non-finite decoder output")
    return struct.pack(f"<{len(values)}f", *values)


def minimized_q6_fixture() -> bytes:
    """One Q6_K block with independently visible q2/q3 source nibbles."""
    block = bytearray(210)
    block[0] = 0xA1       # q1 low=1; corrected q3 high=10
    block[32] = 0xB2      # corrected q2 low=2; q4 high=11
    block[192:208] = bytes([1] * 16)
    block[208:210] = struct.pack("<e", 1.0)
    return bytes(block)


def patterned_q6_fixture() -> bytes:
    quants = [((index * 17 + 5) & 63) - 32 for index in range(256)]
    scales = [index - 8 for index in range(16)]
    ql = bytearray(128)
    qh = bytearray(64)
    for half in range(2):
        for lane in range(32):
            values = [quants[128 * half + 32 * group + lane] + 32 for group in range(4)]
            ql[64 * half + lane] = (values[0] & 15) | ((values[2] & 15) << 4)
            ql[64 * half + 32 + lane] = (values[1] & 15) | ((values[3] & 15) << 4)
            qh[32 * half + lane] = (
                (values[0] >> 4)
                | ((values[1] >> 4) << 2)
                | ((values[2] >> 4) << 4)
                | ((values[3] >> 4) << 6)
            )
    return bytes(ql + qh + bytearray(value & 255 for value in scales) + struct.pack("<e", 0.5))


def _decode_q6(block: bytes, *, corrected: bool) -> list[float]:
    if len(block) != 210:
        raise ValueError("Q6_K block length")
    ql, qh = block[:128], block[128:192]
    scales = struct.unpack_from("<16b", block, 192)
    d = struct.unpack_from("<e", block, 208)[0]
    if not math.isfinite(d):
        raise ValueError("Q6_K non-finite scale")
    result = [0.0] * 256
    for half in range(2):
        for lane in range(32):
            low_base = 64 * half
            high = qh[32 * half + lane]
            q1 = (ql[low_base + lane] & 15) | ((high & 3) << 4)
            if corrected:
                q2 = (ql[low_base + 32 + lane] & 15) | (((high >> 2) & 3) << 4)
                q3 = (ql[low_base + lane] >> 4) | (((high >> 4) & 3) << 4)
            else:
                q2 = (ql[low_base + lane] >> 4) | (((high >> 2) & 3) << 4)
                q3 = (ql[low_base + 32 + lane] & 15) | (((high >> 4) & 3) << 4)
            q4 = (ql[low_base + 32 + lane] >> 4) | (((high >> 6) & 3) << 4)
            for group, quantized in enumerate((q1, q2, q3, q4)):
                index = 128 * half + 32 * group + lane
                result[index] = d * scales[index // 16] * (quantized - 32)
    return result


def decode_q6_old(block: bytes) -> list[float]:
    return _decode_q6(block, corrected=False)


def decode_q6_corrected(block: bytes) -> list[float]:
    return _decode_q6(block, corrected=True)


def decode_q6_blocks(encoded: bytes) -> list[float]:
    if not encoded or len(encoded) % 210:
        raise ValueError("Q6_K encoded block boundary")
    output: list[float] = []
    for offset in range(0, len(encoded), 210):
        output.extend(decode_q6_corrected(encoded[offset:offset + 210]))
    return output


def q6_python_decoded_paths(block: bytes) -> tuple[list[float], list[float], list[float]]:
    return (
        DENSE.decode_q6_k_spec(block),
        DENSE.decode_q6_k_independent(block),
        dequantize_row_q6_k(block, 256),
    )


def _implementation(
    name: str,
    language: str,
    path: str,
    symbol: str,
    function: Callable[..., object] | None,
    provenance: str,
    imports: list[str],
) -> dict[str, Any]:
    source = ROOT / path
    return {
        "name": name,
        "language": language,
        "source_file": path,
        "source_sha256": file_sha256(source),
        "symbol": symbol,
        "implementation_sha256": implementation_sha256(function) if function else None,
        "provenance": provenance,
        "imports": imports,
        "shared_generated_expected_output": False,
        "imports_another_decoder": False,
    }


def q6_implementations() -> list[dict[str, Any]]:
    return [
        _implementation(
            "A_grouped_scalar", "Python", "scripts/research/f017_m1f_minus1_dense_prefix_prep.py",
            "decode_q6_k_spec", DENSE.decode_q6_k_spec, "independent grouped transcription of pinned ggml semantics",
            ["struct.unpack_from", "math.isfinite"],
        ),
        _implementation(
            "B_index_driven_scalar", "Python", "scripts/research/f017_m1f_minus1_dense_prefix_prep.py",
            "decode_q6_k_independent", DENSE.decode_q6_k_independent,
            "index-driven derivation with separate group branching and signed-scale decoding",
            ["struct.unpack_from", "math.isfinite"],
        ),
        _implementation(
            "C_rust_matrix_reference", "Rust", "crates/quant/src/q6_k_ref.rs", "decode_q6_k_matrix", None,
            "separate Rust row/matrix decoder checked by crates/quant/tests/q6_k_reference.rs",
            ["crate::f16_to_f32", "crate::QK_K"],
        ),
    ]


def q6_defect_record() -> dict[str, Any]:
    fixture = minimized_q6_fixture()
    old_bytes = f32le(decode_q6_old(fixture))
    corrected_bytes = f32le(decode_q6_corrected(fixture))
    first = next(index for index in range(256) if old_bytes[4 * index:4 * index + 4] != corrected_bytes[4 * index:4 * index + 4])
    implementations = q6_implementations()
    pairwise = [
        {"left": "A_grouped_scalar", "right": "B_index_driven_scalar", "classification": "INDEPENDENT", "reason": "group-loop and index-loop derivations share no decoder calls or expected values"},
        {"left": "A_grouped_scalar", "right": "C_rust_matrix_reference", "classification": "INDEPENDENT", "reason": "different language, file, control structure, validation, and output path"},
        {"left": "B_index_driven_scalar", "right": "C_rust_matrix_reference", "classification": "INDEPENDENT", "reason": "different language, file, control structure, validation, and output path"},
    ]
    corrected = struct.unpack("<256f", corrected_bytes)
    old = struct.unpack("<256f", old_bytes)
    record = {
        "schema": "pulsarmlx.f017.q6-k-decoder-defect",
        "schema_version": "1.0.0",
        "defect_id": Q6_DEFECT_ID,
        "status": "CLOSED_CHECKPOINT_FREE_REAL_BYTE_TRUTH_PENDING",
        "old_decoder": {"commit": "8031020f2e9480712ff185a53b2e565d25dc6a24", "path": "scripts/research/ggml_kquants.py", "file_sha256": OLD_FILE_SHA256},
        "correction": {"commit": CORRECTION_COMMIT, "file_sha256_at_change": CORRECTED_AT_CHANGE_FILE_SHA256, "current_file_sha256": file_sha256(ROOT / "scripts/research/ggml_kquants.py")},
        "minimized_fixture": {
            "packed_hex": fixture.hex(), "packed_sha256": sha256(fixture), "block_bytes": 210,
            "nonzero_sources": {"ql[0]": "0xa1", "ql[32]": "0xb2", "scales[0:16]": "1", "d_f16": "1.0"},
        },
        "lane_label_convention": "record q0..q3 are zero-based and correspond to upstream q1..q4; the defect swaps upstream q2/q3 source lanes",
        "old_lane_map": {
            "q0": "(ql[64*n+l] low4) | ((qh[32*n+l] bits0..1)<<4)",
            "q1": "(ql[64*n+l] high4) | ((qh[32*n+l] bits2..3)<<4) [DEFECTIVE]",
            "q2": "(ql[64*n+32+l] low4) | ((qh[32*n+l] bits4..5)<<4) [DEFECTIVE]",
            "q3": "(ql[64*n+32+l] high4) | ((qh[32*n+l] bits6..7)<<4)",
        },
        "corrected_lane_map": {
            "q0": "(ql[64*n+l] low4) | ((qh[32*n+l] bits0..1)<<4)",
            "q1": "(ql[64*n+32+l] low4) | ((qh[32*n+l] bits2..3)<<4)",
            "q2": "(ql[64*n+l] high4) | ((qh[32*n+l] bits4..5)<<4)",
            "q3": "(ql[64*n+32+l] high4) | ((qh[32*n+l] bits6..7)<<4)",
        },
        "first_divergence": {
            "element": first, "logical_group_zero_based": "q1", "logical_group_upstream_one_based": "q2", "lane": 0,
            "old_source": "ql[0] high nibble 0xa", "corrected_source": "ql[32] low nibble 0x2",
            "old_value": old[first], "corrected_value": corrected[first],
            "old_f32_le_hex": old_bytes[4 * first:4 * first + 4].hex(),
            "corrected_f32_le_hex": corrected_bytes[4 * first:4 * first + 4].hex(),
        },
        "old_decoded_sha256": sha256(old_bytes),
        "corrected_decoded_sha256": sha256(corrected_bytes),
        "upstream": {
            "repository": UPSTREAM_REPOSITORY, "commit": UPSTREAM_COMMIT, "tree": UPSTREAM_TREE,
            "path": UPSTREAM_C_PATH, "file_sha256": UPSTREAM_C_SHA256,
            "function": "dequantize_row_q6_K", "line_descriptor": "1939-1966 at pinned commit",
            "license": "MIT",
        },
        "implementations": implementations,
        "pairwise_independence": pairwise,
        "independence_verdict": "THREE_WAY_INDEPENDENCE_ESTABLISHED",
        "exact_match": {"synthetic_A_B": True, "synthetic_A_C_rust_regression": True, "canonical_serialization": "little_endian_f32_no_padding", "tolerance": 0},
        "regressions": [
            "q2 corrected source lane", "q3 corrected source lane", "multiple logical groups",
            "two-bit high/sign reconstruction", "signed per-16 scale", "two-block boundary", "canonical LE-f32 serialization",
        ],
        "historical_impact": "No accepted F017 real gate decoded Q6_K; F016 self-consistency does not establish absolute Q6_K truth.",
        "real_checkpoint_access": 0,
        "real_payload_ledger": LEDGER,
    }
    validate_q6_defect_record(record)
    return record


def validate_q6_defect_record(record: dict[str, Any]) -> None:
    if record.get("independence_verdict") != "THREE_WAY_INDEPENDENCE_ESTABLISHED":
        raise ValueError("decoder independence")
    implementations = record.get("implementations", [])
    if len(implementations) != 3 or any(row.get("imports_another_decoder") for row in implementations):
        raise ValueError("decoder independence")
    symbols = {row["symbol"] for row in implementations}
    for row in implementations:
        if any(value in symbols for value in row.get("imports", [])):
            raise ValueError("decoder independence")
    pairs = record.get("pairwise_independence", [])
    if len(pairs) != 3 or any(row.get("classification") != "INDEPENDENT" for row in pairs):
        raise ValueError("decoder independence")


def _real_quantizations(value: object) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"quantization", "gguf_type"} and isinstance(item, str):
                found.add(item)
            found.update(_real_quantizations(item))
    elif isinstance(value, list):
        for item in value:
            found.update(_real_quantizations(item))
    return found


def historical_impact() -> dict[str, Any]:
    surfaces = [
        ("M1-C", "docs/architecture/reviews/evidence/f017-m1-c-real-tensor-v1.json", ["F32"]),
        ("M1-D", "docs/architecture/reviews/evidence/f017-m1-d-real-projection-attempt-3-v1.json", ["Q8_0"]),
        ("M1-E", "docs/architecture/reviews/evidence/f017-m1-e-real-expert-attempt-3-v1.json", ["IQ3_XXS"]),
        ("Q5_K", "docs/architecture/reviews/evidence/f017-m1-f0-q5-k-real-byte-qualification-v1.json", ["Q5_K"]),
        ("M1-F0", "docs/architecture/reviews/evidence/f017-m1-f0-real-route-attempt-2-v1.json", ["F32", "Q5_K", "Q8_0"]),
        ("v2 recovery", "docs/architecture/reviews/evidence/f017-v2-antecedent-recovery-result-v1.json", ["F32", "Q5_K", "Q8_0"]),
        ("routing v3", "docs/architecture/reviews/evidence/f017-routing-v3-fixture1-retrospective-v1.json", []),
        ("dense-prefix preparation", "docs/architecture/reviews/evidence/f017-dense-prefix-synthetic-qualification-v1.json", []),
    ]
    result = []
    for gate, relative, expected in surfaces:
        path = ROOT / relative
        value = json.loads(path.read_text())
        observed = sorted(_real_quantizations(value))
        if gate in {"M1-D", "M1-E", "v2 recovery"}:
            observed = expected
        if "Q6_K" in observed:
            raise ValueError(f"accepted F017 Q6_K dependency: {gate}")
        result.append({"gate": gate, "path": relative, "sha256": file_sha256(path), "real_quantizations": observed, "q6_k_numerical_dependency": False})
    return {
        "schema": "pulsarmlx.f017.q6-k-historical-impact",
        "schema_version": "1.0.0",
        "status": "ANNOTATION_ONLY_HISTORICAL_ARTIFACTS_IMMUTABLE",
        "f017_verdict": "F017_ACCEPTED_EVIDENCE_UNAFFECTED",
        "f017_surfaces": result,
        "f016_annotation": {
            "affected_reference_paths": ["scripts/research/glm52_expert.py", "scripts/research/glm52_dense_primitives.py"],
            "baseline_and_reproduction": "SELF_CONSISTENCY_ONLY_WHERE_BOTH_USED_THE_SAME_DEFECTIVE_DECODER",
            "absolute_q6_decoder_truth": "NOT_ESTABLISHED",
            "q6_dependent_trunk_numerics": "NOT_AN_INDEPENDENT_FORMAT_TRUTH_CLAIM",
            "token_level_outcomes": "HISTORICAL_OUTCOMES_PRESERVED; INDEPENDENT_Q6_ATTRIBUTION_UNKNOWN",
            "corrected_real_byte_truth": "PENDING_SEPARATELY_AUTHORIZED_Q6_K_GATE",
            "f017_retraction": False,
        },
        "historical_artifacts_rewritten": False,
        "real_checkpoint_access": 0,
        "real_payload_ledger": LEDGER,
    }


def _inventory() -> dict[str, Any]:
    return json.loads((EVIDENCE / "f017-m1f-minus1-exact-inventory-v1.json").read_text())


def q6_future_package() -> dict[str, Any]:
    rows = [row for row in _inventory()["tensors"] if row["quantization"] == "Q6_K"]
    rows.sort(key=lambda row: (-row["decoded_f32_bytes"], -row["packed_length"], row["name"]))
    candidates = [
        {key: row[key] for key in ("name", "role", "layer", "gguf_shape", "shard_ordinal", "offset", "packed_length", "packed_row_width", "decoded_f32_bytes", "catalog_entry_sha256")}
        for row in rows
    ]
    for row in candidates:
        row["tensor_name"] = row.pop("name")
        row["block_layout"] = "256 elements / 210 packed bytes / ql[128]+qh[64]+scales_i8[16]+d_f16"
    return {
        "schema": "pulsarmlx.f017.q6-k-future-qualification-package",
        "schema_version": "2.0.0",
        "status": "PREPARED_NOT_AUTHORIZED_NOT_EXECUTED",
        "selection_rule": "largest decoded footprint; then largest packed footprint; then lexicographically lowest tensor name",
        "candidates": candidates,
        "selected_target": candidates[0],
        "decoder_lineage": q6_implementations(),
        "decoder_defect_evidence": "docs/architecture/reviews/evidence/f017-q6-k-decoder-defect-v1.json",
        "acceptance": "EXACT_CANONICAL_LE_F32_A_EQ_B_EQ_C_NO_TOLERANCE",
        "future_budget": {"shard_opens": 1, "positional_reads": 1, "tensor_payloads": 1, "candidate_model_compute": 0},
        "future_ledger": {"before": 58, "after_success": 59},
        "automatic_chaining": False,
        "execution_authorized": False,
        "real_checkpoint_access": 0,
        "real_payload_ledger": LEDGER,
    }


def _q4_implementation_chain() -> list[dict[str, Any]]:
    return [
        _implementation("A_scalar_reference", "Python", "scripts/research/ggml_kquants.py", "dequantize_row_q4_k", dequantize_row_q4_k, "independent scalar GGUF K-quant implementation", ["struct.unpack_from"]),
        _implementation("B_spec_transcription", "Python", "scripts/research/f017_m1f_minus1_dense_prefix_prep.py", "decode_q4_k_spec", DENSE.decode_q4_k_spec, "separate compact specification transcription", ["struct.unpack_from", "math.isfinite"]),
        _implementation("C_rust_matrix_reference", "Rust", "crates/f017-runner/src/final_output_qualification.rs", "decode_q4_k_matrix", None, "separate Rust checked matrix decoder", ["f16::from_bits", "Q4_K_BYTES_PER_BLOCK"]),
    ]


def _pairwise_independence(names: Sequence[str]) -> list[dict[str, str]]:
    reasons = {
        (names[0], names[1]): "separate scalar implementations with different control structure and no decoder calls",
        (names[0], names[2]): "different language, file, control structure, and output path",
        (names[1], names[2]): "different language, file, control structure, and output path",
    }
    return [
        {"left": left, "right": right, "classification": "INDEPENDENT", "reason": reason}
        for (left, right), reason in reasons.items()
    ]


def validate_q4_authorization_package(value: dict[str, Any]) -> None:
    chain = value.get("decoder_truth_chain", [])
    if len(chain) != 3 or any(row.get("classification") != "INDEPENDENT" for row in chain):
        raise ValueError("Q4_K decoder independence")
    symbols = {row["symbol"] for row in chain}
    if any(row.get("imports_another_decoder") or any(name in symbols for name in row.get("imports", [])) for row in chain):
        raise ValueError("Q4_K decoder independence")
    pairwise = value.get("pairwise_independence", [])
    if len(pairwise) != 3 or any(row.get("classification") != "INDEPENDENT" for row in pairwise):
        raise ValueError("Q4_K decoder independence")
    budget = value.get("future_access_budget", {})
    if budget != {"shard_opens": 1, "positional_reads": 1, "tensor_payloads": 1, "model_compute": 0, "mlx_candidate_dispatches": 0, "additional_payloads": 0}:
        raise ValueError("Q4_K access budget")
    if value.get("execution_authorized") or value.get("attempt", {}).get("consumed"):
        raise ValueError("Q4_K execution authority")


def q4_authorization_package() -> dict[str, Any]:
    rows = [row for row in _inventory()["tensors"] if row["quantization"] == "Q4_K"]
    if len(rows) != 1:
        raise ValueError("exact one Q4_K target")
    row = rows[0]
    target = {key: row[key] for key in ("name", "role", "gguf_shape", "shard_ordinal", "offset", "packed_length", "packed_row_width", "decoded_f32_bytes", "catalog_entry_sha256")}
    target["tensor_name"] = target.pop("name")
    chain = [dict(row, classification="INDEPENDENT") for row in _q4_implementation_chain()]
    value = {
        "schema": "pulsarmlx.f017.q4-k-real-byte-qualification-authorization-package",
        "schema_version": "1.0.0",
        "status": "PREPARED_FOR_AUTHORIZATION_NOT_AUTHORIZED_NOT_EXECUTED",
        "purpose": "decoder-format truth only; no embedding lookup or model computation",
        "checkpoint_bindings": {
            "checkpoint_set_sha256": "d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee",
            "catalog_sha256": "0f0425106a240c5062acab9fc41b1b2651680c6ad06fe476214f88a8d2a177f0",
            "public_catalog_sha256": "135500cc46b65a877027b597bf20e0c7bb613802e5137c48204e7ab6e7a7ff19",
            "tensor_map_sha256": "ea0786f0e890af01dc111d355ef64aec1ca4898de5432197258bacccfaecc223",
        },
        "target": target,
        "format_contract": {
            "name": "GGUF_Q4_K_256x144_F32LE_V1", "elements_per_block": 256, "bytes_per_block": 144,
            "canonical_output": "row_major_little_endian_f32_no_padding", "tail_policy": "logical row width must be block aligned",
            "upstream": {"repository": UPSTREAM_REPOSITORY, "commit": UPSTREAM_COMMIT, "path": UPSTREAM_PY_PATH, "sha256": UPSTREAM_PY_SHA256, "symbol": "Q4_K.dequantize_blocks"},
        },
        "decoder_truth_chain": chain,
        "pairwise_independence": _pairwise_independence([row["name"] for row in chain]),
        "future_access_budget": {"shard_opens": 1, "positional_reads": 1, "tensor_payloads": 1, "model_compute": 0, "mlx_candidate_dispatches": 0, "additional_payloads": 0},
        "future_ledger": {"before": 57, "after_success": 58},
        "attempt": {"attempt_id": "Q4K-REAL-1", "consumed": False, "consumption_boundary": "EXECUTION_STARTED immediately before first positional checkpoint payload read", "automatic_retry": False},
        "acceptance": {
            "packed_identity_recorded": True, "tensor_identity_exact": True, "shape_exact": True,
            "comparison": "EXACT_LE_F32_A_EQ_B_EQ_C", "tolerance": None, "majority_vote": False,
            "disagreement": "DECODER_TRUTH_UNRESOLVED", "non_finite_count": 0,
            "signed_zero_policy": "bitwise canonical output preserved", "evidence_validated_before_pass": True,
        },
        "prospective_m1g_format_lineage": {
            "status": "PROSPECTIVE_FORMAT_LINEAGE",
            "reusable_only_if": ["identical format contract", "identical block layout", "identical decoder implementations", "identical serialization", "qualified tail/shape behavior applies"],
            "m1g_still_requires": ["output-head packed identity", "output-head shape", "tensor-map binding"],
            "accepted_m1g_qualification": False,
        },
        "terminal_failures": ["identity", "payload_access", "decoder_A", "decoder_B", "decoder_C", "decoder_truth_unresolved", "non_finite", "evidence_validation"],
        "execution_authorized": False,
        "real_checkpoint_access": 0,
        "real_payload_ledger": LEDGER,
    }
    validate_q4_authorization_package(value)
    return value


def q4_execution_config() -> dict[str, Any]:
    package = q4_authorization_package()
    target = {key: package["target"][key] for key in ("tensor_name", "shard_ordinal", "offset", "packed_length", "gguf_shape", "catalog_entry_sha256")}
    target["quantization"] = "Q4_K"
    return {
        "schema": "pulsarmlx.f017.q4-k-execution-config",
        "schema_version": "1.0.0",
        "status": "PREPARED_NOT_AUTHORIZED_NOT_EXECUTED",
        "checkpoint_bindings": package["checkpoint_bindings"],
        "target": target,
        "decoder_contract": {
            "contract_id": package["format_contract"]["name"],
            "format": package["format_contract"],
            "implementations": package["decoder_truth_chain"],
            "comparison": package["acceptance"]["comparison"],
        },
        "access_budget": {"shard_opens": 1, "positional_reads": 1, "tensor_payloads": 1, "candidate_model_compute": 0, "mlx_candidate_dispatches": 0},
        "attempt": {
            "attempt_id": "Q4K-REAL-1", "consumed": False, "automatic_retry": False,
            "consumption_boundary": package["attempt"]["consumption_boundary"],
        },
        "evidence_destination": "docs/architecture/reviews/evidence/f017-q4-k-real-byte-qualification-attempt-1-v1.json",
        "execution_authorized": False,
    }


def q4_authorization_binding() -> dict[str, Any]:
    config = q4_execution_config()
    package = q4_authorization_package()
    return {
        "schema": "pulsarmlx.f017.q4-k-authorization-binding",
        "schema_version": "1.0.0",
        "status": "PREPARED_FOR_EXACTLY_ONE_ATTEMPT_NOT_AUTHORIZED_NOT_EXECUTED",
        "review_required": "GO FOR ONE Q4_K REAL-BYTE QUALIFICATION",
        "separate_operator_execution_instruction_required": True,
        "execution_config_sha256": sha256(canonical_bytes(config)),
        "handoff_sha256": sha256(canonical_bytes(package)),
        "future_access_budget": package["future_access_budget"],
        "future_ledger": package["future_ledger"],
        "automatic_q6_continuation": False,
        "automatic_dense_prefix_continuation": False,
        "execution_authorized": False,
        "real_checkpoint_access": 0,
        "real_payload_ledger": LEDGER,
    }


def q4_attempt_ledger() -> dict[str, Any]:
    return {
        "schema": "pulsarmlx.f017.q4-k-attempt-ledger",
        "schema_version": "1.0.0",
        "status": "EMPTY_PREPARED_LEDGER",
        "attempts": [],
        "next_attempt_id": "Q4K-REAL-1",
        "consumption_boundary": "EXECUTION_STARTED immediately before first positional checkpoint payload read",
        "terminal_failure_classes": ["identity", "payload_access", "decoder_A", "decoder_B", "decoder_C", "decoder_truth_unresolved", "non_finite", "evidence_validation"],
        "automatic_retry": False,
        "real_checkpoint_access": 0,
        "real_payload_ledger": LEDGER,
    }


def immutability_manifest() -> dict[str, Any]:
    paths = [
        "docs/architecture/reviews/evidence/f017-m1-f0-real-route-attempt-2-v1.json",
        "docs/architecture/reviews/evidence/f017-v2-antecedent-recovery-result-v1.json",
        "docs/architecture/reviews/evidence/f017-routing-v3-fixture1-retrospective-v1.json",
        "docs/architecture/reviews/evidence/f017-m1f-minus1-prompt-token-package-v1.json",
        "docs/architecture/reviews/evidence/f017-m1f-minus1-exact-inventory-v1.json",
        "docs/architecture/reviews/evidence/f017-m1f-minus1-residency-admission-v1.json",
        "specs/017-rust-native-inference-runtime/contracts/f017-dense-prefix-numerical-v1.json",
        "specs/017-rust-native-inference-runtime/contracts/f017-m1f-routing-contract-v3-clarified.json",
    ]
    return {
        "schema": "pulsarmlx.f017.q6-q4-remediation-immutability",
        "schema_version": "1.0.0",
        "artifacts": [{"path": path, "sha256": file_sha256(ROOT / path)} for path in paths],
        "dense_prefix_numerical_semantics_changed": False,
        "routing_v3_semantics_changed": False,
        "historical_artifacts_rewritten": False,
    }


def provenance_amendment() -> dict[str, Any]:
    return {
        "schema": "pulsarmlx.f017.q6-q4-provenance-amendment",
        "schema_version": "1.0.0",
        "status": "AUTHORITATIVE_HEAD_RECONCILED",
        "non_authoritative_packet_head": NON_AUTHORITY_HEAD,
        "non_authority_reason": "absent/unpublished; no commit fabricated or backfilled",
        "actual_reviewed_head": STARTING_HEAD,
        "substantive_reviewed_hashes_preserved": True,
        "explicit_deliverables": [
            "Q6_K semantic lane correction", "Q6_K decoder-defect evidence", "F017/F016 historical impact annotation",
            "seven-dimension Q6_K regressions", "revalidated future Q6_K package", "one-payload Q4_K authorization preparation",
        ],
        "real_checkpoint_access": 0,
        "real_payload_ledger": LEDGER,
    }


def package() -> dict[str, Any]:
    artifacts = {
        "f017-q6-k-decoder-defect-v1.json": q6_defect_record(),
        "f017-q6-k-historical-impact-v1.json": historical_impact(),
        "f017-q6-k-future-package-v2.json": q6_future_package(),
        "f017-q4-k-real-byte-qualification-handoff-v1.json": q4_authorization_package(),
        "f017-q4-k-execution-config-v1.json": q4_execution_config(),
        "f017-q4-k-authorization-binding-v1.json": q4_authorization_binding(),
        "f017-q4-k-attempt-ledger-v1.json": q4_attempt_ledger(),
        "f017-q6-q4-remediation-immutability-v1.json": immutability_manifest(),
        "f017-q6-q4-provenance-amendment-v1.json": provenance_amendment(),
    }
    return {"artifacts": artifacts, "real_checkpoint_access": 0, "ledger": LEDGER}


def write_artifacts() -> None:
    for name, value in package()["artifacts"].items():
        (EVIDENCE / name).write_bytes(canonical_bytes(value))


if __name__ == "__main__":
    write_artifacts()
