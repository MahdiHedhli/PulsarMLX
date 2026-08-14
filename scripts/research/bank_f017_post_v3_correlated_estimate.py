#!/usr/bin/env python3
"""Bank the correlated-family planning estimate with frozen family identities."""

from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path


ESTIMATOR_PATH = Path(__file__).with_name("f017_post_v3_estimator.py")
SPEC = importlib.util.spec_from_file_location("f017_post_v3_estimator_banked", ESTIMATOR_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load frozen post-v3 estimator")
estimator = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(estimator)


FAMILY_SHA256 = "a5c248e52ac576e2a9a332f748bc26be0aa068688d82af743bab814d1bbbfe03"
FAMILY_GENERATOR_SHA256 = "559b351256db68d348712ec7bb0e0b26092c3e2b5c88263376e6a31e12a34ac1"
ESTIMATOR_CONTRACT_SHA256 = "5d54d1532df4c7b3ce442295f76f43f4ff6fade6c94c531d01d374aa9ae869b7"
FAMILY_PATH = Path("docs/architecture/reviews/evidence/f017-m1f0-post-v3-correlated-family-v1.json")
GENERATOR_PATH = Path("scripts/research/generate_f017_m1f0_post_v3_correlated_family.py")
ESTIMATOR_CONTRACT_PATH = Path("specs/017-rust-native-inference-runtime/contracts/f017-m1f0-v3-membership-estimator-v1.json")


def build(root: Path, planning_contract: Path, sample_count: int = 1_000_000) -> dict[str, object]:
    for path, expected in (
        (root / FAMILY_PATH, FAMILY_SHA256),
        (root / GENERATOR_PATH, FAMILY_GENERATOR_SHA256),
        (root / ESTIMATOR_CONTRACT_PATH, ESTIMATOR_CONTRACT_SHA256),
    ):
        if estimator.sha256_path(path) != expected:
            raise ValueError(f"correlated planning identity mismatch: {path}")
    contract = estimator.parse_json(planning_contract)
    if contract["post_observation_retuning"] != "FORBIDDEN":
        raise ValueError("correlated planning contract is not frozen")
    result = estimator.simulate(
        root,
        family="correlated_low_rank",
        sample_count=sample_count,
        seed=estimator.OFFICIAL_CORRELATED_SEED,
    )
    result["estimator_contract_sha256"] = ESTIMATOR_CONTRACT_SHA256
    result["correlated_planning_contract_sha256"] = estimator.sha256_path(planning_contract)
    result["correlated_family_sha256"] = FAMILY_SHA256
    result["correlated_family_generator_sha256"] = FAMILY_GENERATOR_SHA256
    result["fixture_seed_order"] = list(range(17_017_201, 17_017_209))
    result["actual_real_routes_predicted"] = False
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--planning-contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sample-count", type=int, default=1_000_000)
    args = parser.parse_args()
    root = args.repository_root.resolve()
    contract = args.planning_contract if args.planning_contract.is_absolute() else root / args.planning_contract
    output = args.output if args.output.is_absolute() else root / args.output
    payload = estimator.canonical_json_bytes(build(root, contract, args.sample_count))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
