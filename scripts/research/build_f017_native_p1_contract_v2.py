#!/usr/bin/env python3
"""Build the exact non-authorizing F017 native bounded-P1 contract."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-native-bounded-p1-admission-contract-v2.json"

CODE = [
    "Cargo.lock",
    "crates/f017-native/Cargo.toml",
    "crates/f017-native/build.rs",
    "crates/f017-native/src/lib.rs",
    "crates/f017-native/src/contract.rs",
    "crates/f017-native/src/executor.rs",
    "crates/f017-native/src/loader.rs",
    "crates/f017-native/src/model.rs",
    "crates/f017-native/src/bin/bounded_p1.rs",
    "crates/gguf/src/lib.rs",
    "crates/quant/build.rs",
    "crates/quant/src/lib.rs",
    "crates/quant/src/cpu_dot.rs",
    "crates/quant/src/cpu_dot_tables.rs",
    "crates/quant/src/extra_ref.rs",
    "crates/quant/src/iq.rs",
    "crates/quant/src/iq_ref.rs",
    "crates/quant/src/q6_k_ref.rs",
    "crates/stream/build.rs",
    "crates/stream/src/lib.rs",
    "crates/stream/src/p1_domain.rs",
    "crates/stream/src/apple_mlx_bridge.rs",
    "crates/stream/src/apple_mlx_bridge.mm",
    "crates/stream/src/apple_mlx_deallocation_observer.mm",
]


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def binding(path: str) -> dict[str, object]:
    return {"path": path, "sha256": sha(ROOT / path)}


def main() -> None:
    manifest_path = "docs/validation/glm52-checkpoint.json"
    manifest = json.loads((ROOT / manifest_path).read_text())
    prefix = Path("/opt/homebrew/opt/pulsarmlx-f017-native-mlx-0.31.2")
    contract = {
        "schema": "pulsarmlx.f017.native-bounded-p1-admission-contract/2.0.0",
        "status": "PREPARED_HUMAN_GATE_REQUIRED",
        "branch": "feat/017-rust-native-inference-runtime",
        "execution_code_head": "22a76e4c248434a1827e81501607f93b0779352e",
        "executor": binding("specs/017-rust-native-inference-runtime/bin/f017-native-bounded-p1"),
        "code_manifest": [binding(path) for path in CODE],
        "authorities": {
            "cross_branch_authority": binding("specs/017-rust-native-inference-runtime/contracts/f017-native-domain-cross-branch-authority-v1.json"),
            "execution_architecture": binding("specs/017-rust-native-inference-runtime/contracts/f017-native-bounded-p1-execution-architecture-v2.json"),
            "runtime_provenance": binding("specs/017-rust-native-inference-runtime/contracts/f017-native-bounded-p1-runtime-provenance-v1.json"),
            "d0": binding("specs/017-rust-native-inference-runtime/contracts/f017-native-bounded-p1-numeric-acceptance-contract-v2.json"),
            "d1": binding("specs/017-rust-native-inference-runtime/contracts/f017-native-bounded-p1-counter-semantics-v1.json"),
            "d2": binding("specs/017-rust-native-inference-runtime/contracts/f017-native-bounded-p1-accounting-residency-v1.json"),
            "retention_reuse_grant": binding("specs/017-rust-native-inference-runtime/contracts/f017-native-representative-retention-reuse-grant-v1.json"),
            "comparison_read_grant": binding("specs/017-rust-native-inference-runtime/contracts/f017-native-d3-5-comparison-read-grant-v1.json"),
            "d3_5_result": binding("docs/architecture/reviews/evidence/f017-native-d3-5-numerical-grading-result-v1.json"),
            "d3_5_acceptance": binding("docs/architecture/reviews/evidence/f017-native-d3-5-numerical-qualification-acceptance-v1.json"),
            "synthetic_full_graph_result": binding("docs/architecture/reviews/evidence/f017-native-full-model-synthetic-qualification-v2.json"),
            "historical_master_ledger_sha256": "aa98f5cc7f1cfae1eb49a9bc64dbefec1d6ef9ccae1504a1aa8879a8edf22e3e",
            "historical_master_terminal_value": 175,
        },
        "checkpoint": {
            "root_environment": "PULSARMLX_GLM_GGUF",
            "manifest": binding(manifest_path),
            "catalog": binding("docs/research/glm52/raw/f016-c01-catalog-0001.json"),
            "checkpoint_set_sha256": manifest["checkpoint_set_sha256"],
            "fallback": "PROHIBITED",
            "shards": [
                {"filename": row["filename"], "sha256": row["sha256"], "size_bytes": row["size_bytes"]}
                for row in manifest["files"]
            ],
        },
        "runtime": {
            "machine_brand": "Apple M1 Ultra",
            "architecture": "arm64",
            "macos_build": "25A354",
            "mlx_version": "0.31.2",
            "mlx_c_version": "0.6.0",
            "rustc_version": "rustc 1.97.1 (8bab26f4f 2026-07-14) (Homebrew)",
            "build_profile": "release",
            "minimum_available_memory_bytes": 17179869184,
            "memory_sample_max_age_seconds": 5,
            "dylibs": [
                {"path": str(prefix / "lib/libmlx.dylib"), "sha256": sha(prefix / "lib/libmlx.dylib")},
                {"path": str(prefix / "lib/libmlxc.dylib"), "sha256": sha(prefix / "lib/libmlxc.dylib")},
            ],
            "environment": {
                "MLX_C_PREFIX": str(prefix),
                "MLX_PREFIX": str(prefix),
                "OMP_NUM_THREADS": "1",
                "PULSAR_REQUIRE_NATIVE_MLX": "1",
                "RAYON_NUM_THREADS": "1",
                "VECLIB_MAXIMUM_THREADS": "1"
            },
        },
        "one_shot": {
            "attempt_id": "F017-NATIVE-BOUNDED-P1-ATTEMPT-1",
            "prompt_token": 9703,
            "expected_token": 21615,
            "attempts": 1,
            "retries": 0,
            "resume": False,
            "mandatory_stop": True,
            "generated_token_limit": 1,
            "sequence_position": 0,
            "initial_kv_state": "EMPTY_CLEAN_PROCESS",
            "receipt_schema": "pulsarmlx.f017.native-bounded-p1-execution-receipt/2.0.0",
        },
        "state_root": "/Users/mhedhli/.local/share/pulsarmlx/f017/native-bounded-p1-v1",
        "live_authorization_present": False,
        "normal_validation_can_authorize": False,
    }
    OUT.write_text(json.dumps(contract, indent=2, sort_keys=True) + "\n")
    print(f"{sha(OUT)}  {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
