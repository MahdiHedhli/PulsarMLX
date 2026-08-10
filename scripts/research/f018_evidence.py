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
    if (
        record.get("schema") == "pulsarmlx.research.glm52-inference"
        and record.get("feature_id") == "018-direct-quantized-metal-runtime"
    ):
        return _validate_p1_record(record)
    if record.get("schema") == "pulsarmlx.research.f018-direct-iq2-routed-expert":
        return _validate_routed_expert_record(record)
    if record.get("schema") == "pulsarmlx.research.f018-direct-iq2-iq3-routed-expert":
        return _validate_iq2_iq3_routed_expert_record(record)
    if record.get("schema") == "pulsarmlx.research.f018-direct-iq2-moe":
        return _validate_moe_record(record)
    if record.get("schema") == "pulsarmlx.research.f018-direct-iq2-iq3-moe":
        return _validate_iq2_iq3_moe_record(record)
    if record.get("schema") == "pulsarmlx.research.f018-direct-iq2-complete-layer":
        return _validate_complete_layer_record(record)
    if record.get("schema") == "pulsarmlx.research.f018-direct-iq2-iq3-complete-layer":
        return _validate_complete_layer_record(record)
    matrix_schema = record.get("schema")
    if matrix_schema not in {
        "pulsarmlx.research.f018-direct-iq2-xxs",
        "pulsarmlx.research.f018-direct-iq3-xxs",
    }:
        raise ValueError("unexpected Feature 018 schema")
    if record.get("schema_version") not in {"1.0.0", "1.1.0"}:
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
    is_iq3 = matrix_schema == "pulsarmlx.research.f018-direct-iq3-xxs"
    expected_quantization = "IQ3_XXS" if is_iq3 else "IQ2_XXS"
    kernel = record.get("kernel")
    if not isinstance(kernel, dict) or kernel.get("quantization") != expected_quantization:
        raise ValueError(f"kernel quantization must be {expected_quantization}")
    if kernel.get("cpu_fallback_count") != 0:
        raise ValueError("cpu_fallback_count must be zero")
    if kernel.get("complete_f32_weight_materialized_bytes") != 0:
        raise ValueError("complete_f32_weight_materialized_bytes must be zero")
    if record.get("schema_version") == "1.1.0" or is_iq3:
        compiler = kernel.get("compiler", {})
        expected_pipeline = (
            "iq3_xxs_sequential_scaffold_v1"
            if is_iq3
            else "iq2_xxs_sequential_scaffold_v1"
        )
        if (
            compiler.get("fast_math_enabled") is not False
            or compiler.get("language_version") != "3.2"
            or compiler.get("math_mode") != "safe"
            or compiler.get("math_floating_point_functions") != "precise"
            or compiler.get("pipeline_identity") != expected_pipeline
        ):
            raise ValueError("strict compiler settings are incomplete")
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
    expected_contract = "f018-iq3-down-v1" if is_iq3 else "f018-numerical-v1"
    if correctness["contract_version"] != expected_contract:
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
    required_components = ["dispatch", "synchronization", "kernel"]
    if record.get("schema_version") == "1.1.0":
        required_components.append("dispatch_preparation")
    for component in required_components:
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


