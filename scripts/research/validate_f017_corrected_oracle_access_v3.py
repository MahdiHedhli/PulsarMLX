#!/usr/bin/env python3
"""Two-phase validator/authorizer for corrected-oracle authorization v3."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from f017_corrected_oracle_authorization_v3 import (
    PRIMARY_ROLE,
    SCHEMA,
    SECONDARY_ROLE,
    canonical_bytes,
    load_and_validate,
    sha256_bytes,
    sha256_path,
    strict_bytes,
    strict_path,
    validate_document,
)

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_RELATIVE = Path("specs/017-rust-native-inference-runtime/contracts/f017-corrected-full-checkpoint-oracle-scientific-access-v3.json")
APPROVAL_SCHEMA = "pulsarmlx.f017.corrected-oracle-operator-approval/3.0.0"
PREFLIGHT_SCHEMA = "pulsarmlx.f017.corrected-oracle-memory-preflight/3.0.0"
MINT_EVIDENCE_SCHEMA = "pulsarmlx.f017.corrected-oracle-two-phase-mint-evidence/1.0.0"
APPROVAL_KEYS = {
    "schema", "approval_id", "decision", "branch", "contract_sha256",
    "live_authorization_id", "primary_event_id", "secondary_event_id",
    "package_state_root", "checkpoint_root", "attempts", "retries", "resume",
    "operator_identity", "approved_at_utc", "new_go", "prior_go_reused",
    "p1_attempt_2", "authorization_survives_bound_byte_change",
}


def _bank(path: Path, value: dict, mode: int = 0o400) -> str:
    data = canonical_bytes(value)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    with os.fdopen(descriptor, "wb") as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())
    parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    quarantined_install_sha = None
    try:
        os.fsync(parent)
        read_descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
        with os.fdopen(read_descriptor, "rb") as source:
            observed = source.read()
    finally:
        os.close(parent)
    if observed != data or strict_bytes(observed) != value:
        raise ValueError("exact installed readback mismatch")
    return sha256_bytes(observed)


def exact_contract(path: Path, repo: Path, *, production: bool) -> tuple[Path, dict]:
    supplied = (path if path.is_absolute() else repo / path).absolute()
    if production:
        expected = (repo / CONTRACT_RELATIVE).absolute()
        if supplied != expected:
            raise ValueError("canonical production contract path required")
    if any(item.is_symlink() for item in (supplied, *supplied.parents)):
        raise ValueError("contract symlink prohibited")
    canonical = supplied.resolve(strict=True)
    return canonical, strict_path(canonical)


def validate_approval(approval: dict, contract_path: Path, contract: dict, *, production: bool) -> None:
    if set(approval) != APPROVAL_KEYS or approval["schema"] != APPROVAL_SCHEMA:
        raise ValueError("operator approval census")
    if approval["decision"] != "GO_CORRECTED_FULL_CHECKPOINT_ORACLE_EVENT_V3":
        raise ValueError("operator decision")
    if approval["branch"] != contract["branch"] or approval["contract_sha256"] != sha256_path(contract_path):
        raise ValueError("operator contract binding")
    for key in ("live_authorization_id", "primary_event_id", "secondary_event_id", "operator_identity", "approved_at_utc"):
        if not isinstance(approval[key], str) or not approval[key]:
            raise ValueError(f"approval {key}")
    if approval["attempts"] != 1 or approval["retries"] != 0 or type(approval["resume"]) is not bool or approval["resume"]:
        raise ValueError("approval one-shot lifecycle")
    if approval["new_go"] is not True or approval["prior_go_reused"] is not False:
        raise ValueError("approval GO generation")
    if approval["p1_attempt_2"] != "PROHIBITED" or approval["authorization_survives_bound_byte_change"] is not False:
        raise ValueError("approval safety boundary")
    if not Path(approval["package_state_root"]).is_absolute() or not Path(approval["checkpoint_root"]).is_absolute():
        raise ValueError("approval absolute roots")
    if production and approval["operator_identity"] == "SYNTHETIC_QUALIFICATION":
        raise ValueError("synthetic operator cannot authorize production")


def validate_preflight(report: dict, contract_path: Path, contract: dict) -> tuple[int, int]:
    expected = {
        "schema", "result", "branch", "implementation_head", "git_head",
        "local_remote_parity", "worktree_clean", "contract_sha256", "coordinator_sha256",
        "memory_observer_sha256", "machine_brand", "architecture", "minimum_free_bytes",
        "observation", "state_created", "authorization_created", "checkpoint_shard_opens",
        "checkpoint_identity_hash_reads", "checkpoint_payload_reads",
    }
    if set(report) != expected or report["schema"] != PREFLIGHT_SCHEMA or report["result"] != "PASS":
        raise ValueError("preflight schema/result")
    if report["contract_sha256"] != sha256_path(contract_path) or report["coordinator_sha256"] != contract["authorization_bindings"]["event_coordinator_sha256"]:
        raise ValueError("preflight execution binding")
    if report["state_created"] or report["authorization_created"] or report["checkpoint_shard_opens"] != 0 or report["checkpoint_identity_hash_reads"] != 0 or report["checkpoint_payload_reads"] != 0:
        raise ValueError("preflight side effect")
    observation = report["observation"]
    for key in ("observed_at_unix_ns", "available_bytes"):
        if type(observation.get(key)) is not int or observation[key] <= 0:
            raise ValueError("preflight memory observation")
    age = time.time_ns() - observation["observed_at_unix_ns"]
    if age < 0 or age > contract["memory_preflight"]["sample_freshness_seconds"] * 1_000_000_000:
        raise ValueError("preflight freshness")
    if observation["available_bytes"] < contract["memory_preflight"]["minimum_free_bytes"]:
        raise ValueError("preflight memory floor")
    return observation["observed_at_unix_ns"], observation["available_bytes"]


def _require_unused_live_identities(approval: dict, approval_path: Path) -> None:
    identities = {
        approval["live_authorization_id"], approval["primary_event_id"],
        approval["secondary_event_id"],
    }
    roots = [
        ROOT / "docs/architecture/reviews/evidence",
        Path.home() / ".local/share/pulsarmlx/f017",
    ]
    for root in roots:
        if not root.is_dir() or root.is_symlink():
            continue
        for path in root.rglob("*.json"):
            if path.resolve(strict=True) == approval_path.resolve(strict=True):
                continue
            try:
                data = read_regular_bytes(path)
            except (OSError, ValueError):
                continue
            if any(identity.encode() in data for identity in identities):
                raise ValueError(f"previously used live identity: {path}")


def build_candidate(inert: dict, contract_path: Path, contract: dict, approval_path: Path,
                    preflight_path: Path, checkpoint_root: Path, package_root: Path,
                    *, scope: str) -> dict:
    validate_document(inert, contract, ROOT, require_live=False, expected_scope=scope,
                      contract_sha256=sha256_path(contract_path))
    approval = strict_path(approval_path)
    validate_approval(approval, contract_path, contract, production=scope == "PRODUCTION")
    if scope == "PRODUCTION":
        _require_unused_live_identities(approval, approval_path)
    report = strict_path(preflight_path)
    observed_at, available = validate_preflight(report, contract_path, contract)
    if checkpoint_root.resolve(strict=True) != Path(approval["checkpoint_root"]):
        raise ValueError("approval checkpoint root")
    if package_root != Path(approval["package_state_root"]):
        raise ValueError("approval package root")
    if package_root.exists() or package_root.is_symlink():
        raise ValueError("unused package root required")
    primary_root = package_root / "primary"
    secondary_root = package_root / "secondary"
    candidate = json.loads(json.dumps(inert))
    candidate.update({
        "state": "AUTHORIZED",
        "live": True,
        "authorization_id": approval["live_authorization_id"],
        "checkpoint_root": str(checkpoint_root.resolve(strict=True)),
        "package_state_root": str(package_root),
        "package_output_root": str(package_root),
        "operator_approval_sha256": sha256_path(approval_path),
        "memory_preflight_sha256": sha256_path(preflight_path),
        "memory_observed_at_unix_ns": observed_at,
        "memory_available_bytes": available,
        "candidate_nonce": hashlib.sha256(
            (sha256_path(approval_path) + approval["live_authorization_id"] + approval["primary_event_id"] + approval["secondary_event_id"]).encode()
        ).hexdigest(),
    })
    candidate["primary"].update({
        "event_id": approval["primary_event_id"],
        "state_root": str(primary_root),
        "output_root": str(primary_root),
    })
    candidate["secondary"].update({
        "event_id": approval["secondary_event_id"],
        "state_root": str(secondary_root),
        "output_root": str(secondary_root),
    })
    validate_document(candidate, contract, ROOT, require_live=True, expected_scope=scope,
                      contract_sha256=sha256_path(contract_path))
    return candidate


def _run_consumer(script: Path, candidate: Path, contract_path: Path, catalog: Path,
                  checkpoint_root: Path, report: Path) -> None:
    subprocess.run(
        [sys.executable, str(script), "validate-live-authorization", str(candidate),
         str(contract_path), str(catalog), str(checkpoint_root), str(report)],
        cwd=ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        shell=False, check=True, timeout=30,
    )


def two_phase_install(candidate: dict, contract_path: Path, contract: dict,
                      checkpoint_root: Path, output: Path, evidence_output: Path,
                      report_directory: Path) -> dict:
    if output.exists() or output.is_symlink() or evidence_output.exists() or evidence_output.is_symlink():
        raise ValueError("unused authorization/evidence outputs required")
    report_directory.mkdir(mode=0o700, parents=False, exist_ok=False)
    candidate_bytes = canonical_bytes(candidate)
    candidate_sha = sha256_bytes(candidate_bytes)
    candidate_path = report_directory / "candidate.json"
    descriptor = os.open(candidate_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
    with os.fdopen(descriptor, "wb") as candidate_file:
        candidate_file.write(candidate_bytes)
        candidate_file.flush()
        os.fsync(candidate_file.fileno())
    directory_fd = os.open(report_directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    os.fsync(directory_fd)
    os.close(directory_fd)
    primary_report = report_directory / "primary-validation.json"
    secondary_report = report_directory / "secondary-validation.json"
    catalog = (ROOT / candidate["checkpoint_catalog_path"]).resolve(strict=True)
    quarantined_install_sha = None
    try:
        _run_consumer(ROOT / contract["bindings"]["primary"]["path"], candidate_path, contract_path, catalog, checkpoint_root, primary_report)
        _run_consumer(ROOT / contract["bindings"]["secondary"]["path"], candidate_path, contract_path, catalog, checkpoint_root, secondary_report)
        primary = strict_path(primary_report)
        secondary = strict_path(secondary_report)
        if primary["authorization_sha256"] != candidate_sha or secondary["authorization_sha256"] != candidate_sha:
            raise ValueError("consumer candidate SHA mismatch")
        if primary["consumer_role"] != PRIMARY_ROLE or secondary["consumer_role"] != SECONDARY_ROLE:
            raise ValueError("consumer validation role mismatch")
        installed_sha = _bank(output, candidate)
        installed_bytes = read_regular_bytes(output)
        if installed_sha != candidate_sha or installed_bytes != candidate_bytes:
            raise ValueError("candidate/install byte identity")
        installed_authority = load_and_validate(output, contract_path, ROOT, require_live=True)
        if installed_authority.sha256 != candidate_sha:
            raise ValueError("installed authorization strict revalidation")
        result = "PASS"
        error = None
    except Exception as exc:
        result = "FAIL"
        error = f"{type(exc).__name__}:{exc}"
        if output.exists():
            quarantined = report_directory / "failed-installed-authorization.invalid"
            os.rename(output, quarantined)
            quarantine_fd = os.open(report_directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            os.fsync(quarantine_fd)
            os.close(quarantine_fd)
            quarantined_install_sha = sha256_path(quarantined)
    evidence = {
        "schema": MINT_EVIDENCE_SCHEMA,
        "result": result,
        "candidate_sha256": candidate_sha,
        "installed_authorization_sha256": sha256_path(output) if output.is_file() else None,
        "candidate_installed_byte_identity": output.is_file() and read_regular_bytes(output) == candidate_bytes,
        "quarantined_install_sha256": quarantined_install_sha,
        "primary_validation_report_sha256": sha256_path(primary_report) if primary_report.is_file() else None,
        "secondary_validation_report_sha256": sha256_path(secondary_report) if secondary_report.is_file() else None,
        "checkpoint_shard_opens": 0,
        "checkpoint_identity_hash_reads": 0,
        "checkpoint_mmaps": 0,
        "checkpoint_tensor_reads": 0,
        "state_created": False,
        "error": error,
    }
    _bank(evidence_output, evidence)
    if candidate_path.is_file() and not candidate_path.is_symlink():
        candidate_path.unlink()
        report_fd = os.open(report_directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        os.fsync(report_fd)
        os.close(report_fd)
    if result != "PASS":
        raise ValueError(error)
    return evidence


def read_regular_bytes(path: Path) -> bytes:
    from f017_corrected_oracle_authorization_v3 import read_regular_nofollow
    return read_regular_nofollow(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("validate")
    check.add_argument("authorization", type=Path)
    check.add_argument("contract", type=Path)
    check.add_argument("repo", type=Path)
    check.add_argument("--require-live", action="store_true")
    mint = sub.add_parser("authorize-live")
    mint.add_argument("inert", type=Path)
    mint.add_argument("contract", type=Path)
    mint.add_argument("repo", type=Path)
    mint.add_argument("operator_approval", type=Path)
    mint.add_argument("preflight_report", type=Path)
    mint.add_argument("checkpoint_root", type=Path)
    mint.add_argument("package_root", type=Path)
    mint.add_argument("output", type=Path)
    mint.add_argument("evidence_output", type=Path)
    mint.add_argument("report_directory", type=Path)
    arguments = parser.parse_args()
    repo = arguments.repo.resolve()
    if repo != ROOT:
        raise SystemExit("repository root mismatch")
    production = arguments.command == "authorize-live"
    contract_path, contract = exact_contract(arguments.contract, repo, production=production)
    if arguments.command == "validate":
        load_and_validate(arguments.authorization, contract_path, repo, require_live=arguments.require_live)
        print("PASS")
        return 0
    if os.environ.get("F017_OPERATOR_MINT_CORRECTED_ORACLE_V3") != "I_UNDERSTAND_THIS_OPENS_THE_ORIGINAL_CHECKPOINT_ON_EXECUTION":
        raise SystemExit("operator mint environment missing")
    inert = strict_path(arguments.inert)
    candidate = build_candidate(
        inert, contract_path, contract, arguments.operator_approval,
        arguments.preflight_report, arguments.checkpoint_root, arguments.package_root,
        scope="PRODUCTION",
    )
    two_phase_install(candidate, contract_path, contract, arguments.checkpoint_root,
                      arguments.output, arguments.evidence_output, arguments.report_directory)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
