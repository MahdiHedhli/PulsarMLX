#!/usr/bin/env python3
"""Disposable future-GO fixture for Sequence 14 no-access qualification."""
from __future__ import annotations

import hashlib
import os
import subprocess
import time
from pathlib import Path

from f017_canonical_serialization_v10 import canonical_bytes
from f017_event06_collapsed_live_installation_v2 import (
    HUMAN_AUTHORITY_SCHEMA,
    HUMAN_GO_RECORD_DECISION,
    HUMAN_GO_RECORD_SCHEMA,
    HUMAN_GO_SCOPE,
    PLANNER_ACCEPTANCE_SCHEMA,
    TARGET_MACHINE,
    assert_collapsed_live_security_surface,
    begin_qualification_live_installation,
    commit_qualification_collapsed_installation,
    derive_production_event_identities,
    prepare_collapsed_production_installation,
    produce_bound_sanitized_human_decision,
    produce_checkpoint_bound_candidate_bundle,
    produce_collapsed_live_approval,
    produce_collapsed_live_prompt_identity,
    produce_qualification_checkpoint_root_authority,
    produce_qualification_installation_capability,
    produce_qualification_installation_target,
    produce_qualification_prompt_control_authority,
    seal_bound_collapsed_one_shot_go,
    seal_collapsed_live_preparation,
    validate_collapsed_installed_triple,
)
from f017_event06_execution_plan_v1 import validate_execution_plan
from f017_event06_readiness_authority_v3 import (
    validate_event06_readiness_declaration_v3,
)
from f017_event06_sequence08_fixture_v1 import execution_plan_value
from f017_event06_sequence09_fixture_v1 import build_readiness_fixture
from execute_f017_corrected_oracle_event_v12 import (
    validate_collapsed_installed_package_gate,
)

PROMPT_PATH = "Prompts/F017/Mac-Studio-M1-Ultra/future-event06-go.md"
HUMAN_RECORD_PATH = "Prompts/F017/Mac-Studio-M1-Ultra/future-human-go.json"
ACCEPTANCE_PATH = "Prompts/F017/Mac-Studio-M1-Ultra/future-human-go-acceptance.json"
AUTHORITY_PATH = "Prompts/F017/Mac-Studio-M1-Ultra/future-human-go-authority.json"
PROMPT_BYTES = b"F017 Event 06 future execution prompt\n"


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


class _PlanIds:
    def __init__(self, package_attempt_id: str) -> None:
        self.package_attempt_id = package_attempt_id

    def get(self, name: str) -> str:
        if name != "package_attempt_id":
            raise KeyError(name)
        return self.package_attempt_id