def _validate_p1_record(record: dict[str, Any]) -> dict[str, Any]:
    """Validate the optional clean-source Feature 018 P1 acceptance record."""

    if record.get("schema_version") != "2.0.0" or record.get("actual_status") != "passed":
        raise ValueError("Feature 018 P1 must use inference schema 2.0.0 and pass")
    if record.get("source_dirty") is not False or not _HEX40.fullmatch(
        str(record.get("source_commit", ""))
    ):
        raise ValueError("Feature 018 P1 source must be a clean commit")
    checkpoint = record.get("checkpoint", {})
    if (
        not _HEX64.fullmatch(str(checkpoint.get("checkpoint_set_sha256", "")))
        or checkpoint.get("file_count") != 6
        or checkpoint.get("total_bytes") != 238_458_632_928
    ):
        raise ValueError("Feature 018 P1 checkpoint identity changed")
    combined_iq3 = record.get("expert_execution_mode") == "direct_iq2_gate_up_iq3_down"
    if (
        record.get("mode") != "inference"
        or record.get("expert_execution_mode")
        not in {"direct_iq2_gate_up", "direct_iq2_gate_up_iq3_down"}
        or record.get("decoder_mode") != "numpy_vectorized"
        or record.get("dense_read_mode")
        != "whole_matrix_numpy_q5_q8_q6_head_numpy"
        or record.get("cache_policy") != "decoded_shared_only"
    ):
        raise ValueError("Feature 018 P1 execution policy changed")
    if (
        record.get("prompt_token_ids") != [9703]
        or record.get("requested_new_tokens") != 1
        or record.get("generated_token_ids") != [9703, 21615]
        or record.get("matches_golden_prefix") is not True
    ):
        raise ValueError("Feature 018 P1 exact token gate failed")
    timings = record.get("timings")
    routing = record.get("routing")
    if not isinstance(timings, list) or len(timings) != 2:
        raise ValueError("Feature 018 P1 must retain exactly two complete stacks")
    if not isinstance(routing, list) or len(routing) != 2:
        raise ValueError("Feature 018 P1 routing population is incomplete")
    for stack in timings:
        layers = stack.get("layers")
        if (
            not isinstance(layers, list)
            or [layer.get("layer") for layer in layers] != list(range(79))
            or stack.get("resource_after", {}).get("level") != "normal"
        ):
            raise ValueError("Feature 018 P1 stack or resource shape changed")
    for stack in routing:
        layers = stack.get("layers")
        if not isinstance(layers, list) or len(layers) != 76:
            raise ValueError("Feature 018 P1 must retain 76 MoE routes per stack")
        if [layer.get("layer") for layer in layers] != list(range(3, 79)):
            raise ValueError("Feature 018 P1 MoE layer identities changed")
        if any(
            not isinstance(layer.get("expert_ids"), list)
            or len(layer["expert_ids"]) != 8
            or layer.get("shared_expert") != 0
            for layer in layers
        ):
            raise ValueError("Feature 018 P1 route shape is incomplete")
    cache = record.get("expert_cache", {})
    if (
        cache.get("cpu_fallbacks") != 0
        or cache.get("evictions") != 0
        or cache.get("admission_rejections") != 0
        or cache.get("decoded_cache_hits") != 228
        or cache.get("resident_entries") != 228
    ):
        raise ValueError("Feature 018 P1 protected shared-cache gate failed")
    direct = record.get(
        "direct_quantized_metal" if combined_iq3 else "direct_iq2_metal", {}
    )
    selection = direct.get("selection", {})
    worker = direct.get("worker", {})
    identity = direct.get("worker_identity", {})
    direct_count = selection.get("direct_routed_expert_count")
    reference_count = selection.get("explicit_reference_routed_expert_count")
    if (
        not isinstance(direct_count, int)
        or direct_count <= 0
        or not isinstance(reference_count, int)
        or reference_count < 0
        or direct_count + reference_count != 2 * 76 * 8
    ):
        raise ValueError("Feature 018 P1 routed execution accounting failed")
    if (
        worker.get("gemv_count") != direct_count * (3 if combined_iq3 else 2)
        or worker.get("cpu_fallback_count") != 0
        or worker.get("complete_f32_weight_materialized_bytes") != 0
        or identity.get("source_commit") != record["source_commit"]
        or identity.get("max_resident_matrices") != (3 if combined_iq3 else 2)
    ):
        raise ValueError("Feature 018 P1 direct worker gate failed")
    if combined_iq3 and (
        identity.get("combined_iq3") is not True
        or identity.get("pipeline_identities")
        != ["iq2_xxs_sequential_scaffold_v1", "iq3_xxs_sequential_scaffold_v1"]
    ):
        raise ValueError("Feature 018 P1 combined IQ3 worker identity changed")
    if record.get("resource_before", {}).get("level") != "normal":
        raise ValueError("Feature 018 P1 resource admission was not normal")
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


