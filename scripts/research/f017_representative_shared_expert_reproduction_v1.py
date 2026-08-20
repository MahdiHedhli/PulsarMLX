#!/usr/bin/env python3
"""Fresh-process retained-only reproduction for representative shared expert."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
EXECUTOR = ROOT / "scripts/research/f017_representative_shared_expert_recovery_executor_v1.py"
AUTHORIZATION = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-shared-expert-recovery-authorization-v1.json"


def sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load_executor():
    spec = importlib.util.spec_from_file_location("f017_shared_executor_reproduction", EXECUTOR)
    if spec is None or spec.loader is None:
        raise RuntimeError("EXECUTOR_IMPORT")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--representative-input", type=Path, required=True)
    parser.add_argument("--parameter-root", type=Path, required=True)
    parser.add_argument("--expected-output-sha256", required=True)
    args = parser.parse_args()
    module = load_executor()
    authorization_raw = AUTHORIZATION.read_bytes()
    authorization = json.loads(authorization_raw)
    module.validate_authorization(authorization)
    normalized, manifest, parameters = module.open_retained(
        authorization, args.representative_input, args.parameter_root
    )
    try:
        output = module.compute(authorization, normalized, parameters)
        after = module.verify_after(normalized, manifest, parameters)
    finally:
        module.close_all(normalized, manifest, parameters)
    output_sha256 = sha256_bytes(output)
    if output_sha256 != args.expected_output_sha256:
        raise RuntimeError("REPRODUCTION_OUTPUT_IDENTITY")
    packet = {
        "schema": "pulsarmlx.f017.representative-shared-expert-retained-reproduction",
        "schema_version": "1.0.0",
        "result": "EXACT_IDENTITY",
        "output_sha256": output_sha256,
        "output_bytes": len(output),
        "output_dtype": "little-endian-f32",
        "output_shape": [6144],
        "finite": True,
        "input_after_sha256": after,
        "checkpoint_reads": 0,
        "shard_opens": 0,
        "routed_aggregate_executions": 0,
        "ffn_completions": 0,
        "s2_constructions": 0,
        "authoritative_output_published": False,
    }
    print(json.dumps(packet, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
