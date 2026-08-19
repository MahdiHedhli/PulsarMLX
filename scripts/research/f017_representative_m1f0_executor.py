#!/usr/bin/env python3
"""Crash-safe executor for the representative layer-3 attention -> route event.

The executable event shape is deliberately narrow: nine positional checkpoint
reads, three retained router inputs, and one retained DPREFIX-EXACT-1 input.
The CLI exposes checkpoint-free validation/rehearsal only until a separately
reviewed real-event release is supplied.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
import stat
import struct
import tempfile
from typing import Any, Callable, Protocol

import numpy as np


EVENT_ID = "F017-REPRESENTATIVE-M1F0-ATTENTION-ROUTE-RECOVERY-1"
ATTEMPT_ID = EVENT_ID + "-ATTEMPT-1"
SCHEMA = "pulsarmlx.f017.representative-m1f0-execution-authorization"
SCHEMA_VERSION = "2.0.0"
LEDGER_BEFORE = 166
LEDGER_AFTER = 175
EPSILON = np.float32(1.0e-5)
EPSILON_BITS = "0x3727c5ac"
CHUNK = 1024 * 1024
EXPECTED_HEAD = "2a657bdf41267817ff03cc5d233ec2507c87dbf2"
EXPECTED_BOUNDARY = "a9dc0d9effb3e52844203a34be587d12f0f7b011fb58d33c5dbdbe5b650deed3"
EXPECTED_GRAPH = "1585dad6b989fd0ac9b231f4e66e4d0129021868d027a3352a7b740707561558"
EXPECTED_EPSILON_ADJUDICATION = "fc92b11223ee174b5f206a45a6d2b50540b4c82ba5d2c2333010947d525646e4"
FROZEN_INVENTORY = (
    (0, "blk.3.attn_norm.weight", 2008634208, 24576, "F32", (6144,)),
    (1, "blk.3.attn_q_a.weight", 2077864800, 8650752, "Q5_K", (2048, 6144)),
    (2, "blk.3.attn_q_a_norm.weight", 2086515552, 8192, "F32", (2048,)),
    (3, "blk.3.attn_q_b.weight", 2086523744, 35651584, "Q8_0", (16384, 2048)),
    (4, "blk.3.attn_kv_a_mqa.weight", 2004872032, 3760128, "Q8_0", (576, 6144)),
    (5, "blk.3.attn_kv_a_norm.weight", 2008632160, 2048, "F32", (512,)),
    (6, "blk.3.attn_k_b.weight", 1998187360, 6684672, "Q8_0", (64, 512, 192)),
    (7, "blk.3.attn_v_b.weight", 2122175328, 8912896, "Q8_0", (64, 256, 512)),
    (8, "blk.3.attn_output.weight", 2008658784, 69206016, "Q5_K", (6144, 16384)),
)
FROZEN_RETAINED = {
    "canonical_s0": ("9c3a8821deda6a9983b49544d5726efad97b2e560f55a7eb0f182aaa128ceb11", (6144,), 24576),
    "ffn_norm": ("1d9228483902bf2ca1088589d25c1cbc116facd82454a117e7dafb2d48f83d8f", (6144,), 24576),
    "router_matrix": ("da0263ba11f06e21532aff708b8677c76381c1165e11134c72d7039ebb64439a", (256, 6144), 6291456),
    "correction_bias": ("eb6feeb8d7ab446e4e786aaac55c22cc7b98521dbd71cb0a57610d8da59b0491", (256,), 1024),
}

CANONICAL_STAGE_NAMES = (
    "input_hidden", "attention_normalized", "query_rank",
    "query_rank_normalized", "query_heads", "kv_raw", "kv_normalized",
    "key_nope", "attention_scores", "attention_weights", "value_heads",
    "attention_output", "post_attention_residual", "router_normalized",
    "router_logits", "router_scores", "ranking", "selected_ids",
    "routing_weights",
)


class EventError(RuntimeError):
    """Fail-closed event error carrying a stable reason code."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_bytes(path: Path, value: bytes, mode: int = 0o444) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("wb") as handle:
        handle.write(value)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, mode)
    os.replace(temporary, path)
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def atomic_json(path: Path, value: Any) -> str:
    payload = canonical_json(value)
    atomic_bytes(path, payload)
    return sha_bytes(payload)


