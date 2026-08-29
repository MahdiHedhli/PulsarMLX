#!/usr/bin/env python3
"""Tiny repository fixture for Sequence 9 no-access qualification."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path

from f017_canonical_serialization_v10 import canonical_bytes
from f017_event06_sequence08_fixture_v1 import execution_plan_value


ROOT = Path(__file__).resolve().parents[2]
INTERFACE_REL = (
    "specs/017-rust-native-inference-runtime/contracts/"
    "f017-corrected-oracle-event06-readiness-consumer-interface-v11.json"
)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _bank(root: Path, relative: str, value: object) -> tuple[str, str]:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = canonical_bytes(value)
    path.write_bytes(raw)
    return relative, _sha(raw)


def _git(root: Path, *arguments: str) -> str:
    return subprocess.check_output(["git", *arguments], cwd=root, text=True).strip()


def build_readiness_fixture(
    root: Path, *, fixture_variant: str = "sequence-9"
) -> tuple[bytes, Path, dict[str, object]]:
    """Build a closed 86-field declaration without any checkpoint coordinate."""

    if not fixture_variant or not fixture_variant.isascii() or not fixture_variant.replace("-", "").isalnum():
        raise ValueError("fixture variant")

    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "F017 Fixture"], cwd=root, check=True)
    subprocess.run(
        ["git", "config", "user.email", "fixture.invalid@example.invalid"],
        cwd=root,
        check=True,
    )
    (root / "base.txt").write_text(f"{fixture_variant}\n", encoding="utf-8")
    subprocess.run(["git", "add", "base.txt"], cwd=root, check=True)
    environment = dict(os.environ)
    environment.update(
        GIT_AUTHOR_DATE="2000-01-01T00:00:00+0000",
        GIT_COMMITTER_DATE="2000-01-01T00:00:00+0000",
    )
    subprocess.run(
        ["git", "commit", "-q", "-m", "fixture base"],
        cwd=root,
        check=True,
        env=environment,
    )
    head = _git(root, "rev-parse", "HEAD")
    tree = _git(root, "rev-parse", "HEAD^{tree}")

    interface_path = root / INTERFACE_REL
    interface_path.parent.mkdir(parents=True, exist_ok=True)
    interface_path.write_bytes((ROOT / INTERFACE_REL).read_bytes())
    interface = json.loads(interface_path.read_text(encoding="utf-8"))
    manifest_contract_rel = interface["manifest_contract"]
    manifest_contract_path = root / manifest_contract_rel
    manifest_contract_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_contract_path.write_bytes((ROOT / manifest_contract_rel).read_bytes())
    manifest_contract = json.loads(manifest_contract_path.read_text(encoding="utf-8"))
    roles = manifest_contract["required_roles"]

    reproduction_path, reproduction_sha = _bank(
        root,
        "fixtures/challenge-reproduction.json",
        {"schema": "pulsarmlx.f017.fixture-reproduction/1.0.0", "result": "PASS"},
    )
    role_values: dict[str, dict[str, object]] = {}
    for role in roles:
        value: dict[str, object] = {
            "schema": f"pulsarmlx.f017.fixture-{role.replace('_', '-')}/1.0.0",
            "result": "PASS",
        }
        if role == "implementation_measurement":
            value.update(implementation_head=head, implementation_tree=tree)
        elif role == "bridge_declaration":
            value["bridge_digest"] = "b" * 64
        elif role == "challenge_result":
            value.update(
                reviewed_commit=head,
                reproduction_report_path=reproduction_path,
                reproduction_report_sha256=reproduction_sha,
            )
        elif role == "opus_result":
            value["reviewed_commit"] = head
        role_values[role] = value

    role_values["readiness_interface"] = interface
    role_rules = {role: {"required": {"result": "PASS"}} for role in roles}
    role_rules["readiness_interface"] = {"required": {"schema": interface["schema"]}}
    role_values["qualification_role_requirements"] = {
        "schema": "pulsarmlx.f017.fixture-qualification-role-requirements/1.0.0",
        "result": "PASS",
        "roles": role_rules,
    }

    role_paths: dict[str, tuple[str, str]] = {}
    for role in roles:
        if role == "readiness_interface":
            role_paths[role] = (INTERFACE_REL, _sha(interface_path.read_bytes()))
        elif role == "qualification_role_requirements":
            role_paths[role] = _bank(
                root, interface["qualification_role_requirements"], role_values[role]
            )
        else:
            role_paths[role] = _bank(root, f"fixtures/{role}.json", role_values[role])

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
    manifest_path, manifest_sha = _bank(
        root, "fixtures/authority-manifest.json", manifest_value
    )
    supersedes_path, supersedes_sha = _bank(
        root,
        "fixtures/historical-readiness.json",
        {"schema": "pulsarmlx.f017.fixture-historical/1.0.0", "result": "HISTORICAL"},
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
    for category, fields in interface["exact_types"].items():
        for field in fields:
            declaration[field] = defaults[category]
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
    return canonical_bytes(declaration), interface_path, declaration


__all__ = ["ROOT", "build_readiness_fixture", "execution_plan_value"]
