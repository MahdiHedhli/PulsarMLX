#!/usr/bin/env python3
"""No-access qualification for the Sequence 14 collapsed live integration."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import pickle
import subprocess
import sys
import tempfile
from pathlib import Path

from f017_canonical_serialization_v10 import canonical_bytes
from f017_event06_collapsed_live_installation_v2 import (
    HUMAN_AUTHORITY_FIELDS,
    HUMAN_AUTHORITY_SCHEMA,
    HUMAN_GO_RECORD_FIELDS,
    PLANNER_ACCEPTANCE_FIELDS,
    BoundSanitizedHumanDecisionV2,
    CheckpointBoundCandidateBundleV2,
    CollapsedInstallationEligibilityV2,
    CollapsedInstalledTripleV2,
    CollapsedLiveApprovalV2,
    CollapsedLiveInstallationCapabilityV2,
    CollapsedLivePreparationV2,
    CollapsedLivePromptIdentityV2,
    CollapsedPackageStartGateV2,
    LiveCheckpointRootAuthorityV2,
    LiveInstallationTargetV2,
    LivePromptControlAuthorityV2,
    PreparedCollapsedInstallationV2,
    QualificationCheckpointRootAuthorityV2,
    QualificationInstallationCapabilityV2,
    QualificationInstallationTargetV2,
    QualificationPromptControlAuthorityV2,
    commit_collapsed_live_installation,
    commit_qualification_collapsed_installation,
    derive_production_event_identities,
    prepare_collapsed_production_installation,
    produce_bound_sanitized_human_decision,
    produce_checkpoint_bound_candidate_bundle,
    produce_collapsed_live_approval,
    produce_collapsed_live_installation_capability,
    produce_collapsed_live_prompt_identity,
    produce_qualification_installation_capability,
    resolve_live_checkpoint_root_authority,
    seal_bound_collapsed_one_shot_go,
    seal_collapsed_live_preparation,
    validate_collapsed_installed_triple,
)
from f017_event06_durable_installation_transaction_v1 import (
    RACE_FAMILIES,
    TransactionPayload,
    commit_synthetic_non_authority_transaction,
)
from f017_event06_production_installation_v2 import FutureGoCapabilityV2
from f017_event06_sequence14_fixture_v1 import (
    ACCEPTANCE_PATH,
    AUTHORITY_PATH,
    HUMAN_RECORD_PATH,
    PROMPT_BYTES,
    PROMPT_PATH,
    build_sequence14_qualification,
)
from execute_f017_corrected_oracle_event_v12 import (
    validate_collapsed_installed_package_gate,
)

ROOT = Path(__file__).resolve().parents[2]
FIXED_NOW = 4_000_000_000_000_000_000


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _git_commit(repository: Path, paths: list[str], message: str) -> str:
    subprocess.run(["git", "add", "--", *paths], cwd=repository, check=True)
    environment = dict(os.environ)
    environment.update(
        GIT_AUTHOR_DATE="2001-01-01T00:00:00+0000",
        GIT_COMMITTER_DATE="2001-01-01T00:00:00+0000",
    )
    subprocess.run(
        ["git", "commit", "-q", "-m", message],
        cwd=repository,
        check=True,
        env=environment,
    )
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repository, text=True
    ).strip()


class MutationCampaign:
    def __init__(self) -> None:
        self.total = 0
        self.rejected = 0
        self.unexpected: list[str] = []
        self.categories: dict[str, int] = {}

    def reject(self, label: str, category: str, operation) -> None:
        self.total += 1
        self.categories[category] = self.categories.get(category, 0) + 1
        try:
            operation()
        except Exception:
            self.rejected += 1
            return
        self.unexpected.append(label)


def _wrong(field: str, value: object) -> object:
    if field.endswith("_sha256") or field == "nonce_sha256":
        return "z" * 64
    if field.endswith("_commit"):
        return "z" * 40
    if field.endswith("_path"):
        return "/absolute/substitution"
    if type(value) is bool:
        return 1
    if type(value) is int:
        return True
    return 7


def _semantic_substitution(field: str, value: object) -> object:
    if field.endswith("_sha256") or field == "nonce_sha256":
        return "a" * 64 if value != "a" * 64 else "b" * 64
    if field.endswith("_commit"):
        return "a" * 40 if value != "a" * 40 else "b" * 40
    if field.endswith("_path"):
        return f"Prompts/F017/substituted-{field}.json"
    if type(value) is bool:
        return not value
    if type(value) is int:
        return value + 1
    return f"SUBSTITUTED_{field.upper()}"


def _produce(package: dict[str, object], authority_commit: str):
    return produce_bound_sanitized_human_decision(
        prompt_control_authority=package["prompt_control"],
        authority_commit=authority_commit,
        authority_path=AUTHORITY_PATH,
        readiness=package["readiness"],
        now_unix_ns=FIXED_NOW,
        state=package["state"],
    )


def _commit_authority_mutation(
    package: dict[str, object], value: dict[str, object], label: str
) -> str:
    repository = package["prompt_control_root"]
    (repository / AUTHORITY_PATH).write_bytes(canonical_bytes(value))
    return _git_commit(repository, [AUTHORITY_PATH], label)


def _commit_record_mutation(
    package: dict[str, object], value: dict[str, object], label: str
) -> str:
    repository = package["prompt_control_root"]
    record = canonical_bytes(value)
    sidecar = f"{_sha(record)}  {Path(HUMAN_RECORD_PATH).name}\n".encode()
    (repository / HUMAN_RECORD_PATH).write_bytes(record)
    (repository / (HUMAN_RECORD_PATH + ".sha256")).write_bytes(sidecar)
    (repository / ACCEPTANCE_PATH).write_bytes(package["human"]["acceptance"])
    record_commit = _git_commit(
        repository,
        [HUMAN_RECORD_PATH, HUMAN_RECORD_PATH + ".sha256", ACCEPTANCE_PATH],
        label + " record",
    )
    authority = dict(package["human"]["authority_value"])
    authority.update(
        prompt_control_commit=record_commit,
        human_go_record_sha256=_sha(record),
        human_go_sidecar_sha256=_sha(sidecar),
        planner_acceptance_sha256=_sha(package["human"]["acceptance"]),
    )
    return _commit_authority_mutation(package, authority, label + " authority")


def _commit_acceptance_mutation(
    package: dict[str, object], value: dict[str, object], label: str
) -> str:
    repository = package["prompt_control_root"]
    record = package["human"]["record"]
    sidecar = package["human"]["sidecar"]
    acceptance = canonical_bytes(value)
    (repository / HUMAN_RECORD_PATH).write_bytes(record)
    (repository / (HUMAN_RECORD_PATH + ".sha256")).write_bytes(sidecar)
    (repository / ACCEPTANCE_PATH).write_bytes(acceptance)
    record_commit = _git_commit(
        repository,
        [HUMAN_RECORD_PATH, HUMAN_RECORD_PATH + ".sha256", ACCEPTANCE_PATH],
        label + " acceptance",
    )
    authority = dict(package["human"]["authority_value"])
    authority.update(
        prompt_control_commit=record_commit,
        planner_acceptance_sha256=_sha(acceptance),
    )
    return _commit_authority_mutation(package, authority, label + " authority")


def _single() -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="f017-seq14-single-") as directory:
        package = build_sequence14_qualification(
            Path(directory), now_unix_ns=FIXED_NOW
        )
        return {
            "human_authority_sha256": package["decision"].source_sha256,
            "collapsed_go_sha256": package["go"].source_sha256,
            "ids": dict(package["ids"]),
            "approval_sha256": package["approval"].source_sha256,
            "preparation_sha256": package["preparation"].source_sha256,
            "prompt_identity_sha256": package["identity"].source_sha256,
            "type_chain": [
                type(package[name]).__name__
                for name in (
                    "decision", "go", "approval", "preparation", "identity",
                    "root_authority", "bundle", "prepared", "target",
                    "transaction", "installed", "gate",
                )
            ],
            "gate": package["gate"].get("result"),
        }


def _field_mutations(
    campaign: MutationCampaign, package: dict[str, object]
) -> None:
    base_authority = dict(package["human"]["authority_value"])
    for field in HUMAN_AUTHORITY_FIELDS:
        missing = dict(base_authority)
        missing.pop(field)
        commit = _commit_authority_mutation(
            package, missing, f"authority missing {field}"
        )
        campaign.reject(
            f"authority_missing_{field}", "authority_fields", lambda c=commit: _produce(package, c)
        )
        wrong = dict(base_authority)
        wrong[field] = _wrong(field, wrong[field])
        commit = _commit_authority_mutation(
            package, wrong, f"authority wrong {field}"
        )
        campaign.reject(
            f"authority_wrong_{field}", "authority_types", lambda c=commit: _produce(package, c)
        )
        alias = dict(base_authority)
        alias[f"ALIAS_{field.upper()}"] = alias[field]
        commit = _commit_authority_mutation(
            package, alias, f"authority alias {field}"
        )
        campaign.reject(
            f"authority_alias_{field}", "alias_unknown", lambda c=commit: _produce(package, c)
        )
        semantic = dict(base_authority)
        semantic[field] = _semantic_substitution(field, semantic[field])
        commit = _commit_authority_mutation(
            package, semantic, f"authority semantic {field}"
        )
        campaign.reject(
            f"authority_semantic_{field}", "authority_semantics", lambda c=commit: _produce(package, c)
        )

    record_base = json.loads(package["human"]["record"])
    for field in HUMAN_GO_RECORD_FIELDS:
        missing = dict(record_base)
        missing.pop(field)
        commit = _commit_record_mutation(package, missing, f"record missing {field}")
        campaign.reject(
            f"record_missing_{field}", "record_fields", lambda c=commit: _produce(package, c)
        )
        wrong = dict(record_base)
        wrong[field] = _wrong(field, wrong[field])
        commit = _commit_record_mutation(package, wrong, f"record wrong {field}")
        campaign.reject(
            f"record_wrong_{field}", "record_types", lambda c=commit: _produce(package, c)
        )
        alias = dict(record_base)
        alias[f"ALIAS_{field.upper()}"] = alias[field]
        commit = _commit_record_mutation(package, alias, f"record alias {field}")
        campaign.reject(
            f"record_alias_{field}", "alias_unknown", lambda c=commit: _produce(package, c)
        )
        semantic = dict(record_base)
        semantic[field] = _semantic_substitution(field, semantic[field])
        commit = _commit_record_mutation(package, semantic, f"record semantic {field}")
        campaign.reject(
            f"record_semantic_{field}", "record_semantics", lambda c=commit: _produce(package, c)
        )

    acceptance_base = json.loads(package["human"]["acceptance"])
    for field in PLANNER_ACCEPTANCE_FIELDS:
        missing = dict(acceptance_base)
        missing.pop(field)
        commit = _commit_acceptance_mutation(
            package, missing, f"acceptance missing {field}"
        )
        campaign.reject(
            f"acceptance_missing_{field}", "acceptance_fields", lambda c=commit: _produce(package, c)
        )
        wrong = dict(acceptance_base)
        wrong[field] = _wrong(field, wrong[field])
        commit = _commit_acceptance_mutation(
            package, wrong, f"acceptance wrong {field}"
        )
        campaign.reject(
            f"acceptance_wrong_{field}", "acceptance_types", lambda c=commit: _produce(package, c)
        )
        alias = dict(acceptance_base)
        alias[f"ALIAS_{field.upper()}"] = alias[field]
        commit = _commit_acceptance_mutation(
            package, alias, f"acceptance alias {field}"
        )
        campaign.reject(
            f"acceptance_alias_{field}", "alias_unknown", lambda c=commit: _produce(package, c)
        )
        semantic = dict(acceptance_base)
        semantic[field] = _semantic_substitution(field, semantic[field])
        commit = _commit_acceptance_mutation(
            package, semantic, f"acceptance semantic {field}"
        )
        campaign.reject(
            f"acceptance_semantic_{field}", "acceptance_semantics", lambda c=commit: _produce(package, c)
        )


def _security_mutations(
    campaign: MutationCampaign, package: dict[str, object]
) -> None:
    artifacts = [
        package["prompt_control"], package["state"], package["decision"],
        package["approval"], package["preparation"], package["identity"],
        package["root_authority"], package["bundle"], package["prepared"],
        package["target"], package["installed"], package["gate"],
    ]
    for index, value in enumerate(artifacts):
        for operation_name, operation in (
            ("copy", copy.copy), ("deepcopy", copy.deepcopy), ("pickle", pickle.dumps)
        ):
            campaign.reject(
                f"closed_{index}_{operation_name}", "closed_types", lambda v=value, op=operation: op(v)
            )

    classes = (
        BoundSanitizedHumanDecisionV2,
        CollapsedLiveApprovalV2,
        CollapsedLivePreparationV2,
        CollapsedLivePromptIdentityV2,
        CollapsedInstallationEligibilityV2,
        CheckpointBoundCandidateBundleV2,
        QualificationCheckpointRootAuthorityV2,
        LiveCheckpointRootAuthorityV2,
        PreparedCollapsedInstallationV2,
        QualificationInstallationTargetV2,
        LiveInstallationTargetV2,
        QualificationInstallationCapabilityV2,
        CollapsedLiveInstallationCapabilityV2,
        CollapsedInstalledTripleV2,
        CollapsedPackageStartGateV2,
        QualificationPromptControlAuthorityV2,
        LivePromptControlAuthorityV2,
    )
    for cls in classes:
        campaign.reject(
            f"constructor_{cls.__name__}", "forged_types", lambda c=cls: c()
        )

    campaign.reject(
        "legacy_second_go_capability",
        "legacy_second_go",
        lambda: produce_collapsed_live_installation_capability(
            package["prepared"], package["bundle"], object.__new__(FutureGoCapabilityV2),
            target_leaf="legacy", expires_at_unix_ns=2**62, state=package["state"]
        ),
    )
    campaign.reject(
        "qualification_root_as_live",
        "mode_substitution",
        lambda: resolve_live_checkpoint_root_authority(
            package["decision"], state=package["state"]
        ),
    )
    campaign.reject(
        "qualification_target_as_live",
        "mode_substitution",
        lambda: produce_collapsed_live_installation_capability(
            package["prepared"], package["bundle"], package["target"],
            target_leaf="cross-mode", expires_at_unix_ns=2**62,
            state=package["state"],
        ),
    )

    public_wrong_args = (
        lambda: produce_collapsed_live_approval(object(), package["go"], package["readiness"], package["plan"], now_unix_ns=FIXED_NOW),
        lambda: produce_collapsed_live_approval(package["decision"], object(), package["readiness"], package["plan"], now_unix_ns=FIXED_NOW),
        lambda: seal_collapsed_live_preparation(object(), package["decision"], package["go"], package["readiness"], package["plan"]),
        lambda: seal_collapsed_live_preparation(package["approval"], object(), package["go"], package["readiness"], package["plan"]),
        lambda: produce_collapsed_live_prompt_identity(object(), package["go"], package["plan"], prompt_bytes=PROMPT_BYTES, prompt_repository_commit=package["human"]["prompt_commit"], prompt_repository_path=PROMPT_PATH),
        lambda: produce_checkpoint_bound_candidate_bundle(object(), package["identity"], package["go"], package["readiness"], package["plan"], package["root_authority"], state=package["state"]),
        lambda: produce_checkpoint_bound_candidate_bundle(package["preparation"], object(), package["go"], package["readiness"], package["plan"], package["root_authority"], state=package["state"]),
        lambda: prepare_collapsed_production_installation(object(), package["go"], package["approval"], package["preparation"], package["bundle"], package["readiness"], package["plan"], state=package["state"]),
        lambda: prepare_collapsed_production_installation(package["decision"], package["go"], object(), package["preparation"], package["bundle"], package["readiness"], package["plan"], state=package["state"]),
        lambda: validate_collapsed_installed_triple(object(), "leaf", package["prepared"], package["transaction"]),
        lambda: validate_collapsed_installed_triple(package["target"], "wrong-leaf", package["prepared"], package["transaction"]),
        lambda: validate_collapsed_installed_package_gate(object(), package["bundle"], package["plan"], state=package["state"]),
        lambda: validate_collapsed_installed_package_gate(package["installed"], object(), package["plan"], state=package["state"]),
        lambda: derive_production_event_identities(package["go"], repository_identity_census=frozenset(package["ids"].values())),
        lambda: commit_qualification_collapsed_installation(package["prepared"], object.__new__(QualificationInstallationCapabilityV2), state=package["state"]),
        lambda: commit_collapsed_live_installation(package["prepared"], object.__new__(CollapsedLiveInstallationCapabilityV2), state=package["state"]),
    )
    for index, operation in enumerate(public_wrong_args):
        campaign.reject(
            f"public_boundary_{index}", "public_boundary", operation
        )

    # Binding substitutions from another complete causal chain.
    with tempfile.TemporaryDirectory(prefix="f017-seq14-splice-") as directory:
        other = build_sequence14_qualification(
            Path(directory), now_unix_ns=FIXED_NOW + 10_000_000
        )
        splices = (
            lambda: seal_collapsed_live_preparation(package["approval"], other["decision"], package["go"], package["readiness"], package["plan"]),
            lambda: produce_collapsed_live_prompt_identity(other["preparation"], package["go"], package["plan"], prompt_bytes=PROMPT_BYTES, prompt_repository_commit=package["human"]["prompt_commit"], prompt_repository_path=PROMPT_PATH),
            lambda: produce_checkpoint_bound_candidate_bundle(package["preparation"], other["identity"], package["go"], package["readiness"], package["plan"], package["root_authority"], state=package["state"]),
            lambda: prepare_collapsed_production_installation(package["decision"], package["go"], package["approval"], package["preparation"], other["bundle"], package["readiness"], package["plan"], state=package["state"]),
            lambda: produce_qualification_installation_capability(package["prepared"], other["bundle"], package["target"], target_leaf="splice", expires_at_unix_ns=2**62),
            lambda: validate_collapsed_installed_package_gate(package["installed"], other["bundle"], package["plan"], state=package["state"]),
        )
        for index, operation in enumerate(splices):
            campaign.reject(f"causal_splice_{index}", "causal_splice", operation)

    with tempfile.TemporaryDirectory(prefix="f017-seq14-faults-") as directory:
        root = Path(directory).resolve()
        root.chmod(0o700)
        payloads = (TransactionPayload("candidate", "candidate.json", b"candidate"),)
        for index, family in enumerate(RACE_FAMILIES):
            campaign.reject(
                f"transaction_fault_{family}",
                "filesystem_fault",
                lambda f=family, i=index: commit_synthetic_non_authority_transaction(
                    root, f"fault-{i}", payloads, fault_stage=f
                ),
            )


def qualify() -> dict[str, object]:
    script = Path(__file__).resolve()
    reconstructions = []
    for _ in range(20):
        raw = subprocess.check_output(
            [sys.executable, str(script), "--single"], text=True
        )
        reconstructions.append(json.loads(raw))
    deterministic = len({canonical_bytes(item) for item in reconstructions}) == 1
    if not deterministic:
        raise AssertionError("fresh-process collapsed integration drift")

    with tempfile.TemporaryDirectory(prefix="f017-seq14-qualification-") as directory:
        package = build_sequence14_qualification(
            Path(directory), now_unix_ns=FIXED_NOW
        )
        campaign = MutationCampaign()
        _field_mutations(campaign, package)
        _security_mutations(campaign, package)
        if campaign.total < 200 or campaign.unexpected:
            raise AssertionError(
                f"mutation qualification: total={campaign.total} unexpected={campaign.unexpected}"
            )
        counters = dict(package["state"].snapshot())
        one_shot = dict(package["state"].one_shot_snapshot())
        forbidden = {
            name: counters[name]
            for name in (
                "sanitized_human_decisions_from_live_go",
                "collapsed_live_go_tokens",
                "canonical_live_reservations",
                "live_checkpoint_root_resolutions",
                "live_installation_commit_calls",
                "live_authorities_or_capabilities",
                "package_starts",
                "original_checkpoint_shard_opens",
                "original_checkpoint_identity_hash_reads",
                "original_checkpoint_payload_reads",
                "original_checkpoint_mmaps_or_tensor_reads",
                "numerical_operations",
                "event06_identities_instantiated",
                "event06_identities_consumed",
                "authorization_delta", "package_delta", "primary_delta", "secondary_delta",
                "p1_actions",
            )
        }
        if any(forbidden.values()):
            raise AssertionError(f"no-access counter changed: {forbidden}")
        return {
            "schema": "pulsarmlx.f017.event06-v12-sequence14-collapsed-live-installation-qualification/1.0.0",
            "real_public_end_to_end_composition": "PASS",
            "fresh_process_reconstructions": 20,
            "deterministic_reconstructions": 20,
            "distinct_reconstruction_sets": 1,
            "type_chain": reconstructions[0]["type_chain"],
            "eight_field_collapsed_go_drift": 0,
            "human_go_authenticity_binding": "PASS",
            "qualification_live_root_type_separation": "PASS",
            "checkpoint_bound_candidate_composition": "PASS",
            "collapsed_go_derived_installation_capability": "PASS",
            "legacy_second_go_authority_required": False,
            "installed_triple_and_package_gate_composition": "PASS",
            "mutation_campaign": {
                "total": campaign.total,
                "rejected": campaign.rejected,
                "unexpected_passes": len(campaign.unexpected),
                "categories": campaign.categories,
                "result": "PASS",
            },
            "observed_no_access_counters": forbidden,
            "one_shot_counters": one_shot,
            "original_checkpoint_access": "NONE",
            "event_06_executed": False,
            "historical_master_ledger": 175,
            "result": "PASS",
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--single", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = _single() if args.single else qualify()
    raw = canonical_bytes(result)
    if args.output is not None:
        args.output.write_bytes(raw)
    else:
        sys.stdout.buffer.write(raw + b"\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