def _validate_iq2_iq3_routed_expert_record(record: dict[str, Any]) -> dict[str, Any]:
    if record.get("schema_version") != "1.0.0" or record.get("actual_status") != "passed":
        raise ValueError("IQ2/IQ3 routed-expert evidence must use schema 1.0.0 and pass")
    if record.get("classification") not in CLASSES:
        raise ValueError("IQ2/IQ3 routed-expert classification is unsupported")
    source = record.get("source", {})
    if not _HEX40.fullmatch(str(source.get("commit", ""))) or source.get("dirty") is not False:
        raise ValueError("IQ2/IQ3 routed-expert source must be a clean commit")
    checkpoint = record.get("checkpoint", {})
    if (
        not _HEX64.fullmatch(str(checkpoint.get("checkpoint_set_sha256", "")))
        or checkpoint.get("file_count") != 6
        or checkpoint.get("total_bytes") != 238_458_632_928
    ):
        raise ValueError("IQ2/IQ3 routed-expert checkpoint identity changed")
    binding = record.get("binding", {})
    if (
        binding.get("layer") != 3
        or binding.get("expert_id") != 15
        or binding.get("gate_quantization") != "IQ2_XXS"
        or binding.get("up_quantization") != "IQ2_XXS"
        or binding.get("down_quantization") != "IQ3_XXS"
    ):
        raise ValueError("IQ2/IQ3 routed-expert frozen binding changed")
    worker = record.get("worker", {})
    if (
        worker.get("source_commit") != source["commit"]
        or worker.get("max_resident_matrices") != 3
        or worker.get("pipeline_identities")
        != ["iq2_xxs_sequential_scaffold_v1", "iq3_xxs_sequential_scaffold_v1"]
    ):
        raise ValueError("IQ2/IQ3 worker identity or residency bound changed")
    protocol = record.get("protocol", {})
    if (
        protocol.get("optimized_reference_warmups") != 3
        or protocol.get("optimized_reference_measured") != 10
        or protocol.get("direct_warmups") != 3
        or protocol.get("direct_measured") != 10
    ):
        raise ValueError("IQ2/IQ3 routed-expert protocol changed")
    if record.get("oracle_comparison", {}).get("passed") is not True:
        raise ValueError("IQ2/IQ3 optimized reference did not pass the CPU oracle")
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
        raise ValueError("IQ2/IQ3 routed-expert numerical qualification failed")
    samples = record.get("direct_samples")
    if not isinstance(samples, list) or len(samples) != 10:
        raise ValueError("IQ2/IQ3 routed-expert raw samples are incomplete")
    hashes = set()
    for sample in samples:
        hashes.add(sample.get("output_f32_sha256"))
        direct = sample.get("direct", {})
        events = direct.get("events")
        if (
            direct.get("cache_hits") != 3
            or direct.get("resident_entries") != 3
            or direct.get("evictions") != 0
            or direct.get("cpu_fallback_count") != 0
            or direct.get("complete_f32_weight_materialized_bytes") != 0
            or not isinstance(events, list)
            or [event.get("quantization") for event in events]
            != ["IQ2_XXS", "IQ2_XXS", "IQ3_XXS"]
        ):
            raise ValueError("IQ2/IQ3 routed-expert warm lifecycle failed")
        if sample.get("resource_after", {}).get("level") != "normal":
            raise ValueError("IQ2/IQ3 routed-expert resource state changed")
    if len(hashes) != 1 or not _HEX64.fullmatch(str(next(iter(hashes), ""))):
        raise ValueError("IQ2/IQ3 routed-expert outputs are not deterministic")
    first = record.get("process_first_direct", {}).get("direct", {})
    if (
        first.get("cache_hits") != 0
        or first.get("storage_read_count") != 3
        or first.get("resident_entries") != 3
        or first.get("evictions") != 0
    ):
        raise ValueError("IQ2/IQ3 process-first lifecycle is malformed")
    if record.get("resource_before", {}).get("level") != "normal" or record.get(
        "resource_after", {}
    ).get("level") != "normal":
        raise ValueError("IQ2/IQ3 boundary resource state is not normal")
    if not record.get("unsupported_interpretations"):
        raise ValueError("IQ2/IQ3 unsupported interpretations are required")
    return record


