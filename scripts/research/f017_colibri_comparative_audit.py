#!/usr/bin/env python3
"""Pinned, checkpoint-free Colibrì comparison and independent risk controls.

No Colibrì source is imported or executed.  The module records independently
verified source identities and implements small PulsarMLX-owned falsifiers for
the generic failure classes exposed by the external audit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
from pathlib import Path
from typing import Iterable, Sequence


COLIBRI_REPOSITORY = "https://github.com/JustVugg/colibri"
COLIBRI_COMMIT = "6546cdde7296f28771e2ba1a1d7c1d4b0cb550aa"
COLIBRI_TREE = "bc52bec7cf224d641318c68e5ef7d6a5e3489ef0"
OBSERVED_PROMPT_COMMIT = COLIBRI_COMMIT
LICENSE_SPDX = "Apache-2.0"
LICENSE_SHA256 = "c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4"

REUSE_V2_SHA256 = "3a947427cfc285119fe9b8bcc910e26fdde4cdd6599711fe3f6b5df14d95c71c"
ROUTING_V3_SHA256 = "c5662a611abc000703606d799a7214ee27e39c556bc6595f217c86498e944a85"
LEDGER = 57

FILE_HASHES = {
    "LICENSE": LICENSE_SHA256,
    "docs/metal.md": "4e551eaad0f9c671d01e4cc202a6730ed242d3789cb0f995e2710b3b46630853",
    "c/backend_metal.h": "3e14e1d3a61a5fe0467618235613d686884c9ef2147da60d9df686490949c7db",
    "c/backend_metal.mm": "8cec3921794b4fcb0afe0e784d85e9959fc8c599382bab4f4568fb21f9fce0c2",
    "c/colibri.c": "fc64daf929eeae5ca957bd1e56ffa9b3a61c9c180d1b2a0eb42d5a9346a0b51e",
    "c/Makefile": "1d7513e0bac72caf1098cbf8e8f7f44a1d4c8621f2ea17068bdf6637137dc4ad",
    "c/tests/test_backend_metal.mm": "26ea8a0c625fec7da86060ae57ec437277b20ed79efe41ea91d749d191002488",
    "c/tests/test_gemm_largebatch.mm": "73d9713902ba751e8f3110e731d634bf0c70619841c88c99652706ceb1ca30a5",
    "docs/METAL-M1ULTRA-FMT2-REPORT.md": "ca1af868bb68a7d3589a68016d1f57ccc2538d41b1674264b57347ecd04f469d",
    "docs/METAL-M5MAX-PERF-REPORT.md": "ab1d0b1d79d4414312591b53d1b1add5e18d01c1218afaa71b21788c70996ddc",
    "docs/FORMATS.md": "f0564fcff1a1f089d2233130938b411bbba0f2c400cb52bfb3acae5410121f1a",
    "c/resource_plan.py": "e63f5fcac8769535764eafdc879083f48a5bd9be74036d718d42665c87717e9f",
}

ISSUES = [
    {
        "number": 596,
        "state": "CLOSED",
        "title": "Metal residency-set symbols were not compile-time gated for older SDKs",
        "url": "https://github.com/JustVugg/colibri/issues/596",
        "body_sha256": "eb83a85a20b012abfee29d3c8d2131cec0de306e83bfcb409b82aab75791a89f",
        "comments_sha256": "1d0732458f38bc89eef419950d1ce3918d6a91f0497ab418a33b5f5d467a6293",
        "updated_at": "2026-07-25T11:51:04Z",
    },
    {
        "number": 622,
        "state": "OPEN",
        "title": "Metal prefill GEMM near-tie token divergence",
        "url": "https://github.com/JustVugg/colibri/issues/622",
        "body_sha256": "34bfb247b7e997d5e5229737f1bb275e3614d4be37632a843d112f9b3583735e",
        "comments_sha256": "dac35669cdeec7f277fd0ad22127407dd00fbee0e2d7e988b8fdced2a012eec3",
        "updated_at": "2026-07-26T08:21:06Z",
    },
    {
        "number": 637,
        "state": "CLOSED",
        "title": "Metal fmt=6 routed-expert support",
        "url": "https://github.com/JustVugg/colibri/issues/637",
        "body_sha256": "a3bdb6a0ecd8e7214f4d8a6c6f24782c4580725ab4778f63de2219bd3f90bb63",
        "comments_sha256": "56dc373b4e9fb7098679e3b6d610c5284a606e9476e8944c6cffd5c2395ac839",
        "updated_at": "2026-08-01T01:25:17Z",
    },
    {
        "number": 706,
        "state": "CLOSED",
        "title": "Metal is ineffective at low expert residency",
        "url": "https://github.com/JustVugg/colibri/issues/706",
        "body_sha256": "e35b8ae32e3eaffce1f367f4552300c9dd85060637e9b5b293a8500f79abbf90",
        "comments_sha256": "ab795112ee1616b4036834ed9c6c15607069077271e9b2b32692c8b0453d7d68",
        "updated_at": "2026-08-02T12:01:57Z",
    },
    {
        "number": 813,
        "state": "OPEN",
        "title": "Metal mode announcement without routed-expert dispatch",
        "url": "https://github.com/JustVugg/colibri/issues/813",
        "body_sha256": "e6b9d32d9745f9abaf3c0dbab63db5f03a8f4a5f6f4844cb38b61e5352676fef",
        "comments_sha256": "7d51fde756965fab22924f2be065c14e686c1c34e7c15b6d9a60c565cc97f375",
        "updated_at": "2026-08-05T15:16:48Z",
    },
    {
        "number": 826,
        "state": "OPEN",
        "title": "Optional streamable dense trunk",
        "url": "https://github.com/JustVugg/colibri/issues/826",
        "body_sha256": "558b103ccaf1593125fd6d61dcdc0a1035b87e0b39649caa619b5c99f274cee3",
        "comments_sha256": "db4978bc8af83e81a69a55dc21999ef3d2a8314ae3d908f34114566df932bbe0",
        "updated_at": "2026-08-11T20:15:09Z",
    },
]

PULL_REQUESTS = [
    {"number": 457, "state": "MERGED", "merge_commit": "df5486ca540b83f88c16e555c3bb0cdbb1eb605f", "body_sha256": "0b0c557ebf934891d251d6def7581d998e8b5dc32fd88d71a33005d50c4dee06", "url": "https://github.com/JustVugg/colibri/pull/457"},
    {"number": 587, "state": "MERGED", "merge_commit": "98cab3b6622eddd5ad4c9defa728b797b697c840", "body_sha256": "50f7eab7ec79f1664956d2028fe9b9aa6b47abe86ae3660c1328a7187fb5da69", "url": "https://github.com/JustVugg/colibri/pull/587"},
    {"number": 624, "state": "MERGED", "merge_commit": "6fcc555652d0e04dc7deb57856c38d8d9c41cdeb", "body_sha256": "a241caf7bcf293000f4d1628ec97f5e456908f327c6f4a0d43ef1d9b1afcf8b0", "url": "https://github.com/JustVugg/colibri/pull/624"},
]


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def f32(value: float) -> float:
    return struct.unpack("<f", struct.pack("<f", value))[0]


def reduce_f32(terms: Sequence[float], order: Sequence[int]) -> float:
    if sorted(order) != list(range(len(terms))):
        raise ValueError("order must be a permutation")
    total = f32(0.0)
    for index in order:
        term = f32(terms[index])
        if not math.isfinite(term):
            raise ValueError("non-finite reduction term")
        total = f32(total + term)
    return total


def top2_margin(logits: Sequence[float]) -> dict[str, object]:
    if len(logits) < 2 or any(not math.isfinite(value) for value in logits):
        raise ValueError("at least two finite logits required")
    ranking = sorted(range(len(logits)), key=lambda index: (-logits[index], index))
    first, second = ranking[:2]
    return {
        "top1_id": first,
        "top1_value": logits[first],
        "top2_id": second,
        "top2_value": logits[second],
        "margin": logits[first] - logits[second],
        "tie_policy": "lower token ID wins exact ties",
    }


def near_tie_transition_record(
    reference_logits: Sequence[float], candidate_logits: Sequence[float], rows: int, threshold: int
) -> dict[str, object]:
    if rows < 0 or threshold < 1:
        raise ValueError("invalid dispatch dimensions")
    reference = top2_margin(reference_logits)
    candidate = top2_margin(candidate_logits)
    return {
        "rows": rows,
        "threshold": threshold,
        "path_class": "BELOW_THRESHOLD" if rows < threshold else "AT_OR_ABOVE_THRESHOLD",
        "reference": reference,
        "candidate": candidate,
        "token_diverged": reference["top1_id"] != candidate["top1_id"],
        "all_margin_fields_retained": True,
    }


def validate_near_tie_record(record: dict[str, object]) -> None:
    if set(record) != {
        "rows", "threshold", "path_class", "reference", "candidate", "token_diverged", "all_margin_fields_retained"
    }:
        raise ValueError("near-tie record surface incomplete")
    expected_path = "BELOW_THRESHOLD" if int(record["rows"]) < int(record["threshold"]) else "AT_OR_ABOVE_THRESHOLD"
    if record["path_class"] != expected_path or record["all_margin_fields_retained"] is not True:
        raise ValueError("near-tie dispatch or retention mismatch")
    for side in ("reference", "candidate"):
        value = record[side]
        if not isinstance(value, dict) or set(value) != {
            "top1_id", "top1_value", "top2_id", "top2_value", "margin", "tie_policy"
        }:
            raise ValueError("top-2 analytical retention incomplete")
        if not all(math.isfinite(float(value[field])) for field in ("top1_value", "top2_value", "margin")):
            raise ValueError("non-finite top-2 analytical value")
        if float(value["margin"]) < 0:
            raise ValueError("negative top-2 margin")
    expected_divergence = record["reference"]["top1_id"] != record["candidate"]["top1_id"]
    if record["token_diverged"] != expected_divergence:
        raise ValueError("token divergence summary mismatch")


def reconcile_dispatch_evidence(value: dict[str, int | bool]) -> str:
    required = {
        "backend_announced", "eligible_operations", "native_dispatches", "format_refusals",
        "fallbacks", "backend_errors", "unclassified_no_dispatch",
    }
    if set(value) != required:
        raise ValueError("dispatch evidence surface incomplete")
    for field in required - {"backend_announced"}:
        if int(value[field]) < 0:
            raise ValueError("negative dispatch counter")
    if value["backend_errors"] or value["unclassified_no_dispatch"]:
        raise ValueError("backend error or unclassified missing dispatch")
    accounted = int(value["native_dispatches"]) + int(value["format_refusals"]) + int(value["fallbacks"])
    if accounted != int(value["eligible_operations"]):
        raise ValueError("eligible operations do not reconcile")
    if value["backend_announced"] and value["eligible_operations"] and not value["native_dispatches"]:
        return "BACKEND_AVAILABLE_BUT_NO_NATIVE_WORK"
    return "RECONCILED"


def verify_colibri_source(source_root: Path) -> None:
    git_dir = source_root / ".git"
    if not git_dir.exists():
        raise ValueError("pinned Colibrì git checkout required")
    for relative, expected in FILE_HASHES.items():
        path = source_root / relative
        if not path.is_file() or sha256_path(path) != expected:
            raise ValueError(f"pinned Colibrì file mismatch: {relative}")


def reuse_use_case_matrix() -> list[dict[str, str]]:
    return [
        {"use_case": "multi-fixture oracle-only route analysis", "policy": "REUSE_SAFE_FOR_ORACLE_ONLY", "reason": "one hash-bound read-only package; full precommitted-family banking; no candidate alias"},
        {"use_case": "multi-fixture candidate route analysis", "policy": "SEPARATE_ORACLE_AND_CANDIDATE_PACKAGES_REQUIRED", "reason": "candidate import/decode and lifecycle coverage remain independently visible"},
        {"use_case": "dense-prefix independent oracle", "policy": "REUSE_SAFE_FOR_ORACLE_ONLY", "reason": "oracle completes from immutable canonical bytes before candidate construction"},
        {"use_case": "dense-prefix production candidate", "policy": "SEPARATE_ORACLE_AND_CANDIDATE_PACKAGES_REQUIRED", "reason": "separately hashed copy/import; no shared writable alias; production import remains exercised"},
        {"use_case": "Q4_K/Q6_K decoder qualification", "policy": "REUSE_PROHIBITED", "reason": "A/B/C must independently consume the exact packed payload; decoded truth is not shared"},
        {"use_case": "future M1-F expert execution", "policy": "SEPARATE_ORACLE_AND_CANDIDATE_PACKAGES_REQUIRED", "reason": "route-specific payload and candidate import/decode evidence are load-bearing"},
        {"use_case": "M1-G output-head work", "policy": "SEPARATE_ORACLE_AND_CANDIDATE_PACKAGES_REQUIRED", "reason": "format lineage may transfer but output-head packed identity and candidate import do not"},
    ]


def comparison_matrix() -> list[dict[str, object]]:
    rows = [
        ("embedding", "resident/stored embedding lookup", "PulsarMLX GGUF embedding lookup", "same high-level lookup, different container/runtime", "EVIDENCE_ONLY"),
        ("RMSNorm", "CPU and fused Metal RMSNorm", "independent NumPy oracle plus MLX candidate", "same formula; different reduction and fusion", "NUMERICAL_RISK_REGRESSION"),
        ("MLA/DSA attention", "absorbed MLA with fused decode/prefill options", "reviewed MLA/DSA MLX path", "Colibrì custom Metal command buffers versus MLX operations", "REQUIRES_SEPARATE_REVIEW"),
        ("dense FFN", "large GEMM switches at a row threshold", "MLX matmul path with native dispatch evidence", "no shared threshold; same accumulation-order risk class", "ADOPT_TEST_NOW"),
        ("MoE routing", "sigmoid+bias, exact top-k, weights", "routing-contract v3 atomic ID/weight pairs", "rank diagnostics differ; semantics independently traced", "NOT_APPLICABLE"),
        ("routed experts", "one batched command buffer for resident expert block", "route-independent fused/grouped MLX path", "different backend and quant containers", "INFORM_FUTURE_FEATURE_018"),
        ("shared expert/residual", "may be included in full-layer command buffer", "fixed semantic placement outside routed-term permutation", "same architecture role, different scheduling", "ADOPT_INSTRUMENTATION_NOW"),
        ("zero-copy slabs", "page-aligned host memory wrapped as shared MTLBuffer", "hash-bound decoded package plus explicit MLX import", "PulsarMLX does not expose Colibrì slab registration", "ADOPT_TEST_NOW"),
        ("residency sets", "optional queue-attached MTLResidencySet", "contract-derived host admission and MLX telemetry", "OS/SDK/backend surface differs", "INFORM_FUTURE_FEATURE_018"),
        ("async I/O overlap", "resident GPU block submitted before missed-expert reads", "not active in current F017 qualification", "completion and reduction order must remain deterministic", "INFORM_FUTURE_FEATURE_018"),
        ("dispatch diagnostics", "GPU blocks/fallback/expert counters", "conceptual/native/fallback/error reconciliation", "PulsarMLX is stricter: fallback is gate failure", "ADOPT_INSTRUMENTATION_NOW"),
        ("near-tie numerics", "prefill GEMM can differ from CPU after row threshold", "MLX Tier-B plus exact semantic selection", "generic risk transfers; numeric magnitude does not", "NUMERICAL_RISK_REGRESSION"),
        ("quantized formats", "custom fmt=2/fmt=4 row/group int4", "GGUF Q4_K/Q6_K block formats", "scale/block/container layouts are not equivalent", "FORMAT_INCOMPATIBLE"),
        ("resource planning", "dense/runtime/expert tiers with unified-memory clamping", "dense-prefix liveness plus pre-observation floor", "Colibrì data informs threats, not MLX byte proof", "INFORM_RESIDENCY_PLAN"),
    ]
    return [
        {
            "subsystem": subsystem,
            "colibri_mechanism": colibri,
            "pulsarmlx_equivalent": pulsar,
            "semantic_match": "PARTIAL" if disposition not in {"NOT_APPLICABLE", "FORMAT_INCOMPATIBLE"} else "NO_DIRECT_EQUIVALENCE",
            "implementation_difference": difference,
            "correctness_relevance": disposition in {"ADOPT_TEST_NOW", "ADOPT_INSTRUMENTATION_NOW", "NUMERICAL_RISK_REGRESSION"},
            "performance_relevance": disposition in {"INFORM_FUTURE_FEATURE_018", "INFORM_RESIDENCY_PLAN", "ADOPT_INSTRUMENTATION_NOW"},
            "immediate_action": disposition if disposition in {"ADOPT_TEST_NOW", "ADOPT_INSTRUMENTATION_NOW", "NUMERICAL_RISK_REGRESSION", "INFORM_RESIDENCY_PLAN"} else "NONE",
            "future_action": disposition if disposition in {"INFORM_FUTURE_FEATURE_018", "REQUIRES_SEPARATE_REVIEW"} else "NONE",
            "not_applicable_reason": difference if disposition in {"NOT_APPLICABLE", "FORMAT_INCOMPATIBLE"} else None,
            "classification": disposition,
        }
        for subsystem, colibri, pulsar, difference, disposition in rows
    ]


def risk_register_value() -> dict[str, object]:
    return {
        "schema": "pulsarmlx.f017.colibri-metal-risk-register",
        "schema_version": "1.0.0",
        "source_commit": COLIBRI_COMMIT,
        "status": "CHECKPOINT_FREE_ACTIONABLE_NO_EXTERNAL_CODE",
        "risks": [
            {"id": "C-METAL-001", "risk": "backend accumulation-order drift crosses a near-tie token margin", "control": "retain top-1/top-2 values and margin at every logits boundary; compare exact semantic selection; bank threshold-transition discriminator", "classification": "NUMERICAL_RISK_REGRESSION"},
            {"id": "C-METAL-002", "risk": "backend announces availability while an unsupported format produces zero native work", "control": "eligible=native+refusal+fallback; unclassified no-dispatch is fatal; backend availability is not execution proof", "classification": "ADOPT_INSTRUMENTATION_NOW"},
            {"id": "C-METAL-003", "risk": "zero-copy source is freed, moved, or mutated before GPU completion", "control": "stable identity, read-only bytes, before/after hashes, explicit sync, unregister-before-free, zero in-flight work at PASS", "classification": "ADOPT_TEST_NOW"},
            {"id": "C-METAL-004", "risk": "aggregate decoded volume is mistaken for simultaneous peak residency", "control": "source-backed lifetime intervals, overlap checks, backend/import/evidence reserve, telemetry cannot lower frozen floor", "classification": "INFORM_RESIDENCY_PLAN"},
            {"id": "C-METAL-005", "risk": "asynchronous completion changes routed-term reduction order", "control": "completion order decoupled from deterministic reduction; repeat hashes and accumulation-order bound required", "classification": "INFORM_FUTURE_FEATURE_018"},
            {"id": "C-METAL-006", "risk": "large dispatch grids cross an untested backend limit", "control": "boundary-shaped row/output transition tests and exact first-divergence diagnostics", "classification": "NUMERICAL_RISK_REGRESSION"},
            {"id": "C-METAL-007", "risk": "external custom int4 layout is mistaken for GGUF Q4_K/Q6_K", "control": "formal block/scale/container equivalence required; otherwise algorithmic lesson only", "classification": "FORMAT_INCOMPATIBLE"},
            {"id": "C-METAL-008", "risk": "optional OS API is runtime-gated but not SDK-gated", "control": "compile-time capability gate plus runtime availability and explicit fallback evidence", "classification": "REQUIRES_SEPARATE_REVIEW"},
        ],
        "real_checkpoint_access": 0,
        "ledger": LEDGER,
    }


def adoption_candidates_value() -> dict[str, object]:
    return {
        "schema": "pulsarmlx.f017.colibri-adoption-candidates",
        "schema_version": "1.0.0",
        "source_commit": COLIBRI_COMMIT,
        "license": LICENSE_SPDX,
        "direct_source_copy": False,
        "runtime_dependency": False,
        "submodule": False,
        "immediate": [
            {"candidate": "top1_top2_margin_retention", "disposition": "ADOPT_TEST_NOW"},
            {"candidate": "dispatch_threshold_transition_falsifier", "disposition": "ADOPT_TEST_NOW"},
            {"candidate": "eligible_native_refusal_fallback_reconciliation", "disposition": "ADOPT_INSTRUMENTATION_NOW"},
            {"candidate": "zero_copy_lifetime_invariants", "disposition": "ADOPT_TEST_NOW"},
            {"candidate": "peak_not_aggregate_residency_guard", "disposition": "INFORM_RESIDENCY_PLAN"},
        ],
        "future_feature_018": [
            {"candidate": "fusion_aware_command_buffer_accounting", "disposition": "INFORM_FUTURE_FEATURE_018"},
            {"candidate": "batched_routed_expert_submission", "disposition": "REQUIRES_SEPARATE_REVIEW"},
            {"candidate": "explicit_zero_copy_registration_bridge", "disposition": "REQUIRES_SEPARATE_REVIEW"},
            {"candidate": "residency_set_experiment", "disposition": "REQUIRES_SEPARATE_REVIEW"},
            {"candidate": "resident_compute_overlapped_with_io", "disposition": "REQUIRES_SEPARATE_REVIEW"},
        ],
        "rejected": [
            {"candidate": "Colibrì output as Q4_K/Q6_K oracle", "reason": "FORMAT_INCOMPATIBLE"},
            {"candidate": "direct code copy", "reason": "NO_PROVEN_NEED_AND_SEPARATE_PROVENANCE_REVIEW_REQUIRED"},
            {"candidate": "performance projection from Colibrì hardware reports", "reason": "DIFFERENT_BACKEND_FORMAT_HARDWARE_AND_WORKLOAD"},
        ],
        "real_checkpoint_access": 0,
        "ledger": LEDGER,
    }


def audit_value() -> dict[str, object]:
    return {
        "schema": "pulsarmlx.f017.colibri-comparative-audit",
        "schema_version": "1.0.0",
        "status": "ACTIONABLE_CHECKPOINT_FREE",
        "repository": COLIBRI_REPOSITORY,
        "branch_observed": "main",
        "pinned_commit": COLIBRI_COMMIT,
        "pinned_tree": COLIBRI_TREE,
        "prompt_observed_commit": OBSERVED_PROMPT_COMMIT,
        "head_differs_from_prompt_observation": False,
        "license": {"spdx": LICENSE_SPDX, "file": "LICENSE", "sha256": LICENSE_SHA256},
        "file_hashes": [{"path": path, "sha256": digest} for path, digest in FILE_HASHES.items()],
        "issues": ISSUES,
        "pull_requests": PULL_REQUESTS,
        "comparison_matrix": comparison_matrix(),
        "near_tie_forensics": {
            "issue": 622,
            "pinned_source_threshold": 16,
            "reported_condition": "large-batch prefill GEMM selected at rows >= 16; decode rows=1 did not cross it",
            "reported_discriminator": "raising COLI_METAL_GEMM_MIN kept GEMM on CPU and removed the mismatch",
            "accumulation_order": "CPU and Metal differ; single-kernel tolerance does not guarantee final token identity",
            "propagated_effect": "issue follow-up reports downstream logits drift can exceed the isolated kernel error",
            "fused_attention_disposition": "not implicated by the reported discriminator on the cited fixture; not globally exonerated",
            "current_pinned_status": "OPEN_WITH_DOCS_AND_DEBUG_INSTRUMENTATION_MERGED",
            "pulsarmlx_transfer": "generic threshold/margin/attribution regression only; no MLX magnitude borrowed",
        },
        "m1_ultra_report_interpretation": {
            "classification": "EXTERNAL_SINGLE_RUN_PER_CONFIG_CONTEXT_ONLY",
            "lessons": ["separate disk wait, compute, attention, and orchestration", "model overlap explicitly", "do not infer GPU benefit from core count", "record resident bytes and cache hit rate"],
            "performance_claim_for_pulsarmlx": False,
        },
        "format_compatibility": {
            "colibri_fmt2": "custom per-row int4 plus f32 row scales",
            "colibri_fmt4": "custom grouped int4 plus f32 group scales",
            "pulsarmlx_q4_k_q6_k": "GGUF K-quant block layouts",
            "formal_equivalence": False,
            "decoder_oracle_reuse": "PROHIBITED",
            "algorithmic_lessons_only": True,
        },
        "reuse_use_case_matrix": reuse_use_case_matrix(),
        "track_dispositions": {
            "reuse": "SEPARATE_PACKAGES_REQUIRED",
            "colibri_audit": "ACTIONABLE",
            "dense_prefix": "READY_FOR_REVIEW",
            "q6_k": "PACKAGE_READY",
            "q4_k": "PACKAGE_READY",
            "downstream": "PREPARED",
        },
        "no_copy_declaration": {
            "external_source_copied": False,
            "external_runtime_dependency": False,
            "external_submodule": False,
            "independent_tests_inspired_by_public_failure_reports": True,
        },
        "routing_contract_v3_sha256": ROUTING_V3_SHA256,
        "decoded_reuse_v2_sha256": REUSE_V2_SHA256,
        "real_checkpoint_access": 0,
        "ledger": LEDGER,
    }


def reuse_amendment_value() -> dict[str, object]:
    return {
        "schema": "pulsarmlx.f017.decoded-tensor-reuse-use-case-amendment",
        "schema_version": "1.0.0",
        "contract_id": "f017-decoded-tensor-reuse-v2-use-case-amendment-v1",
        "status": "PREPARED_NOT_AUTHORIZED",
        "predecessor_contract_sha256": REUSE_V2_SHA256,
        "external_audit_pin": {"repository": COLIBRI_REPOSITORY, "commit": COLIBRI_COMMIT, "tree": COLIBRI_TREE},
        "overall_disposition": "SEPARATE_PACKAGES_REQUIRED",
        "use_case_matrix": reuse_use_case_matrix(),
        "additional_threats": [
            "in-place normalization or transpose", "shared mutable cache", "cross-fixture state leakage",
            "same decoded bytes paired with wrong tensor descriptor", "candidate output influencing fixture selection",
        ],
        "required_invariants": [
            "decoder correctness is established independently before decoded reuse",
            "candidate import/decode behavior is never inferred from oracle reuse",
            "source and destination have separate hashes and lifecycles",
            "source bytes outlive all consumers and are rehashed after use",
            "no writable alias or unclassified fallback is permitted",
        ],
        "real_checkpoint_access": 0,
        "ledger": LEDGER,
        "authorization_issued": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--print", choices=("audit", "risk", "adoption", "reuse"), default="audit")
    args = parser.parse_args()
    if args.source_root is not None:
        verify_colibri_source(args.source_root)
    values = {"audit": audit_value, "risk": risk_register_value, "adoption": adoption_candidates_value, "reuse": reuse_amendment_value}
    print(canonical_json_bytes(values[args.print]()).decode(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
