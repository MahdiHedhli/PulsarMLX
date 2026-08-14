#!/usr/bin/env python3
"""Checkpoint-free, route-independent contracts for the future F017 M1-F gate.

This module deliberately has no checkpoint reader.  It validates catalog metadata,
dispatch evidence, decoder comparisons, numerical summaries, and repeat/lifecycle
evidence supplied by callers.  Expert identities and route weights remain inputs to
the future reviewed execution config; this preparation code does not select them.
"""

from __future__ import annotations

import hashlib
import json
import math
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Mapping, Sequence


CATALOG = "docs/research/glm52/raw/f016-c01-catalog-0001.json"
BLOCK_LAYOUT = {"IQ2_XXS": (256, 66), "IQ3_XXS": (256, 98)}
ROLES = ("gate", "up", "down")
PROJECTION_NAMES = {role: f"blk.3.ffn_{role}_exps.weight" for role in ROLES}


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_catalog_metadata(root: Path) -> dict[str, object]:
    catalog_path = root / CATALOG
    catalog_raw = catalog_path.read_bytes()
    catalog = json.loads(catalog_raw)
    by_name = {item["name"]: item for item in catalog["tensors"]}
    projections: dict[str, object] = {}
    expert_count: int | None = None
    for role, name in PROJECTION_NAMES.items():
        item = by_name[name]
        dims = [int(v) for v in item["dims"]]
        if len(dims) != 3:
            raise ValueError(f"{name}: expected projection-major 3-D aggregate")
        if expert_count is None:
            expert_count = dims[2]
        elif dims[2] != expert_count:
            raise ValueError("aggregate expert-count disagreement")
        quant = str(item["type"])
        if quant not in BLOCK_LAYOUT:
            raise ValueError(f"{name}: unsupported quant block layout {quant}")
        block_elements, block_bytes = BLOCK_LAYOUT[quant]
        elements = dims[0] * dims[1]
        if elements % block_elements:
            raise ValueError(f"{name}: quant block alignment")
        stride = elements // block_elements * block_bytes
        projections[role] = {
            "name": name,
            "base": int(item["data_offset_abs"]),
            "stride": stride,
            "packed_total_length": stride * dims[2],
            "quantization": quant,
            "dims": dims,
            "logical_shape": [dims[1], dims[0]],
            "shard": item["file"],
            "quant_block_elements": block_elements,
            "quant_block_bytes": block_bytes,
        }
    result: dict[str, object] = {
        "expert_count": expert_count,
        "indexing": "zero_based",
        "layout": "projection_major_then_expert_major",
        "catalog": CATALOG,
        "catalog_sha256": sha256(catalog_raw),
        "projections": projections,
    }
    validate_aggregate_metadata(result)
    return result


def validate_aggregate_metadata(metadata: Mapping[str, object]) -> None:
    if metadata.get("indexing") != "zero_based":
        raise ValueError("expert indexing must be zero-based")
    if metadata.get("layout") != "projection_major_then_expert_major":
        raise ValueError("projection-major/expert-major storage contract")
    count = int(metadata["expert_count"])
    if count <= 0:
        raise ValueError("expert count")
    projections = metadata["projections"]
    if not isinstance(projections, Mapping) or set(projections) != set(ROLES):
        raise ValueError("exact gate/up/down aggregate metadata required")
    for role in ROLES:
        raw = projections[role]
        if not isinstance(raw, Mapping):
            raise ValueError(f"{role}: projection metadata")
        dims = [int(v) for v in raw["dims"]]
        stride = int(raw["stride"])
        block_elements = int(raw["quant_block_elements"])
        block_bytes = int(raw["quant_block_bytes"])
        if len(dims) != 3 or dims[2] != count:
            raise ValueError(f"{role}: expert axis")
        if dims[0] * dims[1] % block_elements:
            raise ValueError(f"{role}: quant block alignment")
        expected_stride = dims[0] * dims[1] // block_elements * block_bytes
        if stride != expected_stride or stride % block_bytes:
            raise ValueError(f"{role}: per-expert stride")
        if int(raw["packed_total_length"]) != stride * count:
            raise ValueError(f"{role}: truncated aggregate tensor")


