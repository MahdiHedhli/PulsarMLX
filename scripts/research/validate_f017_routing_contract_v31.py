#!/usr/bin/env python3
"""Validate the public, pre-evaluation F017 routing v3.1 theorem freeze."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-routing-contract-v3.1-state-box.json"
EVIDENCE = ROOT / "docs/architecture/reviews/evidence/f017-routing-v3-1-theorem-freeze-v1.json"
LEDGER = ROOT / "docs/architecture/reviews/evidence/f017-real-payload-access-ledger-v1.json"
EXACT = ROOT / "docs/architecture/reviews/evidence/f017-dprefix-exact1-descriptor-v1.json"
REAL_ATTEMPTS = ROOT / "docs/architecture/reviews/evidence/f017-dense-prefix-attempt-ledger-v10.json"
REPLAY_ATTEMPTS = ROOT / "docs/architecture/reviews/evidence/f017-dense-prefix-replay-attempt-ledger-v2.json"

EXPECTED_HEAD = "a906e2b500caf3b8a67803e697728c7781c8d3a8"
EXACT_SHA = "9c3a8821deda6a9983b49544d5726efad97b2e560f55a7eb0f182aaa128ceb11"
CONSUMER = "F017-DPREFIX-ROUTE-AMBIGUITY-PROPAGATION-ANALYTICAL-1"


class FreezeValidationError(ValueError):
    pass


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise FreezeValidationError(f"duplicate key: {key}")
        value[key] = item
    return value


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(), object_pairs_hook=_reject_duplicates)
    if not isinstance(value, dict):
        raise FreezeValidationError(f"expected JSON object: {path}")
    return value


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_contract(contract: dict[str, Any], root: Path = ROOT) -> None:
    if contract.get("schema") != "pulsarmlx.f017.routing-state-box-contract" or contract.get("schema_version") != "3.1.0":
        raise FreezeValidationError("routing v3.1 contract identity mismatch")
    if contract.get("status") != "FROZEN_BEFORE_REAL_AMBIGUITY_EVALUATION":
        raise FreezeValidationError("contract is not a pre-evaluation freeze")
    if contract.get("analytical_consumer_id") != CONSUMER:
        raise FreezeValidationError("analytical consumer mismatch")
    semantics = contract.get("routing_semantics", {})
    if semantics.get("router_matrix_shape") != [256, 6144] or semantics.get("top_k") != 8:
        raise FreezeValidationError("router shape/top-k semantics mismatch")
    if semantics.get("selection_score") != "score_i=p_i+correction_bias_i":
        raise FreezeValidationError("GLM score semantics mismatch")
    if semantics.get("selected_weight") != "q_i=2.5*p_i/max(sum_{k in T}(p_k),2^-14)":
        raise FreezeValidationError("GLM weight semantics mismatch")
    if semantics.get("ordered_top8_requirement") != "diagnostic only; selected-set membership is load-bearing":
        raise FreezeValidationError("ordered top-8 was reintroduced as semantic authority")
    score = contract.get("score_theorem", {})
    if score.get("membership_condition") != "D_ij.lower > 0 for every selected i and unselected j" or score.get("required_real_pair_count") != 1984:
        raise FreezeValidationError("membership theorem mismatch")
    if score.get("real_evaluation_in_this_freeze") is not False:
        raise FreezeValidationError("real ambiguity evaluation leaked into theorem freeze")
    safety = contract.get("safety_factor", {})
    if safety.get("mathematical_threshold") != 1.0 or safety.get("engineering_threshold") != 2.0:
        raise FreezeValidationError("safety thresholds changed")
    if safety.get("engineering_is_mathematical_truth") is not False:
        raise FreezeValidationError("engineering H=2 conflated with mathematical truth")
    weights = contract.get("selected_weight_theorem", {})
    if weights.get("precondition") != "selected-set invariance independently proven" or weights.get("key") != "expert_id":
        raise FreezeValidationError("selected-weight theorem lacks fixed-set/ID semantics")
    rounding = contract.get("outward_rounding", {})
    if "nextafter" not in str(rounding.get("mechanism")) or rounding.get("missing_guard") != "fail closed":
        raise FreezeValidationError("outward-rounding doctrine mismatch")
    if contract.get("private_values_loaded") is not False or contract.get("real_ambiguity_evaluated") is not False:
        raise FreezeValidationError("private or real evaluation occurred")
    if contract.get("checkpoint_reads") != 0 or contract.get("shard_opens") != 0 or contract.get("real_payload_ledger") != 139:
        raise FreezeValidationError("isolation or ledger mismatch")
    sources = contract.get("semantic_sources")
    if not isinstance(sources, list) or len(sources) != 4:
        raise FreezeValidationError("semantic source surface mismatch")
    for item in sources:
        path = Path(str(item.get("path", "")))
        if path.is_absolute() or ".." in path.parts:
            raise FreezeValidationError("unsafe semantic source path")
        if sha256_path(root / path) != item.get("sha256"):
            raise FreezeValidationError(f"semantic source identity mismatch: {path}")
    raw = json.dumps(contract, sort_keys=True)
    if "/Users/" in raw or "file://" in raw or "antecedents/" in raw:
        raise FreezeValidationError("private or machine-local path leaked into theorem contract")


def validate_history(root: Path = ROOT) -> None:
    ledger = load_json(root / LEDGER.relative_to(ROOT))
    real2 = [item for item in ledger.get("events", []) if item.get("attempt") == "DPREFIX-REAL-2"]
    if len(real2) != 1 or real2[0].get("cumulative_tensor_payloads_after_event") != 139:
        raise FreezeValidationError("v3.1 freeze-time real-payload ledger boundary changed")
    if ledger.get("cumulative_tensor_payloads", 0) < 139:
        raise FreezeValidationError("real-payload ledger precedes v3.1 freeze")
    exact = load_json(root / EXACT.relative_to(ROOT))
    if exact.get("artifact_id") != "DPREFIX-EXACT-1" or exact.get("layer3", {}).get("sha256") != EXACT_SHA:
        raise FreezeValidationError("DPREFIX-EXACT-1 authority changed")
    real = load_json(root / REAL_ATTEMPTS.relative_to(ROOT))
    replay = load_json(root / REPLAY_ATTEMPTS.relative_to(ROOT))
    if real.get("prior_terminal_attempt", {}).get("attempt_id") != "DPREFIX-REAL-1" or real.get("prior_terminal_attempt", {}).get("state") != "TERMINAL_REJECTED":
        raise FreezeValidationError("REAL-1 historical disposition changed")
    if real.get("current_state", {}).get("attempt_id") != "DPREFIX-REAL-2" or real.get("current_state", {}).get("terminal_class") != "EVIDENCE_VALIDATION":
        raise FreezeValidationError("REAL-2 historical disposition changed")
    if replay.get("current_state", {}).get("attempt_id") != "DPREFIX-REAL-3" or replay.get("current_state", {}).get("reason_code") != "ORACLE_STATE_IDENTITY_MISMATCH":
        raise FreezeValidationError("REAL-3 historical disposition changed")


def validate_evidence(evidence: dict[str, Any], root: Path = ROOT) -> None:
    if evidence.get("schema") != "pulsarmlx.f017.routing-v3-1-theorem-freeze" or evidence.get("schema_version") != "1.0.0":
        raise FreezeValidationError("freeze evidence identity mismatch")
    if evidence.get("starting_head") != EXPECTED_HEAD or evidence.get("consumer_id") != CONSUMER:
        raise FreezeValidationError("head/consumer binding mismatch")
    if evidence.get("result") != "ROUTING V3.1 THEOREM FROZEN":
        raise FreezeValidationError("freeze result mismatch")
    if evidence.get("real_evaluation", {}).get("performed") is not False:
        raise FreezeValidationError("real evaluation recorded in freeze evidence")
    if evidence.get("real_evaluation", {}).get("membership_inequalities_evaluated") != 0:
        raise FreezeValidationError("real membership inequality leaked into freeze")
    if evidence.get("isolation") != {"checkpoint_reads": 0, "shard_opens": 0, "real_payload_ledger_before": 139, "real_payload_ledger_after": 139}:
        raise FreezeValidationError("freeze isolation mismatch")
    artifacts = evidence.get("artifacts")
    if not isinstance(artifacts, list) or len(artifacts) != 8:
        raise FreezeValidationError("freeze artifact surface mismatch")
    for item in artifacts:
        path = Path(str(item.get("path", "")))
        expected = item.get("sha256")
        current = "" if path.is_absolute() or ".." in path.parts else sha256_path(root / path)
        historical = subprocess.run(
            ["git", "show", f"b899d09b971912a4d8d256fb381558865319818a:{path.as_posix()}"],
            cwd=root, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False,
        ) if not path.is_absolute() and ".." not in path.parts else None
        historical_sha = hashlib.sha256(historical.stdout).hexdigest() if historical is not None and historical.returncode == 0 else ""
        if path.is_absolute() or ".." in path.parts or expected not in {current, historical_sha}:
            raise FreezeValidationError(f"freeze artifact identity mismatch: {path}")
    validation = evidence.get("validation", {})
    if validation.get("synthetic_test_count", 0) < 23 or validation.get("property_samples_contained") is not True:
        raise FreezeValidationError("synthetic/property validation incomplete")
    if validation.get("real_values_loaded") is not False or validation.get("candidate_or_model_dispatches") != 0:
        raise FreezeValidationError("forbidden runtime activity recorded")
    raw = json.dumps(evidence, sort_keys=True)
    if "/Users/" in raw or "file://" in raw or "antecedents/" in raw:
        raise FreezeValidationError("private or machine-local path leaked into evidence")


def validate_freeze(root: Path = ROOT, evidence_path: Path | None = None) -> None:
    contract = load_json(root / CONTRACT.relative_to(ROOT))
    evidence = load_json(evidence_path or (root / EVIDENCE.relative_to(ROOT)))
    validate_contract(contract, root)
    validate_history(root)
    validate_evidence(evidence, root)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, default=EVIDENCE)
    args = parser.parse_args()
    validate_freeze(ROOT, args.evidence)
    print("ROUTING_V3_1_THEOREM_FREEZE_VALID")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
