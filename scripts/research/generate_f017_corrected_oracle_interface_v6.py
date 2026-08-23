#!/usr/bin/env python3
"""Generate the initial v6 authorization interface from the rejected v5 view.

V5 remains immutable historical design evidence.  V6 adds the separately
measured target-source bindings and updates generation authority.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-authorization-consumer-interface-v5.json"
OUTPUT = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-authorization-consumer-interface-v6.json"


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode() + b"\n"


def main() -> int:
    value = json.loads(SOURCE.read_text())
    value["schema"] = "pulsarmlx.f017.corrected-oracle-authorization-consumer-interface/6.0.0"
    value["interface_scope"] = "PRODUCTION"
    value["authorization_schema"] = "pulsarmlx.f017.corrected-full-checkpoint-oracle-access-authorization/6.0.0"
    value["semantic_model_path"] = "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-lifecycle-semantic-model-v6.json"
    value["semantic_model_sha256"] = "0" * 64
    value["artifact_schema_authority"] = "specs/017-rust-native-inference-runtime/contracts/f017-corrected-oracle-artifact-schemas-v6.json"
    value["artifact_schema_authority_sha256"] = "0" * 64
    value["pinned_values"]["authority_generation"] = 6
    value["pinned_values"]["schema"] = value["authorization_schema"]
    checkpoint_index = value["top_level_keys"].index("checkpoint_root")
    value["top_level_keys"][checkpoint_index:checkpoint_index] = [
        "checkpoint_catalog_path",
        "geometry_path",
        "geometry_sha256",
        "shards",
    ]
    index = value["consumer_keys"].index("numerical_path")
    value["consumer_keys"][index:index] = ["target_source_path", "target_source_sha256"]
    value["pinned_context"] = {
        "prompt_token": 9703,
        "position": 0,
        "kv_state": "EMPTY",
        "mask": "ONE_VISIBLE_KEY_CAUSAL",
        "sampling": "NONE_GREEDY_ARGMAX",
        "top_n": 32,
    }
    value["pinned_limits"] = {
        "checkpoint_shard_count": 6,
        "graph_payload_shard_count": 5,
        "identity_only_shard_count": 1,
        "graph_tensor_count": 1410,
        "non_access_tensor_count": 399,
        "expected_token_field_permitted": False,
        "p1_authority": "PROHIBITED",
    }
    value["shard_keys"] = ["filename", "size_bytes", "sha256", "access_role"]
    data = canonical(value)
    temporary = OUTPUT.with_name(OUTPUT.name + ".generating")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, OUTPUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
