#!/usr/bin/env python3
"""No-access instantiability and mutation qualification for collapsed Event 06 GO."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from f017_canonical_serialization_v10 import canonical_bytes
from f017_event06_collapsed_go_path_v1 import (
    COLLAPSED_GO_FIELDS,
    HUMAN_DECISION,
    HUMAN_DECISION_FIELDS,
    HUMAN_DECISION_SCHEMA,
    TARGET_MACHINE,
    CollapsedGoApprovalV1,
    CollapsedOneShotGoV1,
    CollapsedPreparationV1,
    CollapsedPromptIdentityV1,
    PackageStartEligibilityV1,
    SanitizedHumanDecisionV1,
    assert_closed_artifacts,
    begin_no_access_composition,
    derived_event_identities,
    produce_collapsed_approval,
    produce_prompt_bound_identity,
    reconstruct_collapsed_one_shot_go,
    seal_collapsed_one_shot_go,
    seal_collapsed_preparation,
    validate_collapsed_package_start_eligibility,
    validate_sanitized_human_decision,
)
from f017_event06_execution_plan_v1 import validate_execution_plan
from f017_event06_readiness_authority_v3 import (
    validate_event06_readiness_declaration_v3,
)
from f017_event06_sequence08_fixture_v1 import execution_plan_value
from f017_event06_sequence09_fixture_v1 import build_readiness_fixture
from execute_f017_corrected_oracle_event_v12 import (
    validate_collapsed_pre_package_eligibility,
)

ROOT = Path(__file__).resolve().parents[2]
PROMPT_BYTES = b"F017 Event 06 sanitized future human decision boundary\n"
PROMPT_COMMIT = "1" * 40
PROMPT_PATH = "Prompts/F017/Mac-Studio-M1-Ultra/future-event06-go.md"
ISSUED = 100
EXPIRES = 200
NOW = 150


class _PlanIds:
    def __init__(self, package_attempt_id: str) -> None:
        self.package_attempt_id = package_attempt_id

    def get(self, name: str) -> str:
        if name != "package_attempt_id":
            raise KeyError(name)
        return self.package_attempt_id


def _human_value() -> dict[str, object]:
    return {
        "schema": HUMAN_DECISION_SCHEMA,
        "decision": HUMAN_DECISION,
        "target_machine": TARGET_MACHINE,
        "human_decision_nonce_sha256": "f" * 64,
    }


def _build(root: Path) -> dict[str, object]:
    readiness_raw, interface_path, _ = build_readiness_fixture(root / "readiness")
    readiness = validate_event06_readiness_declaration_v3(
        readiness_raw,
        repository_root=root / "readiness",
        contract_path=interface_path,
    )
    state = begin_no_access_composition()
    decision = validate_sanitized_human_decision(
        canonical_bytes(_human_value()), state=state
    )
    go = seal_collapsed_one_shot_go(
        decision,
        readiness,
        issued_at_unix_ns=ISSUED,
        expires_at_unix_ns=EXPIRES,
        now_unix_ns=NOW,
        state=state,
    )
    ids = derived_event_identities(go)
    plan_value = execution_plan_value(_PlanIds(ids["package_attempt_id"]), readiness)
    plan_value["package_attempt_id"] = ids["package_attempt_id"]
    plan_value["primary_event_id"] = ids["primary_event_id"]
    plan_value["secondary_event_id"] = ids["secondary_event_id"]
    plan = validate_execution_plan(plan_value)
    approval = produce_collapsed_approval(
        go, readiness, plan, now_unix_ns=NOW, state=state
    )
    preparation = seal_collapsed_preparation(
        approval, go, readiness, plan, state=state
    )
    identity = produce_prompt_bound_identity(
        preparation,
        go,
        plan,
        prompt_bytes=PROMPT_BYTES,
        prompt_repository_commit=PROMPT_COMMIT,
        prompt_repository_path=PROMPT_PATH,
        state=state,
    )
    checkpoint_root = Path("/NONEXISTENT/F017/EVENT06/SEQUENCE13-COLLAPSED-GO")
    eligibility = validate_collapsed_package_start_eligibility(
        preparation,
        identity,
        go,
        readiness,
        plan,
        checkpoint_root=checkpoint_root,
        now_unix_ns=NOW,
        prompt_bytes=PROMPT_BYTES,
        prompt_repository_commit=PROMPT_COMMIT,
        prompt_repository_path=PROMPT_PATH,
        state=state,
    )
    coordinator = validate_collapsed_pre_package_eligibility(eligibility)
    assert_closed_artifacts(
        decision, go, approval, preparation, identity, eligibility
    )
    return {
        "readiness": readiness,
        "state": state,
        "decision": decision,
        "go": go,
        "plan": plan,
        "plan_value": plan_value,
        "approval": approval,
        "preparation": preparation,
        "identity": identity,
        "eligibility": eligibility,
        "coordinator": coordinator,
        "checkpoint_root": checkpoint_root,
    }


def _single_result() -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="f017-collapsed-go-") as directory:
        package = _build(Path(directory))
        state = package["state"].snapshot()
        forbidden = {
            name: state[name]
            for name in (
                "installation_commit_calls", "live_authorities_created",
                "live_capabilities_created", "live_authority_installs",
                "package_starts",
                "checkpoint_root_resolutions", "checkpoint_opens",
                "checkpoint_identity_reads", "checkpoint_payload_reads",
                "numerical_operations", "full_model_inferences",
                "live_event_ids_instantiated", "live_event_ids_consumed",
                "authorization_delta", "package_delta", "primary_delta",
                "secondary_delta", "event04_retries",
                "event05_retries_or_resumes", "prior_event06_retries_or_resumes",
                "p1_actions",
            )
        }
        if any(forbidden.values()):
            raise AssertionError("no-access boundary changed")
        return {
            "go_sha256": package["go"].source_sha256,
            "approval_sha256": package["approval"].source_sha256,
            "preparation_sha256": package["preparation"].source_sha256,
            "identity_sha256": package["identity"].source_sha256,
            "candidate_sha256": package["eligibility"].get("candidate_sha256"),
            "eligibility_sha256": package["eligibility"].source_sha256,
            "go_field_count": len(COLLAPSED_GO_FIELDS),
            "coordinator": package["coordinator"],
            "observed_counters": dict(state),
            "result": "PASS",
        }


def _expect_failure(operation) -> None:
    try:
        operation()
    except (TypeError, ValueError, RuntimeError):
        return
    raise AssertionError("mutation unexpectedly passed")


def _mutations() -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="f017-collapsed-mutations-") as directory:
        package = _build(Path(directory))
        readiness = package["readiness"]
        decision = package["decision"]
        go = package["go"]
        rejected = 0
        categories: dict[str, int] = {}

        def reject(category: str, operation) -> None:
            nonlocal rejected
            _expect_failure(operation)
            rejected += 1
            categories[category] = categories.get(category, 0) + 1

        human = _human_value()
        for field in HUMAN_DECISION_FIELDS:
            mutated = dict(human)
            mutated.pop(field)
            reject(
                "human_schema",
                lambda value=mutated: validate_sanitized_human_decision(
                    canonical_bytes(value), state=begin_no_access_composition()
                ),
            )
        for index in range(48):
            mutated = dict(human)
            mutated[f"unknown_{index}"] = index
            reject(
                "human_unknown",
                lambda value=mutated: validate_sanitized_human_decision(
                    canonical_bytes(value), state=begin_no_access_composition()
                ),
            )
        human_bad_values = {
            "schema": ["", HUMAN_DECISION_SCHEMA.upper(), False, 1, None],
            "decision": ["", "GO", False, 1, None],
            "target_machine": ["", "MACBOOK_PRO_M2_MAX", False, 1, None],
            "human_decision_nonce_sha256": ["", "F" * 64, "0" * 63, False, 1],
        }
        for field, values in human_bad_values.items():
            for replacement in values:
                mutated = dict(human)
                mutated[field] = replacement
                reject(
                    "human_types",
                    lambda value=mutated: validate_sanitized_human_decision(
                        canonical_bytes(value), state=begin_no_access_composition()
                    ),
                )

        go_value = json.loads(go.source_bytes())
        for field in COLLAPSED_GO_FIELDS:
            mutated = dict(go_value)
            mutated.pop(field)
            reject(
                "go_schema",
                lambda value=mutated: reconstruct_collapsed_one_shot_go(
                    canonical_bytes(value), decision, readiness,
                    expected_issued_at_unix_ns=ISSUED,
                    expected_expires_at_unix_ns=EXPIRES,
                    now_unix_ns=NOW, state=begin_no_access_composition(),
                ),
            )
        for index in range(48):
            mutated = dict(go_value)
            mutated[f"unknown_{index}"] = index
            reject(
                "go_unknown",
                lambda value=mutated: reconstruct_collapsed_one_shot_go(
                    canonical_bytes(value), decision, readiness,
                    expected_issued_at_unix_ns=ISSUED,
                    expected_expires_at_unix_ns=EXPIRES,
                    now_unix_ns=NOW, state=begin_no_access_composition(),
                ),
            )
        replacements = [None, False, True, 0, 1, "", "YES", "0" * 64]
        for field in COLLAPSED_GO_FIELDS:
            for replacement in replacements:
                if replacement == go_value[field]:
                    continue
                mutated = dict(go_value)
                mutated[field] = replacement
                reject(
                    "go_types_and_bindings",
                    lambda value=mutated: reconstruct_collapsed_one_shot_go(
                        canonical_bytes(value), decision, readiness,
                        expected_issued_at_unix_ns=ISSUED,
                        expected_expires_at_unix_ns=EXPIRES,
                        now_unix_ns=NOW, state=begin_no_access_composition(),
                    ),
                )

        reject(
            "expiry",
            lambda: seal_collapsed_one_shot_go(
                decision, readiness, issued_at_unix_ns=ISSUED,
                expires_at_unix_ns=EXPIRES, now_unix_ns=EXPIRES,
                state=begin_no_access_composition(),
            ),
        )
        duplicate_state = begin_no_access_composition()
        seal_collapsed_one_shot_go(
            decision, readiness, issued_at_unix_ns=ISSUED,
            expires_at_unix_ns=EXPIRES, now_unix_ns=NOW, state=duplicate_state,
        )
        reject(
            "replay",
            lambda: seal_collapsed_one_shot_go(
                decision, readiness, issued_at_unix_ns=ISSUED,
                expires_at_unix_ns=EXPIRES, now_unix_ns=NOW,
                state=duplicate_state,
            ),
        )
        reject(
            "replay",
            lambda: validate_collapsed_package_start_eligibility(
                package["preparation"], package["identity"], go, readiness,
                package["plan"], checkpoint_root=package["checkpoint_root"],
                now_unix_ns=NOW, prompt_bytes=PROMPT_BYTES,
                prompt_repository_commit=PROMPT_COMMIT,
                prompt_repository_path=PROMPT_PATH, state=package["state"],
            ),
        )

        for identity_field in ("package_attempt_id", "primary_event_id", "secondary_event_id"):
            mutated = dict(package["plan_value"])
            mutated[identity_field] = (
                f"F017-SUBSTITUTED-{identity_field.upper().replace('_', '-')}"
            )
            altered_plan = validate_execution_plan(mutated)
            reject(
                "identity_substitution",
                lambda plan=altered_plan: produce_collapsed_approval(
                    go, readiness, plan, now_unix_ns=NOW,
                    state=begin_no_access_composition(),
                ),
            )

        fresh_root = Path(directory) / "prompt-substitution"
        substituted = _build(fresh_root)
        reject(
            "prompt_substitution",
            lambda: validate_collapsed_package_start_eligibility(
                substituted["preparation"], substituted["identity"],
                substituted["go"], substituted["readiness"], substituted["plan"],
                checkpoint_root=substituted["checkpoint_root"], now_unix_ns=NOW,
                prompt_bytes=b"substituted\n", prompt_repository_commit=PROMPT_COMMIT,
                prompt_repository_path=PROMPT_PATH, state=substituted["state"],
            ),
        )

        constructors = (
            SanitizedHumanDecisionV1, CollapsedOneShotGoV1,
            CollapsedGoApprovalV1, CollapsedPreparationV1,
            CollapsedPromptIdentityV1, PackageStartEligibilityV1,
        )
        for constructor in constructors:
            reject("forged_sealed_type", constructor)

        source = (ROOT / "scripts/research/f017_event06_collapsed_go_path_v1.py").read_text()
        prohibited = ("sys._getframe", "settrace(", "setprofile(", "inspect.currentframe", "caller_callback")
        if any(term in source for term in prohibited):
            raise AssertionError("dynamic capability introduced")

        if rejected < 200:
            raise AssertionError("mutation floor")
        return {
            "categories": categories,
            "total": rejected,
            "rejected": rejected,
            "unexpected_passes": 0,
            "checkpoint_access": 0,
            "numerical_operations": 0,
            "result": "PASS",
        }


def qualify() -> dict[str, object]:
    command = [sys.executable, str(Path(__file__).resolve()), "--single"]
    repetitions = []
    for _ in range(20):
        completed = subprocess.run(
            command, cwd=ROOT, check=True, text=True, capture_output=True
        )
        repetitions.append(json.loads(completed.stdout))
    stable = {
        tuple(
            item[key] for key in (
                "go_sha256", "approval_sha256", "preparation_sha256",
                "identity_sha256", "candidate_sha256", "eligibility_sha256",
            )
        )
        for item in repetitions
    }
    if len(stable) != 1:
        raise AssertionError("fresh-process composition drift")
    mutations = _mutations()
    return {
        "schema": "pulsarmlx.f017.event06-v12-collapsed-go-qualification/1.0.0",
        "state_transition": "LIQUID_UNTIL_INSTANTIABLE_TO_INSTANTIABLE",
        "real_public_composition": "PASS",
        "go_field_count": 8,
        "fresh_process_repetitions": 20,
        "distinct_composition_sha_sets": len(stable),
        "mutation_campaign": mutations,
        "observed_no_access_counters": repetitions[0]["observed_counters"],
        "checkpoint_access": 0,
        "numerical_operations": 0,
        "event06_executed": False,
        "live_authority_installed": False,
        "result": "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--single", action="store_true")
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    result = _single_result() if arguments.single else qualify()
    rendered = json.dumps(result, sort_keys=True, separators=(",", ":"))
    if arguments.output:
        arguments.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
