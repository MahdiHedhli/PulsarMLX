#!/usr/bin/env python3
"""Tiny deterministic fixtures for Sequence 8 implementation-local verification."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

from f017_canonical_serialization_v10 import canonical_bytes

ROOT = Path(__file__).resolve().parents[2]
INTERFACE_REL = (
    "specs/017-rust-native-inference-runtime/contracts/"
    "f017-corrected-oracle-event06-readiness-consumer-interface-v10.json"
)
MANIFEST_CONTRACT_REL = (
    "specs/017-rust-native-inference-runtime/contracts/"
    "f017-corrected-oracle-event06-readiness-authority-manifest-v8.json"
)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def bank(root: Path, relative: str, value: object) -> tuple[str, str]:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = canonical_bytes(value)
    path.write_bytes(raw)
    return relative, sha(raw)


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def build_readiness_fixture(root: Path) -> tuple[bytes, Path, dict[str, object]]:
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "F017 Fixture"], cwd=root, check=True)
    subprocess.run(
        ["git", "config", "user.email", "fixture.invalid@example.invalid"],
        cwd=root,
        check=True,
    )
    (root / "base.txt").write_text("sequence-8\n", encoding="utf-8")
    subprocess.run(["git", "add", "base.txt"], cwd=root, check=True)
    commit_environment = dict(os.environ)
    commit_environment.update(
        GIT_AUTHOR_DATE="2000-01-01T00:00:00+0000",
        GIT_COMMITTER_DATE="2000-01-01T00:00:00+0000",
    )
    subprocess.run(
        ["git", "commit", "-q", "-m", "fixture base"],
        cwd=root,
        check=True,
        env=commit_environment,
    )
    head = _git(root, "rev-parse", "HEAD")
    tree = _git(root, "rev-parse", "HEAD^{tree}")

    interface_path = root / INTERFACE_REL
    interface_path.parent.mkdir(parents=True, exist_ok=True)
    interface_path.write_bytes((ROOT / INTERFACE_REL).read_bytes())
    manifest_contract_path = root / MANIFEST_CONTRACT_REL
    manifest_contract_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_contract_path.write_bytes((ROOT / MANIFEST_CONTRACT_REL).read_bytes())
    interface = json.loads(interface_path.read_text(encoding="utf-8"))
    manifest_contract = json.loads(manifest_contract_path.read_text(encoding="utf-8"))
    roles = manifest_contract["required_roles"]

    reproduction_path, reproduction_sha = bank(
        root,
        "fixtures/challenge-reproduction.json",
        {"schema": "pulsarmlx.f017.fixture-reproduction/1.0.0", "result": "PASS"},
    )
    role_paths: dict[str, tuple[str, str]] = {}
    role_values: dict[str, dict[str, object]] = {}
    for role in roles:
        value: dict[str, object] = {
            "schema": f"pulsarmlx.f017.fixture-{role.replace('_', '-')}/1.0.0",
            "result": "PASS",
        }
        if role == "implementation_measurement":
            value.update(implementation_head=head, implementation_tree=tree)
        if role == "bridge_declaration":
            value["bridge_digest"] = "b" * 64
        if role == "challenge_result":
            value.update(
                reviewed_commit=head,
                reproduction_report_path=reproduction_path,
                reproduction_report_sha256=reproduction_sha,
            )
        if role == "opus_result":
            value["reviewed_commit"] = head
        role_values[role] = value

    role_values["readiness_interface"] = interface
    requirement_rules = {
        role: {"required": {"result": "PASS"}}
        for role in roles
        if role != "readiness_interface"
    }
    requirement_rules["readiness_interface"] = {
        "required": {"schema": interface["schema"]}
    }
    role_values["qualification_role_requirements"] = {
        "schema": "pulsarmlx.f017.fixture-qualification-role-requirements/1.0.0",
        "result": "PASS",
        "roles": requirement_rules,
    }
    for role in roles:
        relative = (
            INTERFACE_REL if role == "readiness_interface" else f"fixtures/{role}.json"
        )
        if role == "readiness_interface":
            role_paths[role] = (relative, sha(interface_path.read_bytes()))
        else:
            role_paths[role] = bank(root, relative, role_values[role])

    bindings = {
        role: {
            "binding_state": "FINAL_ACCEPTED",
            "path": role_paths[role][0],
            "sha256": role_paths[role][1],
        }
        for role in roles
    }
    manifest_value = {
        "schema": manifest_contract["manifest_schema"],
        "implementation_head": head,
        "implementation_tree": tree,
        "binding_count": len(roles),
        "bindings": bindings,
        "role_count": len(roles),
        "roles": roles,
        "result": "PASS",
    }
    manifest_path, manifest_sha = bank(
        root, "fixtures/authority-manifest.json", manifest_value
    )
    supersedes_path, supersedes_sha = bank(
        root,
        "fixtures/historical-readiness.json",
        {
            "schema": "pulsarmlx.f017.fixture-historical-readiness/1.0.0",
            "result": "HISTORICAL",
        },
    )

    defaults: dict[str, object] = {
        "boolean": False,
        "nonnegative_integer": 0,
        "git_object": head,
        "repository_path": "fixtures/unset.json",
        "sha256": "a" * 64,
        "string": "FIXTURE",
    }
    declaration: dict[str, object] = {}
    for category, names in interface["exact_types"].items():
        for name in names:
            declaration[name] = defaults[category]
    declaration.update(interface["exact_predicates"])
    declaration.update(
        implementation_head=head,
        implementation_tree=tree,
        review_head=head,
        bridge_digest="b" * 64,
        authority_manifest_path=manifest_path,
        authority_manifest_sha256=manifest_sha,
        supersedes_path=supersedes_path,
        supersedes_sha256=supersedes_sha,
        challenge_reproduction_sha256=reproduction_sha,
    )
    for role, (path, digest) in role_paths.items():
        declaration[f"{role}_path"] = path
        declaration[f"{role}_sha256"] = digest
    declaration["implementation_measurement_path"] = role_paths[
        "implementation_measurement"
    ][0]
    declaration["implementation_measurement_sha256"] = role_paths[
        "implementation_measurement"
    ][1]
    return canonical_bytes(declaration), interface_path, declaration


def execution_plan_value(
    candidate: object, readiness: object | None = None
) -> dict[str, object]:
    get = candidate.get
    shards = [
        {
            "filename": f"inert-shard-{ordinal}.bin",
            "size_bytes": 0,
            "sha256": hashlib.sha256(f"inert-{ordinal}".encode()).hexdigest(),
            "role": "IDENTITY_ONLY" if ordinal == 1 else "GRAPH_PAYLOAD",
        }
        for ordinal in range(1, 7)
    ]
    return {
        "schema": "pulsarmlx.f017.event06-v12-execution-plan/1.0.0",
        "package_attempt_id": get("package_attempt_id"),
        "primary_event_id": "F017-SEQUENCE08-INERT-PRIMARY",
        "secondary_event_id": "F017-SEQUENCE08-INERT-SECONDARY",
        "source_head": "1" * 40,
        "source_tree": "2" * 40,
        "implementation_measurement_sha256": "3" * 64,
        "tensor_catalog_path": "fixtures/inert-catalog.json",
        "tensor_catalog_sha256": "4" * 64,
        "primary_numerical_sha256": "5" * 64,
        "secondary_numerical_sha256": "6" * 64,
        "numerical_contract_path": "fixtures/inert-numerical.json",
        "numerical_contract_sha256": (
            readiness.get("numerical_contract_sha256")
            if readiness is not None
            else "7" * 64
        ),
        "result_authority_path": "fixtures/inert-result.json",
        "result_authority_sha256": (
            readiness.get("result_authority_sha256")
            if readiness is not None
            else "8" * 64
        ),
        "result_bundle_builder_sha256": "9" * 64,
        "comparison_authority_sha256": "a" * 64,
        "release_authority_sha256": "b" * 64,
        "accounting_authority_sha256": "c" * 64,
        "primary_target_source_sha256": "d" * 64,
        "secondary_target_source_sha256": "e" * 64,
        "shards": shards,
        "attempts": 1,
        "retries": 0,
        "resume": False,
    }