def human_authority_fixture(
    repository_root: Path,
    *,
    now_unix_ns: int,
    release_authority_sha256: str,
) -> dict[str, bytes | dict[str, object]]:
    repository_root.mkdir(mode=0o700)
    repository_root.chmod(0o700)
    subprocess.run(["git", "init", "-q"], cwd=repository_root, check=True)
    subprocess.run(
        ["git", "config", "user.name", "F017 Sequence 14 Fixture"],
        cwd=repository_root,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "fixture.invalid@example.invalid"],
        cwd=repository_root,
        check=True,
    )
    environment = dict(os.environ)
    environment.update(
        GIT_AUTHOR_DATE="2000-01-01T00:00:00+0000",
        GIT_COMMITTER_DATE="2000-01-01T00:00:00+0000",
    )
    prompt_path = repository_root / PROMPT_PATH
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_bytes(PROMPT_BYTES)
    subprocess.run(["git", "add", PROMPT_PATH], cwd=repository_root, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "fixture execution prompt"],
        cwd=repository_root,
        check=True,
        env=environment,
    )
    prompt_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repository_root, text=True
    ).strip()
    issued = now_unix_ns - 1_000_000
    expires = now_unix_ns + 120_000_000_000
    record = canonical_bytes({
        "schema": HUMAN_GO_RECORD_SCHEMA,
        "decision": HUMAN_GO_RECORD_DECISION,
        "target_machine": TARGET_MACHINE,
        "nonce_sha256": "7" * 64,
        "issued_at_unix_ns": issued,
        "expires_at_unix_ns": expires,
        "scope": HUMAN_GO_SCOPE,
    })
    sidecar = f"{_sha(record)}  {Path(HUMAN_RECORD_PATH).name}\n".encode()
    acceptance = canonical_bytes({
        "schema": PLANNER_ACCEPTANCE_SCHEMA,
        "human_go_record_sha256": _sha(record),
        "execution_prompt_commit": prompt_commit,
        "execution_prompt_path": PROMPT_PATH,
        "execution_prompt_sha256": _sha(PROMPT_BYTES),
        "accepted": True,
        "scope": HUMAN_GO_SCOPE,
    })
    for relative, raw in (
        (HUMAN_RECORD_PATH, record),
        (HUMAN_RECORD_PATH + ".sha256", sidecar),
        (ACCEPTANCE_PATH, acceptance),
    ):
        path = repository_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    subprocess.run(
        ["git", "add", HUMAN_RECORD_PATH, HUMAN_RECORD_PATH + ".sha256", ACCEPTANCE_PATH],
        cwd=repository_root,
        check=True,
    )
    subprocess.run(
        ["git", "commit", "-q", "-m", "fixture sanitized human GO"],
        cwd=repository_root,
        check=True,
        env=environment,
    )
    record_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repository_root, text=True
    ).strip()
    authority_value: dict[str, object] = {
        "schema": HUMAN_AUTHORITY_SCHEMA,
        "prompt_control_commit": record_commit,
        "human_go_record_path": HUMAN_RECORD_PATH,
        "human_go_record_sha256": _sha(record),
        "human_go_sidecar_sha256": _sha(sidecar),
        "planner_acceptance_path": ACCEPTANCE_PATH,
        "planner_acceptance_sha256": _sha(acceptance),
        "execution_prompt_commit": prompt_commit,
        "execution_prompt_path": PROMPT_PATH,
        "execution_prompt_sha256": _sha(PROMPT_BYTES),
        "release_authority_sha256": release_authority_sha256,
        "target_machine": TARGET_MACHINE,
        "one_shot_scope": HUMAN_GO_SCOPE,
        "issued_at_unix_ns": issued,
        "expires_at_unix_ns": expires,
        "go_disposition": "FRESH_UNCONSUMED",
    }
    authority_raw = canonical_bytes(authority_value)
    authority_file = repository_root / AUTHORITY_PATH
    authority_file.write_bytes(authority_raw)
    subprocess.run(["git", "add", AUTHORITY_PATH], cwd=repository_root, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "fixture human GO authority"],
        cwd=repository_root,
        check=True,
        env=environment,
    )
    authority_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repository_root, text=True
    ).strip()
    return {
        "authority_value": authority_value,
        "authority_raw": authority_raw,
        "authority_commit": authority_commit,
        "authority_path": AUTHORITY_PATH,
        "prompt_commit": prompt_commit,
        "record_commit": record_commit,
        "record": record,
        "sidecar": sidecar,
        "acceptance": acceptance,
    }