@dataclass(frozen=True)
class InventoryEntry:
    ordinal: int
    key: str
    offset: int
    packed_bytes: int
    quantization: str
    logical_shape: tuple[int, ...]
    packed_sha256: str
    decoded_sha256: str


@dataclass(frozen=True)
class RetainedSpec:
    role: str
    key: str
    sha256: str
    dtype: str
    shape: tuple[int, ...]
    byte_length: int
    private_manifest_sha256: str | None = None


@dataclass
class DecodedTensor:
    shape: tuple[int, ...]
    canonical_bytes: bytes | None
    identity: str
    synthetic_zero: bool = False


class ShardHandle(Protocol):
    def read_at(self, offset: int, length: int, ordinal: int) -> bytes: ...
    def close(self) -> None: ...


class ShardProvider(Protocol):
    open_count: int
    read_count: int
    def open(self) -> ShardHandle: ...


class Decoder(Protocol):
    identity: str
    def decode(self, retained_path: Path, entry: InventoryEntry) -> DecodedTensor: ...


@dataclass
class DecoderPair:
    a: Decoder
    b: Decoder


class PositionalShardProvider:
    """Production provider with one explicit open and no fallback discovery."""

    def __init__(self, shard_path: Path):
        self.shard_path = shard_path
        self.open_count = 0
        self.read_count = 0

    def open(self) -> "_PositionalHandle":
        if self.open_count != 0:
            raise EventError("SECOND_SHARD_OPEN")
        self.open_count += 1
        descriptor = os.open(self.shard_path, os.O_RDONLY)
        return _PositionalHandle(descriptor, self)


class _PositionalHandle:
    def __init__(self, descriptor: int, provider: PositionalShardProvider):
        self.descriptor = descriptor
        self.provider = provider
        self.closed = False

    def read_at(self, offset: int, length: int, ordinal: int) -> bytes:
        if self.closed:
            raise EventError("READ_AFTER_CLOSE")
        if ordinal != self.provider.read_count:
            raise EventError("READ_ORDER")
        payload = os.pread(self.descriptor, length, offset)
        self.provider.read_count += 1
        return payload

    def close(self) -> None:
        if not self.closed:
            os.close(self.descriptor)
            self.closed = True


class F32Decoder:
    identity = "F32_CANONICAL_LE_IDENTITY_V1"

    def decode(self, retained_path: Path, entry: InventoryEntry) -> DecodedTensor:
        payload = retained_path.read_bytes()
        if len(payload) != math.prod(entry.logical_shape) * 4:
            raise EventError("F32_LENGTH")
        return DecodedTensor(entry.logical_shape, payload, sha_bytes(payload))


class Q5DecoderA:
    identity = "Q5_K_CORRECTED_KQUANTS_F016_A"

    def decode(self, retained_path: Path, entry: InventoryEntry) -> DecodedTensor:
        from prepare_f017_m1f0_real_reference import decode_q5_k_spec
        array = decode_q5_k_spec(retained_path.read_bytes()).reshape(entry.logical_shape)
        payload = np.asarray(array, dtype="<f4", order="C").tobytes()
        return DecodedTensor(entry.logical_shape, payload, sha_bytes(payload))


class Q5DecoderB:
    identity = "Q5_K_INDEPENDENT_SPEC_TRANSCRIPTION_B"

    def decode(self, retained_path: Path, entry: InventoryEntry) -> DecodedTensor:
        from qualify_f017_m1f0_q5_k_real import decode_q5_k_upstream_spec
        array = decode_q5_k_upstream_spec(retained_path.read_bytes()).reshape(entry.logical_shape)
        payload = np.asarray(array, dtype="<f4", order="C").tobytes()
        return DecodedTensor(entry.logical_shape, payload, sha_bytes(payload))


