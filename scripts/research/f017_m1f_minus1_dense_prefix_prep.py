#!/usr/bin/env python3
"""Prepare the checkpoint-free F017 M1-F(-1) dense-prefix admission package.

Only committed public catalog/map metadata is read.  There is intentionally no
checkpoint path, shard opener, tensor store, or payload decoder entry point.
"""

from __future__ import annotations

import hashlib
import inspect
import json
import math
import struct
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "docs/research/glm52/raw/f016-c01-catalog-0001.json"
MAP_SOURCE = ROOT / "crates/f017-runner/src/glm52_map.rs"
PROMPT_SOURCE = ROOT / "scripts/research/glm52_generation_harness.py"
F016_QUICKSTART = ROOT / "specs/016-glm52-full-execution/quickstart.md"
GATE_NAME = "F017 M1-F(-1) REAL DENSE-PREFIX LAYER-3 ENTRY-STATE BOUNDARY"
UPSTREAM_COMMIT = "a94d563ed801d1da1b8c2432946de07d0231bb3d"
UPSTREAM_SOURCE_SHA256 = "2c927a1b3d9f0920dcf4007fb686e1b0999333e9f65ce43dcc689900c0beae8b"
UPSTREAM_Q6_C_SOURCE_SHA256 = "07143d7068936ae46b3c528b2f3d4bbb666e74d88992165716174d243573965d"

BLOCKS = {"F32": (1, 4), "Q8_0": (32, 34), "Q4_K": (256, 144), "Q5_K": (256, 176), "Q6_K": (256, 210)}
LAYER_SUFFIXES: dict[str, tuple[tuple[int, ...], tuple[str, ...], str]] = {
    "attn_k_b.weight": ((192, 512, 64), ("Q8_0",), "attention_key_heads"),
    "attn_kv_a_mqa.weight": ((6144, 576), ("Q8_0",), "attention_kv_lora"),
    "attn_kv_a_norm.weight": ((512,), ("F32",), "attention_kv_norm"),
    "attn_norm.weight": ((6144,), ("F32",), "attention_input_norm"),
    "attn_output.weight": ((16384, 6144), ("Q5_K", "Q6_K"), "attention_output"),
    "attn_q_a.weight": ((6144, 2048), ("Q5_K", "Q6_K"), "attention_query_lora_a"),
    "attn_q_a_norm.weight": ((2048,), ("F32",), "attention_query_norm"),
    "attn_q_b.weight": ((2048, 16384), ("Q8_0",), "attention_query_heads"),
    "attn_v_b.weight": ((512, 256, 64), ("Q8_0",), "attention_value_heads"),
    "ffn_down.weight": ((12288, 6144), ("Q6_K",), "dense_ffn_down"),
    "ffn_gate.weight": ((6144, 12288), ("Q5_K",), "dense_ffn_gate"),
    "ffn_norm.weight": ((6144,), ("F32",), "dense_ffn_norm"),
    "ffn_up.weight": ((6144, 12288), ("Q5_K",), "dense_ffn_up"),
}


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    return sha256(path.read_bytes())


def implementation_sha256(callable_object: object) -> str:
    return sha256(inspect.getsource(callable_object).encode("utf-8"))


