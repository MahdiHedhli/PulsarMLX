#!/usr/bin/env python3
"""Generate the independent two-layer Feature 017 R12 GGUF fixture."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import struct
import tempfile
from pathlib import Path
from typing import Iterable

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
GENERATOR_PATH = "scripts/research/generate_f017_r12_tiny_model.py"
WIDTH = 256
VOCAB = 16
LAYERS = 2
EXPERTS = 12
TOP_K = 8
RMS_EPS = np.float32(1.0e-5)
ATTENTION_SCALE = np.float32(1.0 / math.sqrt(2 * WIDTH))
SHARD_NAMES = ("f017-r12-00001-of-00002.fixture", "f017-r12-00002-of-00002.fixture")


def _load(name: str, relative: str):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


R9 = _load("f017_r9_generator", "scripts/research/generate_f017_r9_oracle.py")
R10 = _load("f017_r10_generator", "scripts/research/generate_f017_r10_oracle.py")
R11 = _load("f017_r11_generator", "scripts/research/generate_f017_r11_oracle.py")
for module in (R9, R10):
    module.WIDTH = WIDTH
R9.Q_NOPE = WIDTH
R9.Q_ROPE = WIDTH
R9.QK = 2 * WIDTH
R9.KV_LORA = WIDTH
R9.VALUE = WIDTH
R9.ATTENTION_SCALE = ATTENTION_SCALE
R11.WIDTH = WIDTH


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _f32(value: float | np.float32) -> np.float32:
    return np.float32(value)


def _f32_bytes(values: Iterable[float]) -> bytes:
    return b"".join(struct.pack("<f", float(_f32(value))) for value in values)


def _record(values: Iterable[float]) -> dict[str, object]:
    materialized = [_f32(value) for value in values]
    payload = _f32_bytes(materialized)
    return {"f32_le_hex": payload.hex(), "sha256": _sha256(payload)}


def _tensor(name: str, dims: list[int], type_id: int, payload: bytes) -> dict[str, object]:
    return {
        "name": name,
        "dims": dims,
        "type_id": type_id,
        "payload": payload,
        "payload_sha256": _sha256(payload),
    }


def _q8(name: str, rows: int, salt: int) -> tuple[dict[str, object], list[np.float32]]:
    packed = bytearray()
    decoded: list[np.float32] = []
    for row in range(rows):
        for block in range(WIDTH // 32):
            scale = _f32((1 + (row + block + salt) % 4) / 64.0)
            packed.extend(struct.pack("<e", float(scale)))
            for lane in range(32):
                column = block * 32 + lane
                quant = ((row * 7 + column * 11 + salt * 5) % 17) - 8
                packed.extend(struct.pack("b", quant))
                decoded.append(_f32(scale * _f32(quant)))
    payload = bytes(packed)
    return _tensor(name, [WIDTH, rows], 8, payload), decoded


def _f32_tensor(name: str, values: list[np.float32], dims: list[int]) -> dict[str, object]:
    return _tensor(name, dims, 0, _f32_bytes(values))


def _layer(layer: int, residual: list[np.float32]) -> tuple[list[dict[str, object]], dict[str, object], list[np.float32]]:
    tensors: list[dict[str, object]] = []
    matrices: dict[str, list[np.float32]] = {}
    for role, rows, salt in (
        ("attn_q_a", WIDTH, 1),
        ("attn_q_b", 2 * WIDTH, 2),
        ("attn_kv_a_mqa", 2 * WIDTH, 3),
        ("attn_k_b", WIDTH, 4),
        ("attn_v_b", WIDTH, 5),
        ("attn_output", WIDTH, 6),
    ):
        name = f"blk.{layer}.{role}.weight"
        tensor, decoded = _q8(name, rows, salt + layer * 101)
        tensors.append(tensor)
        matrices[role] = decoded

    attn_norm = [_f32(0.75 + ((index + layer) % 7) / 16.0) for index in range(WIDTH)]
    q_norm = [_f32(0.875 + ((index + layer) % 5) / 32.0) for index in range(WIDTH)]
    kv_norm = [_f32(0.8125 + ((index + layer) % 3) / 16.0) for index in range(WIDTH)]
    tensors.extend(
        [
            _f32_tensor(f"blk.{layer}.attn_norm.weight", attn_norm, [WIDTH]),
            _f32_tensor(f"blk.{layer}.attn_q_a_norm.weight", q_norm, [WIDTH]),
            _f32_tensor(f"blk.{layer}.attn_kv_a_norm.weight", kv_norm, [WIDTH]),
        ]
    )
    x_norm = R9._rms_norm(residual, attn_norm)
    q_rank = R9._matvec(matrices["attn_q_a"], WIDTH, x_norm)
    q_rank_norm = R9._rms_norm(q_rank, q_norm)
    q_flat = R9._matvec(matrices["attn_q_b"], 2 * WIDTH, q_rank_norm)
    q_nope, q_rope_raw = q_flat[:WIDTH], q_flat[WIDTH:]
    cosine, sine = R9._rope_constants(2)
    q_rope = R9._rotate(q_rope_raw, cosine, sine)
    kv_raw = R9._matvec(matrices["attn_kv_a_mqa"], 2 * WIDTH, x_norm)
    current_latent = R9._rms_norm(kv_raw[:WIDTH], kv_norm)
    current_rope = kv_raw[WIDTH:]
    prior_latents = [
        [_f32((((row + layer + 2) * (column + 3)) % 19 - 9) / 16.0) for column in range(WIDTH)]
        for row in range(2)
    ]
    prior_ropes = [
        [_f32((((row + layer + 5) * (column + 1)) % 17 - 8) / 32.0) for column in range(WIDTH)]
        for row in range(2)
    ]
    cache_latents = prior_latents + [current_latent]
    cache_ropes = prior_ropes + [current_rope]
    qk_low = R9._matvec(matrices["attn_k_b"], WIDTH, q_nope)
    scores: list[np.float32] = []
    for position in range(3):
        key_cos, key_sin = R9._rope_constants(position)
        rotated = R9._rotate(cache_ropes[position], key_cos, key_sin)
        scores.append(_f32(_f32(R9._dot(qk_low, cache_latents[position]) + R9._dot(q_rope, rotated)) * ATTENTION_SCALE))
    probabilities = R9._softmax(scores)
    latent_sum = [_f32(0.0) for _ in range(WIDTH)]
    for weight, position in zip(probabilities, range(3), strict=True):
        for column in range(WIDTH):
            latent_sum[column] = _f32(latent_sum[column] + _f32(weight * cache_latents[position][column]))
    value = R9._matvec(matrices["attn_v_b"], WIDTH, latent_sum)
    projected = R9._matvec(matrices["attn_output"], WIDTH, value)
    attention_output = [_f32(left + right) for left, right in zip(residual, projected, strict=True)]

    ffn_norm = [_f32(0.8125 + ((index + layer) % 7) / 32.0) for index in range(WIDTH)]
    tensors.append(_f32_tensor(f"blk.{layer}.ffn_norm.weight", ffn_norm, [WIDTH]))
    normalized = R10._rms_norm(attention_output, ffn_norm)
    router_tensor, router_matrix = _q8(f"blk.{layer}.ffn_gate_inp.weight", EXPERTS, 31 + layer * 101)
    tensors.append(router_tensor)
    router_logits = R10._matvec(router_matrix, EXPERTS, normalized)
    router_bias = [float(((index * 5 + layer) % 11 - 5) / 32.0) for index in range(EXPERTS)]
    tensors.append(_f32_tensor(f"blk.{layer}.exp_probs_b.bias", [_f32(value) for value in router_bias], [EXPERTS]))
    router_probabilities = [R10._sigmoid(float(value)) for value in router_logits]
    router_scores = [router_probabilities[index] + router_bias[index] for index in range(EXPERTS)]
    selected_ids = sorted(range(EXPERTS), key=lambda index: (-router_scores[index], index))[:TOP_K]
    denominator = math.fsum(router_probabilities[index] for index in selected_ids)
    routing_weights = [router_probabilities[index] / max(denominator, 6.103515625e-5) * 2.5 for index in selected_ids]
    routed_outputs_by_id: dict[int, list[np.float32]] = {}
    for expert_id in range(EXPERTS):
        decoded: list[list[np.float32]] = []
        for role, salt in (("gate", 101), ("up", 151), ("down", 211)):
            tensor, matrix = _q8(f"blk.{layer}.routed.{expert_id}.{role}.weight", WIDTH, salt + expert_id * 7 + layer * 103)
            tensors.append(tensor)
            decoded.append(matrix)
        if expert_id in selected_ids:
            routed_outputs_by_id[expert_id] = R10._expert(decoded, normalized)["down"]
    shared_matrices: list[list[np.float32]] = []
    for role, salt in (("gate", 307), ("up", 359), ("down", 401)):
        tensor, matrix = _q8(f"blk.{layer}.shared.{role}.weight", WIDTH, salt + layer * 107)
        tensors.append(tensor)
        shared_matrices.append(matrix)
    shared_output = R10._expert(shared_matrices, normalized)["down"]
    routed_aggregate = [
        math.fsum(
            routing_weights[route]
            * float(routed_outputs_by_id[selected_ids[route]][column])
            for route in range(TOP_K)
        )
        for column in range(WIDTH)
    ]
    output = [_f32(float(attention_output[column]) + routed_aggregate[column] + float(shared_output[column])) for column in range(WIDTH)]
    expected = {
        "input": _record(residual),
        "runtime_inputs": {
            "prior_cache_latents": _record(value for row in prior_latents for value in row),
            "prior_cache_ropes": _record(value for row in prior_ropes for value in row),
            "q_rope_cosine": _record(cosine),
            "q_rope_sine": _record(sine),
            "rms_epsilon": float(RMS_EPS),
            "attention_scale": float(ATTENTION_SCALE),
            "query_position": 2,
            "visible_positions": 3,
        },
        "attention_output": _record(attention_output),
        "selected_ids": selected_ids,
        "routing_weights": routing_weights,
        "output": _record(output),
    }
    return tensors, expected, output


def _push_string(buffer: bytearray, value: str) -> None:
    encoded = value.encode()
    buffer.extend(struct.pack("<Q", len(encoded)))
    buffer.extend(encoded)


def _build_shard(tensors: list[dict[str, object]], architecture: bool) -> tuple[bytes, list[dict[str, object]], int]:
    header = bytearray(struct.pack("<IIQQ", 0x46554747, 3, len(tensors), 1 if architecture else 0))
    if architecture:
        _push_string(header, "general.architecture")
        header.extend(struct.pack("<I", 8))
        _push_string(header, "glm-dsa")
    offsets: list[int] = []
    cursor = 0
    for tensor in tensors:
        cursor = (cursor + 31) // 32 * 32
        offsets.append(cursor)
        cursor += len(tensor["payload"])
    for tensor, offset in zip(tensors, offsets, strict=True):
        _push_string(header, str(tensor["name"]))
        dims = list(tensor["dims"])
        header.extend(struct.pack("<I", len(dims)))
        for dimension in dims:
            header.extend(struct.pack("<Q", int(dimension)))
        header.extend(struct.pack("<IQ", int(tensor["type_id"]), offset))
    data_offset = (len(header) + 31) // 32 * 32
    output = header + bytes(data_offset - len(header))
    for tensor, offset in zip(tensors, offsets, strict=True):
        target = data_offset + offset
        output.extend(bytes(target - len(output)))
        output.extend(tensor["payload"])
    public = [
        {
            "name": tensor["name"],
            "dims": tensor["dims"],
            "type_id": tensor["type_id"],
            "payload_sha256": tensor["payload_sha256"],
            "payload_bytes": len(tensor["payload"]),
            "offset": offset,
        }
        for tensor, offset in zip(tensors, offsets, strict=True)
    ]
    return bytes(output), public, data_offset


def _catalog_sha(shards: list[tuple[bytes, list[dict[str, object]], int]]) -> str:
    hasher = hashlib.sha256()
    base = 0
    for shard, tensors, data_offset in shards:
        for tensor in tensors:
            hasher.update(str(tensor["name"]).encode())
            hasher.update(b"\0")
            hasher.update(struct.pack("<Q", len(tensor["dims"])))
            for dimension in tensor["dims"]:
                hasher.update(struct.pack("<Q", int(dimension)))
            hasher.update(struct.pack("<I", int(tensor["type_id"])))
            hasher.update(struct.pack("<Q", base + data_offset + int(tensor["offset"])))
            hasher.update(struct.pack("<Q", int(tensor["payload_bytes"])))
        base += len(shard)
    return hasher.hexdigest()


def generate(source_commit: str, out_dir: Path) -> None:
    embedding = [_f32((((token + 3) * (column + 5)) % 29 - 14) / 16.0) for token in range(VOCAB) for column in range(WIDTH)]
    tensors: list[dict[str, object]] = [_f32_tensor("token_embd.weight", embedding, [WIDTH, VOCAB])]
    residual = embedding[3 * WIDTH : 4 * WIDTH]
    expected_layers = []
    layer_tensors = []
    for layer in range(LAYERS):
        current, expected, residual = _layer(layer, residual)
        layer_tensors.append(current)
        expected_layers.append(expected)
    output_norm = [_f32(0.75 + (index % 9) / 32.0) for index in range(WIDTH)]
    head_record, decoded_head = R11._q4_k_matrix(VOCAB)
    normalized = R11._rms_norm(residual, output_norm)
    logits = R11._matvec(decoded_head, VOCAB, normalized)
    top_ids, top_scores = R11._stable_top_k(logits, 8)
    final_tensors = [
        _f32_tensor("output_norm.weight", output_norm, [WIDTH]),
        _tensor("output.weight", [WIDTH, VOCAB], 12, bytes.fromhex(head_record["packed_hex"])),
    ]
    shard1_tensors = tensors + layer_tensors[0]
    shard2_tensors = layer_tensors[1] + final_tensors
    shard1 = _build_shard(shard1_tensors, True)
    shard2 = _build_shard(shard2_tensors, False)
    shards = [shard1, shard2]
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, (payload, _, _) in zip(SHARD_NAMES, shards, strict=True):
        (out_dir / name).write_bytes(payload)
    shard_hashes = [_sha256(shard[0]) for shard in shards]
    set_hasher = hashlib.sha256()
    for digest, shard in zip(shard_hashes, shards, strict=True):
        set_hasher.update(digest.encode())
        set_hasher.update(str(len(shard[0])).encode())
    checkpoint = {
        "schema": "pulsarmlx.f017.checkpoint-manifest",
        "schema_version": "1.0.0",
        "kind": "fixture",
        "immutable_revision": "f017-r12-tiny-model-v1",
        "architecture": "glm-dsa",
        "tokenizer_identity": "exact-token-ids",
        "checkpoint_set_sha256": set_hasher.hexdigest(),
        "catalog_sha256": _catalog_sha(shards),
        "tensor_count": sum(len(shard[1]) for shard in shards),
        "shards": [
            {"filename": name, "size_bytes": len(shard[0]), "sha256": digest}
            for name, shard, digest in zip(SHARD_NAMES, shards, shard_hashes, strict=True)
        ],
    }
    (out_dir / "checkpoint.json").write_text(json.dumps(checkpoint, indent=2, sort_keys=True) + "\n")
    contracts = []
    for shard_name, (_, shard_tensors, _) in zip(SHARD_NAMES, shards, strict=True):
        for tensor in shard_tensors:
            contracts.append({
                "name": tensor["name"],
                "dims": tensor["dims"],
                "type_id": tensor["type_id"],
                "payload_sha256": tensor["payload_sha256"],
                "payload_bytes": tensor["payload_bytes"],
                "shard": shard_name,
            })
    generator_sha = _sha256(Path(__file__).read_bytes())
    oracle = {
        "schema": "pulsarmlx.f017.r12-tiny-model-oracle",
        "schema_version": "1.0.0",
        "fixture_version": "f017-r12-tiny-glm-dsa-v1",
        "source_commit": source_commit,
        "generator_path": GENERATOR_PATH,
        "generator_sha256": generator_sha,
        "independence": {"classification": "INDEPENDENT", "uses_rust_candidate": False, "uses_mlx": False, "uses_checkpoint": False},
        "checkpoint_manifest": "checkpoint.json",
        "architecture": {"family": "glm-dsa", "hidden_width": WIDTH, "vocabulary_size": VOCAB, "layer_count": LAYERS, "expert_count": EXPERTS, "top_k": TOP_K, "shared_expert_count": 1},
        "input": {"tokens": [3], "n_new": 1, "expected_token": top_ids[0]},
        "tensor_contracts": contracts,
        "expected": {
            "embedding": _record(embedding[3 * WIDTH : 4 * WIDTH]),
            "layers": expected_layers,
            "final_hidden": _record(residual),
            "final_normalized": _record(normalized),
            "logits": _record(logits),
            "top_k_ids": top_ids,
            "top_k_scores": _record(top_scores),
            "argmax": top_ids[0],
        },
        "contracts": ["f017-production-expert-tier-b-v1", "f017-production-r9-tier-b-v2", "f017-production-r10-tier-b-v2", "f017-production-r11-tier-b-v1"],
        "deterministic_repeats": 10,
        "checkpoint_accessed": False,
        "review_status": "pending_adversarial_canonical_runner_review",
    }
    (out_dir / "model.json").write_text(json.dumps(oracle, indent=2, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        with tempfile.TemporaryDirectory() as temporary:
            generated = Path(temporary)
            generate(args.source_commit, generated)
            for name in (*SHARD_NAMES, "checkpoint.json", "model.json"):
                if (generated / name).read_bytes() != (args.out_dir / name).read_bytes():
                    raise SystemExit(f"{name}: deterministic regeneration differs")
    else:
        generate(args.source_commit, args.out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
