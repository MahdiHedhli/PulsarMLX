#!/usr/bin/env python3
"""Inventory explicit Feature 018 P1 reference dispatches from routes/catalog."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/research"))

from glm52_tensor_store import Glm52TensorStore, nbytes_for_tensor  # noqa: E402


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_identity() -> str:
    status = subprocess.check_output(
        ["git", "status", "--porcelain=v1"], cwd=ROOT, text=True
    ).strip()
    if status:
        raise RuntimeError("analysis source must be clean")
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def build(checkpoint: Path, evidence_path: Path, analysis_commit: str) -> dict[str, Any]:
    evidence = json.loads(evidence_path.read_text())
    if evidence.get("expert_execution_mode") != "direct_iq2_gate_up":
        raise ValueError("source evidence is not the direct IQ2 validation mode")
    store = Glm52TensorStore(checkpoint)
    records: list[dict[str, Any]] = []
    stack_summaries: list[dict[str, Any]] = []
    for stack_index, stack in enumerate(evidence["routing"]):
        stack_records: list[dict[str, Any]] = []
        for route in stack["layers"]:
            layer = int(route["layer"])
            for expert_id in route["expert_ids"]:
                projections = []
                direct_eligible = True
                for role in ("gate", "up"):
                    tensor_name = f"blk.{layer}.ffn_{role}_exps.weight"
                    location = store.tensors[tensor_name]
                    columns, rows, experts = map(int, location.dims)
                    direct_eligible &= (
                        location.type_id == 16 and location.type_name == "IQ2_XXS"
                    )
                    projections.append(
                        {
                            "role": role,
                            "tensor_name": tensor_name,
                            "quantization": location.type_name,
                            "shape": [columns, rows, experts],
                            "selected_expert_shape": [rows, columns],
                            "selected_expert_compressed_bytes": nbytes_for_tensor(
                                location.type_id, rows * columns
                            ),
                        }
                    )
                if direct_eligible:
                    continue
                record = {
                    "stack_index": stack_index,
                    "phase": stack["phase"],
                    "step": stack.get("step"),
                    "position": int(stack["position"]),
                    "layer": layer,
                    "expert_id": int(expert_id),
                    "dispatch": "explicit_reference",
                    "reason_code": "intentional_out_of_scope_quantization",
                    "capability_miss": False,
                    "runtime_error": False,
                    "fallback": False,
                    "projections": projections,
                }
                records.append(record)
                stack_records.append(record)
        stack_summaries.append(
            {
                "stack_index": stack_index,
                "phase": stack["phase"],
                "step": stack.get("step"),
                "position": int(stack["position"]),
                "direct_routed_expert_count": 76 * 8 - len(stack_records),
                "explicit_reference_routed_expert_count": len(stack_records),
                "direct_error_count": 0,
                "fallback_count": 0,
            }
        )
    selection = evidence["direct_iq2_metal"]["selection"]
    if sum(row["direct_routed_expert_count"] for row in stack_summaries) != selection[
        "direct_routed_expert_count"
    ]:
        raise ValueError("derived direct dispatch count disagrees with P1 evidence")
    if len(records) != selection["explicit_reference_routed_expert_count"]:
        raise ValueError("derived reference count disagrees with P1 evidence")
    reason_counts = Counter(record["reason_code"] for record in records)
    quant_counts = Counter(
        projection["quantization"]
        for record in records
        for projection in record["projections"]
    )
    return {
        "schema": "pulsarmlx.research.f018-p1-dispatch-inventory",
        "schema_version": "1.0.0",
        "actual_status": "passed",
        "analysis_source_commit": analysis_commit,
        "source_evidence": {
            "path": str(evidence_path.relative_to(ROOT)),
            "sha256": _sha256(evidence_path),
            "source_commit": evidence["source_commit"],
        },
        "checkpoint": evidence["checkpoint"],
        "mode": "validation_fail_closed",
        "stack_summaries": stack_summaries,
        "full_run": {
            "direct_routed_expert_count": sum(
                row["direct_routed_expert_count"] for row in stack_summaries
            ),
            "explicit_reference_routed_expert_count": len(records),
            "direct_error_count": 0,
            "fallback_count": 0,
            "reason_counts": dict(sorted(reason_counts.items())),
            "projection_quantization_counts": dict(sorted(quant_counts.items())),
        },
        "reference_dispatches": records,
        "interpretation": {
            "explicit_reference_dispatch": "selected before candidate invocation because the quantization is outside the IQ2_XXS gate/up scope",
            "direct_error": "a selected direct operation failed; validation stops without reference recovery",
            "production_fallback": "not implemented by this research mode; any future policy must be explicit and observable",
        },
        "claim_boundary": "Catalog-derived explanation of the 16 explicit reference routed experts in each of the two committed P1 stacks; no new inference was executed.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument(
        "--input",
        type=Path,
        default=ROOT
        / "docs/research/glm52/raw/f018-inference-p1-direct-iq2-0001.json",
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    record = build(args.checkpoint, args.input, _source_identity())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