def prompt_package() -> dict[str, Any]:
    if '"P-MIN": "Hello"' not in PROMPT_SOURCE.read_text():
        raise ValueError("P-MIN prompt provenance")
    if "[9703, 21615, 220]" not in F016_QUICKSTART.read_text():
        raise ValueError("P-MIN accepted token provenance")
    text = "Hello"
    text_bytes = text.encode("utf-8")
    token_bytes = struct.pack("<I", 9703)
    position_bytes = struct.pack("<I", 0)
    payload = {
        "prompt_id": "P-MIN", "prompt_text": text, "prompt_utf8_hex": text_bytes.hex(),
        "prompt_utf8_sha256": sha256(text_bytes), "token_ids": [9703],
        "token_serialization": "little_endian_u32", "token_bytes_hex": token_bytes.hex(),
        "token_bytes_sha256": sha256(token_bytes), "positions": [0],
        "position_serialization": "little_endian_u32", "position_bytes_hex": position_bytes.hex(),
        "position_bytes_sha256": sha256(position_bytes), "dsa": "range_fill([0])",
        "expected_first_generated_token_diagnostic": 21615,
    }
    return {
        "schema": "pulsarmlx.f017.m1f-minus1-prompt-token-package", "schema_version": "1.0.0",
        "status": "FROZEN_PREOBSERVATION_PUBLIC_SAFE", "selection_policy": {
            "basis": "pre-existing F016 P-MIN, selected before M1-F route outcomes",
            "best_of_n": False, "prompt_mutation_after_real_access": "FORBIDDEN",
            "tokenizer_retokenization_during_execution": "FORBIDDEN",
        },
        "provenance": {
            "prompt_source": {"path": PROMPT_SOURCE.relative_to(ROOT).as_posix(), "sha256": file_sha256(PROMPT_SOURCE)},
            "accepted_token_source": {"path": F016_QUICKSTART.relative_to(ROOT).as_posix(), "sha256": file_sha256(F016_QUICKSTART)},
        },
        "payload": payload, "payload_sha256": sha256(canonical_bytes(payload)), "checkpoint_access": 0,
    }


def _expected_names() -> dict[str, tuple[int | None, tuple[int, ...], tuple[str, ...], str]]:
    expected = {"token_embd.weight": (None, (6144, 154880), ("Q4_K",), "token_embedding")}
    for layer in range(3):
        for suffix, (shape, quant, role) in LAYER_SUFFIXES.items():
            expected[f"blk.{layer}.{suffix}"] = (layer, shape, quant, role)
    return expected


def _packed_length(dims: Sequence[int], quantization: str) -> int:
    block_elements, block_bytes = BLOCKS[quantization]
    elements = math.prod(dims)
    if elements % block_elements:
        raise ValueError("quant block alignment")
    return elements // block_elements * block_bytes


def reconstruct_inventory(catalog_path: Path = CATALOG) -> dict[str, Any]:
    raw = catalog_path.read_bytes()
    catalog = json.loads(raw)
    if catalog.get("tensor_count") != 1809 or catalog.get("architecture") != "glm-dsa":
        raise ValueError("catalog identity")
    by_name = {row["name"]: row for row in catalog["tensors"]}
    expected = _expected_names()
    records = []
    for name, (layer, map_shape, allowed_quant, role) in expected.items():
        if name not in by_name:
            raise ValueError(f"missing dense-prefix tensor {name}")
        row = by_name[name]
        dims = tuple(int(v) for v in row["dims"])
        quant = str(row["type"])
        if dims != map_shape or quant not in allowed_quant:
            raise ValueError(f"catalog/map mismatch {name}")
        packed = _packed_length(dims, quant)
        row_width = _packed_length((dims[0],), quant)
        map_contract = {"name": name, "gguf_shape": list(map_shape), "allowed_quantization": list(allowed_quant)}
        catalog_binding = {
            "name": row["name"], "file": row["file"], "data_offset_abs": int(row["data_offset_abs"]),
            "dims": list(row["dims"]), "type": row["type"], "type_id": int(row["type_id"]),
        }
        record = {
            "ordinal": 0, "name": name, "role": role, "layer": layer,
            "shard_basename": row["file"], "shard_ordinal": int(row["file"].split("-")[-3]),
            "offset": int(row["data_offset_abs"]), "packed_length": packed, "packed_row_width": row_width,
            "quantization": quant, "gguf_shape": list(dims), "element_count": math.prod(dims),
            "decoded_f32_bytes": math.prod(dims) * 4,
            "catalog_entry_sha256": sha256(canonical_bytes(catalog_binding)),
            "map_contract_sha256": sha256(canonical_bytes(map_contract)),
            "packed_sha256": None, "decoded_sha256": None,
            "payload_identity_status": "DEFERRED_UNTIL_SEPARATELY_AUTHORIZED_READ",
        }
        record["metadata_identity_sha256"] = sha256(canonical_bytes(record))
        records.append(record)
    records.sort(key=lambda item: (item["shard_ordinal"], item["offset"], item["name"]))
    for ordinal, record in enumerate(records):
        record["ordinal"] = ordinal
        record["metadata_identity_sha256"] = sha256(canonical_bytes({k: v for k, v in record.items() if k != "metadata_identity_sha256"}))
    if len(records) != 40 or len({row["name"] for row in records}) != 40:
        raise ValueError("exact 40-tensor inventory")
    quant_table = {}
    for family in sorted({row["quantization"] for row in records}):
        subset = [row for row in records if row["quantization"] == family]
        status = "UNQUALIFIED_REAL_GATE" if family in {"Q4_K", "Q6_K"} else "REAL_BYTE_QUALIFIED"
        quant_table[family] = {
            "tensor_count": len(subset), "tensor_names": [row["name"] for row in subset],
            "packed_bytes": sum(row["packed_length"] for row in subset),
            "decoded_f32_bytes": sum(row["decoded_f32_bytes"] for row in subset),
            "qualification_status": status,
        }
    budget = {
        "shard_opens": 1, "positional_reads": 40, "tensor_payloads": 40,
        "packed_bytes": sum(row["packed_length"] for row in records),
        "decoded_f32_bytes_upper_bound": sum(row["decoded_f32_bytes"] for row in records),
        "largest_single_decoded_tensor_bytes": max(row["decoded_f32_bytes"] for row in records),
    }
    identity = {
        "catalog": {"path": catalog_path.relative_to(ROOT).as_posix() if catalog_path.is_relative_to(ROOT) else "temporary_test_catalog", "sha256": sha256(raw)},
        "map_source": {"path": MAP_SOURCE.relative_to(ROOT).as_posix(), "sha256": file_sha256(MAP_SOURCE)},
        "selection": "exact token embedding plus the 13 map-bound non-indexer tensors for each dense layer 0,1,2",
    }
    return {
        "schema": "pulsarmlx.f017.m1f-minus1-exact-inventory", "schema_version": "1.0.0",
        "status": "PREPARED_NOT_AUTHORIZED_METADATA_ONLY", "gate_name": GATE_NAME,
        "checkpoint_access": 0, "identity": identity, "tensor_count": 40, "tensors": records,
        "access_budget": budget, "quantization_table": quant_table,
        "unqualified_real_families": ["Q4_K", "Q6_K"],
    }