def build_sequence14_qualification(
    root: Path,
    *,
    now_unix_ns: int | None = None,
    readiness_variant: str = "sequence-14",
    reservation_root: Path | None = None,
) -> dict[str, object]:
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    root = root.resolve(strict=True)
    now = time.time_ns() if now_unix_ns is None else now_unix_ns
    readiness_root = root / "readiness"
    readiness_raw, readiness_interface, _ = build_readiness_fixture(
        readiness_root, fixture_variant=readiness_variant
    )
    readiness = validate_event06_readiness_declaration_v3(
        readiness_raw,
        repository_root=readiness_root,
        contract_path=readiness_interface,
    )
    prompt_control_root = root / "prompt-control-structural-twin"
    registry = (
        root / "reservation-structural-twin"
        if reservation_root is None
        else reservation_root.resolve(strict=True)
    )
    checkpoint_root = root / "checkpoint-structural-twin"
    installation_root = root / "installation-structural-twin"
    for directory in (registry, checkpoint_root, installation_root):
        directory.mkdir(mode=0o700, exist_ok=True)
        directory.chmod(0o700)
    state = begin_qualification_live_installation(reservation_root=registry)
    human = human_authority_fixture(
        prompt_control_root,
        now_unix_ns=now, release_authority_sha256=readiness.source_sha256
    )
    prompt_control = produce_qualification_prompt_control_authority(
        prompt_control_root
    )
    decision = produce_bound_sanitized_human_decision(
        prompt_control_authority=prompt_control,
        authority_commit=human["authority_commit"],
        authority_path=human["authority_path"],
        readiness=readiness,
        now_unix_ns=now,
        state=state,
    )
    go = seal_bound_collapsed_one_shot_go(
        decision,
        readiness,
        issued_at_unix_ns=now - 1_000_000,
        expires_at_unix_ns=now + 120_000_000_000,
        now_unix_ns=now,
        state=state,
    )
    ids = derive_production_event_identities(go)
    plan_value = execution_plan_value(_PlanIds(ids["package_attempt_id"]), readiness)
    plan_value["package_attempt_id"] = ids["package_attempt_id"]
    plan_value["primary_event_id"] = ids["primary_event_id"]
    plan_value["secondary_event_id"] = ids["secondary_event_id"]
    plan = validate_execution_plan(plan_value)
    approval = produce_collapsed_live_approval(
        decision, go, readiness, plan, now_unix_ns=now, state=state
    )
    preparation = seal_collapsed_live_preparation(
        approval, decision, go, readiness, plan, state=state
    )
    identity = produce_collapsed_live_prompt_identity(
        preparation,
        go,
        plan,
        prompt_bytes=PROMPT_BYTES,
        prompt_repository_commit=human["prompt_commit"],
        prompt_repository_path=PROMPT_PATH,
        state=state,
    )
    root_authority = produce_qualification_checkpoint_root_authority(
        checkpoint_root
    )
    bundle = produce_checkpoint_bound_candidate_bundle(
        preparation,
        identity,
        go,
        readiness,
        plan,
        root_authority,
        state=state,
    )
    prepared = prepare_collapsed_production_installation(
        decision,
        go,
        approval,
        preparation,
        bundle,
        readiness,
        plan,
        state=state,
    )
    target = produce_qualification_installation_target(installation_root)
    capability = produce_qualification_installation_capability(
        prepared,
        bundle,
        target,
        target_leaf="event06-v12-qualification-installation",
        expires_at_unix_ns=now + 120_000_000_000,
    )
    transaction = commit_qualification_collapsed_installation(
        prepared, capability, state=state
    )
    installed = validate_collapsed_installed_triple(
        target,
        "event06-v12-qualification-installation",
        prepared,
        transaction,
    )
    gate = validate_collapsed_installed_package_gate(
        installed, bundle, plan, state=state
    )
    assert_collapsed_live_security_surface(
        decision,
        approval,
        preparation,
        identity,
        bundle,
        prepared,
        installed,
        gate,
    )
    return {
        "readiness": readiness,
        "state": state,
        "human": human,
        "prompt_control": prompt_control,
        "prompt_control_root": prompt_control_root,
        "decision": decision,
        "go": go,
        "ids": ids,
        "plan": plan,
        "approval": approval,
        "preparation": preparation,
        "identity": identity,
        "root_authority": root_authority,
        "bundle": bundle,
        "prepared": prepared,
        "target": target,
        "capability": capability,
        "transaction": transaction,
        "installed": installed,
        "gate": gate,
    }


__all__ = [
    "build_sequence14_qualification",
    "human_authority_fixture",
]