class Q8DecoderA:
    identity = "Q8_0_ACCEPTED_FIXED_ORDER_A"

    def decode(self, retained_path: Path, entry: InventoryEntry) -> DecodedTensor:
        from prepare_f017_m1f0_real_reference import decode_q8_0_spec
        array = decode_q8_0_spec(retained_path.read_bytes()).reshape(entry.logical_shape)
        payload = np.asarray(array, dtype="<f4", order="C").tobytes()
        return DecodedTensor(entry.logical_shape, payload, sha_bytes(payload))


class Q8DecoderB:
    """Independent scalar Q8_0 transcription; does not call decoder A."""

    identity = "Q8_0_INDEPENDENT_SCALAR_TRANSCRIPTION_B"

    def decode(self, retained_path: Path, entry: InventoryEntry) -> DecodedTensor:
        packed = memoryview(retained_path.read_bytes())
        elements = math.prod(entry.logical_shape)
        if elements % 32 or len(packed) != elements // 32 * 34:
            raise EventError("Q8_GEOMETRY")
        output = np.empty(elements, dtype="<f4")
        cursor = 0
        out = 0
        while cursor < len(packed):
            scale = np.float32(struct.unpack_from("<e", packed, cursor)[0])
            cursor += 2
            quants = np.frombuffer(packed[cursor:cursor + 32], dtype=np.int8)
            cursor += 32
            for index in range(32):
                output[out + index] = np.float32(scale * np.float32(quants[index]))
            out += 32
        payload = output.reshape(entry.logical_shape).tobytes(order="C")
        return DecodedTensor(entry.logical_shape, payload, sha_bytes(payload))


class SyntheticZeroDecoder:
    def __init__(self, identity: str, disagreement: bool = False):
        self.identity = identity
        self.disagreement = disagreement

    def decode(self, retained_path: Path, entry: InventoryEntry) -> DecodedTensor:
        if retained_path.stat().st_size != entry.packed_bytes:
            raise EventError("SYNTHETIC_GEOMETRY")
        digest = sha_bytes(canonical_json({"shape": entry.logical_shape, "zero": True}))
        if self.disagreement:
            digest = "f" * 64
        return DecodedTensor(entry.logical_shape, None, digest, synthetic_zero=True)


class RetainedAuthorityResolver:
    """No-fallback resolver for S0 and the three retained router inputs."""

    def __init__(self, paths: dict[str, Path], manifest_paths: dict[str, Path] | None = None,
                 after_override: dict[str, str] | None = None):
        self.paths = paths
        self.manifest_paths = manifest_paths or {}
        self.after_override = after_override or {}
        self.before: dict[str, str] = {}

    @staticmethod
    def _validate_file(path: Path, spec: RetainedSpec) -> str:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or path.is_symlink():
            raise EventError("RETAINED_NOT_REGULAR")
        if info.st_nlink != 1 or info.st_mode & 0o222:
            raise EventError("RETAINED_WRITABLE_ALIAS")
        if info.st_size != spec.byte_length:
            raise EventError("RETAINED_BYTE_LENGTH")
        digest = sha_file(path)
        if digest != spec.sha256:
            raise EventError("RETAINED_BEFORE_HASH")
        return digest

    def load(self, spec: RetainedSpec) -> np.ndarray:
        if spec.role not in self.paths:
            raise EventError("RETAINED_AUTHORITY_UNBOUND")
        path = self.paths[spec.role]
        digest = self._validate_file(path, spec)
        if spec.private_manifest_sha256 is not None:
            manifest = self.manifest_paths.get(spec.role)
            if manifest is None or sha_file(manifest) != spec.private_manifest_sha256:
                raise EventError("PRIVATE_MANIFEST_HASH")
        self.before[spec.role] = digest
        value = np.fromfile(path, dtype="<f4")
        if value.size != math.prod(spec.shape) or not np.isfinite(value).all():
            raise EventError("RETAINED_DTYPE_SHAPE")
        return value.reshape(spec.shape)

    def verify_after(self, specs: list[RetainedSpec]) -> dict[str, str]:
        result: dict[str, str] = {}
        for spec in specs:
            digest = self.after_override.get(spec.role, sha_file(self.paths[spec.role]))
            if digest != spec.sha256 or self.before.get(spec.role) != spec.sha256:
                raise EventError("RETAINED_AFTER_HASH")
            result[spec.role] = digest
        return result


