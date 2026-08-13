#!/usr/bin/env python3
"""Create the sole immutable M1-E execution config without payload access."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

ACTIVATION = "specs/017-rust-native-inference-runtime/fixtures/f017-m1e-activation-v1.json"
ACTIVATION_PAYLOAD = "732ed2b9a6d3df0d185c1e35628a0b6b2cf30717cb697200d45b0e8a74008149"
M1 = {
    "m1_a": "aa0e480261db437eaa788f0dfcba10eba9c32b6e1448c566e5c426df62e5a805",
    "m1_b": "9f9bd444e0fcc2dce3c6bcc119c6113e1c7885eb863459bf73cacce1ff285770",
    "m1_c": "343548afefd4edbe844f0645c63cf0b9cb53edfcdbfc3b3d8e4b15f7c6c3041e",
    "m1_d": "dc5c4900da0cb0c2d293108a4abbdeccccd3c23899db265a84f73fda24ada53c",
    "m1_e_attempt_1": "346d6302648d463738b0ee0f7fc04a34f664675cccb60a181e3393b88b02b119",
}
CHECKPOINT = {
    "checkpoint_set_sha256": "d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee",
    "catalog_sha256": "0f0425106a240c5062acab9fc41b1b2651680c6ad06fe476214f88a8d2a177f0",
    "tensor_map_sha256": "ea0786f0e890af01dc111d355ef64aec1ca4898de5432197258bacccfaecc223",
}
ARTIFACTS = {
    "boundary_contract": "specs/017-rust-native-inference-runtime/contracts/m1e-expert-boundary-v1.json",
    "decoder_contract": "specs/017-rust-native-inference-runtime/contracts/m1e-decoder-contract-v2.json",
    "scaffold_contract": "specs/017-rust-native-inference-runtime/contracts/m1e-exact-scaffold-v1.json",
    "tier_b_contract": "specs/017-rust-native-inference-runtime/contracts/m1e-expert-tier-b-v1.json",
    "repeat_integrity_contract": "specs/017-rust-native-inference-runtime/contracts/m1e-repeat-integrity-v1.json",
    "timing_contract": "specs/017-rust-native-inference-runtime/contracts/m1e-timing-v1.json",
    "evidence_schema": "specs/017-rust-native-inference-runtime/contracts/m1e-evidence-v1.schema.json",
    "execution_config_schema": "specs/017-rust-native-inference-runtime/contracts/m1e-execution-config-v2.schema.json",
    "path_resolution_contract": "specs/017-rust-native-inference-runtime/contracts/m1d-artifact-path-resolution-v1.json",
    "activation_generator": "scripts/research/generate_f017_m1e_activation.py",
    "execution_config_preparer": "scripts/research/prepare_f017_m1e_execution.py",
    "authorized_launcher": "scripts/research/run_f017_m1e_authorized.py",
    "real_reference_preparer": "scripts/research/prepare_f017_m1e_real_reference.py",
    "independent_iq2_decoder": "scripts/research/iq2_xxs_dequant.py",
    "independent_iq3_decoder": "scripts/research/iq3_xxs_dequant.py",
    "third_iq3_decoder": "scripts/research/iq3_xxs_spec_decoder.py",
    "iq3_order_regression": "specs/017-rust-native-inference-runtime/fixtures/f017-iq3-xxs-order-regression-v1.json",
}
DECODER = "9a92bacda92e999a9062c154acd1b52c86e1d644f0d4d697defb2db40a85ce84"
TENSORS = [
    ("gate", "blk.3.ffn_gate_exps.weight", "IQ2_XXS", [6144, 2048, 256], [2048, 6144], 3423197024, 3244032, 1584, "42e379023728565d323fff8b120f2c6dff6fa50f10d9ad1cceb3e3597af36354"),
    ("up", "blk.3.ffn_up_exps.weight", "IQ2_XXS", [6144, 2048, 256], [2048, 6144], 4268636000, 3244032, 1584, "011ccab7ca2293da5b0d1112172b2dccd4b2cdb2482672dd217f996280223119"),
    ("down", "blk.3.ffn_down_exps.weight", "IQ3_XXS", [2048, 6144, 256], [6144, 2048], 2203342688, 4816896, 784, "1c7a04eb897d242a621a09c6dfb78c3e92b407dff44ddf8cf67187dae50081e1"),
]


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def artifact(root: Path, role: str, symbolic: str) -> dict[str, str]:
    return {"path_kind":"repository_relative","symbolic_path":symbolic,"content_sha256":sha(root / symbolic),"logical_role":role}


def write_exclusive(path: Path, document: dict[str, object]) -> str:
    raw = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o400)
    try:
        os.write(descriptor, raw)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return hashlib.sha256(raw).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, required=True)
    parser.add_argument("--package-root", type=Path, required=True)
    parser.add_argument("--environment-manifest", type=Path, required=True)
    parser.add_argument("--checkpoint-manifest", type=Path, required=True)
    parser.add_argument("--target-shard", type=Path, required=True)
    parser.add_argument("--runner-binary", type=Path, required=True)
    parser.add_argument("--oracle-launcher", type=Path, required=True)
    parser.add_argument("--runtime-sha", required=True)
    parser.add_argument("--tooling-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=("fixture_expert", "real_expert"), default="real_expert")
    args = parser.parse_args()
    root = args.repository_root.resolve(strict=True)
    package_root = args.package_root.resolve(strict=True)
    for value in (args.runtime_sha, args.tooling_sha):
        if len(value) != 40 or any(c not in "0123456789abcdef" for c in value):
            raise ValueError("runtime/tooling SHA must be canonical lowercase Git SHA")
    checkpoint = json.loads(args.checkpoint_manifest.read_text())
    shard = next(item for item in checkpoint["shards"] if item["filename"].endswith("00002-of-00006.gguf"))
    if args.target_shard.is_symlink():
        raise ValueError("target shard symlink is forbidden")
    target = args.target_shard.resolve(strict=True)
    runner = args.runner_binary.resolve(strict=True)
    launcher = args.oracle_launcher.resolve(strict=True)
    if target.name != shard["filename"] or target.stat().st_size != shard["size_bytes"]:
        raise ValueError("target shard metadata differs from reviewed manifest")
    tensors = [
        {"role":role,"name":name,"layer":3,"expert":15,"quantization":quant,"gguf_shape":gguf,"logical_matrix_shape":logical,"shard_ordinal":2,"offset":offset,"packed_length":length,"packed_row_width":row,"catalog_entry_sha256":catalog,"decoder_contract_sha256":DECODER,"path_kind":"bounded_checkpoint_range","allowed_read_count":1}
        for role, name, quant, gguf, logical, offset, length, row, catalog in TENSORS
    ]
    document = {
        "schema":"pulsarmlx.f017.m1e-execution-config","schema_version":"2.0.0","status":"READY_TO_EXECUTE_M1_E","attempt":2,"attempt_consumed":False,
        "runtime_sha":args.runtime_sha,"tooling_sha":args.tooling_sha,
        "repository_root":{"path_kind":"absolute_private_local","path":str(root),"identity":args.runtime_sha},
        "package_root":{"path_kind":"absolute_private_local","path":str(package_root),"identity":"m1e_attempt_2_private_package_root"},
        "activation_fixture":artifact(root,"activation_fixture",ACTIVATION),"activation_payload_sha256":ACTIVATION_PAYLOAD,
        "repository_artifacts":{role:artifact(root,role,path) for role,path in ARTIFACTS.items()},
        "local_artifacts":{
            "environment_manifest":{"path_kind":"absolute_private_local","path":str(args.environment_manifest.resolve(strict=True)),"content_sha256":sha(args.environment_manifest)},
            "checkpoint_manifest":{"path_kind":"absolute_private_local","path":str(args.checkpoint_manifest.resolve(strict=True)),"content_sha256":sha(args.checkpoint_manifest)},
            "runner_binary":{"path_kind":"absolute_private_local","path":str(runner),"content_sha256":sha(runner)},
            "oracle_launcher":{"path_kind":"absolute_private_local","path":str(launcher),"content_sha256":sha(launcher)},
            "target_shard":{"path_kind":"absolute_private_local","path":str(target),"ordinal":2,"basename":target.name,"byte_size":target.stat().st_size,"content_sha256":shard["sha256"]},
            "oracle_output":str(package_root / "m1e-oracle-attempt-2-v1.json"),"package_output":str(package_root / "m1e-package-attempt-2-v1.json"),"attempt_state_output":str(package_root / "m1e-attempt-2-state-v1.json"),"preflight_evidence_output":str(package_root / "m1e-attempt-2-preflight-evidence-v1.json"),"evidence_output":str(package_root / "m1e-attempt-2-evidence-v1.json")},
        "prior_evidence":M1,"checkpoint_bindings":CHECKPOINT,
        "expert":{"layer":3,"expert":15,"symbolic_id":"blk.3.expert.15"},"tensors":tensors,
        "runner":{"mode":args.mode,"memory_floor_bytes":17179869184 if args.mode == "real_expert" else 1},
        "execution":{"conceptual_expert_count":1,"repeat_count":10,"native_dispatch_count":30,"maximum_payload_count":3,"maximum_positional_reads":3,"maximum_shard_opens":1,"compressed_byte_budget":11304960,"auto_retry":False,"stop_before_m1_f":True},
    }
    print(write_exclusive(args.output, document))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
