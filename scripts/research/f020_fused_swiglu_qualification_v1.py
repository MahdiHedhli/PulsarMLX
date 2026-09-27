#!/usr/bin/env python3
"""F020 Sequence 002 qualification driver.

The default action is a fail-closed pre-observation gate. Numerical candidate
execution is opt-in and is refused unless every frozen prerequisite has been
mechanically proven by this process.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "specs/020-mlx-safetensors-affine/fused-swiglu-package-manifest-v1.json"
TABLE = ROOT / "fixtures/f020-fused-swiglu/candidate-b-silu-table-v1.json"
B_SRC = ROOT / "scripts/research/f020_fused_swiglu_candidate_b.cpp"
N_SRC = ROOT / "scripts/research/f020_fused_swiglu_candidate_n.cpp"
R1 = ROOT / "scripts/research/f020_fused_swiglu_r1_v1.py"


def die(msg: str) -> None:
    raise SystemExit("F020_PREOBSERVATION_BLOCKER: " + msg)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_frozen() -> dict:
    m = json.loads(MANIFEST.read_text())
    if m["status"] != "FROZEN_PROSPECTIVE_NO_CANDIDATE_OBSERVATIONS":
        die("manifest status changed")
    if m["candidate_observations"] != 0:
        die("candidate observations are not zero")
    for item in m["files"]:
        p = ROOT / item["path"]
        if not p.is_file():
            die(f"missing frozen file {item['path']}")
        got = sha(p)
        if got != item["sha256"]:
            die(f"frozen hash mismatch {item['path']}: {got} != {item['sha256']}")
    r1 = json.loads((ROOT / "specs/020-mlx-safetensors-affine/contracts/fused-swiglu-r1-v1.json").read_text())
    n = json.loads((ROOT / "specs/020-mlx-safetensors-affine/contracts/fused-swiglu-native-sweep-v1.json").read_text())
    b = json.loads((ROOT / "specs/020-mlx-safetensors-affine/contracts/fused-swiglu-candidate-b-v1.json").read_text())
    if r1["reference"]["independent_of_candidates"] is not True:
        die("R1 independence claim changed")
    graph = "g=min(gate,10); s=native MLX sigmoid(g); silu=native MLX multiply(g,s); h=native MLX multiply(silu,clip(up,-10,10))"
    expected_graph = [
        "gate_f32",
        "g = minimum(gate_f32, 10.0f) [upper-only clamp]",
        "s = native MLX sigmoid(g)",
        "silu = native MLX multiply(g, s)",
        "up_clipped = clip(up_f32_control = float32(1.0), -10.0f, 10.0f)",
        "h = native MLX multiply(silu, up_clipped)",
    ]
    if n.get("graph") != expected_graph or m.get("candidate_n_graph") != graph:
        die("Candidate N graph binding mismatch")
    if n.get("up_f32_control_value") != 1.0:
        die("Candidate N up control is not frozen at 1.0")
    if b["domain"]["gate_after_clamp"] != [-16, 10] or b["domain"]["up_after_clamp"] != [-10, 10]:
        die("Candidate B domain mismatch")
    if "-fno-fast-math" not in b["approximation"]["implementation_fail_closed"]["required_compile_flags"]:
        die("Candidate B no-fast-math requirement missing")
    return m


def table_header(tmp: Path) -> Path:
    data = json.loads(TABLE.read_text())
    nodes = data.get("nodes")
    if not isinstance(nodes, list) or len(nodes) != 833:
        die("Candidate B table does not contain 833 nodes")
    vals = [int(n["silu_f32_bits"], 16) if isinstance(n["silu_f32_bits"], str) else int(n["silu_f32_bits"]) for n in nodes]
    out = tmp / "f020_table.h"
    out.write_text("#pragma once\n#include <cstdint>\nstatic const float F020_SILU_TABLE[833] = {\n" +
                   ",\n".join(f"*reinterpret_cast<const float*>(&u{v}u)" for v in vals) +
                   "\n};\n")
    # The generated header uses bit-preserving storage, but C++ constant
    # initializers cannot dereference a temporary. Replace with a union helper.
    out.write_text("#pragma once\n#include <cstdint>\nstatic inline float f020_bits(uint32_t u) { union { uint32_t u; float f; } x{u}; return x.f; }\nstatic const float F020_SILU_TABLE[833] = {\n" +
                   ",\n".join(f"f020_bits(0x{v:08x}u)" for v in vals) + "\n};\n")
    return out


def compiler_gate(tmp: Path) -> None:
    clang = shutil.which("clang++") or "/usr/bin/clang++"
    if not Path(clang).exists():
        die("exact clang++ compiler unavailable")
    hdr = table_header(tmp)
    bbin = tmp / "candidate_b"
    cmd = [clang, "-std=c++17", "-O2", "-fno-fast-math", "-ffp-contract=off",
           "-Werror", "-Wall", "-Wextra", "-Wdouble-promotion",
           f'-DF020_TABLE_HEADER="{hdr.name}"', "-I", str(tmp), str(B_SRC), "-o", str(bbin)]
    subprocess.run(cmd, cwd=tmp, check=True, capture_output=True, text=True)
    p = subprocess.run([str(bbin)], check=True, capture_output=True, text=True)
    if "CANDIDATE_B_COMPILE_SELFTEST_PASS" not in p.stdout:
        die("Candidate B compile self-test did not pass")
    objdump = shutil.which("llvm-objdump") or shutil.which("xcrun")
    if not objdump:
        die("disassembly tool unavailable")
    if Path(objdump).name == "xcrun":
        path = subprocess.check_output([objdump, "-f", "llvm-objdump"], text=True).strip()
        d = subprocess.run([path, "--disassemble", str(bbin)], capture_output=True, text=True)
    else:
        d = subprocess.run([objdump, "--disassemble", str(bbin)], capture_output=True, text=True)
    if d.returncode != 0:
        die("compiled Candidate B disassembly failed: " + (d.stderr or d.stdout).strip())
    text = d.stdout.lower()
    if "fmul" in text and "fadd" not in text:
        die("Candidate B disassembly did not prove separate multiply/add")
    if any(x in text for x in ("fmadd", "fmsub", "fnmadd", "fnmsub")):
        die("Candidate B disassembly contains contracted FMA")


def native_gate(tmp: Path) -> None:
    prefix = Path(os.environ.get("MLX_PREFIX", ""))
    cprefix = Path(os.environ.get("MLX_C_PREFIX", ""))
    if not (prefix / "include/mlx/c/mlx.h").is_file() or not (cprefix / "lib/libmlxc.dylib").is_file():
        die("pinned MLX/MLX-C prefix unavailable")
    cxx = shutil.which("clang++") or "/usr/bin/clang++"
    nbin = tmp / "candidate_n"
    cmd = [cxx, "-std=c++17", "-O2", "-fno-fast-math", "-ffp-contract=off",
           "-Werror", "-Wall", "-Wextra", "-I", str(prefix / "include"), str(N_SRC),
           "-L", str(cprefix / "lib"), "-L", str(prefix / "lib"), "-lmlxc", "-lmlx",
           "-Wl,-rpath," + str(cprefix / "lib"), "-Wl,-rpath," + str(prefix / "lib"), "-o", str(nbin)]
    subprocess.run(cmd, check=True, capture_output=True, text=True)
    p = subprocess.run([str(nbin)], capture_output=True, text=True)
    if p.returncode != 0:
        die("Candidate N graph self-test process failed: " + (p.stderr or p.stdout).strip())
    if "CANDIDATE_N_COMPILE_SELFTEST_PASS" not in p.stdout:
        die("Candidate N graph self-test did not pass")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true", help="reserved for post-gate numerical qualification")
    args = ap.parse_args()
    require_frozen()
    # R1 self-test is allowed before candidate observations and remains
    # entirely independent of both candidate implementations.
    subprocess.run([sys.executable, str(R1)], check=True)
    with tempfile.TemporaryDirectory(prefix="f020-swiglu-preflight-") as d:
        tmp = Path(d)
        compiler_gate(tmp)
        native_gate(tmp)
    if args.execute:
        die("qualification execution driver is not yet admitted: exhaustive exact-R1 reduction and inherited regression integration remain unimplemented")
    print("F020_PREOBSERVATION_PREFLIGHT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
