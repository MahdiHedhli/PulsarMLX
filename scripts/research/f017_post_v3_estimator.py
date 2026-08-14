#!/usr/bin/env python3
"""Checkpoint-free planning estimator for the post-v3 M1-F0 fixture families.

This module never maps a fixture through checkpoint router rows.  It instead
uses a deliberately bounded planning model built from already banked router
analytics.  The three retained-ratio scenarios make the missing arbitrary-row
pair antecedents explicit: ``conservative`` uses the rigorous independent-row
envelope, ``central`` uses the median tightening observed across all 1,984
retained membership pairs, and ``optimistic`` applies the strongest observed
tightening to every pair.  Only the optimistic upper confidence bound may be
used to declare a family not worth a bounded real ladder.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Callable

import numpy as np


V3_CLARIFIED_SHA256 = "c5662a611abc000703606d799a7214ee27e39c556bc6595f217c86498e944a85"
FROZEN_LADDER_SHA256 = "59c55a26d12ff9e0fdbe488608c4cb7ffb1a2082d322dec85ee5ef37719c3ed2"
FROZEN_LADDER_GENERATOR_SHA256 = "0097e78a55cf5d8911a2715cebf7e024606a69713d08d7f3bc07ac04864d60f0"
RAW_RECOVERY_SHA256 = "f9422287cb98322d1412a6dd2397bb0f4a0d6538778aa587dddff7c5154acf2a"
ANALYTICAL_RECOVERY_SHA256 = "1496b8a3ca26448145acbd107387aadbc11322fd93b71fcc5abd659d6e8e7686"
TOP_K = 8
EXPERT_COUNT = 256
ENGINEERING_HEADROOM = 2.0
PLANNING_P_ANY_THRESHOLD = 0.90
OFFICIAL_SAMPLE_COUNT = 1_000_000
OFFICIAL_RANDOM_SEED = 1_701_900_031
OFFICIAL_CORRELATED_SEED = 1_701_900_032
QUANTILES = (0.01, 0.10, 0.50, 0.90, 0.95, 0.99, 0.999)


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_json(path: Path) -> dict:
    def pairs(items: list[tuple[str, object]]) -> dict:
        result: dict[str, object] = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate key {key!r} in {path}")
            result[key] = value
        return result

    value = json.loads(path.read_text(), object_pairs_hook=pairs)
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object in {path}")
    return value


def _find_list(value: object, keys: tuple[str, ...]) -> list[float]:
    if isinstance(value, dict):
        for key in keys:
            candidate = value.get(key)
            if isinstance(candidate, list):
                return [float(item) for item in candidate]
        for candidate in value.values():
            try:
                return _find_list(candidate, keys)
            except KeyError:
                pass
    elif isinstance(value, list):
        for candidate in value:
            try:
                return _find_list(candidate, keys)
            except KeyError:
                pass
    raise KeyError(keys)


def _require_sha(path: Path, expected: str) -> None:
    actual = sha256_path(path)
    if actual != expected:
        raise ValueError(f"identity mismatch for {path}: {actual} != {expected}")


def retained_inputs(root: Path) -> dict[str, np.ndarray | float]:
    clarified = root / "specs/017-rust-native-inference-runtime/contracts/f017-m1f-routing-contract-v3-clarified.json"
    ladder = root / "docs/architecture/reviews/evidence/f017-m1-f0-input-ladder-v1.json"
    generator = root / "scripts/research/generate_f017_m1f0_ladder_input.py"
    raw = root / "docs/architecture/reviews/evidence/f017-v2-antecedent-recovery-result-v1.json"
    analytical = root / "docs/architecture/reviews/evidence/f017-m1-f0-router-analytical-recovery-v1.json"
    for path, expected in (
        (clarified, V3_CLARIFIED_SHA256),
        (ladder, FROZEN_LADDER_SHA256),
        (generator, FROZEN_LADDER_GENERATOR_SHA256),
        (raw, RAW_RECOVERY_SHA256),
        (analytical, ANALYTICAL_RECOVERY_SHA256),
    ):
        _require_sha(path, expected)

    raw_value = parse_json(raw)
    analytical_value = parse_json(analytical)
    probabilities = np.asarray(raw_value["antecedent_retention"]["router_probabilities"], dtype=np.float64)
    bias = np.asarray(raw_value["antecedent_retention"]["router_bias"], dtype=np.float64)
    logits = np.asarray(raw_value["antecedent_retention"]["router_logits"], dtype=np.float64)
    independent = np.asarray(
        _find_list(
            analytical_value,
            ("router_score_abs_error_bounds", "post_bias_score_error_bounds", "score_error_bounds"),
        ),
        dtype=np.float64,
    )
    if any(values.shape != (EXPERT_COUNT,) for values in (probabilities, bias, logits, independent)):
        raise ValueError("retained router vectors must each contain 256 values")
    pair_records = raw_value["antecedent_retention"]["pairwise_surface"]["selected_unselected_pair_bounds"]
    if len(pair_records) != TOP_K * (EXPERT_COUNT - TOP_K):
        raise ValueError("retained membership surface is incomplete")
    ratios = np.asarray(
        [
            float(item["B_pair"])
            / (independent[int(item["selected"])] + independent[int(item["challenger"])])
            for item in pair_records
        ],
        dtype=np.float64,
    )
    if not np.isfinite(ratios).all() or np.any(ratios <= 0.0) or np.any(ratios > 1.0):
        raise ValueError("retained pairwise tightening ratio outside (0,1]")
    return {
        "probabilities": probabilities,
        "bias": bias,
        "logits": logits,
        "independent_bounds": independent,
        "ratio_min": float(np.min(ratios)),
        "ratio_median": float(np.median(ratios)),
        "ratio_max": float(np.max(ratios)),
    }


def wilson(successes: int, count: int) -> tuple[float, float]:
    if count <= 0 or not 0 <= successes <= count:
        raise ValueError("invalid binomial counts")
    p = successes / count
    z = 1.959963984540054
    denominator = 1.0 + z * z / count
    center = (p + z * z / (2.0 * count)) / denominator
    half = z * math.sqrt(p * (1.0 - p) / count + z * z / (4.0 * count * count)) / denominator
    low = 0.0 if successes == 0 else max(0.0, center - half)
    high = 1.0 if successes == count else min(1.0, center + half)
    return low, high


def p_any(probability: float, ladder_size: int = 8) -> float:
    return 1.0 - (1.0 - probability) ** ladder_size


def _surface_safety(scores: np.ndarray, bounds: np.ndarray) -> np.ndarray:
    """Minimum independent-row safety factor over all selected/unselected pairs."""
    order = np.argsort(-scores, axis=1, kind="stable")
    selected = order[:, :TOP_K]
    unselected = order[:, TOP_K:]
    selected_scores = np.take_along_axis(scores, selected, axis=1)
    unselected_scores = np.take_along_axis(scores, unselected, axis=1)
    selected_bounds = bounds[selected]
    unselected_bounds = bounds[unselected]
    margin = selected_scores[:, :, None] - unselected_scores[:, None, :]
    envelope = selected_bounds[:, :, None] + unselected_bounds[:, None, :]
    if np.any(margin < 0.0) or np.any(envelope <= 0.0):
        raise AssertionError("invalid selected/unselected surface")
    return np.min(margin / envelope, axis=(1, 2))


def _random_probability_source(
    retained: dict[str, np.ndarray | float], rng: np.random.Generator, count: int
) -> np.ndarray:
    probability = np.asarray(retained["probabilities"], dtype=np.float64)
    return probability[rng.integers(0, EXPERT_COUNT, size=(count, EXPERT_COUNT))]


def _correlated_probability_source(
    retained: dict[str, np.ndarray | float], rng: np.random.Generator, count: int
) -> np.ndarray:
    """Fixed low-rank planning surrogate; it is not a checkpoint route model."""
    banked_logits = np.asarray(retained["logits"], dtype=np.float64)
    latent_width = 16
    loading_rng = np.random.Generator(np.random.PCG64(1_701_900_033))
    loadings = loading_rng.normal(0.0, 1.0, size=(EXPERT_COUNT, latent_width))
    loadings /= np.linalg.norm(loadings, axis=1, keepdims=True)
    latent = rng.normal(0.0, 1.0, size=(count, latent_width))
    standardized = latent @ loadings.T
    logits = float(np.mean(banked_logits)) + float(np.std(banked_logits, ddof=0)) * standardized
    return 1.0 / (1.0 + np.exp(-logits))


def _scenario_summary(base_safety: np.ndarray, multiplier: float) -> dict[str, object]:
    safety = base_safety / multiplier
    mathematical = int(np.count_nonzero(safety > 1.0))
    engineering = int(np.count_nonzero(safety >= ENGINEERING_HEADROOM))
    count = safety.size
    math_ci = wilson(mathematical, count)
    engineering_ci = wilson(engineering, count)
    return {
        "pair_bound_multiplier": multiplier,
        "mathematical": {
            "qualifiers": mathematical,
            "rate": mathematical / count,
            "wilson_95": list(math_ci),
            "p_any_8": p_any(mathematical / count),
            "p_any_8_wilson_95": [p_any(math_ci[0]), p_any(math_ci[1])],
        },
        "engineering_H2": {
            "qualifiers": engineering,
            "rate": engineering / count,
            "wilson_95": list(engineering_ci),
            "expected_qualifiers_in_8": 8.0 * engineering / count,
            "p_any_8": p_any(engineering / count),
            "p_any_8_wilson_95": [p_any(engineering_ci[0]), p_any(engineering_ci[1])],
        },
        "safety_factor_quantiles": {
            str(q): float(np.quantile(safety, q)) for q in QUANTILES
        },
        "maximum_safety_factor": float(np.max(safety)),
    }


def simulate(
    root: Path,
    *,
    family: str,
    sample_count: int = OFFICIAL_SAMPLE_COUNT,
    seed: int | None = None,
) -> dict[str, object]:
    retained = retained_inputs(root)
    if family == "frozen_random_normal":
        probability_source: Callable[[dict[str, np.ndarray | float], np.random.Generator, int], np.ndarray] = _random_probability_source
        default_seed = OFFICIAL_RANDOM_SEED
        family_model = "exchangeable bootstrap of banked probabilities plus fixed banked bias"
    elif family == "correlated_low_rank":
        probability_source = _correlated_probability_source
        default_seed = OFFICIAL_CORRELATED_SEED
        family_model = "fixed 16-factor checkpoint-independent logit surrogate calibrated only to banked marginal mean/std plus fixed bias"
    else:
        raise ValueError("unsupported family")
    official_seed = default_seed if seed is None else seed
    rng = np.random.Generator(np.random.PCG64(official_seed))
    base_safety = np.empty(sample_count, dtype=np.float64)
    bounds = np.asarray(retained["independent_bounds"], dtype=np.float64)
    bias = np.asarray(retained["bias"], dtype=np.float64)
    chunk = 512
    for start in range(0, sample_count, chunk):
        size = min(chunk, sample_count - start)
        probabilities = probability_source(retained, rng, size)
        base_safety[start : start + size] = _surface_safety(probabilities + bias, bounds)

    ratios = {
        "conservative_independent_envelope": 1.0,
        "central_retained_ratio_median": float(retained["ratio_median"]),
        "optimistic_strongest_observed_tightening": float(retained["ratio_min"]),
    }
    scenarios = {
        name: _scenario_summary(base_safety, multiplier)
        for name, multiplier in ratios.items()
    }
    conservative_lower = scenarios["conservative_independent_envelope"]["engineering_H2"]["p_any_8_wilson_95"][0]
    optimistic_upper = scenarios["optimistic_strongest_observed_tightening"]["engineering_H2"]["p_any_8_wilson_95"][1]
    if conservative_lower >= PLANNING_P_ANY_THRESHOLD:
        disposition = "EXISTING_FROZEN_LADDER_VIABLE" if family == "frozen_random_normal" else "CORRELATED_FAMILY_PLANNING_VIABLE"
    elif optimistic_upper < PLANNING_P_ANY_THRESHOLD:
        disposition = "EXISTING_FROZEN_LADDER_NOT_VIABLE" if family == "frozen_random_normal" else "CORRELATED_FAMILY_NOT_VIABLE"
    else:
        disposition = "ESTIMATOR_INCONCLUSIVE"
    return {
        "schema": "pulsarmlx.f017.post-v3-membership-estimate",
        "schema_version": "1.0.0",
        "planning_only": True,
        "checkpoint_access": 0,
        "real_payload_ledger": 57,
        "family": family,
        "family_model": family_model,
        "sample_count": sample_count,
        "prng": "NumPy PCG64",
        "seed": official_seed,
        "semantic_target": "exact selected membership with H=2; rank order excluded",
        "complete_semantic_set_plus_weight_rate": "NOT_ESTIMABLE_CHECKPOINT_FREE_WITHOUT_CANDIDATE_OUTPUTS",
        "arbitrary_route_pairwise_antecedents": "UNAVAILABLE; retained-ratio scenarios are planning sensitivities, not qualification bounds",
        "retained_pair_ratio_summary": {
            "minimum": retained["ratio_min"],
            "median": retained["ratio_median"],
            "maximum": retained["ratio_max"],
            "count": 1984,
        },
        "scenarios": scenarios,
        "planning_decision": {
            "threshold_p_any_8": PLANNING_P_ANY_THRESHOLD,
            "threshold_frozen_before_simulation": True,
            "cost_basis": "naive eight-fixture execution costs 96 tensor payload reads; decoded-tensor reuse requires separate reviewed authorization",
            "viable_rule": "conservative H2 Wilson-lower P(any of 8) >= 0.90",
            "not_viable_rule": "optimistic H2 Wilson-upper P(any of 8) < 0.90",
            "otherwise": "ESTIMATOR_INCONCLUSIVE",
            "disposition": disposition,
        },
        "frozen_ladder_executed": False,
        "real_access_authorized": False,
        "limitations": [
            "no checkpoint-independent map exists from frozen hidden bytes to unseen real router rows",
            "the bootstrap/surrogate preserves only explicitly documented retained marginals",
            "arbitrary-route pairwise tightening is bracketed by sensitivity scenarios rather than invented",
            "per-expert candidate weight qualification cannot be estimated without candidate output",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--family", choices=("frozen_random_normal", "correlated_low_rank"), required=True)
    parser.add_argument("--sample-count", type=int, default=OFFICIAL_SAMPLE_COUNT)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.repository_root.resolve()
    contract = args.contract if args.contract.is_absolute() else root / args.contract
    contract_value = parse_json(contract)
    if contract_value["post_observation_retuning"] != "FORBIDDEN":
        raise SystemExit("estimator contract is not frozen")
    result = simulate(root, family=args.family, sample_count=args.sample_count, seed=args.seed)
    result["estimator_contract_sha256"] = sha256_path(contract)
    result["estimator_implementation_sha256"] = sha256_path(Path(__file__))
    result["frozen_ladder_sha256"] = FROZEN_LADDER_SHA256
    result["frozen_ladder_generator_sha256"] = FROZEN_LADDER_GENERATOR_SHA256
    payload = canonical_json_bytes(result)
    if args.output:
        output = args.output if args.output.is_absolute() else root / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(payload)
    else:
        print(payload.decode(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
