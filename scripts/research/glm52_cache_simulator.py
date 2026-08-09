#!/usr/bin/env python3
"""Deterministic GLM expert-cache working-set and reuse simulator.

The simulator consumes only committed metadata and routing IDs. It never opens
checkpoint shards and never calls MLX. Storage hits and decoded hits are
reported separately so compressed residency cannot masquerade as avoided
dequantization.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import OrderedDict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from glm52_tensor_store import nbytes_for_tensor


@dataclass(frozen=True)
class Access:
    key: str
    layer: int
    expert: int
    kind: str
    shared: bool
    compressed_bytes: int
    decoded_bytes: int
    quantization: str


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_catalog(path: Path) -> dict[str, dict[str, Any]]:
    document = json.loads(path.read_text())
    tensors = document.get("tensors")
    if not isinstance(tensors, list):
        raise ValueError("catalog tensors must be a list")
    result: dict[str, dict[str, Any]] = {}
    for tensor in tensors:
        name = tensor.get("name")
        if not isinstance(name, str) or name in result:
            raise ValueError("catalog tensor names must be unique strings")
        result[name] = tensor
    return result


def load_route_trace(path: Path) -> list[dict[str, Any]]:
    document = json.loads(path.read_text())
    layers = document.get("layer_meta")
    if not isinstance(layers, list):
        raise ValueError("route trace layer_meta must be a list")
    result: list[dict[str, Any]] = []
    for record in layers:
        expert_ids = record.get("expert_ids")
        if expert_ids is None:
            continue
        layer = record.get("layer")
        if not isinstance(layer, int) or not isinstance(expert_ids, list):
            raise ValueError("route record requires integer layer and expert_ids")
        if len(expert_ids) != 8 or len(set(expert_ids)) != 8:
            raise ValueError(f"layer {layer} must have eight distinct experts")
        if any(not isinstance(expert, int) or not 0 <= expert < 256 for expert in expert_ids):
            raise ValueError(f"layer {layer} has invalid expert ID")
        result.append({"layer": layer, "expert_ids": expert_ids})
    if not result:
        raise ValueError("route trace contains no MoE layers")
    return result


def _access(
    catalog: dict[str, dict[str, Any]],
    *,
    name: str,
    layer: int,
    expert: int,
    kind: str,
    shared: bool,
) -> Access:
    tensor = catalog.get(name)
    if tensor is None:
        raise ValueError(f"missing tensor {name}")
    dims = tensor.get("dims")
    type_id = tensor.get("type_id")
    quantization = tensor.get("type")
    if not isinstance(dims, list) or len(dims) not in (2, 3):
        raise ValueError(f"{name}: expected 2D or 3D tensor")
    if not isinstance(type_id, int) or not isinstance(quantization, str):
        raise ValueError(f"{name}: missing tensor type")
    cols, rows = int(dims[0]), int(dims[1])
    compressed_bytes = nbytes_for_tensor(type_id, cols) * rows
    decoded_bytes = cols * rows * 4
    return Access(
        key=f"{name}#{expert}",
        layer=layer,
        expert=expert,
        kind=kind,
        shared=shared,
        compressed_bytes=compressed_bytes,
        decoded_bytes=decoded_bytes,
        quantization=quantization,
    )


def build_accesses(
    catalog: dict[str, dict[str, Any]], route_layers: list[dict[str, Any]]
) -> list[Access]:
    accesses: list[Access] = []
    for route in route_layers:
        layer = int(route["layer"])
        for expert in route["expert_ids"]:
            for kind, suffix in (
                ("gate", "ffn_gate_exps.weight"),
                ("up", "ffn_up_exps.weight"),
                ("down", "ffn_down_exps.weight"),
            ):
                name = f"blk.{layer}.{suffix}"
                accesses.append(
                    _access(
                        catalog,
                        name=name,
                        layer=layer,
                        expert=int(expert),
                        kind=kind,
                        shared=False,
                    )
                )
        for kind, suffix in (
            ("shared_gate", "ffn_gate_shexp.weight"),
            ("shared_up", "ffn_up_shexp.weight"),
            ("shared_down", "ffn_down_shexp.weight"),
        ):
            name = f"blk.{layer}.{suffix}"
            accesses.append(
                _access(
                    catalog,
                    name=name,
                    layer=layer,
                    expert=0,
                    kind=kind,
                    shared=True,
                )
            )
    return accesses


def summarize_working_set(accesses: list[Access]) -> dict[str, int]:
    unique = {access.key: access for access in accesses}
    return {
        "access_count": len(accesses),
        "unique_entry_count": len(unique),
        "compressed_bytes": sum(access.compressed_bytes for access in unique.values()),
        "decoded_bytes": sum(access.decoded_bytes for access in unique.values()),
        "routed_compressed_bytes": sum(
            access.compressed_bytes for access in unique.values() if not access.shared
        ),
        "routed_decoded_bytes": sum(
            access.decoded_bytes for access in unique.values() if not access.shared
        ),
        "shared_compressed_bytes": sum(
            access.compressed_bytes for access in unique.values() if access.shared
        ),
        "shared_decoded_bytes": sum(
            access.decoded_bytes for access in unique.values() if access.shared
        ),
    }


_COUNTERS = (
    "accesses",
    "storage_hits",
    "storage_misses",
    "decoded_hits",
    "decoded_misses",
    "admissions",
    "evictions",
    "admission_rejections",
    "policy_bypasses",
    "bytes_read",
    "bytes_avoided",
    "decoded_bytes_materialized",
    "decoded_bytes_avoided",
    "redequantizations",
)


def _empty_counters(token_index: int) -> dict[str, int]:
    result = {name: 0 for name in _COUNTERS}
    result["token_index"] = token_index
    return result


def simulate(
    accesses: list[Access], *, budget_bytes: int, policy: str, repeats: int = 2
) -> dict[str, Any]:
    if budget_bytes < 0:
        raise ValueError("budget_bytes must be non-negative")
    if repeats < 1:
        raise ValueError("repeats must be positive")
    if policy not in {"decoded_lru", "compressed_lru", "decoded_shared_only"}:
        raise ValueError(f"unsupported policy {policy}")

    resident: OrderedDict[str, tuple[int, Access]] = OrderedDict()
    resident_bytes = 0
    per_token: list[dict[str, int]] = []

    for token_index in range(repeats):
        counters = _empty_counters(token_index)
        for access in accesses:
            counters["accesses"] += 1
            cached = resident.get(access.key)
            if cached is not None:
                if policy != "decoded_shared_only":
                    resident.move_to_end(access.key)
                counters["storage_hits"] += 1
                counters["bytes_avoided"] += access.compressed_bytes
                if policy in {"decoded_lru", "decoded_shared_only"}:
                    counters["decoded_hits"] += 1
                    counters["decoded_bytes_avoided"] += access.decoded_bytes
                else:
                    counters["decoded_misses"] += 1
                    counters["decoded_bytes_materialized"] += access.decoded_bytes
                    counters["redequantizations"] += 1
                continue

            counters["storage_misses"] += 1
            counters["decoded_misses"] += 1
            counters["bytes_read"] += access.compressed_bytes
            counters["decoded_bytes_materialized"] += access.decoded_bytes
            counters["redequantizations"] += 1

            if policy == "decoded_shared_only" and not access.shared:
                counters["policy_bypasses"] += 1
                continue

            entry_bytes = (
                access.compressed_bytes if policy == "compressed_lru" else access.decoded_bytes
            )
            if entry_bytes > budget_bytes:
                counters["admission_rejections"] += 1
                continue

            if policy == "decoded_shared_only":
                if resident_bytes + entry_bytes > budget_bytes:
                    counters["admission_rejections"] += 1
                    continue
            else:
                while resident and resident_bytes + entry_bytes > budget_bytes:
                    _, (old_bytes, _) = resident.popitem(last=False)
                    resident_bytes -= old_bytes
                    counters["evictions"] += 1

            resident[access.key] = (entry_bytes, access)
            resident_bytes += entry_bytes
            counters["admissions"] += 1

        counters["resident_entries_end"] = len(resident)
        counters["resident_bytes_end"] = resident_bytes
        per_token.append(counters)

    totals = {name: sum(token[name] for token in per_token) for name in _COUNTERS}
    return {
        "policy": policy,
        "budget_bytes": budget_bytes,
        "repeats": repeats,
        "per_token": per_token,
        "totals": totals,
        "resident_entries": len(resident),
        "resident_bytes": resident_bytes,
    }


def build_report(catalog_path: Path, trace_path: Path) -> dict[str, Any]:
    catalog = load_catalog(catalog_path)
    route_trace = load_route_trace(trace_path)
    accesses = build_accesses(catalog, route_trace)
    budgets_gib = (8, 16, 24, 32, 40, 48)
    policies = ("decoded_lru", "compressed_lru", "decoded_shared_only")
    simulations = [
        simulate(
            accesses,
            budget_bytes=budget_gib * 1024**3,
            policy=policy,
            repeats=2,
        )
        for budget_gib in budgets_gib
        for policy in policies
    ]
    return {
        "schema": "pulsarmlx.research.glm52-cache-simulation",
        "schema_version": "1.0.0",
        "actual_status": "passed_proxy_analysis",
        "inputs": {
            "catalog": str(catalog_path),
            "catalog_sha256": _sha256(catalog_path),
            "route_trace": str(trace_path),
            "route_trace_sha256": _sha256(trace_path),
            "route_scope": (
                "committed C09 single-token layer routing replayed identically; "
                "P1 did not retain its route IDs"
            ),
        },
        "key_granularity": "tensor_name#expert_id",
        "access_order": "layer_then_routed_expert_gate_up_down_then_shared_gate_up_down",
        "working_set": summarize_working_set(accesses),
        "representative_accesses": [asdict(access) for access in accesses[:6]],
        "simulations": simulations,
        "limitations": [
            "identical replay measures policy mechanics, not observed P1-to-P2 route overlap",
            "compressed hits avoid modeled storage bytes but not dequantization",
            "decoded byte accounting excludes Python object overhead in the legacy cache",
            "simulation contains no latency or throughput estimate",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path("docs/research/glm52/raw/f016-c01-catalog-0001.json"),
    )
    parser.add_argument(
        "--trace",
        type=Path,
        default=Path("docs/research/glm52/raw/f016-c09-depth-0001.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/research/glm52/raw/f016-cache-simulation-0001.json"),
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    report = build_report(args.catalog, args.trace)
    encoded = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.check:
        if not args.output.exists() or args.output.read_text() != encoded:
            raise SystemExit("cache simulation output differs; regenerate it")
        print(f"cache simulation check passed: {args.output}")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(encoded)
    print(json.dumps({"output": str(args.output), "working_set": report["working_set"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