def _validate_moe_record(record: dict[str, Any]) -> dict[str, Any]:
    if record.get("schema_version") != "1.0.0" or record.get("actual_status") != "passed":
        raise ValueError("MoE evidence must use schema 1.0.0 and pass")
    if record.get("classification") not in CLASSES:
        raise ValueError("MoE classification is unsupported")
    source = record.get("source", {})
    if not _HEX40.fullmatch(str(source.get("commit", ""))) or source.get("dirty") is not False:
        raise ValueError("MoE source must be a clean commit")
    checkpoint = record.get("checkpoint", {})
    if (
        not _HEX64.fullmatch(str(checkpoint.get("checkpoint_set_sha256", "")))
        or checkpoint.get("file_count") != 6
        or checkpoint.get("total_bytes") != 238_458_632_928
    ):
        raise ValueError("MoE checkpoint identity changed")
    binding = record.get("binding", {})
    if (
        binding.get("layer") != 3
        or binding.get("expert_ids") != [15, 177, 10, 233, 166, 41, 152, 26]
        or binding.get("shared_expert") != 0
        or binding.get("historical_reference_hash_match") is not True
    ):
        raise ValueError("MoE frozen route or historical reference binding changed")
    for field in (
        "residual_sha256",
        "reference_output_sha256",
        "historical_reference_output_sha256",
    ):
        if not _HEX64.fullmatch(str(binding.get(field, ""))):
            raise ValueError(f"MoE {field} is malformed")
    if binding["reference_output_sha256"] != binding["historical_reference_output_sha256"]:
        raise ValueError("MoE current reference does not match committed historical evidence")
    worker = record.get("worker", {})
    if worker.get("source_commit") != source["commit"] or worker.get("max_resident_matrices") != 2:
        raise ValueError("MoE worker identity or residency bound changed")
    protocol = record.get("protocol", {})
    if (
        protocol.get("optimized_reference_warmups") != 3
        or protocol.get("optimized_reference_measured") != 10
        or protocol.get("direct_warmups") != 3
        or protocol.get("direct_measured") != 10
        or protocol.get("direct_compressed_slot_limit") != 2
    ):
        raise ValueError("MoE sample protocol changed")
    numerical = record.get("numerical_qualification", {})
    if (
        numerical.get("contract_version") != "f018-numerical-v1"
        or numerical.get("classification") != record["classification"]
        or numerical.get("numerically_qualified") is not True
        or numerical.get("deterministic") is not True
        or numerical.get("routes_match") is not True
        or numerical.get("elementwise_mismatch_count") != 0
        or numerical.get("signed_zero_mismatch_count") != 0
        or numerical.get("cpu_fallback_count") != 0
        or numerical.get("complete_f32_weight_materialized_bytes") != 0
    ):
        raise ValueError("MoE numerical qualification failed")
    reference_samples = record.get("optimized_reference", {}).get("samples")
    direct_samples = record.get("direct_samples")
    if not isinstance(reference_samples, list) or len(reference_samples) != 10:
        raise ValueError("MoE optimized-reference raw samples are incomplete")
    if not isinstance(direct_samples, list) or len(direct_samples) != 10:
        raise ValueError("MoE direct raw samples are incomplete")
    hashes = set()
    previous_evictions = -1
    for sample in direct_samples:
        hashes.add(sample.get("output_f32_sha256"))
        direct = sample.get("direct_iq2", {})
        evictions = direct.get("evictions_cumulative_end")
        if (
            direct.get("matrix_count") != 16
            or direct.get("storage_read_count") != 16
            or direct.get("cache_hits") != 0
            or direct.get("resident_entries_end") != 2
            or not isinstance(evictions, int)
            or evictions <= previous_evictions
            or direct.get("cpu_fallback_count") != 0
            or direct.get("complete_f32_weight_materialized_bytes") != 0
        ):
            raise ValueError("MoE bounded direct-IQ2 lifecycle failed")
        previous_evictions = evictions
        if sample.get("shared_reference", {}).get("cache_hits") != 3:
            raise ValueError("MoE protected shared reference did not retain three hits")
        if sample.get("resource_after", {}).get("level") != "normal":
            raise ValueError("MoE sample resource state is not normal")
    if len(hashes) != 1 or not _HEX64.fullmatch(str(next(iter(hashes), ""))):
        raise ValueError("MoE direct outputs are not deterministic")
    process_first = record.get("process_first_direct", {}).get("direct_iq2", {})
    if (
        process_first.get("matrix_count") != 16
        or process_first.get("storage_read_count") != 16
        or process_first.get("cache_hits") != 0
        or process_first.get("evictions_cumulative_end") != 14
    ):
        raise ValueError("MoE process-first lifecycle is malformed")
    if record.get("resource_before", {}).get("level") != "normal" or record.get(
        "resource_after", {}
    ).get("level") != "normal":
        raise ValueError("MoE boundary resource state is not normal")
    if not record.get("unsupported_interpretations"):
        raise ValueError("MoE unsupported interpretations are required")
    return record


