#!/usr/bin/env python3
"""Checkpoint-free production evaluation of F017 complete-layer v2.

The evaluator has no checkpoint, shard, decoder, or model-execution surface.
It reconstructs the two historically banked routed byte objects only from the
already-authorized expert outputs and immutable routing-weight evidence, and
requires their frozen SHA-256 identities before applying complete-layer v2.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import stat
import struct
import subprocess
import sys
import tempfile
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.research import f017_complete_layer_aggregate_acceptance_v2 as v2
from scripts.research import f017_routing_contract_v31 as v31
from scripts.research import f017_weighted_moe_aggregate_theorem as routed_theorem


STARTING_HEAD = "d4ce39f4d47503195e3d47cddc0280890cc0bda3"
CONSUMER_ID = "F017-COMPLETE-LAYER-AGGREGATE-V2-ANALYTICAL-1"
DIMENSION = 6144
SELECTED_IDS = (250, 10, 237, 73, 62, 177, 218, 28)

V2_CONTRACT = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-complete-layer-aggregate-acceptance-v2.json"
V2_CONTRACT_SHA = "13896ac22c03d7354c25f4d182de828b44df0d7239dd7e269175f69d597209fe"
V2_IMPLEMENTATION = ROOT / "scripts/research/f017_complete_layer_aggregate_acceptance_v2.py"
V2_IMPLEMENTATION_SHA = "1e5de4c450ff60a8c5eca0042fdf3d6b328b46c958cc2c72b279d48c1d86bd57"
SHARED_REUSE = ROOT / "docs/architecture/reviews/evidence/f017-canonical-shared-expert-output-private-reuse-authorization-v1.json"
SHARED_REUSE_SHA = "19a6890a1bd63f4832e76e3b9cba389eb33eb3e6366ab2cd0bb0aefa8a93f151"
ROUTED_REUSE = ROOT / "docs/architecture/reviews/evidence/f017-canonical-expert-output-private-reuse-authorization-v1.json"
ROUTED_REUSE_SHA = "b370d3c3dd938eeadd18f34fabab89077319b979b994b97ffa33afddf2bffa28"
ROUTED_EVALUATION = ROOT / "docs/architecture/reviews/evidence/f017-weighted-moe-aggregate-safety-evaluation-v1.json"
ROUTED_EVALUATION_SHA = "672884e0c217600f9104d7a4d6fdd27a87e0a73fac686044de86461af98781e7"
ROUTE_EVIDENCE = ROOT / "docs/architecture/reviews/evidence/f017-dprefix-route-ambiguity-v31-evaluation-v1.json"
ROUTE_EVIDENCE_SHA = "a4f3e1afe84be2cade1ed6c1728b2f82cd0ff2d22e8a964779f3216baf124eb4"
WEIGHT_EVIDENCE = ROOT / "docs/architecture/reviews/evidence/f017-selected-routing-weight-qualification-v1.json"
WEIGHT_EVIDENCE_SHA = "834eefb7e0f127e12768285097dc3601135c1c1ff8ef0e871d65f59af1bc6b1f"
LEDGER = ROOT / "docs/architecture/reviews/evidence/f017-real-payload-access-ledger-v1.json"
LEDGER_SHA = "c68be19f2840dea612e8b20ff2933751800555c80ae66fcfbbff02086bbe18c0"

RESIDUAL_SHA = "9c3a8821deda6a9983b49544d5726efad97b2e560f55a7eb0f182aaa128ceb11"
SHARED_SHA = "01dbd9ac75091fcd452ac9bb1bc2479ccdebc0bc7ac46d79285ff45d70e5928d"
ROUTED_NOMINAL_SHA = "5a30a81b6e10b126ac22a3be991e5f5c6486372068888f699625b684eb85fc70"
ROUTED_INTERSECTION_SHA = "adbbbef090c4d10acc80d0216cc82b5a8dbe299dad4baad1a0d957f661762a50"


class EvaluationError(ValueError):
    """Fail-closed complete-layer evaluation error."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise EvaluationError(message)


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EvaluationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(), object_pairs_hook=reject_duplicates)
    require(isinstance(value, dict), f"JSON root must be object: {path.name}")
    return value


