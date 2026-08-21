#!/usr/bin/env python3
"""Retained-only package assembly and validation for F017 Apple serial-f32.

This program has no checkpoint interface and no numerical execution mode.  It
derives the exact 40-tensor census from accepted committed authorities, copies
those bytes without transformation, and computes a deterministic package root
from the ordered census plus rehashed destination bytes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile


class ReadinessError(RuntimeError):
    pass


REPO = Path(__file__).resolve().parents[2]
PACKAGE_PARENT = Path("/Users/mhedhli/.local/share/pulsarmlx/f017/apple-production-serial-f32-equivalence-readiness-1")
PACKAGE_ROOT = PACKAGE_PARENT / "retained-package"
PACKAGE_JSON = PACKAGE_PARENT / "package.json"
PACKAGE_CENSUS = PACKAGE_PARENT / "package-census.json"
ATTEMPT_ROOT = Path("/Users/mhedhli/.local/share/pulsarmlx/f017/apple-production-serial-f32-equivalence-release-1/attempt-state")
CAPTURE_ROOT = Path("/Users/mhedhli/.local/share/pulsarmlx/f017/apple-production-serial-f32-equivalence-release-1/captures")
EXECUTION_CODE_HEAD_BINDING = REPO / "specs/017-rust-native-inference-runtime/contracts/f017-apple-production-serial-f32-execution-code-head-v1.json"

S0 = Path("/Users/mhedhli/Documents/Coding/PulsarMLX-f017-vocabulary/.pulsarmlx-local/dprefix-exact-1/retained/layer_3_entry.f32le")
ATTN_ROOT = Path("/Users/mhedhli/.local/share/pulsarmlx/f017/representative-m1f0-release-1/retention/packed")
ROUTER_ROOT = Path("/Users/mhedhli/Documents/Coding/PulsarMLX-f017-runner/.pulsarmlx-local/representative-m1f0-router-reuse-1")
EXPERT_ROOT = Path("/Users/mhedhli/Documents/Coding/PulsarMLX-f017-runner/.pulsarmlx-local/canonical-expert-output-recovery-1/event-state/retained-packed")
SHARED_ROOT = Path("/Users/mhedhli/Documents/Coding/PulsarMLX-f017-runner/.pulsarmlx-local/canonical-shared-expert-output-recovery-1/package/packed")

REAL_RESULT = REPO / "docs/architecture/reviews/evidence/f017-representative-m1f0-real-execution-result-v1.json"
EXPERT_AUTH = REPO / "specs/017-rust-native-inference-runtime/contracts/f017-representative-expert-packed-weight-reuse-authorization-v1.json"
SHARED_AUTH = REPO / "specs/017-rust-native-inference-runtime/contracts/f017-representative-shared-expert-recovery-authorization-v1.json"
BOUNDARY = REPO / "specs/017-rust-native-inference-runtime/contracts/f017-representative-m1f0-boundary-v3.json"

AUTHORITY_HASHES = {
    REAL_RESULT: "dc53b458fe9c189b4cfbfd83889e7997aa5decba799c421944ac93edb237f190",
    EXPERT_AUTH: "fb6eb026bee375674c5d6ac0f18b837ad17ea770868d7c3dbd4f5e94decf4b39",
    SHARED_AUTH: "45b25de7978e01898eb5ea948202d70d5b43f33c2cbc84ec7b11a9955c5d9596",
    BOUNDARY: "a9dc0d9effb3e52844203a34be587d12f0f7b011fb58d33c5dbdbe5b650deed3",
}

ATTENTION = [
    ("attention_norm_scale", "00.bin", "F32_LE", [6144]),
    ("q_a", "01.bin", "Q5_K", [2048, 6144]),
    ("q_rank_norm_scale", "02.bin", "F32_LE", [2048]),
    ("q_b", "03.bin", "Q8_0", [64, 256, 2048]),
    ("kv_a", "04.bin", "Q8_0", [576, 6144]),
    ("kv_norm_scale", "05.bin", "F32_LE", [512]),
    ("k_b", "06.bin", "Q8_0", [64, 512, 192]),
    ("v_b", "07.bin", "Q8_0", [64, 256, 512]),
    ("attention_output", "08.bin", "Q5_K", [6144, 16384]),
]
ROUTER = [
    ("ffn_norm_scale", "ffn_norm_weight.bin", "F32_LE", [6144], "1d9228483902bf2ca1088589d25c1cbc116facd82454a117e7dafb2d48f83d8f"),
    ("correction_bias", "router_bias.bin", "F32_LE", [256], "eb6feeb8d7ab446e4e786aaac55c22cc7b98521dbd71cb0a57610d8da59b0491"),
    ("router", "router_matrix.bin", "F32_LE", [256, 6144], "da0263ba11f06e21532aff708b8677c76381c1165e11134c72d7039ebb64439a"),
]
EXPERT_IDS = [250, 10, 237, 62, 73, 177, 218, 28]


def load_unique(path: Path):
    def pairs(rows):
        value = {}
        for key, item in rows:
            if key in value:
                raise ReadinessError(f"DUPLICATE_JSON_KEY:{path}:{key}")
            value[key] = item
        return value
    try:
        return json.loads(path.read_text(), object_pairs_hook=pairs)
    except (OSError, json.JSONDecodeError) as exc:
        raise ReadinessError(f"JSON:{path}:{exc}") from exc


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode() + b"\n"


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fsync_dir(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def validate_source(path: Path, expected_sha: str, expected_bytes: int) -> None:
    meta = os.lstat(path)
    if not stat.S_ISREG(meta.st_mode) or stat.S_ISLNK(meta.st_mode):
        raise ReadinessError(f"SOURCE_FILE_POLICY:{path}")
    if meta.st_nlink != 1 or meta.st_mode & 0o222:
        raise ReadinessError(f"SOURCE_IMMUTABILITY:{path}")
    if meta.st_size != expected_bytes or sha(path) != expected_sha:
        raise ReadinessError(f"SOURCE_IDENTITY:{path}")


def expected_f32_bytes(shape: list[int]) -> int:
    count = 1
    for item in shape:
        count *= item
    return count * 4


def derive_descriptors() -> list[dict]:
    for path, expected in AUTHORITY_HASHES.items():
        if sha(path) != expected:
            raise ReadinessError(f"COMMITTED_AUTHORITY:{path}")
    result = load_unique(REAL_RESULT)
    receipts = result["receipts"]
    if len(receipts) != 9:
        raise ReadinessError("ATTENTION_RECEIPT_CENSUS")
    receipt_by_ordinal = {row["ordinal"]: row for row in receipts}
    descriptors = [{
        "canonical_tensor_id": "layer3.s0",
        "role": "s0",
        "source_path": str(S0),
        "source_authority_path": "docs/architecture/reviews/evidence/f017-dprefix-exact1-descriptor-v1.json",
        "source_authority_sha256": "393bd6f6e933aa8a50e1a836328e91cb3a42b68b08249d723c70190f4fa52256",
        "source_result_event": "DPREFIX-EXACT-1",
        "sha256": "9c3a8821deda6a9983b49544d5726efad97b2e560f55a7eb0f182aaa128ceb11",
        "encoding": "F32_LE", "shape": [6144], "byte_count": 24576,
        "quantization": "F32", "decoder_binding": "CANONICAL_F32_LE",
    }]
    for ordinal, (role, filename, encoding, shape) in enumerate(ATTENTION):
        receipt = receipt_by_ordinal[ordinal]
        descriptors.append({
            "canonical_tensor_id": receipt["key"], "role": role,
            "source_path": str(ATTN_ROOT / filename),
            "source_authority_path": str(REAL_RESULT.relative_to(REPO)),
            "source_authority_sha256": AUTHORITY_HASHES[REAL_RESULT],
            "source_result_event": "F017-REPRESENTATIVE-M1F0-ATTEMPT-1",
            "sha256": receipt["packed_sha256"], "encoding": encoding,
            "shape": shape, "byte_count": receipt["packed_bytes"],
            "quantization": encoding.replace("_LE", ""),
            "decoder_binding": f"F017_APPLE_{encoding}_V1",
        })
    for role, filename, encoding, shape, expected_sha in ROUTER:
        descriptors.append({
            "canonical_tensor_id": {"ffn_norm_scale":"blk.3.ffn_norm.weight","correction_bias":"blk.3.exp_probs_b.bias","router":"blk.3.ffn_gate_inp.weight"}[role],
            "role": role, "source_path": str(ROUTER_ROOT / filename),
            "source_authority_path": "specs/017-rust-native-inference-runtime/contracts/f017-representative-m1f0-router-retained-authority-reuse-v1.json",
            "source_authority_sha256": "175539424a5fe1b66c60d1e95c8361858d90fd4566b24b4915c2b1affda5023b",
            "source_result_event": "F017-REPRESENTATIVE-M1F0-ATTEMPT-1",
            "sha256": expected_sha, "encoding": encoding, "shape": shape,
            "byte_count": expected_f32_bytes(shape), "quantization": "F32",
            "decoder_binding": "CANONICAL_F32_LE",
        })
    expert = load_unique(EXPERT_AUTH)["retained_payload_inventory"]
    by_key = {(row["expert_id"], row["role"]): row for row in expert}
    if len(by_key) != 24:
        raise ReadinessError("EXPERT_CENSUS")
    for slot, expert_id in enumerate(EXPERT_IDS):
        for role in ("gate", "up", "down"):
            row = by_key[(expert_id, role)]
            descriptors.append({
                "canonical_tensor_id": row["checkpoint_key"],
                "role": f"routed.{slot}.{role}",
                "source_path": str(EXPERT_ROOT / row["source_relative_path"]),
                "source_authority_path": str(EXPERT_AUTH.relative_to(REPO)),
                "source_authority_sha256": AUTHORITY_HASHES[EXPERT_AUTH],
                "source_result_event": f"F017-CANONICAL-EXPERT-OUTPUT-RECOVERY:{row['source_event_sequence']}",
                "sha256": row["packed_sha256"], "encoding": row["quantization"],
                "shape": row["logical_shape"], "byte_count": row["packed_bytes"],
                "quantization": row["quantization"],
                "decoder_binding": "F017_IQ2_XXS_DUAL_ACCEPTED" if role != "down" else "F017_IQ3_XXS_DUAL_ACCEPTED",
                "decoded_sha256": row["decoded_sha256"], "expert_id": expert_id,
            })
    shared = load_unique(SHARED_AUTH)["retained_parameters"]
    if len(shared) != 3:
        raise ReadinessError("SHARED_CENSUS")
    for row in shared:
        descriptors.append({
            "canonical_tensor_id": row["checkpoint_key"], "role": f"shared.{row['role']}",
            "source_path": str(SHARED_ROOT / Path(row["relative_path"]).name),
            "source_authority_path": str(SHARED_AUTH.relative_to(REPO)),
            "source_authority_sha256": AUTHORITY_HASHES[SHARED_AUTH],
            "source_result_event": "F017-CANONICAL-SHARED-EXPERT-OUTPUT-RECOVERY-1",
            "sha256": row["packed_sha256"], "encoding": row["quantization"],
            "shape": row["decoded_shape"], "byte_count": row["packed_bytes"],
            "quantization": row["quantization"], "decoder_binding": f"F017_{row['quantization']}_DUAL_ACCEPTED",
            "decoded_sha256": row["decoded_sha256"],
        })
    if len(descriptors) != 40 or len({row["role"] for row in descriptors}) != 40:
        raise ReadinessError("TOTAL_CENSUS")
    for ordinal, row in enumerate(descriptors):
        row["ordinal"] = ordinal
        suffix = ".f32le" if row["encoding"] == "F32_LE" else ".bin"
        row["destination_relative_path"] = f"tensors/{ordinal:02d}-{row['role'].replace('.', '-')}{suffix}"
        validate_source(Path(row["source_path"]), row["sha256"], row["byte_count"])
    return descriptors


def root_document(descriptors: list[dict]) -> dict:
    fields = ("ordinal", "canonical_tensor_id", "role", "destination_relative_path", "sha256", "byte_count", "encoding", "shape", "quantization", "decoder_binding", "source_authority_path", "source_authority_sha256", "source_result_event")
    return {
        "schema": "pulsarmlx.f017.apple-production-serial-f32-retained-package-root",
        "schema_version": "1.0.0", "package_version": "F017-APPLE-SERIAL-F32-RETAINED-40-V1",
        "tensor_count": 40,
        "ordered_tensor_descriptors": [{key: row[key] for key in fields} for row in descriptors],
    }


def package_root_sha(descriptors: list[dict]) -> str:
    return hashlib.sha256(canonical(root_document(descriptors))).hexdigest()


def write_exclusive(path: Path, data: bytes, mode: int = 0o400) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        os.write(descriptor, data)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def execution_code_head() -> str:
    value = load_unique(EXECUTION_CODE_HEAD_BINDING)
    head = value.get("execution_code_head")
    if value.get("schema") != "pulsarmlx.f017.apple-production-serial-f32-execution-code-head" or not isinstance(head, str) or len(head) != 40:
        raise ReadinessError("EXECUTION_CODE_HEAD_BINDING")
    return head


def make_runner_package(descriptors: list[dict]) -> dict:
    return {
        "schema": "pulsarmlx.f017.apple-production-serial-f32-package", "schema_version": "1.0.0",
        "graph_version": "f017-apple-serial-f32-s0-s2-v1", "execution_code_head": execution_code_head(),
        "fixed_attempt_root": str(ATTEMPT_ROOT), "fixed_capture_root": str(CAPTURE_ROOT),
        "tensors": {row["role"]: {"path": str(PACKAGE_ROOT / row["destination_relative_path"]), "sha256": row["sha256"], "encoding": row["encoding"], "shape": row["shape"]} for row in descriptors},
        "position": 0, "rope_base": 1000000.0, "attention_scale": 0.0625,
        "expert_weight_scale": 2.5, "heads": 64, "qk_nope": 192, "qk_rope": 64,
        "kv_lora": 512, "value_dim": 256, "routed_expert_ids": EXPERT_IDS,
        "runtime": {"device":"APPLE_METAL_GPU","mlx_version":"0.32.1","mlx_c_version":"0.6.0_4","libmlx_sha256":"c30b1529178de28d23817e6e73ea5133cf63af060379c41a27aa7420aa616b3d","libmlxc_sha256":"9882fe1f7ec1fcdb10cebde60e88b41826ab4dfed8ae624b99be419d6fa89561","backend":"MLX_C_MATVEC_PLUS_RUST_SERIAL_F32","thread_limits":{"OPENBLAS_NUM_THREADS":"1","OMP_NUM_THREADS":"1","VECLIB_MAXIMUM_THREADS":"1","MKL_NUM_THREADS":"1","NUMEXPR_NUM_THREADS":"1"}},
        "checkpoint_paths": [],
    }


def census_document(descriptors: list[dict]) -> dict:
    root = package_root_sha(descriptors)
    return {
        **root_document(descriptors), "package_root_sha256": root,
        "package_root_path": str(PACKAGE_ROOT), "runner_package_path": str(PACKAGE_JSON),
        "total_bytes": sum(row["byte_count"] for row in descriptors),
        "assembly_operation": "BYTE_FOR_BYTE_COPY_NO_TRANSFORMATION",
        "checkpoint_reads": 0, "shard_opens": 0, "numerical_transformations": 0,
        "source_destination_identity_required": True,
    }


def validate_destination(descriptors: list[dict]) -> dict:
    if not PACKAGE_ROOT.is_dir() or PACKAGE_ROOT.is_symlink():
        raise ReadinessError("PACKAGE_ROOT_POLICY")
    expected_files = {row["destination_relative_path"] for row in descriptors}
    actual_files = {str(path.relative_to(PACKAGE_ROOT)) for path in PACKAGE_ROOT.rglob("*") if path.is_file()}
    actual_dirs = {str(path.relative_to(PACKAGE_ROOT)) for path in PACKAGE_ROOT.rglob("*") if path.is_dir()}
    if actual_files != expected_files or actual_dirs != {"tensors"}:
        raise ReadinessError("PACKAGE_EXTRA_MISSING")
    for row in descriptors:
        dest = PACKAGE_ROOT / row["destination_relative_path"]
        validate_source(dest, row["sha256"], row["byte_count"])
        if sha(Path(row["source_path"])) != sha(dest):
            raise ReadinessError(f"SOURCE_DESTINATION_MISMATCH:{row['role']}")
    census = load_unique(PACKAGE_CENSUS)
    expected_census = census_document(descriptors)
    if census != expected_census or census["package_root_sha256"] != package_root_sha(descriptors):
        raise ReadinessError("PACKAGE_ROOT_REDERIVATION")
    package = load_unique(PACKAGE_JSON)
    if package != make_runner_package(descriptors):
        raise ReadinessError("RUNNER_PACKAGE_BINDING")
    return {"tensor_count": 40, "total_bytes": expected_census["total_bytes"], "package_root_sha256": expected_census["package_root_sha256"], "source_destination_byte_identity": "40/40 PASS"}


def assemble(descriptors: list[dict]) -> dict:
    PACKAGE_PARENT.mkdir(parents=True, exist_ok=True, mode=0o700)
    if PACKAGE_ROOT.exists() or PACKAGE_JSON.exists() or PACKAGE_CENSUS.exists():
        return validate_destination(descriptors)
    temp = Path(tempfile.mkdtemp(prefix="package.tmp.", dir=PACKAGE_PARENT))
    try:
        tensors = temp / "tensors"
        tensors.mkdir(mode=0o700)
        for row in descriptors:
            dest = temp / row["destination_relative_path"]
            with Path(row["source_path"]).open("rb") as source:
                write_exclusive(dest, source.read(), 0o400)
            if sha(dest) != row["sha256"]:
                raise ReadinessError(f"COPY_IDENTITY:{row['role']}")
        fsync_dir(tensors); fsync_dir(temp)
        os.rename(temp, PACKAGE_ROOT)
        fsync_dir(PACKAGE_PARENT)
        write_exclusive(PACKAGE_CENSUS, canonical(census_document(descriptors)))
        write_exclusive(PACKAGE_JSON, canonical(make_runner_package(descriptors)))
        fsync_dir(PACKAGE_PARENT)
    finally:
        if temp.exists():
            shutil.rmtree(temp)
    return validate_destination(descriptors)


def refresh_runner_package(descriptors: list[dict]) -> dict:
    if ATTEMPT_ROOT.exists() or CAPTURE_ROOT.exists():
        raise ReadinessError("EXECUTION_STATE_PRESENT_NO_REFRESH")
    if not PACKAGE_ROOT.is_dir() or not PACKAGE_CENSUS.is_file():
        raise ReadinessError("PACKAGE_NOT_ASSEMBLED")
    expected = canonical(make_runner_package(descriptors))
    temporary = PACKAGE_PARENT / "package.json.refresh"
    if temporary.exists():
        raise ReadinessError("REFRESH_TEMP_PRESENT")
    write_exclusive(temporary, expected)
    if PACKAGE_JSON.exists():
        PACKAGE_JSON.chmod(0o600)
        PACKAGE_JSON.unlink()
    os.rename(temporary, PACKAGE_JSON)
    fsync_dir(PACKAGE_PARENT)
    return validate_destination(descriptors)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--assemble", action="store_true")
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--print-census", action="store_true")
    parser.add_argument("--refresh-runner-package", action="store_true")
    args = parser.parse_args()
    if sum((args.assemble, args.validate, args.print_census, args.refresh_runner_package)) != 1:
        raise SystemExit("choose exactly one mode")
    descriptors = derive_descriptors()
    if args.assemble:
        result = assemble(descriptors)
    elif args.validate:
        result = validate_destination(descriptors)
    elif args.print_census:
        result = census_document(descriptors)
    else:
        result = refresh_runner_package(descriptors)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
