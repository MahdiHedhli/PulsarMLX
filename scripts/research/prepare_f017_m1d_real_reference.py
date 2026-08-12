#!/usr/bin/env python3
"""Prepare the local-only real M1-D oracle before candidate execution.

This tool is intentionally not invoked by checkpoint-free CI. A later, explicit
M1-D authorization may use it to read exactly one reviewed Q8_0 range, decode
with independent NumPy, apply the frozen activation, and atomically create the
pre-candidate oracle/package. It never launches the Rust runner or MLX.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
import time
from pathlib import Path

import numpy as np

import generate_f017_m1d_projection_oracle as frozen

OFFSET = 1_077_266_272
LENGTH = 3_760_128


def exclusive_write(path: Path, data: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    path.chmod(stat.S_IRUSR)


def main() -> int:
    preparation_started_at = time.time_ns()
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-shard", type=Path, required=True)
    parser.add_argument("--checkpoint-manifest", type=Path, required=True)
    parser.add_argument("--activation-oracle", type=Path, required=True)
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--runtime-source-sha", required=True)
    parser.add_argument("--output-oracle", type=Path, required=True)
    parser.add_argument("--output-package", type=Path, required=True)
    args = parser.parse_args()

    repository_root = args.repository_root.resolve(strict=True)
    repository_identity = subprocess.run(
        ["git", "-C", str(repository_root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if repository_identity != args.runtime_source_sha:
        raise SystemExit("repository root differs from the authorized runtime source")
    if args.output_oracle.parent.resolve(strict=True) != args.output_package.parent.resolve(strict=True):
        raise SystemExit("oracle and package must share one private package root")

    activation_doc = json.loads(args.activation_oracle.read_text())
    activation_bytes = bytes.fromhex(activation_doc["activation"]["bytes_hex"])
    if frozen.sha256(activation_bytes) != activation_doc["activation"]["sha256"]:
        raise SystemExit("activation identity mismatch")
    activation = np.frombuffer(activation_bytes, dtype="<f4").copy()

    with args.target_shard.open("rb", buffering=0) as handle:
        handle.seek(OFFSET)
        packed = handle.read(LENGTH)
        if len(packed) != LENGTH:
            raise SystemExit("short real M1-D tensor read")
    decoded = frozen.decode_q8(packed)
    output = frozen.sequential_matvec(decoded, activation)
    output_bytes = frozen.f32_bytes(output)
    matrix_sha = frozen.sha256(packed)

    checkpoint = json.loads(args.checkpoint_manifest.read_text())
    if checkpoint["checkpoint_set_sha256"] != "d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee":
        raise SystemExit("checkpoint set differs from accepted M1-B")
    oracle = {
        "schema": frozen.SCHEMA,
        "schema_version": frozen.SCHEMA_VERSION,
        "generator": {
            "version": "f017-m1d-independent-real-reference-v1",
            "source_sha256": frozen.sha256(Path(__file__).read_bytes()),
            "python": frozen.platform.python_version(),
            "numpy": np.__version__,
            "seed": frozen.SEED,
            "prng": "frozen_activation_only",
        },
        "boundary": activation_doc["boundary"],
        "activation": activation_doc["activation"],
        "synthetic_matrix": {
            "generator": "reviewed_real_q8_0_range",
            "packed_sha256": matrix_sha,
            "decoded_f32_sha256": frozen.sha256(frozen.f32_bytes(decoded)),
        },
        "oracle": {
            "scaffold_version": frozen.SCAFFOLD_VERSION,
            "decoder_contract_version": frozen.DECODER_VERSION,
            "output_f32_hex": output_bytes.hex(),
            "output_sha256": frozen.sha256(output_bytes),
        },
        "tier_b": {"contract_version": frozen.TIER_B_VERSION, **frozen.tier_b(decoded, activation, output)},
        "policies": activation_doc["policies"],
        "stress_cases": activation_doc["stress_cases"],
        "checkpoint_accessed": True,
        "finalization": {
            "preparation_started_at": str(preparation_started_at),
            "oracle_completed_at": str(time.time_ns()),
            "completion_marker": "oracle_finalized_sequence_0",
            "immutable_after_finalization": True,
        },
    }
    oracle_bytes = (json.dumps(oracle, indent=2, sort_keys=True) + "\n").encode()

    contracts_relative = Path("specs/017-rust-native-inference-runtime/contracts")

    def binding(filename: str, version: str, role: str) -> dict:
        symbolic_path = contracts_relative / filename
        path = repository_root / symbolic_path
        return {
            "version": version,
            "path_kind": "repository_relative",
            "symbolic_path": symbolic_path.as_posix(),
            "content_sha256": frozen.sha256(path.read_bytes()),
            "logical_role": role,
        }

    package = {
        "schema": "pulsarmlx.f017.m1d-projection-package",
        "schema_version": "2.0.0",
        "package_kind": "production_reviewed",
        "path_resolution_contract": binding(
            "m1d-artifact-path-resolution-v1.json",
            "f017-m1d-artifact-path-resolution-v1",
            "path_resolution_contract",
        ),
        "boundary_contract": binding("m1d-projection-boundary-v1.json", "f017-m1d-projection-boundary-v1", "boundary_contract"),
        "decoder_contract": binding("m1d-q8-0-decoder-v1.json", frozen.DECODER_VERSION, "decoder_contract"),
        "scaffold_contract": binding("m1d-exact-scaffold-v1.json", frozen.SCAFFOLD_VERSION, "scaffold_contract"),
        "tier_b_contract": binding("production-m1d-projection-tier-b-v1.json", frozen.TIER_B_VERSION, "tier_b_contract"),
        "checkpoint_set_sha256": checkpoint["checkpoint_set_sha256"],
        "catalog_sha256": checkpoint["catalog_sha256"],
        "tensor_map_sha256": "ea0786f0e890af01dc111d355ef64aec1ca4898de5432197258bacccfaecc223",
        "prior_evidence": {
            "m1_a_sha256": "aa0e480261db437eaa788f0dfcba10eba9c32b6e1448c566e5c426df62e5a805",
            "m1_b_sha256": "9f9bd444e0fcc2dce3c6bcc119c6113e1c7885eb863459bf73cacce1ff285770",
            "m1_c_sha256": "343548afefd4edbe844f0645c63cf0b9cb53edfcdbfc3b3d8e4b15f7c6c3041e",
        },
        "tensor": {
            "name": "blk.0.attn_kv_a_mqa.weight", "layer": 0,
            "role": "mla_kv_latent_projection", "shard_ordinal": 2,
            "offset": OFFSET, "packed_length": LENGTH, "quantization": "Q8_0",
            "gguf_shape": [6144, 576], "matrix_shape": [576, 6144],
            "output_shape": [576], "packed_sha256": matrix_sha,
        },
        "oracle": {
            "path_kind": "package_relative",
            "symbolic_path": args.output_oracle.name,
            "content_sha256": frozen.sha256(oracle_bytes),
            "logical_role": "independent_oracle",
            "package_artifact_id": "f017-m1d-independent-real-oracle-v1",
        },
        "activation_sha256": activation_doc["activation"]["sha256"],
        "one_attempt": True,
    }
    exclusive_write(args.output_oracle, oracle_bytes)
    exclusive_write(args.output_package, (json.dumps(package, indent=2, sort_keys=True) + "\n").encode())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
