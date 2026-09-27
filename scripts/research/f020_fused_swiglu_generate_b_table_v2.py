#!/usr/bin/env python3
"""Generate a compile-time Candidate-B table from the frozen v1 fixture."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TABLE = ROOT / "fixtures/f020-fused-swiglu/candidate-b-silu-table-v1.json"


def generate(out: Path) -> None:
    data = json.loads(TABLE.read_text())
    nodes = data.get("nodes")
    if data.get("node_count") != 833 or not isinstance(nodes, list) or len(nodes) != 833:
        raise SystemExit("frozen Candidate-B table must contain exactly 833 nodes")
    values = []
    for i, node in enumerate(nodes):
        if node.get("i") != i or node.get("x_num") != -512 + i:
            raise SystemExit("Candidate-B table grid is not the frozen deterministic grid")
        bits = node.get("silu_f32_bits")
        if not isinstance(bits, str) or len(bits) != 10 or not bits.startswith("0x"):
            raise SystemExit("invalid frozen Candidate-B f32 coefficient")
        values.append(int(bits, 16))
    out.write_text(
        "#pragma once\n"
        "#include <cstdint>\n"
        "static inline float f020_bits(uint32_t u) { union { uint32_t u; float f; } x{u}; return x.f; }\n"
        "static const float F020_SILU_TABLE[833] = {\n"
        + ",\n".join(f"f020_bits(0x{v:08x}u)" for v in values)
        + "\n};\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    generate(args.out)
    if args.self_test:
        text = args.out.read_text()
        if text.count("f020_bits(") != 834:
            raise SystemExit("generated Candidate-B table header self-test failed")
        print("F020_B_TABLE_GENERATION_SELFTEST_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
