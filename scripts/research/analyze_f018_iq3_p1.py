#!/usr/bin/env python3
"""Validate and render the optional Feature 018 direct-IQ3 P1 result."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/research"))

from f018_evidence import load_unique_json, validate_record  # noqa: E402

DEFAULT_INPUT = ROOT / "docs/research/glm52/raw/f018-inference-p1-direct-iq2-iq3-0001.json"
DEFAULT_OUTPUT = ROOT / "docs/research/glm52/tables/f018-inference-p1-direct-iq2-iq3-0001.md"
PRIOR = ROOT / "docs/research/glm52/raw/f018-inference-p1-direct-iq2-0001.json"


def render(record: dict, raw_sha256: str) -> str:
    cold, warm = record["timings"]
    direct = record["direct_quantized_metal"]
    worker = direct["worker"]
    selection = direct["selection"]
    prior = load_unique_json(PRIOR)
    return "\n".join(
        [
            "# Feature 018 exact P1 with direct IQ2/IQ3 experts",
            "",
            "> One clean-source P1 execution on one M1 Ultra; not P2, golden-eight, steady-state throughput, or production evidence.",
            "",
            f"- Source: `{record['source_commit']}` (clean)",
            f"- Raw SHA-256: `{raw_sha256}`",
            f"- Exact sequence: `{record['generated_token_ids']}`; golden prefix: `{str(record['matches_golden_prefix']).lower()}`",
            f"- Direct routed experts: `{selection['direct_routed_expert_count']}`; explicit references: `{selection['explicit_reference_routed_expert_count']}`",
            f"- Direct GEMVs: `{worker['gemv_count']}`; CPU fallbacks/direct errors: `{worker['cpu_fallback_count']}` / `{worker['direct_error_count']}`",
            "",
            "| Boundary/component | Seconds |",
            "| --- | ---: |",
            f"| Complete evidence wall | {float(record['seconds']):.9f} |",
            f"| Cold prompt stack | {float(cold['stack_seconds']):.9f} |",
            f"| Full-vocabulary logits | {float(warm['logits_seconds']):.9f} |",
            f"| Terminal warm stack | {float(warm['stack_seconds']):.9f} |",
            f"| Direct packed storage | {float(worker['storage_read_seconds']):.9f} |",
            f"| Direct kernel intervals | {float(worker['kernel_seconds']):.9f} |",
            f"| Direct synchronized calls | {float(worker['total_seconds']):.9f} |",
            "",
            f"For cross-commit context only, the prior IQ2-only direct P1 wall was `{float(prior['seconds']):.9f}` s and its terminal warm stack was `{float(prior['timings'][1]['stack_seconds']):.9f}` s. The current wall difference is `{float(prior['seconds']) - float(record['seconds']):.9f}` s; this is not a controlled same-binary population.",
            "",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    record = validate_record(load_unique_json(args.input))
    rendered = render(record, hashlib.sha256(args.input.read_bytes()).hexdigest())
    if args.check:
        if not args.output.is_file() or args.output.read_text() != rendered:
            raise SystemExit(f"generated table differs: {args.output}")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