def _regular_immutable(path: Path, expected_size: int, expected_sha: str, label: str) -> bytes:
    require(path.exists() and not path.is_symlink(), f"{label}: missing or symlink")
    metadata = path.stat()
    require(stat.S_ISREG(metadata.st_mode), f"{label}: not regular")
    require(metadata.st_size == expected_size, f"{label}: size")
    require(not metadata.st_mode & 0o222, f"{label}: writable")
    require(metadata.st_nlink == 1, f"{label}: hard-link alias")
    raw = path.read_bytes()
    require(sha256_bytes(raw) == expected_sha, f"{label}: identity")
    return raw


def _safe_relative(value: str, prefix: str) -> PurePosixPath:
    relative = PurePosixPath(value)
    require(not relative.is_absolute() and ".." not in relative.parts, "unsafe symbolic path")
    require(relative.parts and relative.parts[0] == prefix, "unexpected symbolic path prefix")
    return relative


def _source_authority() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    for path, expected in (
        (V2_CONTRACT, V2_CONTRACT_SHA), (V2_IMPLEMENTATION, V2_IMPLEMENTATION_SHA),
        (SHARED_REUSE, SHARED_REUSE_SHA), (ROUTED_REUSE, ROUTED_REUSE_SHA),
        (ROUTED_EVALUATION, ROUTED_EVALUATION_SHA), (ROUTE_EVIDENCE, ROUTE_EVIDENCE_SHA),
        (WEIGHT_EVIDENCE, WEIGHT_EVIDENCE_SHA), (LEDGER, LEDGER_SHA),
    ):
        require(sha256_path(path) == expected, f"source identity mismatch: {path.name}")
    ledger = load_json(LEDGER)
    require(ledger.get("cumulative_tensor_payloads") == 166, "real-payload ledger is not 166")
    shared = load_json(SHARED_REUSE)
    require(shared.get("status") == "AUTHORIZED_NOT_EVALUATED", "shared reuse status")
    require(shared.get("consumer", {}).get("consumer_id") == CONSUMER_ID, "consumer identity")
    require(shared.get("complete_layer_v2", {}).get("sha256") == V2_CONTRACT_SHA, "v2 binding")
    routed = load_json(ROUTED_REUSE)
    route = load_json(ROUTE_EVIDENCE)
    weights = load_json(WEIGHT_EVIDENCE)
    routed_eval = load_json(ROUTED_EVALUATION)
    require(routed_eval.get("nominal_aggregate", {}).get("canonical_le_f64_sha256") == ROUTED_NOMINAL_SHA,
            "routed nominal historical identity")
    require(routed_eval.get("enclosures", {}).get("sound_intersection", {}).get("canonical_le_f64_interval_sha256") == ROUTED_INTERSECTION_SHA,
            "routed enclosure historical identity")
    require(routed_eval.get("qualifications", {}).get("aggregate_mathematical") == "FAIL",
            "routed v1 historical result")
    membership = route.get("evaluation", {}).get("membership", {})
    require((membership.get("evaluated"), membership.get("mathematical_pass_count"), membership.get("mathematical_fail_count")) == (1984, 1984, 0),
            "membership history")
    require(weights.get("qualification", {}).get("mathematical_pass_count") == 0, "coefficient history")
    return shared, routed, route, weights


def _load_f32_point(path: Path, expected_sha: str, label: str) -> tuple[tuple[float, ...], str]:
    raw = _regular_immutable(path, DIMENSION * 4, expected_sha, label)
    values = struct.unpack(f"<{DIMENSION}f", raw)
    require(all(math.isfinite(value) for value in values), f"{label}: non-finite")
    return values, expected_sha


def _load_shared(shared_root: Path, authorization: Mapping[str, Any]) -> tuple[tuple[float, ...], str]:
    item = authorization.get("artifact", {})
    relative = _safe_relative(str(item.get("symbolic_name")), "outputs")
    return _load_f32_point(shared_root / "package" / Path(*relative.parts), SHARED_SHA, "shared output")


