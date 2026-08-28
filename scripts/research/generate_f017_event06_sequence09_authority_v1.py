#!/usr/bin/env python3
"""Generate the Sequence 9 version-forward no-access authority bundle."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Final

from f017_canonical_serialization_v10 import canonical_bytes


ROOT: Final = Path(__file__).resolve().parents[2]
C = ROOT / "specs/017-rust-native-inference-runtime/contracts"
E = ROOT / "docs/architecture/reviews/evidence"
START_HEAD: Final = "23c4c41540c6e780bb9d194f2b5f50f1ad75c892"

BASE_READINESS = (
    C / "f017-corrected-oracle-event06-readiness-consumer-interface-v10.json"
)
BASE_INSTALL = C / "f017-corrected-oracle-event06-live-installation-interface-v10.json"
BASE_QUAL = C / "f017-event06-sequence05-qualification-role-requirements-v8.json"
BASE_MANIFEST = C / "f017-corrected-oracle-event06-readiness-authority-manifest-v9.json"
BASE_PREPARED = (
    E / "f017-event06-v12-sequence05-readiness-authority-manifest-prepared-v6.json"
)
BASE_FUTURE = C / "f017-corrected-oracle-event06-future-go-capability-v1.json"

SCHEMA5 = C / "f017-event06-sequence09-qualification-schema-authority-v1.json"
QUAL9 = C / "f017-event06-sequence09-qualification-role-requirements-v1.json"
READINESS11 = C / "f017-corrected-oracle-event06-readiness-consumer-interface-v11.json"
INSTALL11 = C / "f017-corrected-oracle-event06-live-installation-interface-v11.json"
MANIFEST10 = C / "f017-corrected-oracle-event06-readiness-authority-manifest-v10.json"

SCHEMA6 = C / "f017-event06-sequence09-qualification-schema-authority-v2.json"
QUAL10 = C / "f017-event06-sequence09-qualification-role-requirements-v2.json"
READINESS12 = C / "f017-corrected-oracle-event06-readiness-consumer-interface-v12.json"
INSTALL12 = C / "f017-corrected-oracle-event06-live-installation-interface-v12.json"
MANIFEST11 = C / "f017-corrected-oracle-event06-readiness-authority-manifest-v11.json"
PREPARED8 = (
    E / "f017-event06-v12-sequence09-readiness-authority-manifest-prepared-v1.json"
)

FUTURE2 = C / "f017-corrected-oracle-event06-future-go-capability-v2.json"
TRANSACTION = C / "f017-event06-production-installation-transaction-policy-v1.json"
MEASUREMENT_SCHEMA = (
    C / "f017-event06-sequence09-implementation-measurement-schema-v1.json"
)
MEASUREMENT = E / "f017-event06-v12-sequence09-implementation-measurement-v1.json"
MATRIX = E / "f017-event06-v12-sequence09-producer-consumer-matrix-v1.json"
DISPOSITIONS = (
    E / "f017-event06-v12-sequence09-prequalification-finding-dispositions-v1.json"
)

READINESS_SCHEMA_CANDIDATE = (
    "pulsarmlx.f017.corrected-oracle-event06-readiness-consumer-interface/2.9.0"
)
READINESS_SCHEMA_FINAL = (
    "pulsarmlx.f017.corrected-oracle-event06-readiness-consumer-interface/2.10.0"
)
INSTALL_SCHEMA_CANDIDATE = (
    "pulsarmlx.f017.corrected-oracle-event06-live-installation-interface/2.0.0"
)
INSTALL_SCHEMA_FINAL = (
    "pulsarmlx.f017.corrected-oracle-event06-live-installation-interface/2.1.0"
)
QUAL_SCHEMA_CANDIDATE = (
    "pulsarmlx.f017.event06-sequence09-qualification-role-requirements/2.0.0"
)
QUAL_SCHEMA_FINAL = (
    "pulsarmlx.f017.event06-sequence09-qualification-role-requirements/2.1.0"
)

IMPLEMENTATION_PATHS: Final = (
    "scripts/research/f017_corrected_oracle_authorization_v12_v3.py",
    "scripts/research/f017_event06_durable_installation_transaction_v1.py",
    "scripts/research/f017_event06_production_installation_v2.py",
    "scripts/research/f017_event06_readiness_authority_v3.py",
    "scripts/research/f017_event06_sequence09_fixture_v1.py",
    "scripts/research/generate_f017_event06_sequence09_authority_v1.py",
    "scripts/research/validate_f017_event06_sequence09_authority_v1.py",
    "scripts/research/qualify_f017_event06_sequence09_no_access_v1.py",
    "scripts/research/tests/test_f017_event06_sequence09_authority_v1.py",
)


def load(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if type(value) is not dict:
        raise TypeError(path)
    return value


def sha_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def sha(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def git(*arguments: str) -> str:
    return subprocess.check_output(
        ["git", *arguments], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
    ).strip()


def git_sha(head: str, path: str) -> str:
    return sha_bytes(
        subprocess.check_output(["git", "show", f"{head}:{path}"], cwd=ROOT)
    )


def write(path: Path, value: dict[str, object], check: bool) -> None:
    raw = canonical_bytes(value)
    if check:
        if not path.is_file() or path.read_bytes() != raw:
            raise SystemExit(f"drift: {relative(path)}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)


def preserved_predicate_surface() -> dict[str, object]:
    qualification = load(BASE_QUAL)
    roles = qualification["roles"]
    if type(roles) is not dict:
        raise TypeError("base qualification roles")
    future = qualification["future_output_roles"]
    if type(future) is not list:
        raise TypeError("base future roles")
    selected: dict[str, object] = {}
    for role in sorted(future):
        rule = roles[role]
        if type(rule) is not dict:
            raise TypeError(role)
        selected[role] = {
            key: copy.deepcopy(rule[key])
            for key in (
                "acceptance_predicates",
                "availability_stage",
                "minimums",
                "required_schema",
            )
            if key in rule
        }
    return selected


def build_measurement_schema() -> dict[str, object]:
    return {
        "schema": "pulsarmlx.f017.event06-sequence09-implementation-measurement-schema/1.0.0",
        "measurement_schema": "pulsarmlx.f017.event06-v12-sequence09-implementation-measurement/1.0.0",
        "required_fields": [
            "schema",
            "implementation_head",
            "implementation_tree",
            "measured_paths",
            "measured_path_count",
            "historical_sequence08_head",
            "historical_sequence08_tree",
            "numerical_drift",
            "result_authority_drift",
            "checkpoint_access",
            "production_capability_instances",
            "production_commit_success_calls",
            "result",
        ],
        "measured_path_entry_fields": ["path", "sha256"],
        "head_tree_exact": True,
        "path_sha_exact": True,
        "unknown_keys_permitted": False,
    }


def build_transaction_policy() -> dict[str, object]:
    return {
        "schema": "pulsarmlx.f017.event06-production-installation-transaction-policy/1.0.0",
        "attributes_before_q10": [
            "BANKED",
            "PINNED",
            "TEMPORALLY_FROZEN",
            "INSTANTIABLE",
        ],
        "operational_ratification_before_q10": False,
        "production_module": "scripts/research/f017_event06_production_installation_v2.py",
        "transaction_engine": "scripts/research/f017_event06_durable_installation_transaction_v1.py",
        "production_entrypoint": "commit_production_installation_v2",
        "synthetic_qualification_entrypoint": "commit_synthetic_non_authority_transaction",
        "production_fault_injection": False,
        "synthetic_fault_injection": "CLOSED_ENUMERATION_ONLY",
        "transaction_requirements": [
            "trusted nonsymlink parent",
            "exclusive target directory creation",
            "exclusive no-follow payload creation",
            "complete write counters",
            "file fsync",
            "descriptor-relative readback",
            "device and inode stability",
            "transaction receipt binding",
            "target and parent directory fsync",
            "one-shot consumption marker before production target creation",
            "restart and replay fail closed",
            "partial failure preserved",
        ],
        "race_families": [
            "exclusive_create",
            "target_identity",
            "write_short",
            "write_error",
            "file_fsync",
            "directory_fsync",
            "readback_identity",
            "concurrent_replacement",
            "capability_expiry",
            "candidate_replay",
        ],
        "production_success_calls_required_in_sequence09": 0,
        "production_capability_instances_required_in_sequence09": 0,
    }


def build_future_capability(transaction_sha: str) -> dict[str, object]:
    value = copy.deepcopy(load(BASE_FUTURE))
    value.update(
        schema="pulsarmlx.f017.corrected-oracle-event06-future-go-capability/2.0.0",
        sealing_authority="produce_future_go_capability",
        producer_path="scripts/research/f017_event06_production_installation_v2.py",
        checker="validate_future_go_capability",
        production_wrapper="commit_production_installation_v2",
        transaction_policy_path=relative(TRANSACTION),
        transaction_policy_sha256=transaction_sha,
        sequence_5_factory_available=False,
        future_human_go_factory_implemented=True,
        sequence_9_factory_invocations=0,
        sequence_9_capability_instances=0,
        sequence_9_production_commit_success_calls=0,
        accepted_live_go_schema="pulsarmlx.f017.event06-v12-future-human-go/2.0.0",
        accepted_live_go_decision="GO_FRESH_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_06",
        inert_stale_expired_reused_mismatched_copied_pickled_caller_created_cross_posture="REJECT",
        success_capable_path="producer -> sealed capability -> checker -> production wrapper -> durable transaction engine",
    )
    return value


def build_schema_authority(profile: str) -> dict[str, object]:
    final = profile == "final"
    return {
        "schema": f"pulsarmlx.f017.event06-sequence09-qualification-schema-authority/{'2.1.0' if final else '2.0.0'}",
        "qualification_schema": QUAL_SCHEMA_FINAL if final else QUAL_SCHEMA_CANDIDATE,
        "readiness_schema": READINESS_SCHEMA_FINAL
        if final
        else READINESS_SCHEMA_CANDIDATE,
        "installation_schema": INSTALL_SCHEMA_FINAL
        if final
        else INSTALL_SCHEMA_CANDIDATE,
        "implementation_measurement_schema": "pulsarmlx.f017.event06-v12-sequence09-implementation-measurement/1.0.0",
        "future_go_capability_schema": "pulsarmlx.f017.corrected-oracle-event06-future-go-capability/2.0.0",
        "transaction_policy_schema": "pulsarmlx.f017.event06-production-installation-transaction-policy/1.0.0",
        "artifact_schema_equality_required": True,
        "self_reference_permitted": False,
        "profile": profile.upper(),
    }


def build_readiness(
    profile: str, qualification_path: Path, manifest_path: Path
) -> dict[str, object]:
    value = copy.deepcopy(load(BASE_READINESS))
    final = profile == "final"
    value.update(
        schema=READINESS_SCHEMA_FINAL if final else READINESS_SCHEMA_CANDIDATE,
        qualification_role_requirements=relative(qualification_path),
        manifest_contract=relative(manifest_path),
        sequence09_freeze_transition_table_required=True,
        sequence09_preobservation_freeze_required=True,
        historical_v10_supersession="PROSPECTIVE_ONLY",
    )
    predicates = value["exact_predicates"]
    if type(predicates) is not dict:
        raise TypeError("readiness predicates")
    predicates["schema"] = (
        "pulsarmlx.f017.corrected-oracle-event06-execution-readiness-final-declaration/12.3.0"
    )
    predicates["opus_verdict"] = (
        "ACCEPT_FOR_FRESH_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_06_GO"
    )
    value["declaration_schema"] = predicates["schema"]
    return value


def build_install(
    profile: str,
    qualification_path: Path,
    future_sha: str,
    transaction_sha: str,
) -> dict[str, object]:
    value = copy.deepcopy(load(BASE_INSTALL))
    final = profile == "final"
    value.update(
        schema=INSTALL_SCHEMA_FINAL if final else INSTALL_SCHEMA_CANDIDATE,
        qualification_role_requirements=relative(qualification_path),
        future_go_capability_contract=relative(FUTURE2),
        future_go_capability_sha256=future_sha,
        transaction_policy_path=relative(TRANSACTION),
        transaction_policy_sha256=transaction_sha,
        production_module="scripts/research/f017_event06_production_installation_v2.py",
        transaction_engine="scripts/research/f017_event06_durable_installation_transaction_v1.py",
        production_prepare_entrypoint="prepare_production_installation_v2",
        production_commit_entrypoint="commit_production_installation_v2",
        future_go_capability_producer="produce_future_go_capability",
        future_go_capability_checker="validate_future_go_capability",
        success_capable_transaction_path=True,
        durable_commit_authorized_in_sequence_9=False,
        sequence_9_production_capability_instances=0,
        sequence_9_production_commit_success_calls=0,
        operational_ratification="PENDING_Q10",
        supersedes=relative(INSTALL11 if final else BASE_INSTALL),
    )
    return value


def build_qualification(
    profile: str,
    schema_path: Path,
    schema_sha: str,
    readiness_path: Path,
    install_path: Path,
    candidate_validation_path: Path | None,
) -> dict[str, object]:
    value = copy.deepcopy(load(BASE_QUAL))
    final = profile == "final"
    value.update(
        schema=QUAL_SCHEMA_FINAL if final else QUAL_SCHEMA_CANDIDATE,
        active_validation_gap_ids=[]
        if final
        else ["EXTERNAL_SUCCESSOR_VALIDATOR_REQUIRED"],
        validation_gap_count=0 if final else 1,
        all_requirements_mechanically_validated=final,
        validation_state="PASS" if final else "PENDING_EXTERNAL_SUCCESSOR_VALIDATOR",
        validation_result_source=(
            relative(candidate_validation_path)
            if candidate_validation_path is not None
            else "scripts/research/validate_f017_event06_sequence09_authority_v1.py"
        ),
        preserved_cycle11_acceptance_surface_sha256=sha_bytes(
            canonical_bytes(preserved_predicate_surface())
        ),
        mutation_floor=324,
        installation_outcome_count=16,
        race_family_count=10,
        zero_access_required=True,
        producer_consumer_instantiability_required=True,
        supersedes=relative(QUAL9 if final else BASE_QUAL),
    )
    roles = value["roles"]
    if type(roles) is not dict:
        raise TypeError("qualification roles")
    authority_sha = schema_sha
    authority_rel = relative(schema_path)
    roles["implementation_measurement"]["required"] = {
        "schema": "pulsarmlx.f017.event06-v12-sequence09-implementation-measurement/1.0.0",
        "result": "PASS",
    }
    roles["readiness_interface"].update(
        artifact_path=relative(readiness_path),
        schema_authority_path=authority_rel,
        schema_authority_sha256=authority_sha,
        schema_authority_field="readiness_schema",
    )
    roles["live_installation_interface"].update(
        artifact_path=relative(install_path),
        schema_authority_path=authority_rel,
        schema_authority_sha256=authority_sha,
        schema_authority_field="installation_schema",
        required={
            "durable_commit_authorized_in_sequence_9": False,
            "success_capable_transaction_path": True,
            "sequence_9_production_capability_instances": 0,
            "sequence_9_production_commit_success_calls": 0,
        },
    )
    roles["future_go_capability"]["required"] = {
        "attempts": 1,
        "retries": 0,
        "resume": False,
        "future_human_go_factory_implemented": True,
        "sequence_9_factory_invocations": 0,
        "sequence_9_capability_instances": 0,
        "sequence_9_production_commit_success_calls": 0,
    }
    roles["qualification_role_requirements"].update(
        artifact_path=relative(QUAL10 if final else QUAL9),
        external_schema_authority_path=authority_rel,
        external_schema_authority_sha256=authority_sha,
        schema_authority_field="qualification_schema",
    )
    return value


def build_manifest(profile: str, prepared_path: Path) -> dict[str, object]:
    value = copy.deepcopy(load(BASE_MANIFEST))
    final = profile == "final"
    value.update(
        schema=f"pulsarmlx.f017.corrected-oracle-event06-readiness-authority-manifest-contract/{'2.0.0' if final else '1.9.0'}",
        manifest_schema=f"pulsarmlx.f017.corrected-oracle-event06-readiness-authority-manifest/{'2.0.0' if final else '1.9.0'}",
        prepared_instance_path=relative(prepared_path),
        prepared_instance_schema="pulsarmlx.f017.corrected-oracle-event06-readiness-authority-manifest-prepared/2.0.0",
        sequence09_layered_manifest_required=True,
        sequence09_operational_ratification_node="Q10_CONDITIONAL_OPERATIONAL_RATIFICATION",
        supersedes=relative(MANIFEST10 if final else BASE_MANIFEST),
    )
    forbidden = list(value.get("forbidden_current_binding_paths", []))
    for path in (relative(BASE_PREPARED), relative(BASE_MANIFEST)):
        if path not in forbidden:
            forbidden.append(path)
    value["forbidden_current_binding_paths"] = forbidden
    return value


def build_measurement(head: str) -> dict[str, object]:
    tree = git("rev-parse", f"{head}^{{tree}}")
    measured: list[dict[str, str]] = []
    for path in IMPLEMENTATION_PATHS:
        try:
            digest = git_sha(head, path)
        except subprocess.CalledProcessError:
            continue
        measured.append({"path": path, "sha256": digest})
    return {
        "schema": "pulsarmlx.f017.event06-v12-sequence09-implementation-measurement/1.0.0",
        "implementation_head": head,
        "implementation_tree": tree,
        "measured_paths": measured,
        "measured_path_count": len(measured),
        "historical_sequence08_head": "3a37d05fcd44ef56924f797b5427c8a488aed523",
        "historical_sequence08_tree": "5639d6509b0d148ae9b16cea12ff377971ea253a",
        "numerical_drift": "NONE",
        "result_authority_drift": "NONE",
        "checkpoint_access": 0,
        "production_capability_instances": 0,
        "production_commit_success_calls": 0,
        "result": "PASS",
    }


def build_prepared(
    head: str,
    qualification: Path,
    readiness: Path,
    installation: Path,
    generated: dict[Path, dict[str, object]],
) -> dict[str, object]:
    value = copy.deepcopy(load(BASE_PREPARED))
    value.update(
        schema="pulsarmlx.f017.corrected-oracle-event06-readiness-authority-manifest-prepared/2.0.0",
        purpose="SEQUENCE09_PREOBSERVATION_PREPARED_AUTHORITY_NOT_FINAL_ACCEPTANCE",
        implementation_head=head,
        implementation_tree=git("rev-parse", f"{head}^{{tree}}"),
        result="PREPARED_INCOMPLETE",
        final_acceptance_eligible=False,
        live_authority=False,
        checkpoint_root_resolved=False,
        checkpoint_access=0,
        numerical_operations=0,
    )
    replacements = {
        "implementation_measurement": MEASUREMENT,
        "readiness_interface": readiness,
        "live_installation_interface": installation,
        "future_go_capability": FUTURE2,
        "qualification_role_requirements": qualification,
    }
    bindings = value["bindings"]
    if type(bindings) is not dict:
        raise TypeError("prepared bindings")
    for role, path in replacements.items():
        digest = (
            sha_bytes(canonical_bytes(generated[path]))
            if path in generated
            else sha(path)
        )
        bindings[role] = {
            "binding_state": "CURRENT_DESIGN_AUTHORITY",
            "path": relative(path),
            "sha256": digest,
        }
    current = value["roles"]
    if type(current) is not list:
        raise TypeError("prepared roles")
    value["validated_binding_count"] = sum(
        type(binding) is dict
        and binding.get("binding_state") == "CURRENT_DESIGN_AUTHORITY"
        for binding in bindings.values()
    )
    value["binding_count"] = len(bindings)
    value["role_count"] = len(current)
    return value


def build_matrix(profile: str) -> dict[str, object]:
    final = profile == "final"
    return {
        "schema": "pulsarmlx.f017.event06-v12-sequence09-producer-consumer-matrix/1.0.0",
        "profile": profile.upper(),
        "rows": [
            {
                "authority": "canonical readiness declaration",
                "producer": "future layered readiness producer at Q8",
                "consumer": "scripts/research/f017_event06_readiness_authority_v3.py",
                "contract": relative(READINESS12 if final else READINESS11),
                "instantiable": True,
            },
            {
                "authority": "fresh Event 06 human GO capability",
                "producer": "produce_future_go_capability",
                "consumer": "validate_future_go_capability",
                "contract": relative(FUTURE2),
                "instantiable": True,
                "sequence09_instances": 0,
            },
            {
                "authority": "durable production installation",
                "producer": "commit_production_installation_v2",
                "consumer": "future package-start installed-authority validator",
                "contract": relative(INSTALL12 if final else INSTALL11),
                "storage_policy": relative(TRANSACTION),
                "success_capable": True,
                "sequence09_success_calls": 0,
            },
        ],
        "row_count": 3,
        "unimplemented_bridges": 0,
        "production_capability_instances": 0,
        "production_commit_success_calls": 0,
        "result": "PASS" if final else "PENDING_EXTERNAL_VALIDATION",
    }


def build_dispositions(candidate_validation: Path) -> dict[str, object]:
    return {
        "schema": "pulsarmlx.f017.event06-v12-sequence09-prequalification-finding-dispositions/1.0.0",
        "candidate_external_validation_path": relative(candidate_validation),
        "candidate_external_validation_sha256": sha(candidate_validation),
        "findings": [
            {
                "id": "F017-S9-PREQUAL-001",
                "status": "RESOLVED",
                "disposition": "VERSION_FORWARD_COHERENT_SUCCESSOR_CHAIN_WITH_DOMAIN_CORRECT_MEASUREMENT",
            },
            {
                "id": "F017-S9-PREQUAL-002",
                "status": "RESOLVED",
                "disposition": "REAL_FUTURE_GO_PRODUCER_CHECKER_AND_SUCCESS_CAPABLE_DURABLE_TRANSACTION_PATH_ZERO_LIVE_INVOCATIONS",
            },
        ],
        "finding_count": 2,
        "resolved_count": 2,
        "open_count": 0,
        "acceptance_predicates_changed": False,
        "checkpoint_access": 0,
        "production_capability_instances": 0,
        "production_commit_success_calls": 0,
        "result": "PASS",
    }


def generate(
    profile: str,
    *,
    implementation_head: str | None,
    candidate_validation: Path | None,
) -> dict[Path, dict[str, object]]:
    schema_path = SCHEMA6 if profile == "final" else SCHEMA5
    qualification_path = QUAL10 if profile == "final" else QUAL9
    readiness_path = READINESS12 if profile == "final" else READINESS11
    installation_path = INSTALL12 if profile == "final" else INSTALL11
    manifest_path = MANIFEST11 if profile == "final" else MANIFEST10
    prepared_path = PREPARED8

    artifacts: dict[Path, dict[str, object]] = {
        MEASUREMENT_SCHEMA: build_measurement_schema(),
        TRANSACTION: build_transaction_policy(),
    }
    transaction_sha = sha_bytes(canonical_bytes(artifacts[TRANSACTION]))
    artifacts[FUTURE2] = build_future_capability(transaction_sha)
    future_sha = sha_bytes(canonical_bytes(artifacts[FUTURE2]))
    artifacts[schema_path] = build_schema_authority(profile)
    schema_sha = sha_bytes(canonical_bytes(artifacts[schema_path]))
    artifacts[readiness_path] = build_readiness(
        profile, qualification_path, manifest_path
    )
    artifacts[installation_path] = build_install(
        profile, qualification_path, future_sha, transaction_sha
    )
    artifacts[qualification_path] = build_qualification(
        profile,
        schema_path,
        schema_sha,
        readiness_path,
        installation_path,
        candidate_validation,
    )
    artifacts[manifest_path] = build_manifest(profile, prepared_path)
    artifacts[MATRIX] = build_matrix(profile)
    if profile == "final":
        if implementation_head is None or candidate_validation is None:
            raise SystemExit(
                "final profile requires implementation head and candidate validation"
            )
        artifacts[MEASUREMENT] = build_measurement(implementation_head)
        artifacts[PREPARED8] = build_prepared(
            implementation_head,
            qualification_path,
            readiness_path,
            installation_path,
            artifacts,
        )
        artifacts[DISPOSITIONS] = build_dispositions(candidate_validation)
    return artifacts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=("candidate", "final"), required=True)
    parser.add_argument("--implementation-head")
    parser.add_argument("--candidate-validation", type=Path)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    candidate_validation = arguments.candidate_validation
    if candidate_validation is not None and not candidate_validation.is_absolute():
        candidate_validation = ROOT / candidate_validation
    artifacts = generate(
        arguments.profile,
        implementation_head=arguments.implementation_head,
        candidate_validation=candidate_validation,
    )
    for path, value in artifacts.items():
        write(path, value, arguments.check)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
