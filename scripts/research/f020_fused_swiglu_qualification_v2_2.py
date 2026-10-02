#!/usr/bin/env python3
"""Admitted F020 v2.2 qualification driver.

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
MANIFEST = ROOT / "specs/020-mlx-safetensors-affine/fused-swiglu-package-manifest-v2-2.json"
CONTRACT = ROOT / "specs/020-mlx-safetensors-affine/contracts/fused-swiglu-native-sweep-v2-2.json"
PINS = ROOT / "specs/020-mlx-safetensors-affine/contracts/fused-swiglu-source-pins-v1.json"
BRIDGE = ROOT / "scripts/research/f020_fused_swiglu_native_bridge_v2.cpp"
GEN = ROOT / "scripts/research/f020_fused_swiglu_generate_b_table_v2.py"
R1 = ROOT / "scripts/research/f020_fused_swiglu_r1_v1.py"
STATIC_CHECK = ROOT / "scripts/research/f020_fused_swiglu_v2_2_static_selfcheck.py"
DRIVER = ROOT / "scripts/research/f020_fused_swiglu_qualification_v2_2.py"
TESTS = ROOT / "scripts/research/tests/test_f020_fused_swiglu_qualification_v2_2.py"
REPAIR_NOTE = ROOT / "specs/020-mlx-safetensors-affine/fused-swiglu-v2-3-repair-note.md"
EXPECTED_TOTAL = 2_197_815_298
BRANCH = "feat/020-synthetic-expert-mlp-20260925"
PRIMITIVE_MANIFEST = ROOT / "fixtures/native-primitives/manifest.json"
COMPOSITION_MANIFEST = ROOT / "fixtures/native-composition/manifest.json"
PRIMITIVE_SHA = "472b5b64aaddfe7ecbfd05930ba2f4d261023a9a829f957b5b23b110fcf37d04"
COMPOSITION_SHA = "6f0e39e6d2c705603f3f897133d42c31837c53348aba0f4b0389dca18018fc14"
PUBLIC_FILES = (MANIFEST, CONTRACT, PINS, BRIDGE, GEN, R1, STATIC_CHECK, DRIVER,
                TESTS, REPAIR_NOTE, PRIMITIVE_MANIFEST, COMPOSITION_MANIFEST)


def fail(message: str) -> None:
    raise SystemExit("F020_V2_2_BLOCKER: " + message)


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


def git_authority(requested: str) -> str:
    branch = run(["git", "branch", "--show-current"], cwd=ROOT).strip()
    head = run(["git", "rev-parse", "HEAD"], cwd=ROOT).strip()
    try:
        status = subprocess.run(["git", "status", "--porcelain=v1", "--untracked-files=all"], cwd=ROOT,
                                capture_output=True, text=True, check=False)
    except OSError as exc:
        fail("Git status failed; cleanliness is unproved: " + str(exc))
    if status.returncode != 0:
        fail("Git status failed; cleanliness is unproved")
    remote = run(["git", "ls-remote", "origin", f"refs/heads/{BRANCH}"], cwd=ROOT).split()
    if requested != head or branch != BRANCH or status.stdout or not remote or remote[0] != head:
        fail("Git authority mismatch: require requested==HEAD, exact branch, clean tree, and origin parity")
    return head


def frozen_population(path: Path, expected_sha: str, expected_count: int) -> dict:
    if not path.is_file() or sha(path) != expected_sha:
        fail("frozen population manifest hash mismatch: " + str(path.relative_to(ROOT)))
    data = json.loads(path.read_text())
    cases = data.get("cases")
    if data.get("case_count") != expected_count or not isinstance(cases, list) or len(cases) != expected_count:
        fail("frozen population case-count mismatch: " + str(path.relative_to(ROOT)))
    ids = [case.get("id") for case in cases]
    if any(not isinstance(case_id, str) for case_id in ids) or len(set(ids)) != expected_count:
        fail("frozen population case IDs are not exact and unique")
    return {"manifest": str(path.relative_to(ROOT)), "manifest_sha256": expected_sha,
            "case_count": expected_count, "case_ids": ids}


def frozen_populations() -> dict:
    return {"primitive": frozen_population(PRIMITIVE_MANIFEST, PRIMITIVE_SHA, 363),
            "slice2c": frozen_population(COMPOSITION_MANIFEST, COMPOSITION_SHA, 32)}


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
        f"execution_root={temp.resolve()}", f"capability_path={path.resolve()}",
    ]
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(fd, ("\n".join(lines) + "\n").encode())
    finally:
        os.close(fd)
    if not path.is_file() or path.is_symlink() or (path.stat().st_mode & 0o077):
        fail("capability file is not a restrictive regular file")


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


def r1_check(r1, gate: float, up: float, n_bits: str, b_bits: str) -> dict:
    n = decode_f32_bits(n_bits); b = decode_f32_bits(b_bits)
    if not math.isfinite(n) or not math.isfinite(b):
        fail("R1 corroboration encountered nonfinite candidate evidence")
    interval = r1.evaluate(gate, up)
    n_frac = Fraction.from_float(n); b_frac = Fraction.from_float(b)
    n_distance = max(Fraction(0), interval.lo - n_frac, n_frac - interval.hi)
    b_distance = max(Fraction(0), interval.lo - b_frac, b_frac - interval.hi)
    radius = interval.width / 2
    n_bound = n_distance + radius
    b_bound = b_distance + radius
    if n_bound > Fraction(1, 128) or b_bound > Fraction(5201, 4194304):
        fail("exact-R1 corroboration budget exceeded")
    return {"gate": gate, "up": up, "gate_f32_bits": f"0x{struct.unpack('>I', struct.pack('>f', gate))[0]:08x}",
            "up_f32_bits": f"0x{struct.unpack('>I', struct.pack('>f', up))[0]:08x}",
            "candidate_n_output_f32_bits": n_bits, "candidate_b_output_f32_bits": b_bits,
            "interval_lo": str(interval.lo), "interval_hi": str(interval.hi),
            "interval_width": str(interval.width), "interval_radius": str(radius),
            "n_distance": str(n_distance), "b_distance": str(b_distance),
            "n_bound": str(n_bound), "b_bound": str(b_bound)}


def fixed_controls() -> list[tuple[float, float]]:
    return [(g, u) for g in (-16.0, -10.0, -0.0, 0.0, 10.0, 16.0)
            for u in (-16.0, -10.0, -0.0, 0.0, 1.0, 10.0, 16.0)]


def f32_bits(value: float) -> str:
    return f"0x{struct.unpack('>I', struct.pack('>f', value))[0]:08x}"


def validate_structured_controls(report: dict) -> list[dict]:
    expected = fixed_controls()
    controls = report.get("controls")
    if (report.get("schema") != "pulsarmlx.f020.native-bridge-v2-2-structured/1.0.0"
            or report.get("structured") is not True or report.get("total_evaluated") != len(expected)
            or report.get("anomaly_count") != 0 or not isinstance(controls, list)
            or len(controls) != len(expected)):
        fail("structured up-control report is incomplete or anomalous")
    for index, ((gate, up), item) in enumerate(zip(expected, controls)):
        if not isinstance(item, dict) or item.get("gate_f32_bits") != f32_bits(gate) or item.get("up_f32_bits") != f32_bits(up):
            fail(f"structured control {index} differs from frozen gate/up grid")
        n_bits = item.get("candidate_n_output_f32_bits")
        b_bits = item.get("candidate_b_output_f32_bits")
        delta_bits = item.get("upward_rounded_abs_delta_bits")
        if not all(isinstance(value, str) for value in (n_bits, b_bits, delta_bits)):
            fail(f"structured control {index} lacks candidate/delta bit evidence")
        n = decode_f32_bits(n_bits)
        b = decode_f32_bits(b_bits)
        if not math.isfinite(n) or not math.isfinite(b):
            fail(f"structured control {index} has nonfinite candidate evidence")
        expected_delta = Fraction.from_float(math.nextafter(abs(n - b), math.inf))
        if decode_f64_bits(delta_bits) != expected_delta:
            fail(f"structured control {index} delta does not match candidate bits")
    return controls


def discover_regressions() -> list[list[str]]:
    required = [ROOT / ".github/workflows/macos.yml", ROOT / "scripts/ci/f020_slice2b_regression_compare_v1.py",
                ROOT / "crates/mlx-native-affine/Cargo.toml"]
    if any(not path.is_file() for path in required):
        fail("inherited regression command source missing")
    return [
        ["cargo", "test", "-p", "mlx-native-affine", "--release", "--no-fail-fast", "--", "--test-threads=1", "--nocapture"],
        ["cargo", "test", "-p", "mlx-native-affine", "--release", "--test", "composition_qualification", "--", "--test-threads=1", "--nocapture"],
    ]


def verify_regression_summary(root: Path, population: dict, label: str) -> dict:
    summary_path = root / "qualification/summary.json"
    if not summary_path.is_file():
        fail(label + " qualification summary missing")
    summary = json.loads(summary_path.read_text())
    if summary.get("result") != "PASS" or summary.get("failures") != []:
        fail(label + " qualification summary is not PASS")
    frozen = summary.get("frozen", {})
    if frozen.get("case_count") != population["case_count"] or frozen.get("population_valid_after") is not True:
        fail(label + " summary does not prove frozen case count/population")
    cases = summary.get("cases")
    if not isinstance(cases, list) or len(cases) != population["case_count"]:
        fail(label + " summary case population is not exact")
    observed = [case.get("id") for case in cases]
    if observed != population["case_ids"] or not all(case.get("pass") is True for case in cases):
        fail(label + " summary case IDs or pass evidence do not match frozen manifest")
    return {"manifest": population["manifest"], "manifest_sha256": population["manifest_sha256"],
            "expected_case_count": population["case_count"], "observed_case_count": len(cases),
            "summary": str(summary_path), "summary_sha256": sha(summary_path),
            "case_ids_exact": True}


def run_regressions(temp: Path, populations: dict) -> dict:
    roots = [temp / "primitive", temp / "slice2c"]
    outputs = []
    for command, root, label, population in zip(discover_regressions(), roots,
                                                ("primitive", "slice2c"),
                                                (populations["primitive"], populations["slice2c"])):
        root.mkdir(parents=True)
        env = os.environ.copy()
        env["PULSAR_F020_QUALIFICATION_OUT"] = str(root) if label == "primitive" else env.get("PULSAR_F020_QUALIFICATION_OUT", str(root))
        env["PULSAR_F020_COMPOSITION_OUT"] = str(root)
        proc = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            fail(label + " inherited qualification command failed: " + str(proc.returncode))
        outputs.append({"label": label, "command": command, "exit": proc.returncode,
                       "proven": verify_regression_summary(root, population, label)})
    return {item["label"]: item for item in outputs}


def execute(args: argparse.Namespace, manifest: dict, contract: dict, cap: Path, binary: Path,
            temp: Path, attestation: dict, runtime_sha: str, public_commit: str, populations: dict) -> dict:
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
    cap2 = temp / "capability-structured.txt"
    write_capability(cap2, args, sha(MANIFEST), public_commit, runtime_sha, attestation, temp)
    run([str(binary), "--structured-up-controls", "--capability", str(cap2), "--report", str(structured_report)])
    structured = json.loads(structured_report.read_text())
    controls = validate_structured_controls(structured)
    # Exact R1 is imported only after bridge evidence exists. It is an actual
    # interval admission check, never a synthesized PASS or threshold tuner.
    sys.path.insert(0, str(R1.parent))
    import f020_fused_swiglu_r1_v1 as r1  # type: ignore
    r1.self_test()
    structured_checks = []
    for item in controls:
        check = r1_check(r1, decode_f32_bits(item["gate_f32_bits"]),
                         decode_f32_bits(item["up_f32_bits"]),
                         item["candidate_n_output_f32_bits"],
                         item["candidate_b_output_f32_bits"])
        check["upward_rounded_abs_delta_bits"] = item["upward_rounded_abs_delta_bits"]
        structured_checks.append(check)
    if len(structured_checks) != 42:
        fail("structured report did not retain exactly 42 controls")
    worst_gate = decode_f32_bits(result["input_gate_f32_bits"])
    worst_check = r1_check(r1, worst_gate, 1.0, result["candidate_n_output_f32_bits"],
                           result["candidate_b_output_f32_bits"])
    regressions = run_regressions(temp / "regressions", populations)
    return {"schema": "pulsarmlx.f020.fused-swiglu-v2-3-qualification/1.0.0",
            "status": "PASS", "manifest_sha256": sha(MANIFEST), "bridge": result,
            "delta_plus_beta_leq_E_N": decision, "r1_corroboration": "PASS",
            "structured_up_controls": structured_checks, "worst_delta_r1_corroboration": worst_check,
            "regressions": regressions}


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
    public_commit = git_authority(args.public_commit)
    privacy_scan()
    runtime, runtime_sha = runtime_identity(args)
    with tempfile.TemporaryDirectory(prefix="f020-v2-2-driver-") as raw:
        temp = Path(raw)
        attestation = compile_and_attest(args, sha(MANIFEST), public_commit, temp)
        if not args.execute:
            print(json.dumps({"status": "STATIC_PREFLIGHT_PASS", "capability_issued": False,
                              "compiler_identity_sha256": attestation["compiler_hash"],
                              "disassembly_sha256": attestation["disassembly_hash"]}, sort_keys=True))
            return 0
        populations = frozen_populations()
        capability = temp / "capability-sweep.txt"
        write_capability(capability, args, sha(MANIFEST), public_commit, runtime_sha, attestation, temp)
        result = execute(args, manifest, contract, capability, attestation["binary"], temp,
                         attestation, runtime_sha, public_commit, populations)
        if args.report is None:
            fail("--report is required for execution")
        args.report.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