def _load_routed_outputs(routed_root: Path, authorization: Mapping[str, Any]) -> tuple[dict[int, tuple[float, ...]], dict[str, str]]:
    records = authorization.get("package", {}).get("artifacts", [])
    require(isinstance(records, list) and len(records) == 8, "routed output census")
    require(tuple(item.get("expert_id") for item in records) == SELECTED_IDS, "routed expert ordering")
    output: dict[int, tuple[float, ...]] = {}
    identities: dict[str, str] = {}
    for item in records:
        expert_id = int(item["expert_id"])
        relative = _safe_relative(str(item["symbolic_name"]), "expert_outputs")
        expected = str(item["expected_sha256"])
        values, identity = _load_f32_point(
            routed_root / "recovery-package" / Path(*relative.parts), expected, f"expert {expert_id} output"
        )
        output[expert_id] = values
        identities[str(expert_id)] = identity
    return output, identities


def _routing_inputs(route: Mapping[str, Any], weights: Mapping[str, Any]) -> tuple[dict[int, float], dict[int, v31.Interval], v31.Interval]:
    evaluation = route.get("evaluation", {})
    require(tuple(evaluation.get("exact_route", {}).get("selected_top8", [])) == SELECTED_IDS, "selected set")
    records = evaluation.get("selected_weights", {}).get("by_expert_id", {})
    require(set(records) == {str(item) for item in SELECTED_IDS}, "selected weight census")
    nominal: dict[int, float] = {}
    intervals: dict[int, v31.Interval] = {}
    for expert_id in SELECTED_IDS:
        record = records[str(expert_id)]
        require(record.get("expert_id") == expert_id and record.get("exact_weight_contained") is True,
                "atomic ID/weight semantics")
        nominal[expert_id] = float(record["exact_routing_weight"])
        interval = record["routing_weight_interval"]
        intervals[expert_id] = v31.Interval(float(interval["lower"]), float(interval["upper"]))
    joint_record = weights.get("qualification", {}).get("joint_weight_sum_interval", {})
    require(joint_record == {"lower": 2.4999999999999996, "upper": 2.5000000000000004},
            "joint normalization identity")
    return nominal, intervals, v31.Interval(float(joint_record["lower"]), float(joint_record["upper"]))


def _routed_bytes(route: Mapping[str, Any], weights: Mapping[str, Any], outputs: Mapping[int, Sequence[float]]) -> tuple[tuple[float, ...], tuple[v31.Interval, ...], bytes, bytes]:
    nominal_weights, intervals, joint = _routing_inputs(route, weights)
    result = routed_theorem.qualify_f017_production_aggregate(
        SELECTED_IDS, nominal_weights, intervals, outputs,
        selected_set_invariant=True, joint_weight_sum_interval=joint,
    )
    nominal = tuple(item.nominal for item in result.component_bounds)
    enclosure = tuple(item.enclosure for item in result.component_bounds)
    nominal_raw = struct.pack(f"<{DIMENSION}d", *nominal)
    interval_raw = b"".join(struct.pack("<dd", item.lower, item.upper) for item in enclosure)
    require(sha256_bytes(nominal_raw) == ROUTED_NOMINAL_SHA, "routed nominal rematerialization")
    require(sha256_bytes(interval_raw) == ROUTED_INTERSECTION_SHA, "routed enclosure rematerialization")
    return nominal, enclosure, nominal_raw, interval_raw


