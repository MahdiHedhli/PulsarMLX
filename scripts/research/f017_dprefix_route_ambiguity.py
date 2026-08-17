#!/usr/bin/env python3
"""Fail-closed route-insensitivity analysis for the DPREFIX ambiguity set."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
PRIVATE = ROOT / ".pulsarmlx-local"
MANIFEST = ROOT / "docs/architecture/reviews/evidence/f017-v2-antecedent-recovery-private-manifest-v1.json"
EXACT = PRIVATE / "dprefix-exact-1/run-a1/layer_3_entry.f32le"
REAL2 = PRIVATE / "dprefix-real-2/oracle-primary/layer_3_entry.f32le"
REAL3 = PRIVATE / "dprefix-real-3/oracle-primary/layer_3_entry.f32le"
LEDGER = 139


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ambiguity_envelope() -> dict[str, Any]:
    exact = np.fromfile(EXACT, dtype="<f4").astype(np.float64)
    real2 = np.fromfile(REAL2, dtype="<f4").astype(np.float64)
    real3 = np.fromfile(REAL3, dtype="<f4").astype(np.float64)
    if exact.shape != (6144,) or real2.shape != exact.shape or real3.shape != exact.shape:
        raise ValueError("ambiguity state shape")
    componentwise = np.maximum(np.abs(real2 - exact), np.abs(real3 - exact))
    pairwise = np.abs(real2 - real3)
    return {
        "center": "DPREFIX-EXACT-1",
        "center_sha256": sha(EXACT),
        "members": {"REAL-2": sha(REAL2), "REAL-3": sha(REAL3)},
        "construction": "componentwise symmetric box centered on exact state; each radius is max(|REAL2-exact|, |REAL3-exact|), rounded outward once",
        "componentwise_radius_max": math.nextafter(float(componentwise.max()), math.inf),
        "l1_radius": math.nextafter(float(componentwise.sum()), math.inf),
        "l2_radius": math.nextafter(float(np.linalg.norm(componentwise)), math.inf),
        "pairwise_linf_observed": math.nextafter(float(pairwise.max()), math.inf),
        "covers_all_three_states": bool(np.all(np.abs(real2 - exact) <= componentwise) and np.all(np.abs(real3 - exact) <= componentwise)),
        "component_count": 6144,
    }

def retained_route_surface_status() -> dict[str, Any]:
    manifest = json.loads(MANIFEST.read_text())
    roots = [
        PRIVATE / "f017-v2-antecedent-recovery",
        PRIVATE / "v2-antecedent-recovery",
        PRIVATE / "antecedent-recovery",
    ]
    required = {
        item["symbolic_name"]: item["sha256"]
        for item in manifest["artifacts"]
        if item["artifact_id"] in {"router_matrix", "ffn_norm_weight", "rmsnorm_decomposition_inputs"}
    }
    present: dict[str, str] = {}
    for relative, expected in required.items():
        for root in roots:
            candidate = root / relative
            if candidate.is_file() and not candidate.is_symlink() and sha(candidate) == expected:
                present[relative] = expected
                break
    # The retained v2 surface is evaluated at the old accepted M1-F0 input.  It
    # does not retain the layer-3 attention tensors needed to map a new
    # layer-3-entry ambiguity through attention into router-normalized input.
    missing_semantic = [
        "layer-3 attention tensor bytes or a reviewed global attention Lipschitz bound",
        "router matrix bytes (required for componentwise logit propagation)",
        "layer-3 FFN RMSNorm weight bytes",
    ]
    return {
        "committed_manifest_sha256": sha(MANIFEST),
        "manifest_artifact_count": manifest["artifact_count"],
        "required_persisted_artifacts_found": present,
        "required_persisted_artifacts_expected": required,
        "semantic_inputs_missing": missing_semantic,
        "finding": "COMMITTED DESCRIPTORS EXIST; LOAD-BEARING PRIVATE BYTES ARE ABSENT AND THE V2 PACKAGE DOES NOT RETAIN A NEW-INPUT ATTENTION PROPAGATION SURFACE",
    }


def analyze() -> dict[str, Any]:
    status = retained_route_surface_status()
    complete = len(status["required_persisted_artifacts_found"]) == len(status["required_persisted_artifacts_expected"]) and not status["semantic_inputs_missing"]
    if complete:
        raise RuntimeError("route implementation must be extended before claiming proof")
    return {
        "schema": "pulsarmlx.f017.dprefix-oracle-ambiguity-route-proof",
        "schema_version": "1.0.0",
        "status": "BLOCKED_MISSING_RETAINED_ROUTE_PROPAGATION_SURFACE",
        "ambiguity_set": ambiguity_envelope(),
        "retained_route_surface": status,
        "router_logit_ambiguity_bound": "NOT_DERIVABLE_FROM_COMMITTED_RETAINED_BYTES",
        "membership_inequalities_required": 1984,
        "membership_inequalities_proved": 0,
        "membership_minimum_factor": "NOT_COMPUTED",
        "worst_membership_pair": "NOT_COMPUTED",
        "engineering_h2": "NOT_PROVEN",
        "routing_weight_robustness": "NOT_PROVEN",
        "route_insensitivity_disposition": "ROUTE NOT PROVEN INVARIANT",
        "checkpoint_access": 0,
        "real_payload_ledger": LEDGER,
    }