class CrashSafeBanker:
    """Durable execution start, receipts, journal, synthetic ledger, terminal."""

    def __init__(self, root: Path, ledger_before: int, synthetic: bool):
        self.root = root
        self.synthetic = synthetic
        self.ledger_before = ledger_before
        self.receipts: list[dict[str, Any]] = []
        self.packed_bytes = 0
        self.terminal = False

    def start(self, authorization_sha256: str, inventory_digest: str) -> None:
        if self.root.exists() and any(self.root.iterdir()):
            raise EventError("ATTEMPT_ALREADY_EXISTS")
        self.root.mkdir(parents=True, exist_ok=True)
        atomic_json(self.root / "attempt.json", {"event_id": EVENT_ID, "attempt_id": ATTEMPT_ID,
                    "synthetic": self.synthetic, "no_retry": True})
        atomic_json(self.root / "execution-start.json", {
            "event_id": EVENT_ID, "attempt_id": ATTEMPT_ID,
            "authorization_sha256": authorization_sha256,
            "inventory_digest": inventory_digest, "ledger_before": self.ledger_before,
            "expected_reads": 9, "expected_packed_bytes": 132900864,
            "maximum_shard_opens": 1, "no_retry": True, "synthetic": self.synthetic,
        })
        atomic_json(self.root / "ledger.json", {"value": self.ledger_before, "synthetic": self.synthetic})

    def receipt(self, entry: InventoryEntry, packed_sha256: str, retained_name: str) -> None:
        sequence = len(self.receipts)
        if entry.ordinal != sequence:
            raise EventError("RECEIPT_SEQUENCE")
        receipt = {
            "sequence": sequence, "ordinal": entry.ordinal, "key": entry.key,
            "offset": entry.offset, "requested_bytes": entry.packed_bytes,
            "actual_bytes": entry.packed_bytes, "packed_sha256": packed_sha256,
            "retained_artifact": retained_name,
            "ledger_after": self.ledger_before + sequence + 1,
        }
        atomic_json(self.root / "receipts" / f"{sequence:02d}.json", receipt)
        self.receipts.append(receipt)
        self.packed_bytes += entry.packed_bytes
        atomic_json(self.root / "journal.json", {"entries": self.receipts})
        atomic_json(self.root / "ledger.json", {"value": receipt["ledger_after"], "synthetic": self.synthetic})

    def bank_terminal(self, status: str, reason: str, opens: int, decoder_agreements: int,
                      output_status: str) -> dict[str, Any]:
        if self.terminal:
            raise EventError("TERMINAL_ALREADY_BANKED")
        self.terminal = True
        value = {
            "status": status, "reason": reason, "consumed_reads": len(self.receipts),
            "packed_bytes": self.packed_bytes, "ledger": self.ledger_before + len(self.receipts),
            "shard_opens": opens, "decoder_agreements": decoder_agreements,
            "output_status": output_status, "no_retry": True, "synthetic": self.synthetic,
            "journal_sha256": sha_file(self.root / "journal.json") if self.receipts else None,
        }
        atomic_json(self.root / "terminal.json", value)
        return value


def retain_before_decode(root: Path, entry: InventoryEntry, payload: bytes) -> tuple[Path, str]:
    if len(payload) != entry.packed_bytes:
        raise EventError("SHORT_READ")
    target = root / "packed" / f"{entry.ordinal:02d}.bin"
    atomic_bytes(target, payload)
    digest = sha_file(target)
    if digest != entry.packed_sha256:
        raise EventError("PACKED_HASH_MISMATCH")
    return target, digest


def f32_bytes(value: np.ndarray) -> bytes:
    return np.asarray(value, dtype="<f4", order="C").tobytes()


def f64_bytes(value: np.ndarray) -> bytes:
    return np.asarray(value, dtype="<f8", order="C").tobytes()