def select_decoder_targets(inventory: Mapping[str, Any]) -> dict[str, Any]:
    targets = {}
    for family in ("Q4_K", "Q6_K"):
        candidates = [row for row in inventory["tensors"] if row["quantization"] == family]
        candidates.sort(key=lambda row: (-row["decoded_f32_bytes"], -row["packed_length"], row["name"]))
        selected = candidates[0]
        targets[family] = {
            "selection_rule": "largest decoded footprint; then largest packed payload; then lexicographically lowest tensor name",
            "tensor_name": selected["name"], "shard_ordinal": selected["shard_ordinal"],
            "offset": selected["offset"], "packed_length": selected["packed_length"],
            "element_count": selected["element_count"], "gguf_shape": selected["gguf_shape"],
            "packed_sha256": None, "decoded_sha256": None, "status": "TARGET_FROZEN_NOT_AUTHORIZED_NOT_READ",
        }
    return {
        "sequence": ["Q4_K", "Q6_K"],
        "sequence_rationale": "embedding Q4_K is required before layer 0; Q6_K first appears in layer-0 dense FFN down",
        "qualification_scope": {
            "real_payloads_per_family": 1,
            "sufficiency": "one mechanically selected real payload establishes exact real-byte decoder identity for the shared format contract; separately banked block-pattern coverage exercises format branches",
            "does_not_qualify_tensor_content_by_assumption": True,
            "every_future_tensor_still_requires_packed_identity_and_format-contract_validation": True,
        },
        "separate_authorization_per_payload": True, "targets": targets,
    }