def derive_expert_triplet(metadata: Mapping[str, object], expert_id: int) -> dict[str, dict[str, object]]:
    validate_aggregate_metadata(metadata)
    count = int(metadata["expert_count"])
    if not 0 <= expert_id < count:
        raise ValueError(f"expert id {expert_id} outside [0,{count})")
    projections = metadata["projections"]
    assert isinstance(projections, Mapping)
    triplet: dict[str, dict[str, object]] = {}
    for role in ROLES:
        raw = projections[role]
        assert isinstance(raw, Mapping)
        base, stride = int(raw["base"]), int(raw["stride"])
        limit = base + int(raw["packed_total_length"])
        start = base + expert_id * stride
        end = start + stride
        if start < base or end > limit or end <= start:
            raise ValueError(f"{role}: expert slice overflow/truncation")
        triplet[role] = {
            "aggregate_name": raw["name"], "expert_id": expert_id,
            "start": start, "end": end, "packed_length": stride,
            "quantization": raw["quantization"], "logical_shape": raw["logical_shape"],
            "shard": raw["shard"], "quant_block_aligned": stride % int(raw["quant_block_bytes"]) == 0,
        }
    return triplet


def validate_all_expert_slices(metadata: Mapping[str, object]) -> None:
    count = int(metadata["expert_count"])
    for role in ROLES:
        intervals = [derive_expert_triplet(metadata, expert)[role] for expert in range(count)]
        for left, right in zip(intervals, intervals[1:]):
            if left["end"] != right["start"]:
                raise ValueError(f"{role}: overlap or gap")


DISPATCH_STAGES = (
    "attention_projection", "attention_output", "router_projection",
    "routed_expert_gate", "routed_expert_up", "routed_expert_down",
    "shared_expert_gate", "shared_expert_up", "shared_expert_down",
    "normalization", "non_mlx",
)


class DispatchRecorder:
    """Separate conceptual operations from native launches (which may be fused)."""

    def __init__(self) -> None:
        self.conceptual_records: list[dict[str, object]] = []
        self.native_records: list[dict[str, object]] = []

    def record_conceptual(self, stage: str, multiplicity: int) -> None:
        if stage not in DISPATCH_STAGES:
            raise ValueError(f"unknown conceptual dispatch stage {stage}")
        self.conceptual_records.append({"stage": stage, "multiplicity": multiplicity})

    def record_native(
        self, event: str, backend: str, dispatches_per_unit: int, scaling: str,
        *, fallback: bool = False, reference: bool = False, scaffold: bool = False,
        backend_error: bool = False,
    ) -> None:
        if not event:
            raise ValueError("native event identity")
        if scaling not in {"constant_per_repeat", "per_selected_expert"}:
            raise ValueError("native dispatch scaling")
        self.native_records.append({
            "event": event, "backend": backend, "dispatches_per_unit": dispatches_per_unit,
            "scaling": scaling, "fallback": fallback, "reference": reference,
            "scaffold": scaffold, "backend_error": backend_error,
        })

    def reconcile(self, selected_expert_count: int) -> dict[str, int]:
        return reconcile_dispatches(self.conceptual_records, self.native_records, selected_expert_count)