def u16_bytes(value: np.ndarray) -> bytes:
    return np.asarray(value, dtype="<u2", order="C").tobytes()


class SyntheticComputationStage:
    """Geometry-exact synthetic computation; attention tensors are decoded zeros."""

    def __init__(self, wrong_epsilon: bool = False, wrong_vocabulary: bool = False):
        self.wrong_epsilon = wrong_epsilon
        self.wrong_vocabulary = wrong_vocabulary

    def compute(self, decoded: dict[str, DecodedTensor], retained: dict[str, np.ndarray]) -> dict[str, str]:
        if self.wrong_epsilon:
            raise EventError("EPSILON_IDENTITY")
        if any(not item.synthetic_zero for item in decoded.values()):
            raise EventError("SYNTHETIC_DECODER_CLASS")
        x = retained["canonical_s0"].astype(np.float32)
        gamma = retained["ffn_norm"].astype(np.float32)
        total = np.float32(0.0)
        for value in x:
            total = np.float32(total + np.float32(value * value))
        inv = np.float32(1.0 / np.sqrt(np.float32(np.float32(total / np.float32(6144.0)) + EPSILON)))
        norm = np.empty(6144, dtype=np.float32)
        for index in range(6144):
            norm[index] = np.float32(np.float32(x[index] * inv) * gamma[index])
        logits = np.zeros(256, dtype=np.float32)
        matrix = retained["router_matrix"]
        for row in range(256):
            acc = np.float32(0.0)
            for column in range(6144):
                acc = np.float32(acc + np.float32(matrix[row, column] * norm[column]))
            logits[row] = acc
        scores = 1.0 / (1.0 + np.exp(-logits.astype(np.float64))) + retained["correction_bias"].astype(np.float64)
        ranking = np.asarray(sorted(range(256), key=lambda i: (-float(scores[i]), i)), dtype=np.uint16)
        selected = ranking[:8]
        probabilities = 1.0 / (1.0 + np.exp(-logits[selected].astype(np.float64)))
        weights = 2.5 * probabilities / max(float(np.sum(probabilities, dtype=np.float64)), 2.0 ** -14)
        zeros = lambda shape: np.zeros(shape, dtype=np.float32)
        arrays: dict[str, tuple[np.ndarray, Callable[[np.ndarray], bytes]]] = {
            "input_hidden": (x, f32_bytes), "attention_normalized": (zeros(6144), f32_bytes),
            "query_rank": (zeros(2048), f32_bytes), "query_rank_normalized": (zeros(2048), f32_bytes),
            "query_heads": (zeros(16384), f32_bytes), "kv_raw": (zeros(576), f32_bytes),
            "kv_normalized": (zeros(512), f32_bytes), "key_nope": (zeros((64, 512)), f32_bytes),
            "attention_scores": (zeros(64), f32_bytes), "attention_weights": (np.ones(64, dtype=np.float32), f32_bytes),
            "value_heads": (zeros((64, 256)), f32_bytes), "attention_output": (zeros(6144), f32_bytes),
            "post_attention_residual": (x, f32_bytes), "router_normalized": (norm, f32_bytes),
            "router_logits": (logits, f32_bytes), "router_scores": (scores, f64_bytes),
            "ranking": (ranking, u16_bytes), "selected_ids": (selected, u16_bytes),
            "routing_weights": (weights, f64_bytes),
        }
        if self.wrong_vocabulary:
            arrays["attention_residual"] = arrays.pop("post_attention_residual")
        if tuple(arrays) != CANONICAL_STAGE_NAMES:
            raise EventError("STAGE_VOCABULARY")
        return {name: sha_bytes(serializer(value)) for name, (value, serializer) in arrays.items()}

    @staticmethod
    def execute_expert() -> None:
        raise EventError("EXPERT_EXECUTION_PROHIBITED")