def qualification_reuse_plan(inventory: Mapping[str, Any], targets: Mapping[str, Any]) -> dict[str, Any]:
    """Freeze the cross-event reuse proposal without authorizing either event."""
    target_names = [targets["targets"][family]["tensor_name"] for family in targets["sequence"]]
    retained = [row for row in inventory["tensors"] if row["name"] in target_names]
    remaining = [row for row in inventory["tensors"] if row["name"] not in target_names]
    if len(retained) != 2 or len(remaining) != 38:
        raise ValueError("qualification reuse partition")
    return {
        "schema": "pulsarmlx.f017.m1f-minus1-qualification-reuse-plan",
        "schema_version": "1.0.0",
        "status": "PREPARED_REQUIRES_SEPARATE_CROSS_EVENT_REVIEW_AND_AUTHORIZATION",
        "decision": "RETAIN_Q4_AND_Q6_QUALIFICATION_PAYLOADS_THEN_READ_REMAINING_38",
        "retained_tensor_names": target_names,
        "retained_payload_count": 2,
        "future_dense_prefix_new_payload_reads": 38,
        "future_dense_prefix_new_packed_bytes": sum(row["packed_length"] for row in remaining),
        "future_dense_prefix_logical_tensor_count": 40,
        "future_dense_prefix_total_packed_identity_bytes": inventory["access_budget"]["packed_bytes"],
        "future_dense_prefix_total_decoded_identity_bytes": inventory["access_budget"]["decoded_f32_bytes_upper_bound"],
        "requirements": [
            "qualification events retain canonical packed bytes and decoded little-endian f32 bytes",
            "retained package binds checkpoint/catalog/map/tensor offset/length/packed SHA/decoded SHA/decoder contract",
            "retained bytes and manifest are read-only and rehashed before and after import",
            "production candidate receives a separate immutable import; mutable alias with oracle is forbidden",
            "dense-prefix config binds the exact retained package identities and the exact remaining 38-entry read allowlist",
            "failed reuse validation stops the event; automatic reread fallback is forbidden",
        ],
        "cross_event_precedent": {
            "path": "specs/017-rust-native-inference-runtime/contracts/f017-m1f0-decoded-tensor-reuse-v2.json",
            "sha256": file_sha256(ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-m1f0-decoded-tensor-reuse-v2.json"),
            "scope_note": "precedent does not itself authorize this cross-event reuse",
        },
        "checkpoint_access": 0,
    }


def _scale_min(index: int, scales: bytes) -> tuple[int, int]:
    if index < 4:
        return scales[index] & 63, scales[index + 4] & 63
    return ((scales[index + 4] & 15) | ((scales[index - 4] >> 6) << 4),
            (scales[index + 4] >> 4) | ((scales[index] >> 6) << 4))


def decode_q4_k_spec(block: bytes) -> list[float]:
    if len(block) != 144:
        raise ValueError("Q4_K block length")
    d, dmin = struct.unpack_from("<ee", block, 0)
    if not math.isfinite(d) or not math.isfinite(dmin):
        raise ValueError("Q4_K finite scales")
    scales, qs = block[4:16], block[16:144]
    out: list[float] = []
    for group in range(4):
        s0, m0 = _scale_min(2 * group, scales)
        s1, m1 = _scale_min(2 * group + 1, scales)
        q = qs[32 * group:32 * group + 32]
        out.extend(d * s0 * (value & 15) - dmin * m0 for value in q)
        out.extend(d * s1 * (value >> 4) - dmin * m1 for value in q)
    return out


def decode_q6_k_spec(block: bytes) -> list[float]:
    if len(block) != 210:
        raise ValueError("Q6_K block length")
    ql, qh = block[:128], block[128:192]
    scales = struct.unpack_from("<16b", block, 192)
    d = struct.unpack_from("<e", block, 208)[0]
    if not math.isfinite(d):
        raise ValueError("Q6_K finite scale")
    output = [0.0] * 256
    for n in range(2):
        for l in range(32):
            high = qh[32 * n + l]
            quantized = (
                ((ql[64 * n + l] & 15) | ((high & 3) << 4)) - 32,
                ((ql[64 * n + 32 + l] & 15) | (((high >> 2) & 3) << 4)) - 32,
                ((ql[64 * n + l] >> 4) | (((high >> 4) & 3) << 4)) - 32,
                ((ql[64 * n + 32 + l] >> 4) | (((high >> 6) & 3) << 4)) - 32,
            )
            for group, q in enumerate(quantized):
                index = 128 * n + 32 * group + l
                output[index] = d * scales[index // 16] * q
    return output


def decode_q6_k_independent(block: bytes) -> list[float]:
    """Index-driven transcription kept separate from the grouped scalar decoder."""
    if len(block) != 210:
        raise ValueError("Q6_K block length")
    low, high = block[:128], block[128:192]
    scales = tuple(value - 256 if value >= 128 else value for value in block[192:208])
    d = struct.unpack_from("<e", block, 208)[0]
    if not math.isfinite(d):
        raise ValueError("Q6_K finite scale")
    result = []
    for index in range(256):
        half, within = divmod(index, 128)
        group, lane = divmod(within, 32)
        low_base = 64 * half
        high_byte = high[32 * half + lane]
        if group == 0:
            q = (low[low_base + lane] & 15) | ((high_byte & 3) << 4)
        elif group == 1:
            q = (low[low_base + 32 + lane] & 15) | (((high_byte >> 2) & 3) << 4)
        elif group == 2:
            q = (low[low_base + lane] >> 4) | (((high_byte >> 4) & 3) << 4)
        else:
            q = (low[low_base + 32 + lane] >> 4) | (((high_byte >> 6) & 3) << 4)
        result.append(d * scales[index // 16] * (q - 32))
    return result


def _lef32(values: Sequence[float]) -> bytes:
    if not all(math.isfinite(value) for value in values):
        raise ValueError("non-finite decoded value")
    return struct.pack(f"<{len(values)}f", *values)


def synthetic_decoder_scaffold() -> dict[str, Any]:
    from scripts.research.ggml_kquants import dequantize_row_q4_k, dequantize_row_q6_k

    q4 = bytearray((index * 37 + 11) & 255 for index in range(144))
    q4[:4] = struct.pack("<ee", 0.125, 0.03125)
    q6 = bytearray((index * 29 + 7) & 255 for index in range(210))
    q6[208:210] = struct.pack("<e", 0.015625)
    formats = {}
    for family, packed, decoder_a, decoder_b, decoder_c in (
        ("Q4_K", bytes(q4), dequantize_row_q4_k, decode_q4_k_spec, "crates/f017-runner/src/final_output_qualification.rs"),
        ("Q6_K", bytes(q6), decode_q6_k_spec, decode_q6_k_independent, "crates/quant/src/q6_k_ref.rs"),
    ):
        values_a = decoder_a(packed, 256) if family == "Q4_K" else decoder_a(packed)
        a, b = _lef32(values_a), _lef32(decoder_b(packed))
        if a != b:
            raise ValueError(f"{family} synthetic A/B mismatch")
        decoder_a_path = "scripts/research/ggml_kquants.py" if family == "Q4_K" else "scripts/research/f017_m1f_minus1_dense_prefix_prep.py"
        decoder_b_path = "scripts/research/f017_m1f_minus1_dense_prefix_prep.py"
        formats[family] = {
            "synthetic_packed_sha256": sha256(packed), "synthetic_decoded_sha256": sha256(a),
            "element_count": 256, "a_b_exact": True,
            "decoder_a": {"path": decoder_a_path, "symbol": decoder_a.__name__, "implementation_sha256": implementation_sha256(decoder_a)},
            "decoder_b": {"path": decoder_b_path, "symbol": decoder_b.__name__, "implementation_sha256": implementation_sha256(decoder_b)},
            "decoder_c": {"path": decoder_c, "sha256": file_sha256(ROOT / decoder_c), "status": "SOURCE_BOUND_RUST_REGRESSION"},
            "authoritative_reference": {"repository": "https://github.com/ggml-org/llama.cpp", "commit": UPSTREAM_COMMIT,
                "path": "ggml/src/ggml-quants.c" if family == "Q6_K" else "gguf-py/gguf/quants.py",
                "source_sha256": UPSTREAM_Q6_C_SOURCE_SHA256 if family == "Q6_K" else UPSTREAM_SOURCE_SHA256,
                "symbol": "dequantize_row_q6_K" if family == "Q6_K" else f"{family}.dequantize_blocks"},
            "real_byte_status": "UNQUALIFIED_REAL_GATE",
        }
        if family == "Q6_K":
            legacy = _lef32(dequantize_row_q6_k(packed, 256))
            legacy_matches = legacy == a
            formats[family]["legacy_research_decoder_audit"] = {
                "path": "scripts/research/ggml_kquants.py", "decoded_sha256": sha256(legacy),
                "source_sha256": file_sha256(ROOT / "scripts/research/ggml_kquants.py"),
                "matches_spec": legacy_matches,
                "pre_remediation_decoded_sha256": "ce70c17c1225a959e154b77c89d013cd9a3312ec7a2db58cfd8b81f24b164050",
                "pre_remediation_first_divergence": {"element": 32, "legacy_f32_hex": "000080be", "spec_f32_hex": "000010be"},
                "pre_remediation_differing_elements": 118,
                "remediation": "correct q2/q3 logical group placement without changing bit unpacking or scale indexing",
                "status": "REMEDIATED_SYNTHETIC_EXACT_REAL_BYTE_UNQUALIFIED" if legacy_matches else "EXCLUDED_FROM_QUALIFICATION_UNTIL_REMEDIATED",
            }
            if not legacy_matches:
                raise ValueError("Q6_K legacy decoder regression")
    return {"schema": "pulsarmlx.f017.m1f-minus1-decoder-scaffold", "schema_version": "1.0.0",
            "status": "SYNTHETIC_A_B_EXACT_C_SOURCE_BOUND_REAL_BYTES_NOT_AUTHORIZED", "checkpoint_access": 0,
            "canonical_output": "row_major_logical_little_endian_f32_no_padding", "tolerance": 0,
            "formats": formats}


def residency_contract(inventory: Mapping[str, Any]) -> dict[str, Any]:
    budget = inventory["access_budget"]
    gib = 1024 ** 3
    fixed_reserve = 4 * gib
    decoded_upper = budget["decoded_f32_bytes_upper_bound"]
    oracle_peak = budget["packed_bytes"] + decoded_upper + fixed_reserve
    # Fail closed even if a future native path retains a complete CPU-decoded
    # package while importing a full decoded-equivalent MLX weight set.
    candidate_peak = budget["packed_bytes"] + (2 * decoded_upper) + fixed_reserve
    modeled = candidate_peak
    floor = math.ceil((modeled * 1.25) / gib) * gib
    return {
        "schema": "pulsarmlx.f017.m1f-minus1-residency-admission", "schema_version": "1.0.0",
        "status": "PREOBSERVATION_METHOD_FROZEN_NOT_MEASURED_NOT_AUTHORIZED", "checkpoint_access": 0,
        "liveness_phases": [
            {"phase": "package_read", "live": ["40 immutable packed payloads"], "bytes_upper": budget["packed_bytes"]},
            {"phase": "independent_oracle", "live": ["packed package", "decoded oracle tensors upper bound", "activation/cache reserve"], "bytes_upper": oracle_peak},
            {"phase": "candidate", "live": ["packed package", "complete CPU decoded upper bound", "complete decoded-equivalent MLX residency upper bound", "activation/cache/native-workspace reserve", "layer-3 entry output"], "bytes_upper": candidate_peak},
            {"phase": "evidence_bank", "live": ["canonical layer-3 entry state", "hashes", "timings"], "bytes_upper": 24576},
        ],
        "admission_floor_method": {
            "formula": "ceil_GiB(1.25 * (packed_inventory + decoded_cpu_all_upper_bound + decoded_equivalent_mlx_all_upper_bound + 4_GiB_fixed_runtime_reserve))",
            "packed_inventory_bytes": budget["packed_bytes"],
            "decoded_cpu_all_upper_bound_bytes": decoded_upper,
            "decoded_equivalent_mlx_all_upper_bound_bytes": decoded_upper,
            "fixed_runtime_reserve_bytes": fixed_reserve, "engineering_multiplier": 1.25,
            "fixed_runtime_reserve_rationale": "activation/cache/native-workspace planning reserve pending path-specific telemetry",
            "engineering_multiplier_rationale": "conservative fragmentation and implementation-drift planning envelope; not a measured production claim",
            "required_available_memory_bytes": floor, "required_available_memory_gib": floor // gib,
            "frozen_before_candidate_telemetry": True, "post_observation_lowering": "FORBIDDEN",
        },
        "candidate_residency_caveat": "native path telemetry must be measured and remain below this conservative double-residency host admission floor before authorization; telemetry may not lower the frozen floor",
        "required_runtime_admission": ["normal_or_safe_pressure", "swap_below_reviewed_limit", "no_competing_inference", "safe_thermal_state", "sufficient_disk"],
    }


def boundary_contract(inventory: Mapping[str, Any], prompt: Mapping[str, Any], decoder: Mapping[str, Any], residency: Mapping[str, Any], reuse: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": "pulsarmlx.f017.m1f-minus1-boundary", "schema_version": "1.0.0",
        "contract_id": "f017-m1f-minus1-dense-prefix-layer3-entry-v1", "status": "PREPARED_NOT_AUTHORIZED",
        "honest_name": GATE_NAME, "not_fixture_capture": True,
        "computation": ["token embedding lookup", "complete dense layer 0", "complete dense layer 1", "complete dense layer 2", "capture exact layer-3 entry hidden state"],
        "forbidden": ["layer-3 attention/router", "expert execution", "Q6_K real qualification", "M1-F", "M1-G", "P1", "Feature 018"],
        "input_package_sha256": prompt["payload_sha256"], "tensor_count": inventory["tensor_count"],
        "access_budget": inventory["access_budget"], "decoder_sequence": select_decoder_targets(inventory)["sequence"],
        "execution_access_after_separately_qualified_payload_reuse": {
            "logical_tensor_identities": 40,
            "retained_qualified_payloads": 2,
            "new_positional_reads": reuse["future_dense_prefix_new_payload_reads"],
            "new_tensor_payloads": reuse["future_dense_prefix_new_payload_reads"],
            "new_compressed_bytes": reuse["future_dense_prefix_new_packed_bytes"],
            "reread_fallback": "FORBIDDEN",
            "authorization_status": "NOT_AUTHORIZED",
        },
        "decoder_scaffold_status": decoder["status"], "admission_floor_bytes": residency["admission_floor_method"]["required_available_memory_bytes"],
        "attempt_semantics": {"preflight_consumes_attempt": False, "execution_started_consumes_attempt": True, "auto_retry": False},
        "real_payload_ledger": {
            "current": 57,
            "future_after_q4_qualification": 58,
            "future_after_q6_qualification": 59,
            "future_after_38_new_payload_dense_prefix_with_reviewed_reuse": 97,
            "nonreuse_reference_total": 99,
            "changed_in_preparation": False,
        },
    }


def package() -> dict[str, Any]:
    prompt = prompt_package()
    inventory = reconstruct_inventory()
    decoder = synthetic_decoder_scaffold()
    residency = residency_contract(inventory)
    targets = select_decoder_targets(inventory)
    reuse = qualification_reuse_plan(inventory, targets)
    return {"prompt": prompt, "inventory": inventory, "decoder": decoder, "residency": residency,
            "targets": targets, "reuse": reuse,
            "boundary": boundary_contract(inventory, prompt, decoder, residency, reuse)}


def write_banked_artifacts() -> None:
    """Regenerate the seven canonical checkpoint-free planning artifacts."""
    generated = package()
    mapping = {
        "f017-m1f-minus1-prompt-token-package-v1.json": "prompt",
        "f017-m1f-minus1-exact-inventory-v1.json": "inventory",
        "f017-m1f-minus1-decoder-scaffold-v1.json": "decoder",
        "f017-m1f-minus1-residency-admission-v1.json": "residency",
        "f017-m1f-minus1-decoder-targets-v1.json": "targets",
        "f017-m1f-minus1-boundary-v1.json": "boundary",
        "f017-m1f-minus1-qualification-reuse-plan-v1.json": "reuse",
    }
    evidence = ROOT / "docs/architecture/reviews/evidence"
    for name, key in mapping.items():
        (evidence / name).write_bytes(canonical_bytes(generated[key]))


if __name__ == "__main__":
    write_banked_artifacts()