def reconcile_dispatches(
    conceptual_records: Sequence[Mapping[str, object]],
    native_records: Sequence[Mapping[str, object]],
    selected_expert_count: int,
) -> dict[str, int]:
    """Reconcile observed dispatches without freezing a route-dependent total."""
    if selected_expert_count <= 0:
        raise ValueError("selected expert count")
    seen = [str(record["stage"]) for record in conceptual_records]
    if set(seen) != set(DISPATCH_STAGES) or len(seen) != len(set(seen)):
        raise ValueError("complete unique conceptual dispatch stages required")
    conceptual_operations = 0
    for record in conceptual_records:
        stage = str(record["stage"])
        multiplicity = int(record["multiplicity"])
        routed = stage.startswith("routed_expert_")
        expected_multiplicity = selected_expert_count if routed else 1
        if multiplicity != expected_multiplicity:
            raise ValueError(f"{stage}: conceptual multiplicity")
        conceptual_operations += multiplicity
    native_ids = [str(record["event"]) for record in native_records]
    if not native_ids or len(native_ids) != len(set(native_ids)):
        raise ValueError("unique native dispatch events required")
    constant_native = 0
    per_expert_native = 0
    observed_native = 0
    for record in native_records:
        event = str(record["event"])
        backend = str(record["backend"])
        per_unit = int(record["dispatches_per_unit"])
        scaling = str(record["scaling"])
        if any(bool(record.get(field, False)) for field in ("fallback", "reference", "scaffold", "backend_error")):
            raise ValueError(f"{event}: forbidden fallback/reference/scaffold/error activity")
        if backend == "MLX_NATIVE":
            if scaling == "per_selected_expert":
                per_expert_native += per_unit
                observed_native += per_unit * selected_expert_count
            else:
                constant_native += per_unit
                observed_native += per_unit
        elif backend == "CPU_NON_MODEL":
            if per_unit:
                raise ValueError(f"{event}: CPU stage cannot claim native dispatch")
        else:
            raise ValueError(f"{event}: backend")
    expected = constant_native + selected_expert_count * per_expert_native
    if observed_native != expected:
        raise ValueError("native dispatch reconciliation")
    return {
        "conceptual_operations": conceptual_operations,
        "constant_native_dispatches": constant_native,
        "per_selected_expert_native_dispatches": per_expert_native,
        "selected_expert_count": selected_expert_count,
        "expected_native_dispatches": expected,
        "observed_native_dispatches": observed_native,
    }


@dataclass(frozen=True)
class DecoderImplementation:
    name: str
    source_sha256: str
    dependency_fingerprint: str
    decode: Callable[[bytes], bytes]


def qualify_decoder_exact(packed: bytes, implementations: Sequence[DecoderImplementation], element_count: int) -> dict[str, object]:
    if not packed:
        raise ValueError("empty/truncated packed payload")
    if len(implementations) < 2:
        raise ValueError("at least two independent decoder implementations")
    identities = {(item.source_sha256, item.dependency_fingerprint) for item in implementations}
    if len(identities) != len(implementations):
        raise ValueError("decoder implementations are not independent")
    outputs: list[bytes] = []
    for implementation in implementations:
        if len(implementation.source_sha256) != 64:
            raise ValueError("decoder source identity")
        output = implementation.decode(packed)
        if len(output) != element_count * 4:
            raise ValueError("decoded canonical f32 length")
        values = struct.unpack(f"<{element_count}f", output)
        if not all(math.isfinite(v) for v in values):
            raise ValueError("non-finite decoded value")
        outputs.append(output)
    if any(output != outputs[0] for output in outputs[1:]):
        raise ValueError("decoder exact byte mismatch")
    values = struct.unpack(f"<{element_count}f", outputs[0])
    return {
        "packed_sha256": sha256(packed), "decoded_sha256": sha256(outputs[0]),
        "decoded_element_count": element_count, "canonical_serialization": "little_endian_f32_no_padding",
        "implementation_count": len(implementations),
        "implementation_names": [item.name for item in implementations],
        "non_finite_count": 0,
        "signed_zero_count": sum(v == 0.0 and math.copysign(1.0, v) < 0 for v in values),
    }


