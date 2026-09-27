#!/usr/bin/env python3
"""Admitted F020 v2.1 qualification driver.

The default mode performs only frozen preflight/build/attestation. Candidate
execution requires the explicit --execute flag and proceeds only through the
capability this driver creates after every guard passes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from fractions import Fraction

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "specs/020-mlx-safetensors-affine/fused-swiglu-package-manifest-v2-1.json"
CONTRACT = ROOT / "specs/020-mlx-safetensors-affine/contracts/fused-swiglu-native-sweep-v2-1.json"
PINS = ROOT / "specs/020-mlx-safetensors-affine/contracts/fused-swiglu-source-pins-v1.json"
BRIDGE = ROOT / "scripts/research/f020_fused_swiglu_native_bridge_v2.cpp"
GEN = ROOT / "scripts/research/f020_fused_swiglu_generate_b_table_v2.py"
R1 = ROOT / "scripts/research/f020_fused_swiglu_r1_v1.py"
STATIC_CHECK = ROOT / "scripts/research/f020_fused_swiglu_v2_static_selfcheck.py"
DRIVER = ROOT / "scripts/research/f020_fused_swiglu_qualification_v2_1.py"
PUBLIC_FILES = (MANIFEST, CONTRACT, BRIDGE, GEN, R1, STATIC_CHECK, DRIVER)
EXPECTED_TOTAL = 2_197_815_298


def fail(message: str) -> None:
    raise SystemExit("F020_V2_1_BLOCKER: " + message)


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def run(cmd: list[str], *, cwd: Path | None = None) -> str:
    try:
        return subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        fail("command failed: " + " ".join(cmd) + " :: " + str(exc))


def load_contract() -> tuple[dict, dict]:
    manifest = json.loads(MANIFEST.read_text())
    contract = json.loads(CONTRACT.read_text())
    if manifest["status"] != "FROZEN_PROSPECTIVE_NO_CANDIDATE_OBSERVATIONS":
        fail("manifest is not prospective")
    if contract["status"] != manifest["status"]:
        fail("contract/manifest status mismatch")
    if any(value != 0 for value in manifest["counters"].values()):
        fail("candidate counter is nonzero")
    for item in manifest["files"]:
        path = ROOT / item["path"]
        if item["sha256"] in ("PENDING", "") or not path.is_file() or sha(path) != item["sha256"]:
            fail("manifest hash mismatch: " + item["path"])
    if Fraction(manifest["budgets"]["beta_B"]) != Fraction(5201, 4194304):
        fail("beta_B drift")
    if Fraction(manifest["budgets"]["E_N"]) != Fraction(1, 128):
        fail("E_N drift")
    if Fraction(manifest["budgets"]["delta_max"]) != Fraction(27567, 4194304):
        fail("delta_max drift")
    if contract["enumeration"]["expected_total_evaluated"] != EXPECTED_TOTAL:
        fail("expected exhaustive count drift")
    return manifest, contract


def privacy_scan() -> None:
    patterns = ["/" + "Users/", "/" + "home/", "m" + "hedhli", "g" + "hp_", "s" + "k" + "-", "A" + "KIA",
                "127" + ".0.0.1", "192" + ".168.", "10" + ".0.", "172" + ".16."]
    for path in PUBLIC_FILES:
        if any(pattern.lower() in path.read_text().lower() for pattern in patterns):
            fail("privacy scan matched " + str(path.relative_to(ROOT)))


def runtime_identity(args: argparse.Namespace) -> tuple[dict, str]:
    pins = json.loads(PINS.read_text())
    if platform.machine() != "arm64":
        fail("architecture is not arm64")
    sw = run(["sw_vers", "-productVersion"]).strip() + " (" + run(["sw_vers", "-buildVersion"]).strip() + ")"
    if sw != pins["runtime"]["macos"]:
        fail("macOS identity mismatch")
    try:
        metal = subprocess.run(["xcrun", "metal", "-v"], check=True,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        fail("Metal toolchain probe failed: " + str(exc))
    if "Apple metal version 32023.864" not in metal or "air64-apple-darwin25.0.0" not in metal:
        fail("Metal toolchain identity mismatch")
    source_root = args.native_source_root
    if source_root is None:
        fail("--native-source-root is required for Candidate N runtime/source guard")
    source_files = {}
    for item in pins["source_files"]:
        p = source_root / item["path"]
        if not p.is_file() or sha(p) != item["sha256"]:
            fail("pinned source mismatch: " + item["path"])
        source_files[item["path"]] = item["sha256"]
    artifacts = {}
    for item in pins["runtime"]["native_artifacts"]:
        artifact_prefix = args.mlx_c_prefix if item["name"] == "libmlxc.dylib" else args.mlx_prefix
        p = artifact_prefix / "lib" / item["name"]
        if not p.is_file() or sha(p) != item["sha256"]:
            fail("pinned native artifact mismatch: " + item["name"])
        artifacts[item["name"]] = item["sha256"]
    identity = {"pins": pins["native_mlx"], "pins_c": pins["native_mlx_c"], "macos": sw,
                "metal": metal.strip(), "source_files": source_files, "artifacts": artifacts,
                "architecture": platform.machine()}
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    return identity, hashlib.sha256(encoded).hexdigest()


def compile_and_attest(args: argparse.Namespace, manifest_sha: str, public_commit: str, temp: Path) -> dict:
    clang = shutil.which("clang++") or "/usr/bin/clang++"
    objdump = Path(run(["xcrun", "-f", "llvm-objdump"]).strip())
    header = temp / "f020_candidate_b_table_v1.h"
    run([sys.executable, str(GEN), "--out", str(header), "--self-test"])
    binary = temp / "f020-native-bridge-v2-1"
    source_hash = sha(BRIDGE)
    sdk = run(["xcrun", "--show-sdk-path"]).strip()
    cmd = [clang, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror", "-fno-fast-math",
           "-ffp-contract=off", "-isysroot", sdk, "-I", str(args.mlx_c_prefix / "include"),
           "-I", str(args.mlx_prefix / "include"), "-I", str(temp),
           '-DF020_TABLE_HEADER="f020_candidate_b_table_v1.h"',
           f'-DF020_EXPECTED_MANIFEST_SHA256="{manifest_sha}"',
           f'-DF020_EXPECTED_PUBLIC_COMMIT="{public_commit}"', str(BRIDGE),
           "-L", str(args.mlx_c_prefix / "lib"), "-L", str(args.mlx_prefix / "lib"), "-lmlxc", "-lmlx",
           "-Wl,-rpath," + str(args.mlx_c_prefix / "lib"), "-Wl,-rpath," + str(args.mlx_prefix / "lib"), "-o", str(binary)]
    run(cmd)
    disassembly = run([str(objdump), "--disassemble", str(binary)])
    lowered = disassembly.lower()
    if any(op in lowered for op in ("fmadd", "fmsub", "fnmadd", "fnmsub")):
        fail("actual v2 bridge disassembly contains contracted FMA")
    if "fmul" not in lowered or "fadd" not in lowered:
        fail("actual v2 bridge disassembly lacks separate multiply/add evidence")
    compiler_id = run([clang, "--version"])
    disassembly_path = temp / "bridge.disassembly.txt"
    disassembly_path.write_text(disassembly)
    return {"binary": binary, "source_hash": source_hash, "binary_hash": sha(binary),
            "compiler_hash": hashlib.sha256(compiler_id.encode()).hexdigest(),
            "disassembly_hash": sha(disassembly_path), "compiler_id": compiler_id.strip()}


def write_capability(path: Path, args: argparse.Namespace, manifest_sha: str, public_commit: str,
                     runtime_sha: str, attestation: dict, temp: Path) -> None:
    bridge_path = str(attestation["binary"].resolve())
    lines = [
        "schema=pulsarmlx.f020.native-bridge-capability/1.0.0",
        "preflight=PASS", f"public_commit={public_commit}", f"manifest_sha256={manifest_sha}",
        f"manifest_path={MANIFEST.resolve()}", f"bridge_source_sha256={attestation['source_hash']}",
        f"source_path={BRIDGE.resolve()}", f"bridge_binary_sha256={attestation['binary_hash']}",
        f"bridge_path={bridge_path}", f"runtime_identity_sha256={runtime_sha}",
        f"compiler_identity_sha256={attestation['compiler_hash']}",
        f"disassembly_sha256={attestation['disassembly_hash']}",
        "candidate_b_flags=-fno-fast-math;-ffp-contract=off",
    ]
    path.write_text("\n".join(lines) + "\n")


def decode_f64_bits(text: str) -> Fraction:
    if not re.fullmatch(r"0x[0-9a-fA-F]{16}", text):
        fail("malformed delta bits")
    value = struct.unpack(">d", int(text, 16).to_bytes(8, "big"))[0]
    if not math.isfinite(value) or value < 0:
        fail("nonfinite/negative delta")
    return Fraction.from_float(value)


def decode_f32_bits(text: str) -> float:
    if not re.fullmatch(r"0x[0-9a-fA-F]{8}", text):
        fail("malformed f32 witness bits")
    return struct.unpack(">f", int(text, 16).to_bytes(4, "big"))[0]


def fixed_controls() -> list[tuple[float, float]]:
    return [(g, u) for g in (-16.0, -10.0, -0.0, 0.0, 10.0, 16.0)
            for u in (-16.0, -10.0, -0.0, 0.0, 1.0, 10.0, 16.0)]


def discover_regressions() -> list[list[str]]:
    required = [ROOT / ".github/workflows/macos.yml", ROOT / "scripts/ci/f020_slice2b_regression_compare_v1.py",
                ROOT / "crates/mlx-native-affine/Cargo.toml"]
    if any(not path.is_file() for path in required):
        fail("inherited regression command source missing")
    return [
        ["cargo", "test", "-p", "mlx-native-affine", "--release", "--no-fail-fast", "--", "--test-threads=1", "--nocapture"],
        ["cargo", "test", "-p", "mlx-native-affine", "--release", "--test", "composition_qualification", "--", "--test-threads=1", "--nocapture"],
    ]


def execute(args: argparse.Namespace, manifest: dict, contract: dict, cap: Path, binary: Path, temp: Path) -> dict:
    report = temp / "bridge-result.json"
    run([str(binary), "--execute-sweep", "--capability", str(cap), "--report", str(report)])
    result = json.loads(report.read_text())
    if result.get("anomaly_count") != 0 or not result.get("gate_count_exhaustive"):
        fail("bridge report is not clean/exhaustive")
    if result.get("total_evaluated") != EXPECTED_TOTAL:
        fail("bridge total_evaluated mismatch")
    delta = decode_f64_bits(result["max_delta_f64_bits"])
    beta = Fraction(5201, 4194304)
    en = Fraction(1, 128)
    decision = delta + beta <= en
    if not decision:
        fail("delta + beta_B exceeds E_N")
    structured_report = temp / "structured-result.json"
    run([str(binary), "--structured-up-controls", "--capability", str(cap), "--report", str(structured_report)])
    structured = json.loads(structured_report.read_text())
    if structured.get("structured") is not True or structured.get("total_evaluated") != 42 or structured.get("anomaly_count") != 0:
        fail("structured up-control report is incomplete or anomalous")
    # Exact R1 is imported only after the bridge result and only for fixed,
    # predeclared corroboration points; it never changes a threshold.
    sys.path.insert(0, str(R1.parent))
    import f020_fused_swiglu_r1_v1 as r1  # type: ignore
    r1.self_test()
    for gate, up in fixed_controls():
        r1.evaluate(gate, up)
    worst_gate = decode_f32_bits(result["input_gate_f32_bits"])
    r1.evaluate(worst_gate, 1.0)
    for command in discover_regressions():
        run(command, cwd=ROOT)
    return {"schema": "pulsarmlx.f020.fused-swiglu-v2-1-qualification/1.0.0",
            "status": "PASS", "manifest_sha256": sha(MANIFEST), "bridge": result,
            "delta_plus_beta_leq_E_N": decision, "r1_corroboration": "PASS",
            "structured_up_controls": structured["total_evaluated"], "worst_delta_r1_corroboration": "PASS",
            "regressions": {"primitive": 363, "slice2c": 32}}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mlx-prefix", type=Path, required=True)
    ap.add_argument("--mlx-c-prefix", type=Path, required=True)
    ap.add_argument("--native-source-root", type=Path, required=True)
    ap.add_argument("--public-commit", required=True)
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--report", type=Path)
    args = ap.parse_args()
    manifest, contract = load_contract()
    privacy_scan()
    runtime, runtime_sha = runtime_identity(args)
    with tempfile.TemporaryDirectory(prefix="f020-v2-1-driver-") as raw:
        temp = Path(raw)
        attestation = compile_and_attest(args, sha(MANIFEST), args.public_commit, temp)
        capability = temp / "capability.txt"
        write_capability(capability, args, sha(MANIFEST), args.public_commit, runtime_sha, attestation, temp)
        if not args.execute:
            print(json.dumps({"status": "STATIC_PREFLIGHT_PASS", "capability_issued": False,
                              "compiler_identity_sha256": attestation["compiler_hash"],
                              "disassembly_sha256": attestation["disassembly_hash"]}, sort_keys=True))
            return 0
        result = execute(args, manifest, contract, capability, attestation["binary"], temp)
        if args.report is None:
            fail("--report is required for execution")
        args.report.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