def _validate_iq2_iq3_moe_record(record: dict[str, Any]) -> dict[str, Any]:
    if record.get("schema_version") != "1.0.0" or record.get("actual_status") != "passed":
        raise ValueError("IQ2/IQ3 MoE evidence must use schema 1.0.0 and pass")
    source = record.get("source", {})
    if not _HEX40.fullmatch(str(source.get("commit", ""))) or source.get("dirty") is not False:
        raise ValueError("IQ2/IQ3 MoE source must be a clean commit")
    checkpoint = record.get("checkpoint", {})
    if (
        not _HEX64.fullmatch(str(checkpoint.get("checkpoint_set_sha256", "")))
        or checkpoint.get("file_count") != 6
        or checkpoint.get("total_bytes") != 238_458_632_928
    ):
        raise ValueError("IQ2/IQ3 MoE checkpoint identity changed")
    binding = record.get("binding", {})
    if (
        binding.get("layer") != 3
        or binding.get("expert_ids") != [15, 177, 10, 233, 166, 41, 152, 26]
        or binding.get("shared_expert") != 0
        or binding.get("historical_reference_hash_match") is not True
    ):
        raise ValueError("IQ2/IQ3 MoE frozen route or reference binding changed")
    worker = record.get("worker", {})
    if (
        worker.get("source_commit") != source["commit"]
        or worker.get("max_resident_matrices") != 3
        or worker.get("pipeline_identities")
        != ["iq2_xxs_sequential_scaffold_v1", "iq3_xxs_sequential_scaffold_v1"]
    ):
        raise ValueError("IQ2/IQ3 MoE worker identity changed")
    protocol = record.get("protocol", {})
    if (
        protocol.get("optimized_reference_warmups") != 3
        or protocol.get("optimized_reference_measured") != 10
        or protocol.get("direct_warmups") != 3
        or protocol.get("direct_measured") != 10
        or protocol.get("direct_compressed_slot_limit") != 3
    ):
        raise ValueError("IQ2/IQ3 MoE protocol changed")
    numerical = record.get("numerical_qualification", {})
    if (
        numerical.get("contract_version") != "f018-numerical-v1"
        or numerical.get("classification") != record.get("classification")
        or numerical.get("numerically_qualified") is not True
        or numerical.get("deterministic") is not True
        or numerical.get("routes_match") is not True
        or numerical.get("elementwise_mismatch_count") != 0
        or numerical.get("signed_zero_mismatch_count") != 0
        or numerical.get("cpu_fallback_count") != 0
        or numerical.get("complete_f32_weight_materialized_bytes") != 0
    ):
        raise ValueError("IQ2/IQ3 MoE numerical qualification failed")
    samples = record.get("direct_samples")
    if not isinstance(samples, list) or len(samples) != 10:
        raise ValueError("IQ2/IQ3 MoE samples are incomplete")
    hashes = set()
    for sample in samples:
        hashes.add(sample.get("output_f32_sha256"))
        iq2 = sample.get("direct_iq2", {})
        iq3 = sample.get("direct_iq3", {})
        shared = sample.get("shared_reference", {})
        if (
            iq2.get("matrix_count") != 16
            or iq3.get("matrix_count") != 8
            or iq2.get("cpu_fallback_count") != 0
            or iq3.get("cpu_fallback_count") != 0
            or iq2.get("complete_f32_weight_materialized_bytes") != 0
            or iq3.get("complete_f32_weight_materialized_bytes") != 0
            or shared.get("cache_hits") != 3
            or sample.get("resource_after", {}).get("level") != "normal"
        ):
            raise ValueError("IQ2/IQ3 MoE direct/reference dispatch accounting failed")
    if len(hashes) != 1 or not _HEX64.fullmatch(str(next(iter(hashes), ""))):
        raise ValueError("IQ2/IQ3 MoE outputs are not deterministic")
    if record.get("resource_before", {}).get("level") != "normal" or record.get(
        "resource_after", {}
    ).get("level") != "normal":
        raise ValueError("IQ2/IQ3 MoE resource state is not normal")
    if not record.get("unsupported_interpretations"):
        raise ValueError("IQ2/IQ3 MoE unsupported interpretations are required")
    return record