def tier_b_metrics(candidate: Sequence[float], oracle: Sequence[float]) -> dict[str, float]:
    if len(candidate) != len(oracle) or not candidate:
        raise ValueError("numerical vector shape")
    if not all(math.isfinite(v) for v in (*candidate, *oracle)):
        raise ValueError("non-finite numerical stage")
    errors = [abs(a - b) for a, b in zip(candidate, oracle, strict=True)]
    rmse = math.sqrt(sum(e * e for e in errors) / len(errors))
    dot = sum(a * b for a, b in zip(candidate, oracle, strict=True))
    nc = math.sqrt(sum(a * a for a in candidate))
    no = math.sqrt(sum(b * b for b in oracle))
    cosine = 1.0 if nc == no == 0.0 else dot / (nc * no) if nc and no else 0.0
    return {"max_abs": max(errors), "rmse": rmse, "cosine": cosine}


def validate_repeat_lifecycle(evidence: Mapping[str, object], expected_repeats: int = 10) -> None:
    repeats = evidence.get("repeats")
    if not isinstance(repeats, list) or len(repeats) != expected_repeats:
        raise ValueError("exact complete repeat count")
    required_hashes = tuple(evidence.get("required_stage_hashes", ()))
    if not required_hashes:
        raise ValueError("load-bearing stage hashes")
    first = repeats[0]
    for ordinal, repeat in enumerate(repeats):
        if repeat.get("ordinal") != ordinal:
            raise ValueError("repeat ordinal")
        hashes = repeat.get("stage_hashes")
        if not isinstance(hashes, Mapping) or set(hashes) != set(required_hashes):
            raise ValueError("repeat stage hashes")
        if hashes != first.get("stage_hashes"):
            raise ValueError("repeat nondeterminism")
        if repeat.get("native_dispatches") != repeat.get("expected_native_dispatches"):
            raise ValueError("repeat dispatch mismatch")
        if any(int(repeat.get(field, 0)) != 0 for field in ("fallback", "reference", "scaffold", "backend_errors")):
            raise ValueError("repeat isolation")
    lifecycle = evidence.get("lifecycle")
    if lifecycle != {"teardown_complete": True, "in_flight_work": 0, "stale_generations": 0}:
        raise ValueError("lifecycle not reconciled")


def validate_execution_config_shape(config: Mapping[str, object]) -> None:
    required = {
        "schema", "schema_version", "status", "identities", "checkpoint_bindings", "contracts",
        "input_fixture", "route_artifact", "selected_experts", "routing_pairs", "tensor_allowlist",
        "decoder_contracts", "oracle", "numerical_contract", "execution", "attempt_state", "evidence_destination",
    }
    if set(config) != required:
        raise ValueError("typed execution config fields; loose overrides forbidden")
    if config["status"] != "PREPARED_NOT_AUTHORIZED":
        raise ValueError("M1-F is not authorized")
    selected = config["selected_experts"]
    routing_pairs = config["routing_pairs"]
    if (
        not isinstance(selected, list)
        or len(selected) != 8
        or len({int(value) for value in selected}) != 8
        or any(not 0 <= int(value) < 256 for value in selected)
    ):
        raise ValueError("exact eight unique selected experts")
    if not isinstance(routing_pairs, list) or len(routing_pairs) != 8:
        raise ValueError("exact eight atomic routing pairs")
    pair_ids: list[int] = []
    for pair in routing_pairs:
        if not isinstance(pair, Mapping) or set(pair) != {"expert_id", "routing_weight"}:
            raise ValueError("atomic routing pair shape")
        expert_id = int(pair["expert_id"])
        weight = float(pair["routing_weight"])
        if not 0 <= expert_id < 256 or not math.isfinite(weight) or weight <= 0.0:
            raise ValueError("atomic routing pair value")
        pair_ids.append(expert_id)
    if len(set(pair_ids)) != 8 or set(pair_ids) != {int(value) for value in selected}:
        raise ValueError("selected experts and atomic routing pairs disagree")
    execution = config["execution"]
    if not isinstance(execution, Mapping) or execution.get("repeat_count") != 10 or execution.get("auto_retry") is not False:
        raise ValueError("execution contract")
    if any(key in config for key in ("tensor_cli", "expert_override", "route_override", "loose_args")):
        raise ValueError("loose overrides forbidden")