class ProductionComputationStage:
    """Accepted fixed-order oracle with canonical authorization stage names."""

    def compute(self, decoded: dict[str, DecodedTensor], retained: dict[str, np.ndarray]) -> dict[str, str]:
        from prepare_f017_m1f0_real_reference import compose_oracle, strict_matvec

        tensors: dict[str, np.ndarray] = {}
        for key, tensor in decoded.items():
            if tensor.canonical_bytes is None:
                raise EventError("PRODUCTION_DECODED_BYTES_MISSING")
            tensors[key] = np.frombuffer(tensor.canonical_bytes, dtype="<f4").reshape(tensor.shape)
        tensors["blk.3.ffn_norm.weight"] = retained["ffn_norm"]
        tensors["blk.3.ffn_gate_inp.weight"] = retained["router_matrix"]
        tensors["blk.3.exp_probs_b.bias"] = retained["correction_bias"]
        result = compose_oracle(
            retained["canonical_s0"],
            lambda name: tensors[name],
            lambda name, values: strict_matvec(tensors[name], values),
            lambda name, head, values: strict_matvec(tensors[name][head], values),
        )
        hashes = result["stage_hashes"]
        canonical = {
            "input_hidden": hashes["input_hidden"],
            "attention_normalized": hashes["attention_normalized"],
            "query_rank": hashes["query_rank"],
            "query_rank_normalized": hashes["query_rank_normalized"],
            "query_heads": hashes["query_heads"],
            "kv_raw": hashes["kv_raw"],
            "kv_normalized": hashes["kv_normalized"],
            "key_nope": hashes["key_nope"],
            "attention_scores": hashes["attention_scores"],
            "attention_weights": hashes["attention_weights"],
            "value_heads": hashes["value_heads"],
            "attention_output": hashes["attention_output"],
            "post_attention_residual": hashes["attention_residual"],
            "router_normalized": hashes["router_normalized"],
            "router_logits": hashes["router_logits"],
            "router_scores": result["router_scores_sha256"],
            "ranking": result["ranking_sha256"],
            "selected_ids": result["top8_ids_sha256"],
            "routing_weights": result["routing_weights_sha256"],
        }
        if tuple(canonical) != CANONICAL_STAGE_NAMES:
            raise EventError("STAGE_VOCABULARY")
        return canonical

    @staticmethod
    def execute_expert() -> None:
        raise EventError("EXPERT_EXECUTION_PROHIBITED")


