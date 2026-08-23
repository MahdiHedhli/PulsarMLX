#!/usr/bin/env python3
"""Handshake-first coordinator for corrected-oracle scientific events v3."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from f017_corrected_oracle_authorization_v3 import (
    PRIMARY_ROLE,
    SECONDARY_ROLE,
    canonical_bytes,
    load_and_validate,
    read_regular_nofollow,
    sha256_bytes,
    sha256_path,
    strict_bytes,
    strict_path,
)
from f017_macos_memory_observation_v1 import observe_vm_stat

ROOT = Path(__file__).resolve().parents[2]
MINIMUM_FREE_BYTES = 17_179_869_184
PREFLIGHT_SCHEMA = "pulsarmlx.f017.corrected-oracle-memory-preflight/3.0.0"
HANDSHAKE_SCHEMA = "pulsarmlx.f017.corrected-oracle-consumer-handshake/1.0.0"


def bank(path: Path, value: dict, mode: int = 0o400) -> str:
    data = canonical_bytes(value)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    with os.fdopen(descriptor, "wb") as output:
        output.write(data)
        output.flush()
        os.fsync(output.fileno())
    parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(parent)
        read_descriptor = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
        with os.fdopen(read_descriptor, "rb") as source:
            observed = source.read()
    finally:
        os.close(parent)
    if observed != data or strict_bytes(observed) != value:
        raise ValueError("exact descriptor-relative readback mismatch")
    return sha256_bytes(observed)


def repository_authority(contract: dict) -> dict:
    def git(*arguments: str) -> str:
        return subprocess.run(
            ["/usr/bin/git", *arguments], cwd=ROOT, check=True, text=True,
            capture_output=True, timeout=10, stdin=subprocess.DEVNULL,
        ).stdout.strip()
    if Path(git("rev-parse", "--show-toplevel")).resolve(strict=True) != ROOT:
        raise ValueError("repository root")
    head = git("rev-parse", "HEAD")
    if git("status", "--porcelain=v1", "--untracked-files=all"):
        raise ValueError("worktree not clean")
    if subprocess.run(
        ["/usr/bin/git", "merge-base", "--is-ancestor", contract["implementation_head"], head],
        cwd=ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, timeout=10,
    ).returncode != 0:
        raise ValueError("implementation head not ancestor")
    if git("rev-parse", f"refs/remotes/origin/{contract['branch']}") != head:
        raise ValueError("local/remote parity")
    if git("branch", "--show-current") != contract["branch"]:
        raise ValueError("authoritative branch")
    return {"git_head": head, "local_remote_parity": True, "worktree_clean": True}


def preflight(contract_path: Path, output: Path | None = None) -> dict:
    contract = strict_path(contract_path)
    bindings = contract["authorization_bindings"]
    coordinator = ROOT / contract["bindings"]["event_coordinator"]["path"]
    observer = ROOT / contract["bindings"]["memory_observer"]["path"]
    if Path(__file__).resolve(strict=True) != coordinator.resolve(strict=True) or sha256_path(coordinator) != bindings["event_coordinator_sha256"]:
        raise ValueError("coordinator identity")
    if sha256_path(observer) != bindings["memory_observer_sha256"]:
        raise ValueError("memory observer identity")
    repository = repository_authority(contract)
    brand = subprocess.run(
        ["/usr/sbin/sysctl", "-n", "machdep.cpu.brand_string"], check=True,
        text=True, capture_output=True, timeout=5, stdin=subprocess.DEVNULL,
    ).stdout.rstrip("\r\n")
    if brand != "Apple M1 Ultra" or platform.machine() != "arm64":
        raise ValueError("machine identity")
    observed = observe_vm_stat()
    minimum = contract["memory_preflight"]["minimum_free_bytes"]
    if minimum != MINIMUM_FREE_BYTES or observed.available_bytes < minimum:
        raise ValueError("memory floor")
    report = {
        "schema": PREFLIGHT_SCHEMA, "result": "PASS", "branch": contract["branch"],
        "implementation_head": contract["implementation_head"], "contract_sha256": sha256_path(contract_path),
        "coordinator_sha256": sha256_path(coordinator), "memory_observer_sha256": sha256_path(observer),
        **repository, "machine_brand": brand, "architecture": platform.machine(),
        "minimum_free_bytes": minimum, "observation": observed.as_dict(),
        "state_created": False, "authorization_created": False,
        "checkpoint_shard_opens": 0, "checkpoint_identity_hash_reads": 0,
        "checkpoint_payload_reads": 0,
    }
    if output is not None:
        bank(output, report)
    return report


def _run_report(script: Path, command: str, arguments: list[Path], output: Path) -> dict:
    subprocess.run(
        [sys.executable, str(script), command, *map(str, arguments), str(output)],
        cwd=ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        shell=False, check=True, timeout=30,
    )
    return strict_path(output)


def handshake(authorization_path: Path, contract_path: Path, catalog: Path,
              checkpoint_root: Path, output: Path, *, scope: str) -> dict:
    authority = load_and_validate(
        authorization_path, contract_path, ROOT, require_live=True,
        expected_scope=scope,
    )
    contract = strict_path(contract_path)
    if output.exists() or output.is_symlink():
        raise ValueError("unused handshake output required")
    with tempfile.TemporaryDirectory(prefix="f017-handshake-", dir=output.parent) as directory:
        temporary = Path(directory)
        reports = {}
        for name, role in (("primary", PRIMARY_ROLE), ("secondary", SECONDARY_ROLE)):
            script = ROOT / contract["bindings"][name]["path"]
            capability_path = temporary / f"{name}-capability.json"
            validation_path = temporary / f"{name}-validation.json"
            capability = _run_report(script, "capability", [contract_path], capability_path)
            validation = _run_report(
                script, "validate-live-authorization",
                [authorization_path, contract_path, catalog, checkpoint_root], validation_path,
            )
            expected_capability = contract["consumer_capabilities"][name]
            if sha256_bytes(canonical_bytes(capability)) != expected_capability["sha256"]:
                raise ValueError(f"{name} capability report mismatch")
            if validation["result"] != "PASS" or validation["consumer_role"] != role or validation["authorization_sha256"] != authority.sha256:
                raise ValueError(f"{name} authorization handshake")
            reports[name] = {
                "capability_sha256": sha256_path(capability_path),
                "validation_report_sha256": sha256_path(validation_path),
                "event_id": validation["event_id"],
                "producer_sha256": validation["producer_sha256"],
            }
    result = {
        "schema": HANDSHAKE_SCHEMA,
        "result": "PASS",
        "authorization_id": authority.document["authorization_id"],
        "authorization_sha256": authority.sha256,
        "primary": reports["primary"],
        "secondary": reports["secondary"],
        "checkpoint_shard_opens_before_handshake": 0,
        "checkpoint_identity_hash_reads_before_handshake": 0,
        "checkpoint_mmaps_before_handshake": 0,
        "checkpoint_tensor_reads_before_handshake": 0,
        "package_state_created_before_handshake": False,
    }
    bank(output, result)
    return result


def _identity_event(directory: Path, sequence: int, auth: dict, kind: str,
                    authority: str, result: str, size: int = 0,
                    digest: str | None = None) -> None:
    bank(directory / f"{sequence:08}.json", {
        "schema": "pulsarmlx.f017.corrected-oracle-checkpoint-identity-event/2.0.0",
        "sequence": sequence, "authorization_id": auth["authorization_id"],
        "owner_pid": os.getpid(), "kind": kind, "authority_id": authority,
        "result": result, "size_bytes": size, "sha256": digest,
        "timestamp_ns": time.time_ns(),
    })


def verify_checkpoint_identity(checkpoint_root: Path, auth: dict, package_root: Path) -> str:
    event_root = package_root / "checkpoint-identity-events"
    event_root.mkdir(mode=0o700)
    sequence = 0
    observed = []
    for expected in auth["shards"]:
        name = expected["filename"]
        _identity_event(event_root, sequence, auth, "SHARD_IDENTITY_OPEN_ATTEMPT", name, "STARTED_READ_ONLY_NOFOLLOW")
        sequence += 1
        descriptor = None
        try:
            descriptor = os.open(checkpoint_root / name, os.O_RDONLY | os.O_NOFOLLOW)
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_size != expected["size_bytes"]:
                raise ValueError("shard file/size identity")
            _identity_event(event_root, sequence, auth, "SHARD_IDENTITY_OPEN_RESULT", name, "PASS", info.st_size)
            sequence += 1
            digest = hashlib.sha256()
            total = 0
            _identity_event(event_root, sequence, auth, "SHARD_IDENTITY_HASH_ATTEMPT", name, "STARTED", info.st_size)
            sequence += 1
            while total < info.st_size:
                chunk = os.pread(descriptor, min(1024 * 1024, info.st_size - total), total)
                if not chunk:
                    raise ValueError("short shard identity read")
                digest.update(chunk)
                total += len(chunk)
            actual = digest.hexdigest()
            if actual != expected["sha256"]:
                raise ValueError("shard SHA mismatch")
            _identity_event(event_root, sequence, auth, "SHARD_IDENTITY_HASH_RESULT", name, "PASS", total, actual)
            sequence += 1
            observed.append(dict(expected))
        except Exception as exc:
            _identity_event(event_root, sequence, auth, "SHARD_IDENTITY_FAILURE", name, f"FAIL_{type(exc).__name__}")
            sequence += 1
            raise
        finally:
            if descriptor is not None:
                os.close(descriptor)
                _identity_event(event_root, sequence, auth, "SHARD_IDENTITY_CLOSE", name, "PASS")
                sequence += 1
    return bank(package_root / "checkpoint-identity.json", {
        "schema": "pulsarmlx.f017.corrected-oracle-checkpoint-identity/2.0.0",
        "authorization_id": auth["authorization_id"], "owner_pid": os.getpid(),
        "shards": observed, "event_count": sequence, "result": "PASS",
    })


def _consumer_start(root: Path, auth: dict, grant: dict) -> tuple[str, str]:
    root.mkdir(mode=0o700, parents=False, exist_ok=False)
    value = {
        "schema": "pulsarmlx.f017.corrected-oracle-consumer-start/1.0.0",
        "authorization_id": auth["authorization_id"], "event_id": grant["event_id"],
        "consumer_role": grant["role"], "owner_pid": os.getpid(),
        "started_ns": time.time_ns(), "attempts": 1, "retries": 0, "resume": False,
    }
    return bank(root / "claim.json", value), bank(root / "durable-start.json", value)


def _consumer_terminal(root: Path, auth: dict, grant: dict, start_sha: str,
                       result_path: Path, classification: str, error: str | None) -> tuple[str, str]:
    receipt = {
        "schema": "pulsarmlx.f017.corrected-oracle-consumer-receipt/1.0.0",
        "authorization_id": auth["authorization_id"], "event_id": grant["event_id"],
        "consumer_role": grant["role"], "start_sha256": start_sha,
        "result_sha256": sha256_path(result_path) if result_path.is_file() else None,
        "classification": classification, "error": error,
        "event_delta": 1, "completed_ns": time.time_ns(),
    }
    receipt_sha = bank(root / "receipt.json", receipt)
    terminal_sha = bank(root / "terminal.json", {
        "schema": "pulsarmlx.f017.corrected-oracle-consumer-terminal/1.0.0",
        "authorization_id": auth["authorization_id"], "event_id": grant["event_id"],
        "receipt_sha256": receipt_sha, "classification": classification,
        "retry_permitted": False, "resume_permitted": False, "terminal_ns": time.time_ns(),
    })
    return receipt_sha, terminal_sha


def _access_census(package_root: Path, auth: dict, catalog: Path, geometry: dict) -> dict:
    from execute_f017_corrected_oracle_event_v2 import graph_tensor_names
    records = strict_path(catalog)["tensors"]
    catalog_names = {item["name"] for item in records}
    expected = graph_tensor_names(geometry)
    if not expected.issubset(catalog_names):
        raise ValueError("graph tensor absent from catalog")
    by_name = {item["name"]: item for item in records}
    expected_shards = {by_name[name]["file"] for name in expected}
    authorized_shards = {item["filename"] for item in auth["shards"]}
    if not expected_shards.issubset(authorized_shards):
        raise ValueError("graph shard absent from authority")
    consumers = {}
    for name, role in (("primary", PRIMARY_ROLE), ("secondary", SECONDARY_ROLE)):
        directory = Path(auth[name]["state_root"]) / "access-events"
        events = [strict_path(path) for path in sorted(directory.glob("*.json"))]
        if [event["sequence"] for event in events] != list(range(len(events))):
            raise ValueError("access sequence discontinuity")
        if any(event["authorization_id"] != auth["authorization_id"] or event["consumer"] != role for event in events):
            raise ValueError("access authority mismatch")
        resolved = {event["tensor_name"] for event in events if event["kind"] == "TENSOR_RESOLUTION"}
        opened = {event["authority_id"] for event in events if event["kind"] == "SHARD_OPEN_RESULT" and event["result"] == "PASS_READ_ONLY_NOFOLLOW"}
        if resolved != expected or opened != expected_shards:
            raise ValueError(f"access census mismatch {role}")
        if any(str(event["result"]).startswith(("FAIL", "REJECT")) for event in events):
            raise ValueError("failed access event")
        consumers[role] = {
            "event_count": len(events), "resolved_tensor_count": len(resolved),
            "opened_shard_count": len(opened),
            "first_use_count": sum(event["kind"] == "TENSOR_FIRST_USE" for event in events),
            "repeat_use_count": sum((event.get("repeat_count") or 0) for event in events if event["kind"] == "TENSOR_REUSE_SUMMARY"),
        }
    return {
        "schema": "pulsarmlx.f017.corrected-oracle-access-census/2.0.0",
        "authorization_id": auth["authorization_id"],
        "catalog_tensor_count": len(catalog_names), "graph_tensor_count": len(expected),
        "declared_non_access_tensor_count": len(catalog_names - expected),
        "declared_non_access_tensors": sorted(catalog_names - expected),
        "authorized_shard_count": len(authorized_shards),
        "graph_payload_shards": sorted(expected_shards),
        "identity_only_shards": sorted(authorized_shards - expected_shards),
        "consumers": consumers, "unexpected_access_count": 0,
        "fallback_attempt_count": 0, "alternate_root_attempt_count": 0,
        "result": "PASS",
    }


def _metrics(primary: dict, secondary: dict) -> dict:
    left = [float(value) for value in primary["full_logits"]]
    right = [float(value) for value in secondary["full_logits"]]
    if len(left) != len(right):
        raise ValueError("logit geometry")
    differences = [abs(a - b) for a, b in zip(left, right, strict=True)]
    rmse = math.sqrt(sum(value * value for value in differences) / len(differences))
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norm = math.sqrt(sum(a * a for a in left) * sum(b * b for b in right))
    return {"max_abs": max(differences), "rmse": rmse, "cosine_similarity": dot / norm if norm else 1.0}


def execute_event(arguments, *, scope: str) -> int:
    authority = load_and_validate(arguments.authorization, arguments.contract, ROOT, require_live=True, expected_scope=scope)
    auth = authority.document
    contract = strict_path(arguments.contract)
    if arguments.catalog.resolve(strict=True) != (ROOT / auth["checkpoint_catalog_path"]).resolve(strict=True):
        raise ValueError("catalog authority")
    if arguments.checkpoint_root.resolve(strict=True) != Path(auth["checkpoint_root"]):
        raise ValueError("checkpoint root authority")
    if arguments.package_root != Path(auth["package_state_root"]):
        raise ValueError("package root authority")
    handshake_report = handshake(
        arguments.authorization, arguments.contract, arguments.catalog,
        arguments.checkpoint_root, arguments.handshake_output, scope=scope,
    )
    package_root = arguments.package_root
    if package_root.exists() or package_root.is_symlink():
        raise ValueError("unused package root required")
    package_root.mkdir(mode=0o700, parents=False)
    package_start = {
        "schema": "pulsarmlx.f017.corrected-oracle-package-start/1.0.0",
        "authorization_id": auth["authorization_id"], "owner_pid": os.getpid(),
        "started_ns": time.time_ns(), "attempts": 1, "retries": 0, "resume": False,
        "handshake_sha256": sha256_path(arguments.handshake_output),
        "package_attempt_delta": 1,
    }
    claim_sha = bank(package_root / "claim.json", package_start)
    start_sha = bank(package_root / "durable-start.json", package_start)
    identity_sha = census_sha = comparison_sha = None
    consumer_records = {
        "primary": {"started": False, "event_delta": 0, "receipt_sha256": None, "terminal_sha256": None},
        "secondary": {"started": False, "event_delta": 0, "receipt_sha256": None, "terminal_sha256": None},
    }
    classification = "ORACLE_EXECUTION_FAILURE"
    error = None
    primary_result = Path(auth["primary"]["output_root"]) / "result.json"
    secondary_result = Path(auth["secondary"]["output_root"]) / "result.json"
    try:
        identity_sha = verify_checkpoint_identity(arguments.checkpoint_root, auth, package_root)
        for name, role in (("primary", PRIMARY_ROLE), ("secondary", SECONDARY_ROLE)):
            grant = auth[name]
            consumer_root = Path(grant["state_root"])
            _, consumer_start_sha = _consumer_start(consumer_root, auth, grant)
            consumer_records[name]["started"] = True
            consumer_records[name]["event_delta"] = 1
            result_path = consumer_root / "result.json"
            environment = os.environ.copy()
            environment["F017_ORACLE_ACCESS_EVENT_DIR"] = str(consumer_root / "access-events")
            environment["F017_ORACLE_CHECKPOINT_IDENTITY"] = str(package_root / "checkpoint-identity.json")
            if name == "secondary":
                # The accelerated Python oracle is lockfile-bound to the MLX
                # wheel.  Native Rust CI exports a separately constructed
                # libmlx through DYLD_LIBRARY_PATH; inheriting it can bind the
                # Python extension to an ABI-incompatible dylib.  Keep the two
                # reviewed runtimes isolated without changing oracle math.
                for variable in ("DYLD_LIBRARY_PATH", "MLX_C_PREFIX", "MLX_PREFIX", "RUSTFLAGS"):
                    environment.pop(variable, None)
                environment["F017_ORACLE_SECONDARY_RUNTIME"] = "LOCKFILE_PYTHON_MLX"
            script = ROOT / grant["producer_path"]
            try:
                subprocess.run(
                    [sys.executable, str(script), "target", str(arguments.authorization), str(arguments.contract),
                     str(arguments.catalog), str(arguments.checkpoint_root), str(arguments.geometry), str(result_path)],
                    cwd=ROOT, env=environment, stdin=subprocess.DEVNULL, shell=False, check=True,
                    timeout=contract["execution"]["consumer_timeout_seconds"],
                )
                consumer_classification, consumer_error = "COMPLETE", None
            except Exception as exc:
                consumer_classification, consumer_error = "FAILED", f"{type(exc).__name__}:{exc}"
            receipt_sha, terminal_sha = _consumer_terminal(
                consumer_root, auth, grant, consumer_start_sha, result_path,
                consumer_classification, consumer_error,
            )
            consumer_records[name].update(receipt_sha256=receipt_sha, terminal_sha256=terminal_sha)
            if consumer_classification != "COMPLETE":
                raise RuntimeError(f"{name} consumer failed: {consumer_error}")
        geometry = strict_path(arguments.geometry)
        census_sha = bank(package_root / "access-census.json", _access_census(package_root, auth, arguments.catalog, geometry))
        primary, secondary = strict_path(primary_result), strict_path(secondary_result)
        observed = _metrics(primary, secondary)
        threshold = contract["frozen_thresholds"]
        structural = all(
            left["selected_expert_ids"] == right["selected_expert_ids"]
            for left, right in zip(primary["layers"], secondary["layers"], strict=True)
        )
        within = observed["max_abs"] <= threshold["max_abs"] and observed["rmse"] <= threshold["rmse"] and observed["cosine_similarity"] >= threshold["cosine_min"]
        same_top = primary["selected_token"] == secondary["selected_token"]
        same_order = [item["token_id"] for item in primary["top"]] == [item["token_id"] for item in secondary["top"]]
        if not structural or not within:
            classification = "ORACLE_DISAGREEMENT"
        elif same_top and min(primary["top_1_margin"], secondary["top_1_margin"]) > 2 * threshold["max_abs"]:
            classification = "EXACT_EXPECTED_TOKEN_STABLE"
        elif same_order:
            classification = "NUMERICALLY_STABLE_TOP_K_ONLY"
        else:
            classification = "TOP1_UNSTABLE_WITHIN_FROZEN_UNCERTAINTY"
        comparison_sha = bank(package_root / "comparison.json", {
            "schema": "pulsarmlx.f017.corrected-oracle-comparison/2.0.0",
            "metrics": observed, "frozen_thresholds": threshold,
            "route_structure_exact": structural, "same_top_token": same_top,
            "same_top_n_order": same_order, "classification": classification,
        })
    except Exception as exc:
        error = f"{type(exc).__name__}:{exc}"
    package_delta = 1
    primary_delta = consumer_records["primary"]["event_delta"]
    secondary_delta = consumer_records["secondary"]["event_delta"]
    receipt = {
        "schema": "pulsarmlx.f017.corrected-oracle-package-receipt/3.0.0",
        "authorization_id": auth["authorization_id"], "owner_pid": os.getpid(),
        "claim_sha256": claim_sha, "start_sha256": start_sha,
        "handshake_sha256": sha256_path(arguments.handshake_output),
        "checkpoint_identity_sha256": identity_sha, "access_census_sha256": census_sha,
        "comparison_sha256": comparison_sha, "classification": classification, "error": error,
        "package_attempt_delta": package_delta, "primary_event_delta": primary_delta,
        "secondary_event_delta": secondary_delta,
        "primary": consumer_records["primary"], "secondary": consumer_records["secondary"],
        "historical_master_before": 175, "historical_master_after": 175,
        "historical_master_delta": 0, "completed_ns": time.time_ns(),
    }
    receipt_sha = bank(package_root / "receipt.json", receipt)
    ledger_sha = bank(package_root / "event-ledger-entry.json", {
        "schema": "pulsarmlx.f017.corrected-oracle-event-ledger-entry/2.0.0",
        "authorization_id": auth["authorization_id"], "package_attempt_delta": package_delta,
        "primary_event_delta": primary_delta, "secondary_event_delta": secondary_delta,
        "receipt_sha256": receipt_sha, "historical_master_terminal": 175,
    })
    bank(package_root / "terminal.json", {
        "schema": "pulsarmlx.f017.corrected-oracle-package-terminal/3.0.0",
        "authorization_id": auth["authorization_id"], "receipt_sha256": receipt_sha,
        "event_ledger_entry_sha256": ledger_sha, "classification": classification,
        "retry_permitted": False, "resume_permitted": False, "terminal_ns": time.time_ns(),
    })
    return 0 if classification != "ORACLE_EXECUTION_FAILURE" else 2


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("preflight")
    check.add_argument("contract", type=Path)
    check.add_argument("output", type=Path)
    hello = sub.add_parser("handshake")
    hello.add_argument("authorization", type=Path)
    hello.add_argument("contract", type=Path)
    hello.add_argument("catalog", type=Path)
    hello.add_argument("checkpoint_root", type=Path)
    hello.add_argument("output", type=Path)
    hello.add_argument("--scope", choices=("PRODUCTION", "SYNTHETIC_QUALIFICATION"), default="PRODUCTION")
    for name in ("execute", "execute-synthetic"):
        run = sub.add_parser(name)
        run.add_argument("authorization", type=Path)
        run.add_argument("contract", type=Path)
        run.add_argument("catalog", type=Path)
        run.add_argument("checkpoint_root", type=Path)
        run.add_argument("geometry", type=Path)
        run.add_argument("package_root", type=Path)
        run.add_argument("handshake_output", type=Path)
    arguments = parser.parse_args()
    if arguments.command == "execute" or (arguments.command == "handshake" and arguments.scope == "PRODUCTION"):
        raise SystemExit("HISTORICAL_ONLY: v3 production execution is permanently retired")
    if arguments.command == "preflight":
        preflight(arguments.contract, arguments.output)
        return 0
    if arguments.command == "handshake":
        handshake(arguments.authorization, arguments.contract, arguments.catalog,
                  arguments.checkpoint_root, arguments.output, scope=arguments.scope)
        return 0
    scope = "SYNTHETIC_QUALIFICATION" if arguments.command == "execute-synthetic" else "PRODUCTION"
    if scope == "SYNTHETIC_QUALIFICATION":
        checkpoint = arguments.checkpoint_root.resolve(strict=True)
        if ROOT not in checkpoint.parents or ".pulsarmlx-local" not in checkpoint.parts:
            raise SystemExit("synthetic checkpoint must be under repository-local ignored qualification root")
    return execute_event(arguments, scope=scope)


if __name__ == "__main__":
    raise SystemExit(main())