def _validate_complete_layer_record(record: dict[str, Any]) -> dict[str, Any]:
    combined_iq3 = record.get("schema") == "pulsarmlx.research.f018-direct-iq2-iq3-complete-layer"
    if record.get("schema_version") != "1.0.0" or record.get("actual_status") != "passed":
        raise ValueError("complete-layer evidence must use schema 1.0.0 and pass")
    if record.get("classification") not in CLASSES:
        raise ValueError("complete-layer classification is unsupported")
    source = record.get("source", {})
    if not _HEX40.fullmatch(str(source.get("commit", ""))) or source.get("dirty") is not False:
        raise ValueError("complete-layer source must be a clean commit")
    checkpoint = record.get("checkpoint", {})
    if (
        not _HEX64.fullmatch(str(checkpoint.get("checkpoint_set_sha256", "")))
        or checkpoint.get("file_count") != 6
        or checkpoint.get("total_bytes") != 238_458_632_928
    ):
        raise ValueError("complete-layer checkpoint identity changed")
    binding = record.get("binding", {})
    if (
        binding.get("layer") != 3
        or binding.get("input_token_id") != 9703
        or not isinstance(binding.get("expert_ids"), list)
        or len(binding["expert_ids"]) != 8
        or binding.get("historical_reference_hash_match") is not True
    ):
        raise ValueError("complete-layer frozen input, route, or history binding changed")
    for field in (
        "input_sha256",
        "midpoint_sha256",
        "reference_output_sha256",
        "historical_reference_output_sha256",
    ):
        if not _HEX64.fullmatch(str(binding.get(field, ""))):
            raise ValueError(f"complete-layer {field} is malformed")
    if binding["reference_output_sha256"] != binding["historical_reference_output_sha256"]:
        raise ValueError("complete-layer current reference does not match historical evidence")
    worker = record.get("worker", {})
    expected_slots = 3 if combined_iq3 else 2
    if worker.get("source_commit") != source["commit"] or worker.get("max_resident_matrices") != expected_slots:
        raise ValueError("complete-layer worker identity or residency bound changed")
    if combined_iq3 and worker.get("pipeline_identities") != [
        "iq2_xxs_sequential_scaffold_v1",
        "iq3_xxs_sequential_scaffold_v1",
    ]:
        raise ValueError("complete-layer IQ3 pipeline identity changed")
    protocol = record.get("protocol", {})
    if (
        protocol.get("optimized_reference_warmups") != 3
        or protocol.get("optimized_reference_measured") != 10
        or protocol.get("direct_warmups") != 3
        or protocol.get("direct_measured") != 10
        or protocol.get("direct_compressed_slot_limit") != expected_slots
    ):
        raise ValueError("complete-layer sample protocol changed")
    numerical = record.get("numerical_qualification", {})
    if (
        numerical.get("contract_version") != "f018-numerical-v1"
        or numerical.get("classification") != record["classification"]
        or numerical.get("numerically_qualified") is not True
        or numerical.get("identity_matches") is not True
        or numerical.get("routes_match") is not True
        or numerical.get("deterministic") is not True
        or numerical.get("elementwise_mismatch_count") != 0
        or numerical.get("signed_zero_mismatch_count") != 0
        or numerical.get("cpu_fallback_count") != 0
        or numerical.get("complete_f32_weight_materialized_bytes") != 0
    ):
        raise ValueError("complete-layer numerical qualification failed")
    reference_samples = record.get("optimized_reference", {}).get("samples")
    direct_samples = record.get("direct_samples")
    if not isinstance(reference_samples, list) or len(reference_samples) != 10:
        raise ValueError("complete-layer optimized-reference raw samples are incomplete")
    if not isinstance(direct_samples, list) or len(direct_samples) != 10:
        raise ValueError("complete-layer direct raw samples are incomplete")
    reference_hashes = {sample.get("output_f32_sha256") for sample in reference_samples}
    direct_hashes = {sample.get("output_f32_sha256") for sample in direct_samples}
    midpoint_hashes = {
        sample.get("midpoint_f32_sha256") for sample in reference_samples + direct_samples
    }
    if (
        reference_hashes != {binding["reference_output_sha256"]}
        or len(direct_hashes) != 1
        or not _HEX64.fullmatch(str(next(iter(direct_hashes), "")))
        or midpoint_hashes != {binding["midpoint_sha256"]}
    ):
        raise ValueError("complete-layer outputs or midpoint are not deterministic")
    for sample in direct_samples:
        direct = sample.get("moe", {}).get("direct_iq2", {})
        direct_iq3 = sample.get("moe", {}).get(
            "direct_iq3",
            {
                "matrix_count": 0,
                "cpu_fallback_count": 0,
                "complete_f32_weight_materialized_bytes": 0,
            },
        )
        if (
            direct.get("matrix_count") != 16
            or direct.get("storage_read_count") != 16
            or direct.get("cpu_fallback_count") != 0
            or direct.get("complete_f32_weight_materialized_bytes") != 0
            or direct_iq3.get("matrix_count") != (8 if combined_iq3 else 0)
            or direct_iq3.get("cpu_fallback_count") != 0
            or direct_iq3.get("complete_f32_weight_materialized_bytes") != 0
            or sample.get("moe", {}).get("shared_reference", {}).get("cache_hits") != 3
            or sample.get("resource_after", {}).get("level") != "normal"
        ):
            raise ValueError("complete-layer direct lifecycle or resource gate failed")
    reference_median = record.get("optimized_reference", {}).get("summaries", {}).get(
        "total_seconds", {}
    ).get("median_seconds")
    direct_median = record.get("direct_summaries", {}).get("layer", {}).get(
        "total_seconds", {}
    ).get("median_seconds")
    if not isinstance(reference_median, (int, float)) or not isinstance(
        direct_median, (int, float)
    ) or direct_median >= reference_median:
        raise ValueError("complete-layer candidate did not reduce the measured median")
    if record.get("resource_before", {}).get("level") != "normal" or record.get(
        "resource_after", {}
    ).get("level") != "normal":
        raise ValueError("complete-layer boundary resource state is not normal")
    if not record.get("unsupported_interpretations"):
        raise ValueError("complete-layer unsupported interpretations are required")
    return record


def _validate_real_matrix_record(record: dict[str, Any]) -> None:
    binding = record["binding"]
    is_iq3 = record.get("schema") == "pulsarmlx.research.f018-direct-iq3-xxs"
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
    expected_projections = {"down"} if is_iq3 else {"gate", "up"}
    expected_quantization = "IQ3_XXS" if is_iq3 else "IQ2_XXS"
    if binding["projection"] not in expected_projections:
        raise ValueError("real matrix projection does not match its direct kernel")
    if binding["quantization"] != expected_quantization:
        raise ValueError("real matrix binding quantization does not match its direct kernel")
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