def _summary_once(residual_path: Path, shared_root: Path, routed_root: Path) -> tuple[dict[str, Any], bytes, bytes]:
    shared_auth, routed_auth, route, weights = _source_authority()
    residual, residual_id = _load_f32_point(residual_path, RESIDUAL_SHA, "DPREFIX-EXACT-1 residual")
    shared, shared_id = _load_shared(shared_root, shared_auth)
    routed_outputs, routed_ids = _load_routed_outputs(routed_root, routed_auth)
    before = {"residual": residual_id, "shared": shared_id, "routed_expert_outputs": routed_ids}
    routed_nominal, routed_enclosure, nominal_routed_raw, routed_interval_raw = _routed_bytes(route, weights, routed_outputs)
    result = v2.qualify_f017_production_complete_layer(residual, shared, routed_nominal, routed_enclosure)
    canonical_raw = struct.pack(f"<{DIMENSION}f", *result.nominal)
    perturbation_raw = b"".join(struct.pack("<dd", item.lower, item.upper) for item in result.perturbations)
    require(all(math.isfinite(value) for value in result.nominal), "complete-layer non-finite")
    after_residual, _ = _load_f32_point(residual_path, RESIDUAL_SHA, "DPREFIX-EXACT-1 residual after")
    after_shared, _ = _load_shared(shared_root, shared_auth)
    after_outputs, after_ids = _load_routed_outputs(routed_root, routed_auth)
    require(residual == after_residual and shared == after_shared and routed_outputs == after_outputs,
            "private authority mutated")
    after = {"residual": RESIDUAL_SHA, "shared": SHARED_SHA, "routed_expert_outputs": after_ids}
    max_pass = result.max_absolute_bound <= v2.MAX_ABSOLUTE_BUDGET
    rmse_pass = result.rmse_bound <= v2.RMSE_BUDGET
    cosine_pass = result.cosine_lower_bound is not None and result.cosine_lower_bound >= v2.COSINE_MINIMUM
    qualified = max_pass and rmse_pass and cosine_pass
    require(result.mathematically_qualified == qualified, "qualification reconciliation")
    expectation = (
        "CONSISTENT: routed-scale max-absolute/RMSE preserved and residual-added norm materially improves cosine"
        if result.cosine_lower_bound is not None and result.cosine_lower_bound > 0.9990571244636769
        else "MATERIAL_DEVIATION_REQUIRES_REVIEW"
    )
    nominal_l1 = math.fsum(abs(value) for value in result.nominal)
    nominal_l2 = math.sqrt(math.fsum(value * value for value in result.nominal))
    return ({
        "schema": "pulsarmlx.f017.complete-layer-aggregate-v2-evaluation",
        "schema_version": "1.0.0",
        "starting_authoritative_head": STARTING_HEAD,
        "consumer_id": CONSUMER_ID,
        "authority": {
            "evaluation_implementation_sha256": sha256_path(Path(__file__).resolve()),
            "complete_layer_v2_contract_sha256": V2_CONTRACT_SHA,
            "complete_layer_v2_implementation_sha256": V2_IMPLEMENTATION_SHA,
            "shared_reuse_authorization_file_sha256": SHARED_REUSE_SHA,
            "routed_reuse_authorization_sha256": ROUTED_REUSE_SHA,
            "routed_v1_evaluation_sha256": ROUTED_EVALUATION_SHA,
            "route_evidence_sha256": ROUTE_EVIDENCE_SHA,
            "weight_qualification_evidence_sha256": WEIGHT_EVIDENCE_SHA,
        },
        "private_inputs": {
            "before_sha256": before,
            "after_sha256": after,
            "all_expected_before_after_equal": before == after,
            "read_only_single_link_regular_non_symlink": True,
        },
        "routed_reuse": {
            "nominal_canonical_le_f64_sha256": sha256_bytes(nominal_routed_raw),
            "sound_intersection_canonical_le_f64_interval_sha256": sha256_bytes(routed_interval_raw),
            "historical_identities_matched": True,
            "routing_propagation_recomputed": False,
            "byte_exact_rematerialization_from_banked_weights_intervals_and_outputs": True,
        },
        "canonical_complete_layer": {
            "formula": "L0=f32(f64(R)+(M0+f64(S0)))",
            "canonical_le_f32_sha256": sha256_bytes(canonical_raw),
            "dtype": "f32", "shape": [DIMENSION], "byte_length": len(canonical_raw),
            "finite_count": sum(math.isfinite(value) for value in result.nominal),
            "maximum_absolute_value": max(abs(value) for value in result.nominal),
            "l1_norm": nominal_l1, "l2_norm": nominal_l2,
        },
        "perturbation": {
            "final_f32_componentwise_interval_sha256": sha256_bytes(perturbation_raw),
            "component_count": DIMENSION,
            "maximum_absolute_bound": result.max_absolute_bound,
            "rmse_bound": result.rmse_bound,
            "l2_epsilon": result.perturbation_l2_bound,
            "nominal_l2_A_lower": result.nominal_l2_lower,
            "epsilon_over_A_lower": v31.round_up(result.perturbation_l2_bound / result.nominal_l2_lower),
            "shared_uncertainty_mode": result.shared_uncertainty_mode,
        },
        "acceptance": {
            "max_absolute": {"threshold": v2.MAX_ABSOLUTE_BUDGET, "bound": result.max_absolute_bound,
                             "factor": result.max_absolute_factor, "status": "PASS" if max_pass else "FAIL"},
            "rmse": {"threshold": v2.RMSE_BUDGET, "bound": result.rmse_bound,
                     "factor": result.rmse_factor, "status": "PASS" if rmse_pass else "FAIL"},
            "cosine": {"minimum": v2.COSINE_MINIMUM, "lower_bound": result.cosine_lower_bound,
                       "factor": result.cosine_factor, "status": "PASS" if cosine_pass else "FAIL"},
            "global_safety_factor": result.aggregate_safety_factor,
            "mathematical_qualification": "PASS" if qualified else "FAIL",
            "engineering_h2": "PASS" if result.engineering_h2 else "FAIL",
        },
        "preregistered_expectation": expectation,
        "disposition": {
            "membership": "PASS_UNCHANGED_1984_OF_1984",
            "coefficient_rule": "FAIL_UNCHANGED_0_OF_8",
            "routed_aggregate_v1": "FAIL_UNCHANGED",
            "route_ambiguity": (
                "ROUTE AMBIGUITY QUALIFIED AT COMPLETE-LAYER OUTPUT"
                if qualified else "ROUTE NOT PROVEN INVARIANT"
            ),
        },
        "isolation": {
            "checkpoint_reads": 0, "shard_opens": 0, "payload_reads": 0,
            "route_propagation_runs": 0, "candidate_or_model_dispatches": 0,
            "real_payload_ledger_before": 166, "real_payload_ledger_after": 166,
            "ledger_mutated": False,
        },
        "historical_immutability": {
            "REAL_1": "REJECTED_UNCHANGED", "REAL_2": "REJECTED_UNCHANGED",
            "REAL_3": "REJECTED_UNCHANGED", "DPREFIX_EXACT_1": "CANONICAL_UNCHANGED",
            "membership": "1984_OF_1984_PASS_UNCHANGED",
            "coefficient_qualification": "0_OF_8_FAIL_UNCHANGED",
            "routed_aggregate_v1": "FAIL_UNCHANGED", "real_payload_ledger": 166,
        },
    }, canonical_raw, perturbation_raw)


