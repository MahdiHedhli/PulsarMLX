"""Strict stdlib-only validator for the GLM-5.3-Flash tiny mini-contract.

This validates declarative research metadata.  It does not read checkpoints,
safetensors headers, model weights, or infer omitted values.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
import re
from typing import Any, Mapping, Sequence


class ContractValidationError(ValueError):
    """A bounded, path-addressed mini-contract validation failure."""


SCHEMA = "pulsarmlx.glm53_flash.tiny_mini_contract.v1"
STATUS = "SCOPED_TOY_PREDECLARED"

ROOT_KEYS = {
    "schema", "status", "source_scope", "limits", "constants", "seeds",
    "source_equations", "apis", "edges", "tensors", "tests", "uncertainties",
}
SOURCE_SCOPE_KEYS = {
    "source_lock_sha256", "runtime_revision", "selected_artifact_revision",
    "indexed_name_count", "language_layer_count", "vision_block_count",
    "kda_layers", "sparse_layers", "complete_source_graph_claim",
    "toy_graph_claim", "mtp_indexed_names", "mtp_config_observation",
}
LIMIT_KEYS = {
    "max_batch", "max_sequence", "max_feature", "max_experts", "max_heads",
    "max_elements", "storage_group_size", "arithmetic_allows_group_size_64",
}
CONSTANT_KEYS = {
    "f64_atol", "f64_rtol", "route_scaling_factor", "route_tie_rule",
    "swiglu_limit", "hc_eps", "hc_sinkhorn_iters", "rms_norm_eps",
    "kda_l2_eps", "kda_lower_bound", "tiny_batch_ceiling",
    "tiny_sequence_ceiling", "tiny_feature_ceiling", "tiny_experts_ceiling",
    "tiny_heads_ceiling", "tiny_key_width_ceiling",
    "tiny_value_width_ceiling", "tiny_pool_size_ceiling",
    "tiny_sparse_top_k_ceiling",
}
SEED_KEYS = {"semantic", "independent_stream", "metadata_mutation"}
EQUATION_KEYS = {"id", "source_functions", "edge_ids"}
API_KEYS = {
    "id", "symbol", "inputs", "outputs", "source_functions",
    "equation_ids", "test_ids",
}
EDGE_KEYS = {
    "id", "producer", "producer_port", "consumer", "consumer_port",
    "tensor_ids", "equation_ids", "test_ids",
}
TENSOR_KEYS = {
    "id", "role", "name_kind", "name", "layer", "shape",
    "source_function", "state_owner", "precision", "quant_companions",
    "edge_ids",
}
SHAPE_KEYS = {"tiny", "source_logical", "evidence"}
TEST_KEYS = {"id", "api_ids", "edge_ids", "seed", "unittest_methods", "criteria"}

EXPECTED_LIMITS = {
    "max_batch": 2,
    "max_sequence": 16,
    "max_feature": 32,
    "max_experts": 8,
    "max_heads": 4,
    "max_elements": 65536,
    "storage_group_size": 64,
    "arithmetic_allows_group_size_64": False,
}
EXPECTED_CONSTANTS = {
    "f64_atol": 1e-12,
    "f64_rtol": 1e-10,
    "route_scaling_factor": 2.5,
    "route_tie_rule": "increasing_expert_index_toy_rule_source_uncertain",
    "swiglu_limit": 10.0,
    "hc_eps": 1e-6,
    "hc_sinkhorn_iters": 20,
    "rms_norm_eps": 1e-5,
    "kda_l2_eps": 1e-6,
    "kda_lower_bound": -5.0,
    "tiny_batch_ceiling": 2,
    "tiny_sequence_ceiling": 7,
    "tiny_feature_ceiling": 4,
    "tiny_experts_ceiling": 8,
    "tiny_heads_ceiling": 2,
    "tiny_key_width_ceiling": 2,
    "tiny_value_width_ceiling": 3,
    "tiny_pool_size_ceiling": 2,
    "tiny_sparse_top_k_ceiling": 4,
}
EXPECTED_SEEDS = {
    "semantic": 20260908,
    "independent_stream": 20260909,
    "metadata_mutation": 20260909,
}
KDA_LAYERS = {
    0, 1, 2, 4, 5, 6, 8, 9, 10, 12, 13, 14, 16, 17, 18, 20, 21,
    22, 24, 25, 26, 28, 29, 30, 32, 33, 34, 36, 37, 38, 40, 41, 42, 44,
}
SPARSE_LAYERS = {3, 7, 11, 15, 19, 23, 27, 31, 35, 39, 43}

SUPPORTED_FUNCTIONS = {
    "ClampedMLP.__call__", "ClampedSwiGLU.__call__",
    "Glm5NextDecoderLayer._ffn_block", "Glm5NextForgetGate.__call__",
    "Glm5NextIndexer.__call__", "Glm5NextIndexer._pooled_states",
    "Glm5NextIndexer._visible_tail", "Glm5NextLinearAttention.__call__",
    "Glm5NextMoE.__call__", "Glm5NextMoEGate.__call__", "_hc_ops",
    "_hc_split_sinkhorn_ops", "compute_g_safe", "gated_delta_update",
    "group_expert_select", "hc_expand", "recurrent_kimi_delta",
}
EXPECTED_EQUATIONS = {
    "EQ-ROUTE", "EQ-SPARSE", "EQ-CONV", "EQ-KDA-GATE", "EQ-KDA",
    "EQ-MHC", "EQ-SWIGLU", "EQ-MLP", "EQ-COMPOSE",
}
EXPECTED_APIS = {
    "route_scores", "route_tokens", "sparse_select", "causal_conv_silu",
    "kda_sequence", "mhc_collapse", "mhc_expand", "clamped_swiglu",
    "clamped_mlp", "compose_moe_residual",
}
EXPECTED_EDGES = {
    "E-ROUTE-SCORES-IN", "E-ROUTE-SCORES-OUT", "E-ROUTE-TOKENS-IN",
    "E-ROUTE-TOKENS-OUT", "E-SPARSE-IN", "E-SPARSE-OUT", "E-CONV-IN",
    "E-CONV-OUT", "E-KDA-IN", "E-KDA-OUT", "E-MHC-COLLAPSE-IN",
    "E-MHC-COLLAPSE-TO-EXPAND", "E-MHC-EXPAND-OUT", "E-SWIGLU-IN",
    "E-SWIGLU-OUT", "E-MLP-IN", "E-MLP-OUT", "E-COMPOSE-IN",
    "E-COMPOSE-OUT",
}
EXPECTED_TESTS = {
    "T-CONTRACT-VALID", "T-CONTRACT-REJECT", "T-ROUTE", "T-SPARSE",
    "T-KDA", "T-MHC", "T-SWIGLU", "T-COMPOSE",
}
EXPECTED_TEST_METHODS = {
    "T-CONTRACT-VALID": {"test_canonical_contract_and_arithmetic_bindings"},
    "T-CONTRACT-REJECT": {"test_metadata_mutations_reject", "test_semantic_edge_miswire_rejects"},
    "T-ROUTE": {"test_routing_bias_ids_original_weights", "test_routing_exact_direct_tie"},
    "T-SPARSE": {"test_sparse_live_pools_tail_visibility", "test_sparse_shifted_origin_invalid_query_and_short_bypass"},
    "T-KDA": {"test_kda_empty_and_nonzero_unequal_axes", "test_kda_prefix_incremental_reset_and_interleaving", "test_conv_suffix_and_conv_to_kda_boundary", "test_axis_and_parameter_rejections"},
    "T-MHC": {"test_mhc_nonidentity_collapse_expand"},
    "T-SWIGLU": {"test_clamps_below_at_above", "test_nonfinite_input_and_intermediate_rejections"},
    "T-COMPOSE": {"test_dense_shared_routed_residual_edges"},
}
EXPECTED_EDGE_ENDPOINTS = {
    "E-ROUTE-SCORES-IN": ("source:group_expert_select", "scores_bias_topk", "api:route_scores", "routing_scores"),
    "E-ROUTE-SCORES-OUT": ("api:route_scores", "route_result", "test:T-ROUTE", "assertions"),
    "E-ROUTE-TOKENS-IN": ("source:Glm5NextMoEGate.__call__", "logits_bias_topk", "api:route_tokens", "routing_logits"),
    "E-ROUTE-TOKENS-OUT": ("api:route_tokens", "route_result", "test:T-ROUTE", "assertions"),
    "E-SPARSE-IN": ("source:Glm5NextIndexer.__call__", "projected_indexer_inputs", "api:sparse_select", "indexer_inputs"),
    "E-SPARSE-OUT": ("api:sparse_select", "sparse_result", "test:T-SPARSE", "assertions"),
    "E-CONV-IN": ("source:Glm5NextLinearAttention.__call__", "mixed_suffix_kernel", "api:causal_conv_silu", "conv_inputs"),
    "E-CONV-OUT": ("api:causal_conv_silu", "conv_result", "test:T-KDA", "assertions"),
    "E-KDA-IN": ("source:recurrent_kimi_delta", "q_k_v_gates_state", "api:kda_sequence", "kda_inputs"),
    "E-KDA-OUT": ("api:kda_sequence", "kda_result", "test:T-KDA", "assertions"),
    "E-MHC-COLLAPSE-IN": ("source:_hc_ops", "streams_fn_scale_base", "api:mhc_collapse", "mhc_inputs"),
    "E-MHC-COLLAPSE-TO-EXPAND": ("api:mhc_collapse", "mhc_result", "api:mhc_expand", "expand_inputs"),
    "E-MHC-EXPAND-OUT": ("api:mhc_expand", "expanded_residual", "test:T-MHC", "assertions"),
    "E-SWIGLU-IN": ("source:ClampedSwiGLU.__call__", "gate_up", "api:clamped_swiglu", "gate_up"),
    "E-SWIGLU-OUT": ("api:clamped_swiglu", "activated", "test:T-SWIGLU", "assertions"),
    "E-MLP-IN": ("source:ClampedMLP.__call__", "x_weights", "api:clamped_mlp", "mlp_inputs"),
    "E-MLP-OUT": ("api:clamped_mlp", "mlp_trace", "test:T-COMPOSE", "assertions"),
    "E-COMPOSE-IN": ("source:Glm5NextMoE.__call__", "residual_router_experts_shared", "api:compose_moe_residual", "composition_inputs"),
    "E-COMPOSE-OUT": ("api:compose_moe_residual", "composition_result", "test:T-COMPOSE", "assertions"),
}

RUNTIME_NAMES = {
    "runtime.router.raw_scores": "router_scores",
    "runtime.router.logits": "router_logits",
    "runtime.router.selected_ids": "route_ids",
    "runtime.router.selected_weights": "route_weights",
    "runtime.indexer.projected_key": "index_key",
    "runtime.indexer.pool_gate_scores": "index_gate_scores",
    "runtime.indexer.projected_query": "index_query",
    "runtime.indexer.head_weight": "index_head_weight",
    "runtime.indexer.selected_indices": "sparse_indices",
    "runtime.kda.conv_suffix": "kda_conv_suffix",
    "runtime.kda.conv_silu_output": "kda_conv_output",
    "runtime.kda.query": "kda_query",
    "runtime.kda.key": "kda_key",
    "runtime.kda.value": "kda_value",
    "runtime.kda.state_dk_dv": "kda_recurrent_state",
    "runtime.kda.output": "kda_output",
    "runtime.mhc.streams": "mhc_streams",
    "runtime.mhc.collapsed": "mhc_collapsed",
    "runtime.mhc.post": "mhc_post",
    "runtime.mhc.comb": "mhc_comb",
    "runtime.mhc.expanded": "mhc_expanded",
    "runtime.mlp.gate": "swiglu_gate",
    "runtime.mlp.up": "swiglu_up",
    "runtime.mlp.activated": "swiglu_activated",
    "runtime.moe.residual_output": "composition_output",
}
INDEXED_NAMES = {
    "language_model.model.layers.3.mlp.gate.e_score_correction_bias": "router_correction_bias",
    "language_model.model.layers.3.mlp.gate.weight": "router_weight",
    "language_model.model.layers.3.self_attn.indexer.index_kpool_compress_ape": "index_pool_ape",
    "language_model.model.layers.0.self_attn.conv1d.weight": "kda_conv_weight",
    "language_model.model.layers.0.self_attn.forget_gate.A_log": "kda_a_log",
    "language_model.model.layers.0.self_attn.forget_gate.dt_bias": "kda_dt_bias",
    "language_model.model.layers.3.ffn_hc.fn": "mhc_fn",
    "language_model.model.layers.3.ffn_hc.base": "mhc_base",
    "language_model.model.layers.3.ffn_hc.scale": "mhc_scale",
    "language_model.model.layers.3.mlp.switch_mlp.gate_proj.weight": "routed_gate_weight",
    "language_model.model.layers.3.mlp.switch_mlp.up_proj.weight": "routed_up_weight",
    "language_model.model.layers.3.mlp.switch_mlp.down_proj.weight": "routed_down_weight",
    "language_model.model.layers.3.mlp.shared_experts.gate_proj.weight": "shared_gate_weight",
    "language_model.model.layers.3.mlp.shared_experts.up_proj.weight": "shared_up_weight",
    "language_model.model.layers.3.mlp.shared_experts.down_proj.weight": "shared_down_weight",
}
ROLE_BY_NAME = {**RUNTIME_NAMES, **INDEXED_NAMES}
SUPPORTED_PRECISIONS = {
    "toy-f64", "exact-integer", "protected-fp32",
    "original-precision-sensitive-bf16", "selected-4bit-affine-group64",
    "selected-8bit-affine-group64",
}
SUPPORTED_STATE_OWNERS = {"stateless", "kda.conv_suffix", "kda.recurrent"}
INDEXED_PRECISION_BY_ROLE = {
    "router_correction_bias": "protected-fp32",
    "router_weight": "original-precision-sensitive-bf16",
    "index_pool_ape": "original-precision-sensitive-bf16",
    "kda_conv_weight": "original-precision-sensitive-bf16",
    "kda_a_log": "protected-fp32",
    "kda_dt_bias": "protected-fp32",
    "mhc_fn": "original-precision-sensitive-bf16",
    "mhc_base": "protected-fp32",
    "mhc_scale": "protected-fp32",
    "routed_gate_weight": "selected-4bit-affine-group64",
    "routed_up_weight": "selected-4bit-affine-group64",
    "routed_down_weight": "selected-4bit-affine-group64",
    "shared_gate_weight": "selected-8bit-affine-group64",
    "shared_up_weight": "selected-8bit-affine-group64",
    "shared_down_weight": "selected-8bit-affine-group64",
}
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
LAYER_RE = re.compile(r"\.layers\.(\d+)\.")


def _fail(path: str, message: str) -> None:
    raise ContractValidationError(f"{path}: {message}")


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        _fail(path, "expected object")
    return value


def _sequence(value: Any, path: str) -> Sequence[Any]:
    if not isinstance(value, list):
        _fail(path, "expected array")
    return value


def _exact_keys(value: Any, expected: set[str], path: str) -> Mapping[str, Any]:
    obj = _mapping(value, path)
    actual = set(obj)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        _fail(path, f"missing fields {missing}")
    if extra:
        _fail(path, f"unsupported fields {extra}")
    return obj


def _nonempty_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value:
        _fail(path, "expected non-empty string")
    return value


def _string_list(value: Any, path: str, *, allow_empty: bool = False) -> list[str]:
    items = _sequence(value, path)
    if not items and not allow_empty:
        _fail(path, "empty array is unsupported")
    result = []
    for index, item in enumerate(items):
        result.append(_nonempty_string(item, f"{path}[{index}]"))
    if len(result) != len(set(result)):
        _fail(path, "duplicate values")
    return result


def _records(value: Any, keys: set[str], path: str) -> tuple[list[Mapping[str, Any]], dict[str, Mapping[str, Any]]]:
    raw = _sequence(value, path)
    records: list[Mapping[str, Any]] = []
    by_id: dict[str, Mapping[str, Any]] = {}
    for index, item in enumerate(raw):
        record_path = f"{path}[{index}]"
        record = _exact_keys(item, keys, record_path)
        record_id = _nonempty_string(record["id"], f"{record_path}.id")
        if not ID_RE.fullmatch(record_id):
            _fail(f"{record_path}.id", "unsupported identifier")
        if record_id in by_id:
            _fail(f"{record_path}.id", f"duplicate id {record_id!r}")
        records.append(record)
        by_id[record_id] = record
    return records, by_id


def _require_exact_ids(actual: set[str], expected: set[str], path: str) -> None:
    if actual != expected:
        _fail(path, f"IDs differ; missing={sorted(expected-actual)}, extra={sorted(actual-expected)}")


def _check_refs(values: Any, known: Mapping[str, Any], path: str, *, allow_empty: bool = False) -> list[str]:
    refs = _string_list(values, path, allow_empty=allow_empty)
    for index, ref in enumerate(refs):
        if ref not in known:
            _fail(f"{path}[{index}]", f"unmapped reference {ref!r}")
    return refs


def _check_functions(values: Any, path: str) -> list[str]:
    functions = _string_list(values, path)
    for index, function in enumerate(functions):
        if function not in SUPPORTED_FUNCTIONS:
            _fail(f"{path}[{index}]", f"unsupported source function {function!r}")
    return functions


def _check_fixed_mapping(value: Any, expected: Mapping[str, Any], path: str) -> None:
    obj = _exact_keys(value, set(expected), path)
    for key, wanted in expected.items():
        got = obj[key]
        if isinstance(wanted, float):
            if not isinstance(got, (int, float)) or isinstance(got, bool) or not math.isfinite(got):
                _fail(f"{path}.{key}", "expected finite number")
        if got != wanted:
            _fail(f"{path}.{key}", f"expected {wanted!r}, got {got!r}")


def _endpoint(value: Any, path: str, apis: Mapping[str, Any], tests: Mapping[str, Any], *, producer: bool) -> tuple[str, str]:
    text = _nonempty_string(value, path)
    if ":" not in text:
        _fail(path, "endpoint must be kind:name")
    kind, name = text.split(":", 1)
    allowed = {"source", "api"} if producer else {"api", "test"}
    if kind not in allowed:
        _fail(path, f"unsupported endpoint kind {kind!r}")
    if kind == "source" and name not in SUPPORTED_FUNCTIONS:
        _fail(path, f"unsupported source function {name!r}")
    if kind == "api" and name not in apis:
        _fail(path, f"unmapped API {name!r}")
    if kind == "test" and name not in tests:
        _fail(path, f"unmapped test {name!r}")
    return kind, name


def _check_shape(value: Any, path: str, limits: Mapping[str, Any], name_kind: str) -> None:
    shape = _exact_keys(value, SHAPE_KEYS, path)
    dims = _sequence(shape["tiny"], f"{path}.tiny")
    if not dims:
        _fail(f"{path}.tiny", "rank zero unsupported")
    elements = 1
    for index, dim in enumerate(dims):
        if not isinstance(dim, int) or isinstance(dim, bool) or dim <= 0:
            _fail(f"{path}.tiny[{index}]", "expected positive integer")
        if dim > limits["max_feature"]:
            _fail(f"{path}.tiny[{index}]", "arithmetic dimension exceeds max_feature")
        elements *= dim
    if elements > limits["max_elements"]:
        _fail(f"{path}.tiny", "element count exceeds max_elements")
    _nonempty_string(shape["source_logical"], f"{path}.source_logical")
    evidence = _nonempty_string(shape["evidence"], f"{path}.evidence")
    wanted = "source-derived-logical-not-header" if name_kind == "indexed" else "toy-runtime-boundary"
    if evidence != wanted:
        _fail(f"{path}.evidence", f"expected {wanted!r}")


def _check_tensor(record: Mapping[str, Any], path: str, limits: Mapping[str, Any]) -> None:
    role = _nonempty_string(record["role"], f"{path}.role")
    name = _nonempty_string(record["name"], f"{path}.name")
    if name not in ROLE_BY_NAME:
        _fail(f"{path}.name", f"unsupported tensor name {name!r}")
    if ROLE_BY_NAME[name] != role:
        _fail(f"{path}.role", f"role {role!r} does not map to tensor name {name!r}")
    lower_name = name.lower()
    if any(token in lower_name for token in ("mtp", "nextn", "next_n", "predict")):
        _fail(f"{path}.name", "MTP-like tensor names are omitted")

    kind = _nonempty_string(record["name_kind"], f"{path}.name_kind")
    if kind not in {"runtime", "indexed"}:
        _fail(f"{path}.name_kind", f"unsupported name kind {kind!r}")
    layer = record["layer"]
    if kind == "runtime":
        if name not in RUNTIME_NAMES or layer is not None:
            _fail(f"{path}.layer", "runtime tensors require explicit null layer")
    else:
        if name not in INDEXED_NAMES:
            _fail(f"{path}.name", "indexed name not admitted")
        if not isinstance(layer, int) or isinstance(layer, bool):
            _fail(f"{path}.layer", "indexed tensors require integer layer")
        match = LAYER_RE.search(name)
        if not match or int(match.group(1)) != layer:
            _fail(f"{path}.layer", "layer coordinate does not match tensor name")
        if layer < 0 or layer >= 45:
            _fail(f"{path}.layer", "layer outside retained 0..44 set")
        if role.startswith("kda_") and layer not in KDA_LAYERS:
            _fail(f"{path}.layer", "KDA role placed on non-KDA layer")
        if role.startswith("index_") and layer not in SPARSE_LAYERS:
            _fail(f"{path}.layer", "indexer role placed on non-sparse layer")
        if (role.startswith("routed_") or role.startswith("shared_") or role in {"router_correction_bias", "router_weight"}) and layer < 3:
            _fail(f"{path}.layer", "MoE role placed on dense layer")

    function = _nonempty_string(record["source_function"], f"{path}.source_function")
    if function not in SUPPORTED_FUNCTIONS:
        _fail(f"{path}.source_function", f"unsupported source function {function!r}")
    owner = _nonempty_string(record["state_owner"], f"{path}.state_owner")
    if owner not in SUPPORTED_STATE_OWNERS:
        _fail(f"{path}.state_owner", f"unsupported state owner {owner!r}")
    if role == "kda_recurrent_state" and owner != "kda.recurrent":
        _fail(f"{path}.state_owner", "recurrent state owner mismatch")
    if role == "kda_conv_suffix" and owner != "kda.conv_suffix":
        _fail(f"{path}.state_owner", "convolution suffix owner mismatch")
    if role not in {"kda_recurrent_state", "kda_conv_suffix"} and owner != "stateless":
        _fail(f"{path}.state_owner", "unexpected state ownership")

    precision = _nonempty_string(record["precision"], f"{path}.precision")
    if precision not in SUPPORTED_PRECISIONS:
        _fail(f"{path}.precision", f"unsupported precision {precision!r}")
    if kind == "indexed" and INDEXED_PRECISION_BY_ROLE[role] != precision:
        _fail(f"{path}.precision", "precision does not match retained role")
    companions = _string_list(record["quant_companions"], f"{path}.quant_companions", allow_empty=True)
    if precision in {"selected-4bit-affine-group64", "selected-8bit-affine-group64"}:
        if not name.endswith(".weight"):
            _fail(f"{path}.name", "quantized tensor name must end in .weight")
        expected = [name[:-7] + ".scales", name[:-7] + ".biases"]
        if companions != expected:
            _fail(f"{path}.quant_companions", f"expected exact companions {expected}")
    elif companions:
        _fail(f"{path}.quant_companions", "unquantized role cannot declare companions")
    _check_shape(record["shape"], f"{path}.shape", limits, kind)


def validate_contract(document: Any) -> Mapping[str, Any]:
    """Validate and return *document*; never fills defaults or repairs metadata."""

    root = _exact_keys(document, ROOT_KEYS, "$")
    if root["schema"] != SCHEMA:
        _fail("$.schema", f"unsupported schema {root['schema']!r}")
    if root["status"] != STATUS:
        _fail("$.status", f"unsupported status {root['status']!r}")

    source = _exact_keys(root["source_scope"], SOURCE_SCOPE_KEYS, "$.source_scope")
    if source["source_lock_sha256"] != "f7708546c13ea90fc0a4abc0f3152f596f3d8818eae87bc75b3f05e8490f6f11":
        _fail("$.source_scope.source_lock_sha256", "unrecognized corrected source lock")
    fixed_source = {
        "indexed_name_count": 2998,
        "language_layer_count": 45,
        "vision_block_count": 24,
        "complete_source_graph_claim": "complete indexed-name pattern inventory only",
        "toy_graph_claim": "only APIs, equations, edges, and tests listed in this file",
    }
    for key, expected in fixed_source.items():
        if source[key] != expected:
            _fail(f"$.source_scope.{key}", f"expected {expected!r}")
    if source["kda_layers"] != sorted(KDA_LAYERS):
        _fail("$.source_scope.kda_layers", "does not match retained KDA layer coordinates")
    if source["sparse_layers"] != sorted(SPARSE_LAYERS):
        _fail("$.source_scope.sparse_layers", "does not match retained sparse layer coordinates")
    if source["mtp_indexed_names"] != []:
        _fail("$.source_scope.mtp_indexed_names", "MTP indexed names must remain empty")
    _nonempty_string(source["runtime_revision"], "$.source_scope.runtime_revision")
    _nonempty_string(source["selected_artifact_revision"], "$.source_scope.selected_artifact_revision")
    _nonempty_string(source["mtp_config_observation"], "$.source_scope.mtp_config_observation")

    _check_fixed_mapping(root["limits"], EXPECTED_LIMITS, "$.limits")
    _check_fixed_mapping(root["constants"], EXPECTED_CONSTANTS, "$.constants")
    _check_fixed_mapping(root["seeds"], EXPECTED_SEEDS, "$.seeds")
    limits = _mapping(root["limits"], "$.limits")

    equations, equations_by_id = _records(root["source_equations"], EQUATION_KEYS, "$.source_equations")
    apis, apis_by_id = _records(root["apis"], API_KEYS, "$.apis")
    edges, edges_by_id = _records(root["edges"], EDGE_KEYS, "$.edges")
    tensors, tensors_by_id = _records(root["tensors"], TENSOR_KEYS, "$.tensors")
    tests, tests_by_id = _records(root["tests"], TEST_KEYS, "$.tests")
    _require_exact_ids(set(equations_by_id), EXPECTED_EQUATIONS, "$.source_equations")
    _require_exact_ids(set(apis_by_id), EXPECTED_APIS, "$.apis")
    _require_exact_ids(set(edges_by_id), EXPECTED_EDGES, "$.edges")
    _require_exact_ids(set(tests_by_id), EXPECTED_TESTS, "$.tests")

    for index, equation in enumerate(equations):
        path = f"$.source_equations[{index}]"
        _check_functions(equation["source_functions"], f"{path}.source_functions")
        edge_refs = _check_refs(equation["edge_ids"], edges_by_id, f"{path}.edge_ids")
        for edge_id in edge_refs:
            if equation["id"] not in edges_by_id[edge_id]["equation_ids"]:
                _fail(f"{path}.edge_ids", f"edge {edge_id!r} lacks reciprocal equation reference")

    for index, api in enumerate(apis):
        path = f"$.apis[{index}]"
        if api["symbol"] != api["id"]:
            _fail(f"{path}.symbol", "symbol must exactly match the public API id")
        _string_list(api["inputs"], f"{path}.inputs")
        _string_list(api["outputs"], f"{path}.outputs")
        _check_functions(api["source_functions"], f"{path}.source_functions")
        _check_refs(api["equation_ids"], equations_by_id, f"{path}.equation_ids")
        test_refs = _check_refs(api["test_ids"], tests_by_id, f"{path}.test_ids")
        for test_id in test_refs:
            if api["id"] not in tests_by_id[test_id]["api_ids"]:
                _fail(f"{path}.test_ids", f"test {test_id!r} lacks reciprocal API reference")

    incoming_ports = {api_id: set() for api_id in apis_by_id}
    outgoing_ports = {api_id: set() for api_id in apis_by_id}
    for index, edge in enumerate(edges):
        path = f"$.edges[{index}]"
        signature = (
            edge["producer"], edge["producer_port"],
            edge["consumer"], edge["consumer_port"],
        )
        if signature != EXPECTED_EDGE_ENDPOINTS[edge["id"]]:
            _fail(path, "semantic edge endpoints or ports differ from the frozen wiring")
        producer_kind, producer_name = _endpoint(edge["producer"], f"{path}.producer", apis_by_id, tests_by_id, producer=True)
        consumer_kind, consumer_name = _endpoint(edge["consumer"], f"{path}.consumer", apis_by_id, tests_by_id, producer=False)
        producer_port = _nonempty_string(edge["producer_port"], f"{path}.producer_port")
        consumer_port = _nonempty_string(edge["consumer_port"], f"{path}.consumer_port")
        if producer_kind == "api":
            if producer_port not in apis_by_id[producer_name]["outputs"]:
                _fail(f"{path}.producer_port", "port is not a declared API output")
            outgoing_ports[producer_name].add(producer_port)
        if consumer_kind == "api":
            if consumer_port not in apis_by_id[consumer_name]["inputs"]:
                _fail(f"{path}.consumer_port", "port is not a declared API input")
            incoming_ports[consumer_name].add(consumer_port)
        tensor_refs = _check_refs(edge["tensor_ids"], tensors_by_id, f"{path}.tensor_ids")
        equation_refs = _check_refs(edge["equation_ids"], equations_by_id, f"{path}.equation_ids")
        test_refs = _check_refs(edge["test_ids"], tests_by_id, f"{path}.test_ids")
        for tensor_id in tensor_refs:
            if edge["id"] not in tensors_by_id[tensor_id]["edge_ids"]:
                _fail(f"{path}.tensor_ids", f"tensor {tensor_id!r} lacks reciprocal edge reference")
        for equation_id in equation_refs:
            if edge["id"] not in equations_by_id[equation_id]["edge_ids"]:
                _fail(f"{path}.equation_ids", f"equation {equation_id!r} lacks reciprocal edge reference")
        for test_id in test_refs:
            if edge["id"] not in tests_by_id[test_id]["edge_ids"]:
                _fail(f"{path}.test_ids", f"test {test_id!r} lacks reciprocal edge reference")
    for api_id, api in apis_by_id.items():
        if incoming_ports[api_id] != set(api["inputs"]):
            _fail(f"$.apis[{api_id}].inputs", "not exactly covered by source-derived incoming edges")
        if outgoing_ports[api_id] != set(api["outputs"]):
            _fail(f"$.apis[{api_id}].outputs", "not exactly covered by tested outgoing edges")

    seen_names: dict[str, str] = {}
    for index, tensor in enumerate(tensors):
        path = f"$.tensors[{index}]"
        name = tensor["name"]
        if name in seen_names:
            _fail(f"{path}.name", f"duplicate tensor name; first used by {seen_names[name]!r}")
        seen_names[name] = tensor["id"]
        _check_tensor(tensor, path, limits)
        edge_refs = _check_refs(tensor["edge_ids"], edges_by_id, f"{path}.edge_ids")
        for edge_id in edge_refs:
            if tensor["id"] not in edges_by_id[edge_id]["tensor_ids"]:
                _fail(f"{path}.edge_ids", f"edge {edge_id!r} lacks reciprocal tensor reference")

    for index, test in enumerate(tests):
        path = f"$.tests[{index}]"
        api_refs = _check_refs(test["api_ids"], apis_by_id, f"{path}.api_ids", allow_empty=True)
        edge_refs = _check_refs(test["edge_ids"], edges_by_id, f"{path}.edge_ids", allow_empty=True)
        if not isinstance(test["seed"], int) or isinstance(test["seed"], bool) or test["seed"] not in EXPECTED_SEEDS.values():
            _fail(f"{path}.seed", "unsupported or non-integer seed")
        methods = set(_string_list(test["unittest_methods"], f"{path}.unittest_methods"))
        if methods != EXPECTED_TEST_METHODS[test["id"]]:
            _fail(f"{path}.unittest_methods", "does not exactly bind the frozen unittest methods")
        _string_list(test["criteria"], f"{path}.criteria")
        for api_id in api_refs:
            if test["id"] not in apis_by_id[api_id]["test_ids"]:
                _fail(f"{path}.api_ids", f"API {api_id!r} lacks reciprocal test reference")
        for edge_id in edge_refs:
            if test["id"] not in edges_by_id[edge_id]["test_ids"]:
                _fail(f"{path}.edge_ids", f"edge {edge_id!r} lacks reciprocal test reference")
    _string_list(root["uncertainties"], "$.uncertainties")
    return root


def _object_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            _fail("$", f"duplicate JSON field {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    _fail("$", f"non-finite JSON number {value!r}")


def validate_contract_document(text: str) -> Mapping[str, Any]:
    """Parse JSON with duplicate/non-finite rejection, then validate exactly."""

    if not isinstance(text, str):
        _fail("$", "document text must be a string")
    try:
        document = json.loads(
            text,
            object_pairs_hook=_object_no_duplicates,
            parse_constant=_reject_constant,
        )
    except ContractValidationError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        _fail("$", f"invalid JSON: {error}")
    return validate_contract(document)


def load_contract(path: str | Path) -> Mapping[str, Any]:
    """Read and strictly validate one local mini-contract JSON document."""

    contract_path = Path(path)
    return validate_contract_document(contract_path.read_text(encoding="utf-8"))


__all__ = [
    "ContractValidationError", "load_contract", "validate_contract",
    "validate_contract_document",
]
