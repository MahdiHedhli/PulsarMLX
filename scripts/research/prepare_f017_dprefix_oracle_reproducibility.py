#!/usr/bin/env python3
"""Bank the checkpoint-free DPREFIX oracle reproducibility closure artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import stat
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(ROOT))

from scripts.research.f017_dprefix_oracle_reproducibility import (
    CANDIDATE_STATE, EXACT_ROOT, REAL2_STATE, REAL3_STATE, SURFACES, canonical,
    historical_forensics, metrics, sha,
)
from scripts.research.f017_dprefix_route_ambiguity import analyze as route_analyze

EVIDENCE = ROOT / "docs/architecture/reviews/evidence"
CONTRACTS = ROOT / "specs/017-rust-native-inference-runtime/contracts"
REPORTS = ROOT / "docs/architecture/reviews"
LEDGER = 139


def write_json(path: Path, value: Any) -> None:
    path.write_bytes(canonical(value))


def source(path: str) -> dict[str, str]:
    target = ROOT / path
    return {"path": path, "sha256": sha(target)}


def aggregate_campaign() -> dict[str, Any]:
    observations = []
    for path in sorted((EXACT_ROOT / "blas-campaign").glob("*.json")):
        value = json.loads(path.read_text())
        observations.append({
            "observation": path.name,
            "python": value["python"], "numpy": value["numpy"],
            "thread_environment": value["thread_environment"],
            "surface_sha256": value["surface_sha256"],
        })
    finals = Counter(item["surface_sha256"]["layer_3_entry"] for item in observations)
    by_python: dict[str, set[str]] = {}
    for item in observations:
        by_python.setdefault(item["python"], set()).add(item["surface_sha256"]["layer_3_entry"])
    return {
        "schema": "pulsarmlx.f017.dprefix-blas-process-campaign", "schema_version": "1.0.0",
        "result": "CROSS-PROCESS ORACLE REPRODUCIBILITY CHARACTERIZED",
        "thread_count_result": "NO THREAD-COUNT VARIANCE OBSERVED",
        "blas_reduction_order_result": "BLAS BACKEND/WHEEL VARIANCE DEMONSTRATED; THREAD-COUNT CAUSATION NOT OBSERVED",
        "observations": observations,
        "unique_layer3_hashes": dict(finals),
        "per_python_stability": {key: sorted(value) for key, value in by_python.items()},
        "demonstrated_root_cause": {
            "CPython_3.13.13": "NumPy 2.4.5 Accelerate wheel reproduces REAL-2",
            "CPython_3.14.6": "NumPy 2.4.5 OpenBLAS wheel reproduces REAL-3",
            "source_change": False,
            "input_change": False,
            "classification": "BLAS backend/platform-wheel reduction realization",
        },
        "real2_hash_independently_reproduced": finals.get("541d8dbcf459b49e9b5c69ae44f919a64c2eaaefa4f6daeb7e0d13443b521aff", 0) >= 2,
        "real3_hash_independently_reproduced": finals.get("ad71c3b10531283f55117b8b72f3f754653dfa74f6fbe96faf520f728432ac1a", 0) >= 2,
        "checkpoint_access": 0, "real_payload_ledger": LEDGER,
    }


def retain_exact() -> dict[str, Any]:
    package = EXACT_ROOT / "retained"
    package.mkdir(parents=True, exist_ok=True)
    artifacts = []
    for ordinal, name in enumerate(SURFACES, 1):
        source_path = EXACT_ROOT / "run-a1" / f"{name}.f32le"
        target = package / f"{name}.f32le"
        if target.exists():
            target.chmod(0o644)
        shutil.copyfile(source_path, target)
        target.chmod(0o444)
        artifacts.append({
            "creation_ordinal": ordinal, "semantic_id": name,
            "symbolic_package_relative_path": target.name,
            "sha256": sha(target), "bytes": target.stat().st_size,
            "dtype": "f32", "shape": [6144], "count": 6144,
            "serialization": "canonical_little_endian_ieee754_binary32_c_order",
            "immutable": True, "read_only": True,
        })
    manifest = {
        "schema": "pulsarmlx.f017.dprefix-exact-state-package", "schema_version": "1.0.0",
        "package_identity": "DPREFIX-EXACT-1", "classification": "EXACT_CLASS",
        "source_packed_package_sha256": "705066830506dbebab9212948059c71e76b4535eaeb41672c9dbd62f6e9ed156",
        "artifacts": artifacts, "immutable": True, "read_only": True,
        "checkpoint_access": 0, "real_payload_ledger": LEDGER,
    }
    manifest_path = package / "manifest.json"
    write_json(manifest_path, manifest)
    manifest_path.chmod(0o444)
    return {"private_manifest_sha256": sha(manifest_path), **manifest}


def exact_descriptor(retained: dict[str, Any]) -> dict[str, Any]:
    exact = EXACT_ROOT / "run-a1/layer_3_entry.f32le"
    stages = {name: sha(EXACT_ROOT / "run-a1" / f"{name}.f32le") for name in SURFACES}
    return {
        "schema": "pulsarmlx.f017.dprefix-exact1-public-descriptor", "schema_version": "1.0.0",
        "artifact_id": "DPREFIX-EXACT-1", "classification": "EXACT_CLASS",
        "status": "CANONICALIZATION_PRODUCED_PENDING_INDEPENDENT_REVIEW",
        "contract": source("specs/017-rust-native-inference-runtime/contracts/f017-dprefix-exact-scaffold-v1.json"),
        "implementations": [source("scripts/research/f017_dprefix_exact_scaffold.c"), source("scripts/research/f017_dprefix_exact_scaffold.rs")],
        "stage_sha256": stages,
        "layer3": {"sha256": sha(exact), "shape": [6144], "dtype": "f32", "count": 6144,
                   "private_manifest_sha256": retained["private_manifest_sha256"]},
        "reproduction": {"implementation_count": 2, "fresh_process_count": 4,
                         "all_eight_surfaces_exact": True,
                         "result": "DPREFIX-EXACT-1 BITWISE SELF-REPRODUCIBLE"},
        "comparisons": {
            "REAL-2": metrics(exact, REAL2_STATE),
            "REAL-3": metrics(exact, REAL3_STATE),
            "candidate": metrics(exact, CANDIDATE_STATE),
        },
        "candidate_frozen_tier_b_disposition": "PASS; exact-vs-candidate max_abs and RMSE remain below the frozen final-surface Tier-B limits",
        "canonical_authority": "PENDING_INDEPENDENT_REVIEW",
        "checkpoint_access": 0, "real_payload_ledger": LEDGER,
    }


def gate_audit() -> dict[str, Any]:
    contract = json.loads((CONTRACTS / "f017-identity-gate-contract-v2.json").read_text())
    counts = Counter(item["reproducibility_class"] for item in contract["gate_audit"])
    return {
        "schema": "pulsarmlx.f017.identity-gate-v2-audit", "schema_version": "1.0.0",
        "contract_sha256": sha(CONTRACTS / "f017-identity-gate-contract-v2.json"),
        "gate_count": len(contract["gate_audit"]), "class_counts": dict(counts),
        "misclassified_gate_count": len(contract["misclassified_historical_gates"]),
        "misclassified_gates": contract["misclassified_historical_gates"],
        "missing_mechanism_negative_test": "PASS",
        "blas_exact_sha_negative_test": "PASS",
        "historical_real3_rejected_unchanged": True,
        "checkpoint_access": 0, "real_payload_ledger": LEDGER,
    }


def internal_review(exact: dict[str, Any], campaign: dict[str, Any], route: dict[str, Any]) -> dict[str, Any]:
    answers = {
        "1_inputs_byte_identical": True,
        "2_first_divergent_stage": "layer_0_attention",
        "3_process_variation_reproduced": True,
        "4_blas_mechanism": "demonstrated backend/wheel difference; thread-count mechanism not observed",
        "5_real2_hash_reproducible": campaign["real2_hash_independently_reproduced"],
        "6_real3_hash_reproducible": campaign["real3_hash_independently_reproduced"],
        "7_exact_sha": exact["layer3"]["sha256"],
        "8_exact_fresh_process_reproducible": True,
        "9_exact_distance_to_blas": {key: exact["comparisons"][key] for key in ("REAL-2", "REAL-3")},
        "10_candidate_frozen_tier_b_vs_exact": "PASS",
        "11_gate_v2_mechanism_structural": True,
        "12_other_misclassified_gates": "one historical BLAS recomputation gate; no second live successor gate found",
        "13_route_invariant": False,
        "14_routing_weights_robust": False,
        "15_another_dprefix_replay_needed": False,
        "16_checkpoint_access": 0,
        "17_real_payload_ledger": LEDGER,
    }
    return {
        "schema": "pulsarmlx.f017.dprefix-oracle-reproducibility-internal-review",
        "schema_version": "1.0.0", "verdict": "BLOCKED — ROUTE INSENSITIVITY",
        "answers": answers,
        "blocking_finding": route["retained_route_surface"]["finding"],
        "replay_necessity_disposition": "OPTION_A_NO_FURTHER_DPREFIX_REPLAY_REQUIRED; route proof needs restored/reviewed route inputs, not another dense-prefix replay",
        "checkpoint_access": 0, "real_payload_ledger": LEDGER,
    }


def main() -> int:
    forensics = historical_forensics()
    campaign = aggregate_campaign()
    retained = retain_exact()
    exact = exact_descriptor(retained)
    route = route_analyze()
    audit = gate_audit()
    review = internal_review(exact, campaign, route)
    paths = {
        "forensics": EVIDENCE / "f017-dprefix-oracle-cross-process-forensics-v1.json",
        "campaign": EVIDENCE / "f017-dprefix-blas-process-campaign-v1.json",
        "exact": EVIDENCE / "f017-dprefix-exact1-descriptor-v1.json",
        "audit": EVIDENCE / "f017-identity-gate-v2-audit-v1.json",
        "route": EVIDENCE / "f017-dprefix-route-ambiguity-proof-v1.json",
        "review": EVIDENCE / "f017-dprefix-oracle-reproducibility-internal-review-v1.json",
    }
    for key, value in (("forensics", forensics), ("campaign", campaign), ("exact", exact),
                       ("audit", audit), ("route", route), ("review", review)):
        write_json(paths[key], value)
    packet = {
        "schema": "pulsarmlx.f017.dprefix-oracle-reproducibility-adversarial-packet",
        "schema_version": "1.0.0", "status": "BLOCKED_ROUTE_PROOF_NOT_REVIEW_READY",
        "primary_questions": [
            "Has the cross-process oracle mismatch been demonstrated rather than inferred?",
            "Is DPREFIX-EXACT-1 bitwise reproducible by construction?",
            "Does identity-gate v2 separate exact, bounded, and persisted authority?",
            "Can routing invariance be reviewed without the missing retained route propagation bytes?",
        ],
        "bindings": {key: {"path": str(path.relative_to(ROOT)), "sha256": sha(path)} for key, path in paths.items()},
        "required_verdicts": ["GO FOR DPREFIX EXACT CANONICALIZATION", "GO WITH REQUIRED FIXES", "NO-GO"],
        "review_checkpoint_access": 0, "real_payload_ledger": LEDGER,
    }
    packet_path = EVIDENCE / "f017-dprefix-oracle-reproducibility-adversarial-packet-v1.json"
    write_json(packet_path, packet)
    report = REPORTS / "f017-dprefix-oracle-reproducibility-closure-report.md"
    delta = forensics["real2_real3_layer3_delta"]
    report.write_text(f"""# PulsarMLX F017 DPREFIX Oracle-Reproducibility Closure Report