class RepresentativeM1F0Executor:
    def __init__(self, authorization: dict[str, Any], authorization_sha256: str,
                 provider: ShardProvider, decoders: dict[str, DecoderPair],
                 resolver: RetainedAuthorityResolver, computation: Any,
                 state_root: Path, retention_root: Path, synthetic: bool = False,
                 retention_writer: Callable[[Path, bytes], None] = atomic_bytes):
        self.authorization = authorization
        self.authorization_sha256 = authorization_sha256
        self.provider = provider
        self.decoders = decoders
        self.resolver = resolver
        self.computation = computation
        self.state_root = state_root
        self.retention_root = retention_root
        self.synthetic = synthetic
        self.retention_writer = retention_writer

    def _gate(self) -> tuple[list[InventoryEntry], list[RetainedSpec]]:
        auth = self.authorization
        if auth.get("schema") != SCHEMA or auth.get("schema_version") != SCHEMA_VERSION:
            raise EventError("AUTHORIZATION_SCHEMA")
        if auth.get("status") != "PREPARED_REVIEW_REQUIRED":
            raise EventError("AUTHORIZATION_STATUS")
        if auth.get("authoritative_repository", {}).get("commit_sha256") != EXPECTED_HEAD:
            raise EventError("AUTHORITATIVE_HEAD")
        semantic = auth.get("semantic_authority", {})
        if semantic.get("representative_boundary_v3", {}).get("sha256") != EXPECTED_BOUNDARY or semantic.get("semantic_graph_v2", {}).get("sha256") != EXPECTED_GRAPH or semantic.get("epsilon_adjudication", {}).get("sha256") != EXPECTED_EPSILON_ADJUDICATION:
            raise EventError("SEMANTIC_AUTHORITY")
        release = auth.get("authorization", {})
        if release.get("real_event_authorized") is not False:
            raise EventError("REAL_EVENT_GATE")
        if not self.synthetic and release.get("separate_execution_release_required") is not True:
            raise EventError("EXECUTION_RELEASE_REQUIRED")
        event = auth["event_shape"]
        if event != {"checkpoint_payload_reads": 9, "retained_router_injections": 3,
                     "canonical_retained_s0_inputs": 1, "expert_payload_reads": 0}:
            raise EventError("EVENT_SHAPE")
        if auth["execution_semantics"]["rmsnorm"] != {
            "epsilon_source": "f32(1e-5)", "epsilon_exact_decimal": "9.999999747378752e-6",
            "epsilon_bits_hex": EPSILON_BITS, "epsilon_dtype": "IEEE-754 binary32",
            "accumulator_dtype": "IEEE-754 binary32",
        }:
            raise EventError("EPSILON_IDENTITY")
        separation = auth.get("surface_separation", {})
        if separation.get("historical_direct_dprefix_outputs") != "PROHIBITED_AS_INPUT" or separation.get("representative_route_derived_from_new_post_attention_residual") is not True:
            raise EventError("DIRECT_DPREFIX_REUSE_PROHIBITED")
        inventory = [InventoryEntry(
            item["ordinal"], item["key"], item["offset"], item["packed_bytes"],
            item["quantization"], tuple(item["logical_shape"]), item["packed_sha256"],
            item["decoded_sha256"],
        ) for item in auth["attention_payload_inventory"]]
        observed = tuple((item.ordinal, item.key, item.offset, item.packed_bytes, item.quantization, item.logical_shape) for item in inventory)
        if observed != FROZEN_INVENTORY or sum(item.packed_bytes for item in inventory) != 132900864:
            raise EventError("INVENTORY_ALLOWLIST")
        specs = [RetainedSpec(item["role"], item["key"], item["sha256"], item["dtype"],
                              tuple(item["shape"]), item["byte_length"], item.get("private_manifest_sha256"))
                 for item in auth["retained_inputs"]]
        if [item.role for item in specs] != ["canonical_s0", "ffn_norm", "router_matrix", "correction_bias"]:
            raise EventError("RETAINED_INPUT_ROLES")
        if not self.synthetic:
            for spec in specs:
                digest, shape, byte_length = FROZEN_RETAINED[spec.role]
                if (spec.sha256, spec.shape, spec.byte_length) != (digest, shape, byte_length):
                    raise EventError("RETAINED_INPUT_IDENTITY")
            if auth.get("executor", {}).get("sha256") != sha_file(Path(__file__).resolve()):
                raise EventError("EXECUTOR_SHA")
        return inventory, specs

    def execute(self) -> dict[str, Any]:
        inventory, specs = self._gate()
        inventory_digest = sha_bytes(canonical_json([entry.__dict__ for entry in inventory]))
        banker = CrashSafeBanker(self.state_root, LEDGER_BEFORE, self.synthetic)
        banker.start(self.authorization_sha256, inventory_digest)
        decoded: dict[str, DecodedTensor] = {}
        agreements = 0
        handle: ShardHandle | None = None
        try:
            handle = self.provider.open()
            if self.provider.open_count > 1:
                raise EventError("SECOND_SHARD_OPEN")
            for entry in inventory:
                if self.provider.read_count != entry.ordinal:
                    raise EventError("READ_ORDER")
                payload = handle.read_at(entry.offset, entry.packed_bytes, entry.ordinal)
                if len(payload) != entry.packed_bytes:
                    raise EventError("SHORT_READ")
                # Consumption is counted when the exact-size positional read succeeds.
                target = self.retention_root / "packed" / f"{entry.ordinal:02d}.bin"
                digest = sha_bytes(payload)
                banker.receipt(entry, digest, str(target.relative_to(self.retention_root)))
                self.retention_writer(target, payload)
                if not target.is_file() or sha_file(target) != digest:
                    raise EventError("RETAINED_PACKED_HASH")
                if digest != entry.packed_sha256:
                    raise EventError("PACKED_HASH_MISMATCH")
                pair = self.decoders[entry.quantization]
                a = pair.a.decode(target, entry)
                b = pair.b.decode(target, entry)
                if a.identity != b.identity or a.shape != entry.logical_shape or b.shape != entry.logical_shape:
                    raise EventError("DECODER_DISAGREEMENT")
                if a.identity != entry.decoded_sha256:
                    raise EventError("DECODED_HASH_MISMATCH")
                decoded[entry.key] = a
                agreements += 1
            if self.provider.read_count != 9:
                raise EventError("READ_RECONCILIATION")
            retained = {spec.role: self.resolver.load(spec) for spec in specs}
            stages = self.computation.compute(decoded, retained)
            if tuple(stages) != CANONICAL_STAGE_NAMES:
                raise EventError("STAGE_VOCABULARY")
            after = self.resolver.verify_after(specs)
            if len(banker.receipts) != 9 or banker.packed_bytes != 132900864:
                raise EventError("BANKER_RECONCILIATION")
            terminal = banker.bank_terminal("COMPLETE", "NONE", self.provider.open_count, agreements,
                                            "REPRESENTATIVE_ROUTE_ONLY")
            return {
                "classification": "SYNTHETIC" if self.synthetic else "REAL",
                "event_shape": {"checkpoint_payload_reads": self.provider.read_count,
                                "retained_router_injections": 3,
                                "canonical_retained_s0_inputs": 1,
                                "shard_opens": self.provider.open_count,
                                "expert_payload_reads": 0},
                "stage_sha256": stages, "retained_after_sha256": after, "terminal": terminal,
            }
        except Exception as exc:
            reason = exc.code if isinstance(exc, EventError) else type(exc).__name__
            if not banker.terminal:
                banker.bank_terminal("TERMINAL_FAILURE", reason, self.provider.open_count,
                                     agreements, "NO_OUTPUT_AUTHORITY")
            raise
        finally:
            if handle is not None:
                handle.close()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_bound_authorization(auth_path: Path, repository_root: Path) -> dict[str, Any]:
    """Resolve the append-only v2 wrapper to its hash-bound candidate bytes."""
    wrapper = load_json(auth_path)
    candidate_binding = wrapper.get("authorization_candidate", {})
    relative = Path(str(candidate_binding.get("path", "")))
    if relative.is_absolute() or ".." in relative.parts:
        raise EventError("AUTHORIZATION_CANDIDATE_PATH")
    candidate_path = repository_root / relative
    if not candidate_path.is_file() or sha_file(candidate_path) != candidate_binding.get("sha256"):
        raise EventError("AUTHORIZATION_CANDIDATE_SHA")
    candidate = load_json(candidate_path)
    candidate["status"] = wrapper.get("status")
    candidate["executor"] = wrapper.get("executor")
    candidate["synthetic_rehearsal"] = wrapper.get("synthetic_rehearsal")
    candidate["authorization"] = wrapper.get("authorization")
    candidate["authorization_wrapper_sha256"] = sha_file(auth_path)
    return candidate


def validate_preflight(auth_path: Path) -> dict[str, Any]:
    repository_root = Path(__file__).resolve().parents[2]
    auth = load_bound_authorization(auth_path, repository_root)
    source_sha = sha_file(Path(__file__).resolve())
    if auth.get("executor", {}).get("sha256") != source_sha:
        raise EventError("EXECUTOR_SHA")
    if auth.get("authorization", {}).get("real_event_authorized") is not False:
        raise EventError("REAL_EVENT_GATE")
    return {"result": "PRODUCTION_BINDINGS_RESOLVED", "surfaces": "9_READS+3_RETAINED+S0",
            "checkpoint_reads": 0, "shard_opens": 0, "ledger": 166,
            "real_event_authorized": False}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    if not args.preflight_only or args.authorization is None:
        print(json.dumps({"result": "REJECTED", "reason": "SEPARATE_REAL_EXECUTION_RELEASE_REQUIRED"}, sort_keys=True))
        return 2
    try:
        print(json.dumps(validate_preflight(args.authorization), sort_keys=True))
        return 0
    except EventError as exc:
        print(json.dumps({"result": "FAIL", "reason": exc.code}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
