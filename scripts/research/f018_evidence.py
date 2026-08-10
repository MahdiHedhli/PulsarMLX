#!/usr/bin/env python3
"""Feature 018 public evidence parsing and semantic validation."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Iterable

from f018_numerical_contract import CLASSES
from glm52_telemetry import assert_public_safe

_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _unique_pairs(pairs: Iterable[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key: {key}")
        result[key] = value
    return result


def load_unique_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(), object_pairs_hook=_unique_pairs)
    if not isinstance(value, dict):
        raise ValueError("Feature 018 evidence root must be an object")
    return value


def _samples(record: dict[str, Any]) -> list[float]:
    timing = record.get("timing")
    if not isinstance(timing, dict):
        raise ValueError("timing must be an object")
    raw = timing.get("measured_samples_seconds")
    if not isinstance(raw, list) or not raw:
        raise ValueError("measured_samples_seconds must be nonempty")
    samples = [float(value) for value in raw]
    if not all(math.isfinite(value) and value >= 0.0 for value in samples):
        raise ValueError("timing samples must be finite and nonnegative")
    if timing.get("sample_count") != len(samples):
        raise ValueError("sample_count does not match raw samples")
    expected = {
        "minimum_seconds": min(samples),
        "maximum_seconds": max(samples),
        "mean_seconds": sum(samples) / len(samples),
    }
    for key, value in expected.items():
        if not math.isclose(float(timing.get(key, math.nan)), value, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError(f"{key} does not match raw samples")
    return samples


def validate_record(record: dict[str, Any]) -> dict[str, Any]:
    try:
        assert_public_safe(record)
    except ValueError as exc:
        raise ValueError(f"record is not public-safe: {exc}") from exc
    if record.get("schema") == "pulsarmlx.research.f018-direct-iq2-routed-expert":
        return _validate_routed_expert_record(record)
    if record.get("schema") != "pulsarmlx.research.f018-direct-iq2-xxs":
        raise ValueError("unexpected Feature 018 schema")
    if record.get("schema_version") != "1.0.0":
        raise ValueError("unexpected Feature 018 schema_version")
    if record.get("actual_status") != "passed":
        raise ValueError("only passed Feature 018 evidence is publishable")
    if record.get("classification") not in CLASSES:
        raise ValueError("unsupported numerical classification")
    source = record.get("source")
    if not isinstance(source, dict) or not _HEX40.fullmatch(str(source.get("commit", ""))):
        raise ValueError("source commit must be lowercase 40-character SHA")
    if source.get("dirty") is not False:
        raise ValueError("source must be clean")
    kernel = record.get("kernel")
    if not isinstance(kernel, dict) or kernel.get("quantization") != "IQ2_XXS":
        raise ValueError("kernel quantization must be IQ2_XXS")
    if kernel.get("cpu_fallback_count") != 0:
        raise ValueError("cpu_fallback_count must be zero")
    if kernel.get("complete_f32_weight_materialized_bytes") != 0:
        raise ValueError("complete_f32_weight_materialized_bytes must be zero")
    if record.get("resource", {}).get("level") != "normal":
        raise ValueError("resource level must be normal for a passed record")
    if not isinstance(record.get("claim_boundary"), str) or not record["claim_boundary"]:
        raise ValueError("claim_boundary is required")
    if not record.get("unsupported_interpretations"):
        raise ValueError("unsupported_interpretations are required")
    samples = _samples(record)
    correctness = record.get("correctness")
    if not isinstance(correctness, dict):
        raise ValueError("correctness must be an object")
    required_correctness = {
        "contract_version",
        "exact_f32_bits",
        "deterministic_repetitions",
        "unique_output_hashes",
        "candidate_output_sha256",
        "f32_bit_mismatch_count",
        "first_f32_bit_mismatch_index",
        "signed_zero_mismatch_count",
        "elementwise_mismatch_count",
        "maximum_absolute_error",
        "mean_absolute_error",
        "rmse",
        "maximum_meaningful_relative_error",
        "cosine_similarity",
        "norm_ratio",
        "absolute_tolerance",
        "relative_tolerance",
        "cosine_minimum",
        "norm_ratio_minimum",
        "norm_ratio_maximum",
    }
    missing = sorted(required_correctness - correctness.keys())
    if missing:
        raise ValueError(f"correctness fields missing: {missing}")
    if correctness["contract_version"] != "f018-numerical-v1":
        raise ValueError("correctness contract version mismatch")
    if correctness.get("classification", record["classification"]) != record["classification"]:
        raise ValueError("correctness classification does not match record")
    if not _HEX64.fullmatch(str(correctness["candidate_output_sha256"])):
        raise ValueError("candidate output SHA-256 is malformed")
    if correctness["elementwise_mismatch_count"] != 0:
        raise ValueError("elementwise numerical mismatch is not qualified")
    if correctness["signed_zero_mismatch_count"] != 0:
        raise ValueError("signed-zero mismatch is not admitted for this record")
    if correctness["unique_output_hashes"] != 1:
        raise ValueError("deterministic output hash count must be one")
    if correctness["deterministic_repetitions"] != len(samples):
        raise ValueError("deterministic repetition count must match measured samples")
    if float(correctness["cosine_similarity"]) < float(correctness["cosine_minimum"]):
        raise ValueError("cosine similarity is below the frozen minimum")
    norm_ratio = float(correctness["norm_ratio"])
    if not float(correctness["norm_ratio_minimum"]) <= norm_ratio <= float(
        correctness["norm_ratio_maximum"]
    ):
        raise ValueError("norm ratio is outside the frozen interval")
    for component in ("dispatch", "synchronization", "kernel"):
        summary = record["timing"].get(component)
        if summary is None:
            if component != "kernel":
                raise ValueError(f"{component} timing is required")
            continue
        if not isinstance(summary, dict):
            raise ValueError(f"{component} timing must be an object or null")
        component_samples = summary.get("measured_samples_seconds")
        if not isinstance(component_samples, list) or len(component_samples) != len(samples):
            raise ValueError(f"{component} raw samples must align with total samples")
    binding = record.get("binding", {})
    if isinstance(binding, dict) and "tensor_name" in binding:
        _validate_real_matrix_record(record)
    return record


def _validate_routed_expert_record(record: dict[str, Any]) -> dict[str, Any]:
    if record.get("schema_version") != "1.0.0" or record.get("actual_status") != "passed":
        raise ValueError("routed-expert evidence must use schema 1.0.0 and pass")
    if record.get("classification") not in CLASSES:
        raise ValueError("routed-expert classification is unsupported")
    source = record.get("source", {})
    if not _HEX40.fullmatch(str(source.get("commit", ""))) or source.get("dirty") is not False:
        raise ValueError("routed-expert source must be a clean commit")
    checkpoint = record.get("checkpoint", {})
    if not _HEX64.fullmatch(str(checkpoint.get("checkpoint_set_sha256", ""))):
        raise ValueError("routed-expert checkpoint set SHA-256 is malformed")
    if checkpoint.get("file_count") != 6 or checkpoint.get("total_bytes") != 238_458_632_928:
        raise ValueError("routed-expert checkpoint identity changed")
    binding = record.get("binding", {})
    if (
        binding.get("layer") != 3
        or binding.get("expert_id") != 15
        or binding.get("gate_quantization") != "IQ2_XXS"
        or binding.get("up_quantization") != "IQ2_XXS"
        or binding.get("down_quantization") != "IQ3_XXS"
    ):
        raise ValueError("routed-expert frozen tensor binding changed")
    routes = binding.get("route_expert_ids")
    weights = binding.get("route_weights")
    if not isinstance(routes, list) or len(routes) != 8 or not isinstance(weights, list) or len(weights) != 8:
        raise ValueError("routed-expert top-8 route binding is incomplete")
    for field in ("activation_sha256", "reference_output_sha256"):
        if not _HEX64.fullmatch(str(binding.get(field, ""))):
            raise ValueError(f"routed-expert {field} is malformed")
    worker = record.get("worker", {})
    if worker.get("source_commit") != source["commit"] or worker.get("max_resident_matrices") != 2:
        raise ValueError("routed-expert worker identity or residency bound changed")
    protocol = record.get("protocol", {})
    if (
        protocol.get("optimized_reference_warmups") != 3
        or protocol.get("optimized_reference_measured") != 10
        or protocol.get("direct_warmups") != 3
        or protocol.get("direct_measured") != 10
    ):
        raise ValueError("routed-expert sample protocol changed")
    if record.get("oracle_comparison", {}).get("passed") is not True:
        raise ValueError("routed-expert optimized reference did not pass the CPU oracle")
    numerical = record.get("numerical_qualification", {})
    if (
        numerical.get("contract_version") != "f018-numerical-v1"
        or numerical.get("classification") != record["classification"]
        or numerical.get("numerically_qualified") is not True
        or numerical.get("deterministic") is not True
        or numerical.get("elementwise_mismatch_count") != 0
        or numerical.get("signed_zero_mismatch_count") != 0
        or numerical.get("cpu_fallback_count") != 0
        or numerical.get("complete_f32_weight_materialized_bytes") != 0
    ):
        raise ValueError("routed-expert numerical qualification failed")
    reference_samples = record.get("optimized_reference", {}).get("samples")
    direct_samples = record.get("direct_samples")
    if not isinstance(reference_samples, list) or len(reference_samples) != 10:
        raise ValueError("routed-expert optimized reference raw samples are incomplete")
    if not isinstance(direct_samples, list) or len(direct_samples) != 10:
        raise ValueError("routed-expert direct raw samples are incomplete")
    direct_hashes = set()
    for sample in direct_samples:
        direct_hashes.add(sample.get("output_f32_sha256"))
        direct = sample.get("direct_iq2", {})
        if (
            direct.get("cache_hits") != 2
            or direct.get("resident_entries") != 2
            or direct.get("evictions") != 0
            or direct.get("cpu_fallback_count") != 0
            or direct.get("complete_f32_weight_materialized_bytes") != 0
        ):
            raise ValueError("routed-expert warm direct-IQ2 lifecycle failed")
        if sample.get("resource_after", {}).get("level") != "normal":
            raise ValueError("routed-expert sample resource state is not normal")
    if len(direct_hashes) != 1 or not _HEX64.fullmatch(str(next(iter(direct_hashes), ""))):
        raise ValueError("routed-expert direct outputs are not deterministic")
    process_first = record.get("process_first_direct", {}).get("direct_iq2", {})
    if (
        process_first.get("cache_hits") != 0
        or process_first.get("storage_read_count") != 2
        or process_first.get("evictions") != 0
    ):
        raise ValueError("routed-expert process-first lifecycle is malformed")
    if record.get("resource_before", {}).get("level") != "normal" or record.get(
        "resource_after", {}
    ).get("level") != "normal":
        raise ValueError("routed-expert boundary resource state is not normal")
    if not record.get("unsupported_interpretations"):
        raise ValueError("routed-expert unsupported interpretations are required")
    return record


def _validate_real_matrix_record(record: dict[str, Any]) -> None:
    binding = record["binding"]
    required_binding = {
        "layer",
        "expert_id",
        "projection",
        "tensor_name",
        "shard_filename",
        "quantization",
        "shape",
        "packed_bytes",
        "packed_sha256",
        "activation_identity",
        "activation_token_id",
        "activation_length",
        "activation_sha256",
        "reference_output_sha256",
    }
    missing = sorted(required_binding - binding.keys())
    if missing:
        raise ValueError(f"real matrix binding fields missing: {missing}")
    if binding["projection"] not in {"gate", "up"}:
        raise ValueError("real matrix projection must be gate or up")
    if binding["quantization"] != "IQ2_XXS":
        raise ValueError("real matrix binding must be IQ2_XXS")
    if not str(binding["tensor_name"]).endswith(
        f"ffn_{binding['projection']}_exps.weight"
    ):
        raise ValueError("real matrix tensor role does not match projection")
    shape = binding["shape"]
    if (
        not isinstance(shape, list)
        or len(shape) != 2
        or any(not isinstance(value, int) or value <= 0 for value in shape)
    ):
        raise ValueError("real matrix shape must contain two positive integers")
    for field in ("packed_sha256", "activation_sha256", "reference_output_sha256"):
        if not _HEX64.fullmatch(str(binding[field])):
            raise ValueError(f"real matrix {field} is malformed")
    checkpoint = record.get("checkpoint")
    if not isinstance(checkpoint, dict):
        raise ValueError("real matrix checkpoint identity is required")
    if not _HEX64.fullmatch(str(checkpoint.get("checkpoint_set_sha256", ""))):
        raise ValueError("real matrix checkpoint set SHA-256 is malformed")
    if checkpoint.get("file_count") != 6 or checkpoint.get("total_bytes") != 238_458_632_928:
        raise ValueError("real matrix checkpoint cardinality or size changed")
    protocol = record.get("protocol", {})
    if protocol.get("direct_metal_warmups") != 3 or protocol.get("direct_metal_measured") != 30:
        raise ValueError("real matrix direct Metal protocol must retain 3 warmups and 30 samples")
    if record["timing"].get("sample_count") != 30:
        raise ValueError("real matrix direct Metal timing must retain 30 samples")
    if record["correctness"].get("deterministic_repetitions") != 30:
        raise ValueError("real matrix deterministic repetition count must be 30")
    optimized = record.get("optimized_reference")
    if not isinstance(optimized, dict):
        raise ValueError("real matrix optimized reference is required")
    if optimized.get("deterministic") is not True:
        raise ValueError("real matrix optimized reference must be deterministic")
    if optimized.get("exact_f32_bits_vs_scalar") is not True:
        raise ValueError("real matrix optimized reference must match scalar f32 bits")
    samples = optimized.get("samples")
    if not isinstance(samples, list) or len(samples) != 30:
        raise ValueError("real matrix optimized reference must retain 30 raw samples")
    setup = record.get("setup", {})
    if setup.get("checkpoint_storage_read_count") != 1:
        raise ValueError("real matrix checkpoint path must use one bounded read")
    if setup.get("checkpoint_storage_bytes") != binding["packed_bytes"]:
        raise ValueError("real matrix checkpoint byte accounting mismatch")