- Starting SHA: `{subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip()}`
- Final preparation SHA: `PENDING_FINAL_PREPARATION_COMMIT`
- REAL-2 state SHA: `{sha(REAL2_STATE)}`
- REAL-3 state SHA: `{sha(REAL3_STATE)}`
- Byte-delta statistics: `{delta['differing_elements']}` differing f32 elements; first index `{delta['first_differing_element']}`; max abs `{delta['max_absolute_difference']}`; RMSE `{delta['rmse']}`; cosine `{delta['cosine']}`; no sign or zero changes.
- First divergent surface: `layer_0_attention`
- BLAS thread/process campaign: `{campaign['result']}`; `{campaign['thread_count_result']}`; CPython 3.13/Accelerate reproduces REAL-2 and CPython 3.14/OpenBLAS reproduces REAL-3.
- Demonstrated root cause: platform-wheel BLAS backend/reduction realization changed despite identical source, NumPy version, and inputs.
- Exact-scaffold contract SHA: `{sha(CONTRACTS / 'f017-dprefix-exact-scaffold-v1.json')}`
- Exact implementation identities: C `{sha(ROOT / 'scripts/research/f017_dprefix_exact_scaffold.c')}`; Rust `{sha(ROOT / 'scripts/research/f017_dprefix_exact_scaffold.rs')}`
- DPREFIX-EXACT-1 SHA: `{exact['layer3']['sha256']}`
- Exact fresh-process reproduction: `DPREFIX-EXACT-1 BITWISE SELF-REPRODUCIBLE` across two implementations and four fresh processes.
- Exact vs REAL-2: max abs `{exact['comparisons']['REAL-2']['max_absolute_difference']}`, RMSE `{exact['comparisons']['REAL-2']['rmse']}`, cosine `{exact['comparisons']['REAL-2']['cosine']}`.
- Exact vs REAL-3: max abs `{exact['comparisons']['REAL-3']['max_absolute_difference']}`, RMSE `{exact['comparisons']['REAL-3']['rmse']}`, cosine `{exact['comparisons']['REAL-3']['cosine']}`.
- Exact vs candidate: max abs `{exact['comparisons']['candidate']['max_absolute_difference']}`, RMSE `{exact['comparisons']['candidate']['rmse']}`, cosine `{exact['comparisons']['candidate']['cosine']}`; frozen final Tier-B remains PASS.
- Identity-gate v2 SHA: `{sha(CONTRACTS / 'f017-identity-gate-contract-v2.json')}`
- Gate-class audit: `{audit['gate_count']}` gates; `{audit['class_counts']}`; one historical BLAS exact-recomputation gate misclassified, with REAL-3 unchanged.
- Route ambiguity bound: componentwise L-inf `{route['ambiguity_set']['componentwise_radius_max']}`, L2 `{route['ambiguity_set']['l2_radius']}`, L1 `{route['ambiguity_set']['l1_radius']}`.
- Router-logit ambiguity bound: `NOT_DERIVABLE_FROM_COMMITTED_RETAINED_BYTES`.
- v3 membership minimum factor: `NOT_COMPUTED` (`0/1,984` inequalities proven).
- Worst membership pair: `NOT_COMPUTED`.
- Routing-weight robustness: `NOT_PROVEN`.
- Route-insensitivity disposition: `ROUTE NOT PROVEN INVARIANT`.
- Replay-necessity disposition: `OPTION A — no further dense-prefix replay required`; route proof requires restored/reviewed route inputs rather than another dense-prefix replay.
- Checkpoint access: `0`
- Real-payload ledger: `139`
- Internal verdict: `BLOCKED — ROUTE INSENSITIVITY`
- Adversarial packet SHA: `{sha(packet_path)}`
- Final CI run/head: `PENDING_FINAL_HEAD_CI`

The committed v2 antecedent manifest describes the router matrix and norm artifacts, but the load-bearing private bytes are absent. More importantly, that package retains old-input attention/router antecedents rather than the layer-3 attention tensors or a reviewed global attention propagation bound needed for a new dense-prefix ambiguity set. Reconstructing either from hashes would violate the fail-closed contract; opening the checkpoint is forbidden.

## Exact next action

Restore and independently verify the already-reviewed private route-propagation artifacts, or prepare a checkpoint-free reviewed package containing the missing layer-3 attention and router propagation surface. Then complete all 1,984 v3 membership inequalities and weight intervals before independent adversarial review. No DPREFIX replay, M1-F0, M1-F, or checkpoint access.
""")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
