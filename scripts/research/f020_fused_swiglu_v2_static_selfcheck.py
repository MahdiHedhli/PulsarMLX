#!/usr/bin/env python3
"""Static/non-candidate self-checks for the F020 native-sweep v2 package."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from fractions import Fraction

ROOT = Path(__file__).resolve().parents[2]
V1 = ROOT / "specs/020-mlx-safetensors-affine/fused-swiglu-package-manifest-v1.json"
V2 = ROOT / "specs/020-mlx-safetensors-affine/fused-swiglu-package-manifest-v2.json"
CONTRACT = ROOT / "specs/020-mlx-safetensors-affine/contracts/fused-swiglu-native-sweep-v2.json"
GEN = ROOT / "scripts/research/f020_fused_swiglu_generate_b_table_v2.py"
BRIDGE = ROOT / "scripts/research/f020_fused_swiglu_native_bridge_v2.cpp"
B_SRC = ROOT / "scripts/research/f020_fused_swiglu_candidate_b.cpp"


def fail(message: str) -> None:
    raise SystemExit("F020_V2_STATIC_BLOCKER: " + message)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mlx-prefix", type=Path, default=None)
    args = ap.parse_args()
    m1 = json.loads(V1.read_text())
    for item in m1["files"]:
        p = ROOT / item["path"]
        if digest(p) != item["sha256"]:
            fail("historical v1 hash changed: " + item["path"])
    m = json.loads(V2.read_text())
    c = json.loads(CONTRACT.read_text())
    if m["status"] != "FROZEN_PROSPECTIVE_NO_CANDIDATE_OBSERVATIONS" or c["status"] != m["status"]:
        fail("v2 prospective status mismatch")
    if any(value != 0 for key, value in m["counters"].items()):
        fail("v2 counter is nonzero")
    if Fraction(c["candidate_n"]["E_N"]) != Fraction(1, 128):
        fail("E_N changed")
    if Fraction(c["certified_bridge"]["beta_B"]) != Fraction(5201, 4194304):
        fail("beta_B changed")
    if Fraction(c["differential_gate"]["delta_max"]) != Fraction(27567, 4194304):
        fail("delta_max changed")
    if c["differential_gate"]["acceptance"] != "delta + beta_B <= E_N":
        fail("acceptance relation changed")
    if c["enumeration"]["batch_elements"] != 1048576:
        fail("batch size changed")
    for item in m["files"]:
        if item["sha256"] == "PENDING_SELF_HASH":
            fail("manifest contains pending hash: " + item["path"])
        p = ROOT / item["path"]
        if digest(p) != item["sha256"]:
            fail("v2 hash mismatch: " + item["path"])

    clang = shutil.which("clang++") or "/usr/bin/clang++"
    if not Path(clang).exists():
        fail("clang++ unavailable")
    native = args.mlx_prefix or Path("/Users/mhedhli/.local/share/pulsarmlx/studio-stage-20260925/native")
    if not (native / "include/mlx/c/mlx.h").is_file():
        fail("pinned MLX headers unavailable")
    with tempfile.TemporaryDirectory(prefix="f020-v2-static-") as temp:
        t = Path(temp)
        header = t / "f020_candidate_b_table_v1.h"
        subprocess.run([sys.executable, str(GEN), "--out", str(header), "--self-test"], check=True)
        common = [clang, "-std=c++17", "-fsyntax-only", "-Wall", "-Wextra", "-Werror",
                  "-fno-fast-math", "-ffp-contract=off", "-I", str(native / "include"), "-I", str(t)]
        subprocess.run(common + ["-DF020_TABLE_HEADER=\"f020_candidate_b_table_v1.h\"", str(B_SRC)], check=True)
        subprocess.run(common + [str(BRIDGE)], check=True)

    source = BRIDGE.read_text()
    for required in ("--execute-sweep", "1048576u", "nextafter", "mlx_sigmoid", "mlx_multiply",
                     "candidate_b", "worst_gate_f32_bits", "candidate_n_output_f32_bits",
                     "candidate_b_output_f32_bits", "F020_V2_EXECUTION_AUTHORIZED"):
        if required not in source:
            fail("bridge source missing required guard/operation: " + required)
    print("F020_V2_STATIC_SELFTEST_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