def _write_immutable(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    require(not path.exists(), f"refusing to replace private authority: {path.name}")
    temporary = path.with_name(path.name + ".tmp")
    require(not temporary.exists(), "stale private temporary")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=True) as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o400)
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except BaseException:
        if temporary.exists():
            temporary.unlink()
        raise


def _one_command(args: argparse.Namespace, output: Path) -> list[str]:
    return [sys.executable, str(Path(__file__).resolve()), "--evaluate-once",
            "--residual", str(args.residual), "--shared-root", str(args.shared_root),
            "--routed-root", str(args.routed_root), "--run-output", str(output)]


def run_three(args: argparse.Namespace) -> dict[str, Any]:
    runs: list[bytes] = []
    canonical_payloads: list[bytes] = []
    perturbation_payloads: list[bytes] = []
    with tempfile.TemporaryDirectory(prefix="f017-complete-layer-v2-") as temporary:
        base = Path(temporary)
        for ordinal in range(3):
            output = base / f"run-{ordinal + 1}"
            completed = subprocess.run(_one_command(args, output), cwd=ROOT, check=True,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            runs.append(completed.stdout)
            canonical_payloads.append((output / "complete-layer.f32le").read_bytes())
            perturbation_payloads.append((output / "perturbation-intervals.f64le").read_bytes())
    require(len(set(runs)) == 1, "fresh-process public results differ")
    require(len({sha256_bytes(item) for item in canonical_payloads}) == 1, "fresh-process canonical bytes differ")
    require(len({sha256_bytes(item) for item in perturbation_payloads}) == 1, "fresh-process enclosure bytes differ")
    result = json.loads(runs[0], object_pairs_hook=reject_duplicates)
    qualified = result["acceptance"]["mathematical_qualification"] == "PASS"
    authority: dict[str, Any] | None = None
    if qualified:
        private_root = Path(args.output_private_root)
        canonical_path = private_root / "outputs/complete_layer3_canonical.f32le"
        interval_path = private_root / "bounds/final_f32_perturbation_intervals.f64le"
        manifest = {
            "schema": "pulsarmlx.f017.complete-layer-v2-private-authority",
            "schema_version": "1.0.0",
            "artifacts": [
                {"symbolic_path": "outputs/complete_layer3_canonical.f32le", "dtype": "f32",
                 "shape": [DIMENSION], "byte_length": len(canonical_payloads[0]),
                 "sha256": sha256_bytes(canonical_payloads[0]), "read_only": True, "immutable": True},
                {"symbolic_path": "bounds/final_f32_perturbation_intervals.f64le", "dtype": "interval<f64>",
                 "shape": [DIMENSION, 2], "byte_length": len(perturbation_payloads[0]),
                 "sha256": sha256_bytes(perturbation_payloads[0]), "read_only": True, "immutable": True},
            ],
            "classification": "PERSISTED_AUTHORITY_PRODUCED_BY_EXACT_CLASS_FIXED_ORDER_ANALYTICAL_COMPOSITION",
            "formula_lineage": "DPREFIX-EXACT-1 + routed nominal 5a30a81b... + shared 01dbd9ac... under complete-layer v2",
        }
        manifest_raw = canonical_bytes(manifest)
        manifest_path = private_root / "manifest.json"
        if private_root.exists():
            _regular_immutable(canonical_path, len(canonical_payloads[0]), sha256_bytes(canonical_payloads[0]),
                               "existing canonical authority")
            _regular_immutable(interval_path, len(perturbation_payloads[0]), sha256_bytes(perturbation_payloads[0]),
                               "existing perturbation authority")
            _regular_immutable(manifest_path, len(manifest_raw), sha256_bytes(manifest_raw),
                               "existing private manifest")
        else:
            _write_immutable(canonical_path, canonical_payloads[0])
            _write_immutable(interval_path, perturbation_payloads[0])
            _write_immutable(manifest_path, manifest_raw)
        authority = {
            "classification": manifest["classification"],
            "canonical_object_sha256": sha256_bytes(canonical_payloads[0]),
            "perturbation_object_sha256": sha256_bytes(perturbation_payloads[0]),
            "private_manifest_canonical_sha256": sha256_bytes(manifest_raw),
            "immutable_read_only_single_link": True,
        }
    result["deterministic_replay"] = {
        "fresh_process_count": 3, "byte_identical_public_result": True,
        "public_result_sha256": sha256_bytes(runs[0]),
        "canonical_sha256_by_run": [sha256_bytes(item) for item in canonical_payloads],
        "perturbation_sha256_by_run": [sha256_bytes(item) for item in perturbation_payloads],
    }
    result["canonical_layer3_authority"] = authority
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--evaluate-once", action="store_true")
    mode.add_argument("--run-three", action="store_true")
    parser.add_argument("--residual", type=Path, required=True)
    parser.add_argument("--shared-root", type=Path, required=True)
    parser.add_argument("--routed-root", type=Path, required=True)
    parser.add_argument("--run-output", type=Path)
    parser.add_argument("--output-private-root", type=Path)
    args = parser.parse_args()
    if args.evaluate_once:
        require(args.run_output is not None and args.output_private_root is None, "single-run arguments")
        result, canonical_raw, perturbation_raw = _summary_once(args.residual, args.shared_root, args.routed_root)
        args.run_output.mkdir(parents=True, exist_ok=False)
        (args.run_output / "complete-layer.f32le").write_bytes(canonical_raw)
        (args.run_output / "perturbation-intervals.f64le").write_bytes(perturbation_raw)
    else:
        require(args.output_private_root is not None and args.run_output is None, "three-run arguments")
        result = run_three(args)
    sys.stdout.buffer.write(canonical_bytes(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
