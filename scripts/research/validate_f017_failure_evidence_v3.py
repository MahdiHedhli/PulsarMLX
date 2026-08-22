#!/usr/bin/env python3
"""Validate forward-only F017 P1 v3 failure evidence from durable bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


COUNTERS = {
    "callback_count", "managed_created", "managed_destroyed", "derived_created",
    "derived_destroyed", "default_cpu_stream_created", "default_cpu_stream_freed",
    "default_gpu_stream_created", "default_gpu_stream_freed", "owned_stream_created",
    "owned_stream_freed", "native_default_cpu_stream_freed",
    "native_default_gpu_stream_freed", "native_owned_stream_freed",
    "native_live_stream_handles", "native_duplicate_free_attempts",
    "native_origin_mismatches", "context_active", "registrations", "teardowns",
    "in_flight_work", "stale_native_ready_generations",
}

RECEIPT_KEYS = {
    "schema", "event_class", "authorization_id", "attempt_id", "contract_sha256",
    "executor_sha256", "git_head", "checkpoint_manifest_sha256",
    "checkpoint_catalog_sha256", "checkpoint_set_sha256",
    "historical_master_ledger_sha256", "historical_master_before",
    "historical_master_after", "historical_master_delta", "native_event_delta", "runtime",
    "pre_snapshot_sha256", "post_snapshot_sha256", "access_census_sha256",
    "numerical_diagnostic_manifest_sha256", "prompt_token", "expected_token",
    "produced_token", "generated_token_count", "execution_result", "error_class",
    "mandatory_stop_observed", "terminal_state", "started_at_unix_ns",
    "completed_at_unix_ns",
}

TERMINAL_KEYS = {
    "schema", "state", "authorization_id", "attempt_id", "owner_pid",
    "ownership_nonce", "receipt_count", "receipt_sha256", "pre_snapshot_sha256",
    "post_snapshot_sha256", "access_census_sha256",
    "numerical_diagnostic_manifest_sha256", "produced_token", "error_class",
    "terminalized_at_unix_ns", "retry_permitted",
}

SNAPSHOT_KEYS = {
    "schema", "phase", "authorization_id", "attempt_id", "captured_at_unix_ns", "counters",
}

RUNTIME_KEYS = {
    "mlx_version", "mlx_c_version", "architecture", "machine_brand",
    "stream_origin", "native_handle_owned", "deallocation_responsibility",
}

ACCESS_KEYS = {
    "schema", "authorization_id", "attempt_id", "event_count",
    "shard_open_count", "shard_identity_rehash_count",
    "read_only_private_map_count", "tensor_lookup_count",
    "tensor_first_use_count", "tensor_reuse_count",
    "page_residency_observation_count",
    "historical_explicit_payload_extraction_count",
    "unexpected_access_attempt_count", "fallback_attempt_count",
    "alternate_root_attempt_count", "events",
}

ACCESS_EVENT_KEYS = {
    "schema", "sequence", "kind", "authority_id", "sha256", "size_bytes",
    "tensor_name", "result", "recorded_at_unix_ns",
}

DIAGNOSTIC_KEYS = {
    "schema", "backend", "serialization", "synchronization",
    "direct_production_bytes", "layers", "final_hidden_state_sha256",
    "final_norm_sha256", "full_logits_sha256", "logits_dtype", "logits_shape",
    "top_token_ids", "top_logit_f32_bits", "selected_token", "expected_token",
    "tie_rule",
}

LAYER_KEYS = {
    "layer", "layer_input_sha256", "post_attention_residual_sha256",
    "router_normalized_input_sha256", "selected_expert_ids",
    "routing_weight_f32_bits", "routed_aggregate_sha256", "shared_expert_sha256",
    "layer_output_sha256", "hidden_width", "dtype", "byte_order",
}

EVENT_KINDS = {
    "SHARD_OPEN": "shard_open_count",
    "SHARD_IDENTITY_REHASH": "shard_identity_rehash_count",
    "READ_ONLY_PRIVATE_MMAP": "read_only_private_map_count",
    "TENSOR_LOOKUP": "tensor_lookup_count",
    "TENSOR_FIRST_USE": "tensor_first_use_count",
    "TENSOR_REUSE": "tensor_reuse_count",
    "PAGE_RESIDENCY_OBSERVATION": "page_residency_observation_count",
    "HISTORICAL_EXPLICIT_PAYLOAD_EXTRACTION": "historical_explicit_payload_extraction_count",
    "UNEXPECTED_ACCESS_ATTEMPT": "unexpected_access_attempt_count",
    "FALLBACK_ATTEMPT": "fallback_attempt_count",
    "ALTERNATE_ROOT_ATTEMPT": "alternate_root_attempt_count",
}


def strict_json(path: Path) -> dict[str, Any]:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in pairs:
            if key in out:
                raise ValueError(f"duplicate JSON key {key!r} in {path}")
            out[key] = value
        return out
    value = json.loads(path.read_text(), object_pairs_hook=unique)
    if not isinstance(value, dict):
        raise ValueError(f"object required: {path}")
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def exact(value: dict[str, Any], keys: set[str], label: str) -> None:
    if set(value) != keys:
        raise ValueError(f"{label} key census mismatch")


def validate(attempt: Path) -> dict[str, Any]:
    paths = {
        "receipt": attempt / "execution-receipt.json",
        "terminal": attempt / "terminal.json",
        "pre": attempt / "pre-accounting-snapshot.json",
        "post": attempt / "post-accounting-snapshot.json",
        "access": attempt / "access-census.json",
        "diagnostic": attempt / "numerical-diagnostic-manifest.json",
    }
    if any(path.is_symlink() or not path.is_file() for path in paths.values()):
        raise ValueError("missing or unsafe durable evidence")
    receipt, terminal = strict_json(paths["receipt"]), strict_json(paths["terminal"])
    pre, post = strict_json(paths["pre"]), strict_json(paths["post"])
    access, diagnostic = strict_json(paths["access"]), strict_json(paths["diagnostic"])
    exact(receipt, RECEIPT_KEYS, "receipt")
    exact(terminal, TERMINAL_KEYS, "terminal")
    exact(pre, SNAPSHOT_KEYS, "pre snapshot")
    exact(post, SNAPSHOT_KEYS, "post snapshot")
    exact(receipt["runtime"], RUNTIME_KEYS, "runtime")
    exact(access, ACCESS_KEYS, "access census")
    exact(diagnostic, DIAGNOSTIC_KEYS, "diagnostic")
    if receipt["schema"] != "pulsarmlx.f017.native-bounded-p1-execution-receipt/3.0.0" \
            or terminal["schema"] != "pulsarmlx.f017.native-bounded-p1-terminal/2.0.0":
        raise ValueError("receipt/terminal schema")
    if pre["schema"] != "pulsarmlx.f017.native-bounded-p1-accounting-snapshot/1.0.0" \
            or post["schema"] != pre["schema"]:
        raise ValueError("snapshot schema")
    for label, snapshot in (("pre", pre), ("post", post)):
        if set(snapshot["counters"]) != COUNTERS:
            raise ValueError(f"{label} counter census")
        if any(type(value) is not int or value < 0 for value in snapshot["counters"].values()):
            raise ValueError(f"{label} counter type")
    bindings = {
        "receipt_sha256": sha256(paths["receipt"]),
        "pre_snapshot_sha256": sha256(paths["pre"]),
        "post_snapshot_sha256": sha256(paths["post"]),
        "access_census_sha256": sha256(paths["access"]),
        "numerical_diagnostic_manifest_sha256": sha256(paths["diagnostic"]),
    }
    for field, digest in bindings.items():
        if terminal[field] != digest:
            raise ValueError(f"terminal {field} binding")
        if field != "receipt_sha256" and receipt[field] != digest:
            raise ValueError(f"receipt {field} binding")
    if terminal["receipt_count"] != 1 or terminal["retry_permitted"] is not False:
        raise ValueError("terminal receipt/retry census")
    if receipt["authorization_id"] != terminal["authorization_id"] \
            or receipt["attempt_id"] != terminal["attempt_id"]:
        raise ValueError("receipt/terminal identity mismatch")
    identities = (receipt["authorization_id"], receipt["attempt_id"])
    if (pre["authorization_id"], pre["attempt_id"]) != identities \
            or (post["authorization_id"], post["attempt_id"]) != identities \
            or (access["authorization_id"], access["attempt_id"]) != identities:
        raise ValueError("nested evidence identity mismatch")
    if receipt["prompt_token"] != 9703 or receipt["expected_token"] != 21615:
        raise ValueError("token authority mismatch")
    if receipt["generated_token_count"] != int(receipt["produced_token"] is not None):
        raise ValueError("generated-token census")
    if receipt["historical_master_before"] != 175 \
            or receipt["historical_master_after"] != 175 \
            or receipt["historical_master_delta"] != 0:
        raise ValueError("historical ledger relationship")
    if not receipt["mandatory_stop_observed"]:
        raise ValueError("mandatory stop absent")
    events = access.get("events")
    if not isinstance(events, list) or access.get("event_count") != len(events):
        raise ValueError("access event census")
    if [event.get("sequence") for event in events] != list(range(len(events))):
        raise ValueError("access event continuity")
    computed = {field: 0 for field in EVENT_KINDS.values()}
    event_dir = attempt / "access-events"
    if event_dir.is_symlink() or not event_dir.is_dir():
        raise ValueError("missing or unsafe incremental access event directory")
    event_paths = sorted(event_dir.iterdir())
    if len(event_paths) != len(events):
        raise ValueError("incremental access event file census")
    for sequence, (event, event_path) in enumerate(zip(events, event_paths, strict=True)):
        exact(event, ACCESS_EVENT_KEYS, "access event")
        if event["schema"] != "pulsarmlx.f017.native-bounded-p1-access-event/1.0.0" \
                or event["kind"] not in EVENT_KINDS:
            raise ValueError("access event schema/kind")
        if event_path.name != f"{sequence:08}.json" or event_path.is_symlink() \
                or not event_path.is_file() or strict_json(event_path) != event:
            raise ValueError("incremental access event byte binding")
        if type(event["size_bytes"]) is not int or event["size_bytes"] < 0 \
                or type(event["recorded_at_unix_ns"]) is not int:
            raise ValueError("access event types")
        computed[EVENT_KINDS[event["kind"]]] += 1
    if any(access[field] != count for field, count in computed.items()):
        raise ValueError("access event derived count mismatch")
    if access["schema"] != "pulsarmlx.f017.native-bounded-p1-access-census/1.0.0":
        raise ValueError("access census schema")
    if diagnostic.get("schema") != "pulsarmlx.f017.native-bounded-p1-diagnostic-manifest/1.0.0":
        raise ValueError("diagnostic schema")
    layers = diagnostic["layers"]
    if not isinstance(layers, list):
        raise ValueError("diagnostic layer census")
    for expected_layer, layer in enumerate(layers):
        exact(layer, LAYER_KEYS, "diagnostic layer")
        if layer["layer"] != expected_layer or layer["dtype"] != "little-endian-f32" \
                or type(layer["hidden_width"]) is not int or layer["hidden_width"] <= 0:
            raise ValueError("diagnostic layer identity")
        for field in (
            "layer_input_sha256", "post_attention_residual_sha256",
            "router_normalized_input_sha256", "routed_aggregate_sha256",
            "shared_expert_sha256", "layer_output_sha256",
        ):
            if len(layer[field]) != 64:
                raise ValueError("diagnostic layer hash")
    if len(diagnostic["top_token_ids"]) != len(diagnostic["top_logit_f32_bits"]) \
            or len(diagnostic["top_token_ids"]) > 32 \
            or diagnostic["expected_token"] != receipt["expected_token"] \
            or diagnostic["selected_token"] != receipt["produced_token"]:
        raise ValueError("final diagnostic binding")
    allowed_results = {
        "EXPECTED_TOKEN_MATCH": "COMPLETE_MANDATORY_STOP",
        "TOKEN_MISMATCH": "TERMINAL_FAILURE_NO_RETRY",
        "PRODUCER_FAILURE": "TERMINAL_FAILURE_NO_RETRY",
        "ACCOUNTING_FAILURE": "TERMINAL_FAILURE_NO_RETRY",
    }
    if allowed_results.get(receipt["execution_result"]) != receipt["terminal_state"] \
            or terminal["state"] != receipt["terminal_state"]:
        raise ValueError("execution result/terminal classification")
    if not (pre["captured_at_unix_ns"] <= post["captured_at_unix_ns"]
            <= receipt["completed_at_unix_ns"] <= terminal["terminalized_at_unix_ns"]):
        raise ValueError("evidence timestamp ordering")
    return {
        "status": "PASS",
        "execution_result": receipt["execution_result"],
        "receipt_sha256": bindings["receipt_sha256"],
        "terminal_sha256": sha256(paths["terminal"]),
        "access_event_count": len(events),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("attempt", type=Path)
    args = parser.parse_args()
    print(json.dumps(validate(args.attempt), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
