#!/usr/bin/env python3
"""Static/non-candidate self-checks for the F020 native-sweep v2.5 package."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from fractions import Fraction

ROOT = Path(__file__).resolve().parents[2]
V1 = ROOT / "specs/020-mlx-safetensors-affine/fused-swiglu-package-manifest-v1.json"
V2_PREDECESSOR = ROOT / "specs/020-mlx-safetensors-affine/fused-swiglu-package-manifest-v2-1.json"
V2_2_PREDECESSOR = ROOT / "specs/020-mlx-safetensors-affine/fused-swiglu-package-manifest-v2-2.json"
V2 = ROOT / "specs/020-mlx-safetensors-affine/fused-swiglu-package-manifest-v2-5.json"
CONTRACT = ROOT / "specs/020-mlx-safetensors-affine/contracts/fused-swiglu-native-sweep-v2-5.json"
GEN = ROOT / "scripts/research/f020_fused_swiglu_generate_b_table_v2.py"
BRIDGE = ROOT / "scripts/research/f020_fused_swiglu_native_bridge_v2_5.cpp"
B_SRC = ROOT / "scripts/research/f020_fused_swiglu_candidate_b_v2.cpp"
GUARD_TEST = ROOT / "scripts/research/tests/f020_fused_swiglu_cpu_guard_v2_4_test.cpp"
PROOF_CHECK = ROOT / "scripts/research/f020_fused_swiglu_proof_v2_5.py"


def fail(message: str) -> None:
    raise SystemExit("F020_V2_STATIC_BLOCKER: " + message)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mlx-prefix", type=Path, default=None)
    ap.add_argument("--native-source-root",type=Path,required=True)
    ap.add_argument("--compile-only",action="store_true",help="proof/source/compile checks only; does not certify native runtime artifact readiness")
    args = ap.parse_args()
    m1 = json.loads(V1.read_text())
    for item in m1["files"]:
        p = ROOT / item["path"]
        if digest(p) != item["sha256"]:
            fail("historical v1 hash changed: " + item["path"])
    predecessor = json.loads(V2_PREDECESSOR.read_text())
    for item in predecessor["files"]:
        if digest(ROOT / item["path"]) != item["sha256"]:
            fail("historical v2.2 hash changed: " + item["path"])
    predecessor_2 = json.loads(V2_2_PREDECESSOR.read_text())
    for item in predecessor_2["files"]:
        if digest(ROOT / item["path"]) != item["sha256"]:
            fail("historical v2.3 hash changed: " + item["path"])
    old = ROOT/"specs/020-mlx-safetensors-affine/fused-swiglu-package-manifest-v2-3.json"
    for item in json.loads(old.read_text())["files"]:
        if digest(ROOT/item["path"]) != item["sha256"]:
            fail("historical v2.4 hash changed: "+item["path"])
    m = json.loads(V2.read_text())
    c = json.loads(CONTRACT.read_text())
    if m["status"] != "FROZEN_PROSPECTIVE_NO_CANDIDATE_OBSERVATIONS" or c["status"] != m["status"]:
        fail("v2 prospective status mismatch")
    if any(value != 0 for key, value in m["counters"].items()):
        fail("v2 counter is nonzero")
    if Fraction(c["budgets"]["E_N"]) != Fraction(1, 128):
        fail("E_N changed")
    if Fraction(c["budgets"]["beta_B"]) != Fraction(5201, 4194304):
        fail("beta_B changed")
    if Fraction(c["budgets"]["delta_max"]) != Fraction(27567, 4194304):
        fail("delta_max changed")
    if c["reducer"]["acceptance"] != "exact rational comparison of Fraction.from_float(upward_delta) + 5201/4194304 <= 1/128":
        fail("acceptance relation changed")
    if c["enumeration"]["batch_elements"] != 1048576 or c["enumeration"]["expected_total_evaluated"] != 2197815298:
        fail("batch size changed")
    for item in m["files"]:
        if item["sha256"] == "PENDING_SELF_HASH":
            fail("manifest contains pending hash: " + item["path"])
        p = ROOT / item["path"]
        if digest(p) != item["sha256"]:
            fail("v2 hash mismatch: " + item["path"])

    import f020_fused_swiglu_qualification_v2_5 as driver
    from f020_fused_swiglu_full_up_v2_5 import extended_control_bits
    driver.load_contract()
    driver.privacy_scan()
    driver.frozen_populations()
    subprocess.run([sys.executable, str(PROOF_CHECK)], check=True)

    clang = shutil.which("clang++") or "/usr/bin/clang++"
    if not Path(clang).exists():
        fail("clang++ unavailable")
    prefix_value = args.mlx_prefix or os.environ.get("F020_MLX_PREFIX")
    if not prefix_value:
        fail("operator-supplied --mlx-prefix or F020_MLX_PREFIX is required")
    native = Path(prefix_value)
    if not (native / "include/mlx/c/mlx.h").is_file():
        fail("pinned MLX headers unavailable")
    from types import SimpleNamespace
    if args.compile_only:
        pins=json.loads(driver.PINS.read_text())
        for item in pins["source_files"]:
            if digest(args.native_source_root/item["path"]) != item["sha256"]:
                fail("pinned source mismatch: "+item["path"])
    else:
        driver.runtime_identity(SimpleNamespace(native_source_root=args.native_source_root,
                                               mlx_prefix=native,mlx_c_prefix=native))
    with tempfile.TemporaryDirectory(prefix="f020-v2-static-") as temp:
        t = Path(temp)
        header = t / "f020_candidate_b_table_v1.h"
        subprocess.run([sys.executable, str(GEN), "--out", str(header), "--self-test"], check=True)
        sdk = subprocess.check_output(["xcrun", "--show-sdk-path"], text=True).strip()
        common = [clang, "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror",
                  "-fno-fast-math", "-ffp-contract=off", "-isysroot", sdk,
                  "-I", str(native / "include"), "-I", str(t)]
        controls_binary=t/"controls-test"
        subprocess.run(common+[str(ROOT/"scripts/research/tests/f020_fused_swiglu_controls_v2_5_test.cpp"),
                               "-o",str(controls_binary)],check=True)
        for worst in (0,0x80000000,0xc1800000,0x41800000,0x00800000,0xbf800000):
            output=subprocess.check_output([str(controls_binary),f"{worst:08x}"],text=True)
            got=[tuple(int(v,16) for v in line.split()) for line in output.splitlines()]
            if got != extended_control_bits(worst):fail("C++/Python bit-policy controls mismatch")
        for worst in (0x7f800000,0xff800000,0x7fc00000,0x41800001,0xc1800001):
            if subprocess.run([str(controls_binary),f"{worst:08x}"],capture_output=True).returncode!=65:
                fail("C++ controls accepted out-of-domain gate")
        guard_binary = t / "cpu-guard-test"
        subprocess.run(common + [str(GUARD_TEST), "-o", str(guard_binary)], check=True)
        subprocess.run([str(guard_binary)], check=True)
        b_binary = t / "candidate-b-static"
        subprocess.run(common + ["-DF020_TABLE_HEADER=\"f020_candidate_b_table_v1.h\"", str(B_SRC), "-o", str(b_binary)], check=True)
        binary = t / "f020-native-bridge-v2-3-static"
        subprocess.run(common + ["-DF020_EXPECTED_MANIFEST_SHA256=\"STATIC\"",
                                 "-DF020_EXPECTED_PUBLIC_COMMIT=\"STATIC\"", str(BRIDGE),
                                 "-L", str(native / "lib"), "-lmlxc", "-lmlx",
                                 "-Wl,-rpath," + str(native / "lib"), "-o", str(binary)], check=True)
        static_result = subprocess.check_output([str(binary)], text=True).strip()
        if static_result != "F020_NATIVE_BRIDGE_V2_STATIC_ONLY":
            fail("default bridge mode is not static-only")
        for mode in ("--execute-sweep","--structured-up-controls","--extended-up-controls"):
            blocked = subprocess.run([str(binary),mode],check=False,capture_output=True)
            if blocked.returncode != 78:fail("missing capability did not reject before execution")
        objdump = Path(subprocess.check_output(["xcrun", "-f", "llvm-objdump"], text=True).strip())
        disassembly = subprocess.check_output([str(objdump), "--disassemble", str(binary)], text=True).lower()
        if re.search(r"\bmsr\s+fpcr\b", disassembly):
            fail("bridge binary writes FPCR")
        if any(op in disassembly for op in ("fmadd", "fmsub", "fnmadd", "fnmsub")):
            fail("actual v2 bridge binary contains contracted FMA")
        if "fmul" not in disassembly or "fadd" not in disassembly:
            fail("actual v2 bridge binary lacks separate multiply/add evidence")

    source = BRIDGE.read_text()
    for required in ("--execute-sweep", "1048576u", "nextafter", "mlx_sigmoid", "mlx_multiply",
                     "candidate_b", "candidate_n_output_f32_bits",
                     "candidate_b_output_f32_bits", "input_gate_f32_bits", "--capability",
                     "--structured-up-controls", "structured", "total_evaluated",
                     "anomaly_count", "anomaly_reason", "anomaly_gate_f32_bits",
                     "check_cpu", "cpu_guard_checks", "native_silu_materializations", "--extended-up-controls",
                     "materialized_native_silu_minus_candidate_b_up1", "mlx_array_eval(silu)", "f020_fused_swiglu_candidate_b_v2.h",
                     "F020_EXPECTED_MANIFEST_SHA256",
                     "bridge_binary_sha256", "execution_root", "capability_path", "std::remove",
                     "pulsarmlx.f020.native-bridge-capability/1.0.0"):
        if required not in source:
            fail("bridge source missing required guard/operation: " + required)
    print("F020_V2_5_STATIC_COMPILE_PROOF_PASS_RUNTIME_UNVERIFIED" if args.compile_only else "F020_V2_5_STATIC_SELFTEST_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
