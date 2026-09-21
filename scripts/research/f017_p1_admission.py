#!/usr/bin/env python3
"""Fail-closed admission and one-shot lifecycle for the bounded F017 P1.

Validation and inert-fixture tests never read checkpoint payloads. The `execute`
path is deliberately separate and requires a real operator authorization,
machine observations, exact file rehashes, and an exclusive durable attempt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable


SCHEMA = "pulsarmlx.f017.p1-admission-contract/1.0.0"
AUTH_SCHEMA = "pulsarmlx.f017.p1-one-shot-authorization/1.0.0"
TERMINAL_SCHEMA = "pulsarmlx.f017.p1-terminal/1.0.0"
APPROVAL_STATEMENT = "AUTHORIZE EXACTLY ONE BOUNDED F017 M1 ULTRA P1"
MIN_FREE_BYTES = 17_179_869_184
PROMPT_TOKEN = 9703
EXPECTED_TOKEN = 21615
MAX_MEMORY_SAMPLE_AGE_SECONDS = 5

CONTRACT_KEYS = {
    "schema",
    "status",
    "repository",
    "checkpoint",
    "runtime",
    "memory",
    "p1",
    "accounting",
    "authorization",
    "state",
    "prohibitions",
}
AUTH_KEYS = {
    "schema",
    "authorization_id",
    "contract_sha256",
    "reviewed_head",
    "attempt_id",
    "approval_statement",
    "operator_identity",
    "real_event_authorized",
    "attempts",
    "retries",
    "resume",
    "disposition",
}
REQUIRED_COUNTERS = {
    "callback_count",
    "managed_created",
    "managed_destroyed",
    "derived_created",
    "derived_destroyed",
    "default_cpu_stream_created",
    "default_cpu_stream_freed",
    "default_gpu_stream_created",
    "default_gpu_stream_freed",
    "owned_stream_created",
    "owned_stream_freed",
    "native_default_cpu_stream_freed",
    "native_default_gpu_stream_freed",
    "native_owned_stream_freed",
    "native_live_stream_handles",
    "native_duplicate_free_attempts",
    "native_origin_mismatches",
    "context_active",
    "registrations",
    "teardowns",
    "in_flight_work",
    "stale_native_ready_generations",
}
RECEIPT_KEYS = {
    "schema",
    "authorization_id",
    "attempt_id",
    "contract_sha256",
    "executor_sha256",
    "git_head",
    "checkpoint_identity",
    "runtime_identity",
    "machine_identity",
    "accounting_before",
    "accounting_after",
    "prompt_token",
    "generated_tokens",
    "expected_token",
    "mandatory_stop_observed",
    "execution_result",
    "terminal_state",
    "started_at_unix",
    "completed_at_unix",
}
CHECKPOINT_IDENTITY_KEYS = {"manifest_sha256", "set_sha256"}
RUNTIME_IDENTITY_KEYS = {"mlx_version", "mlx_c_version", "machine_file_sha256"}
MACHINE_IDENTITY_KEYS = {"architecture", "brand"}


class AdmissionError(RuntimeError):
    pass


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise AdmissionError(f"duplicate JSON key: {key}")
        output[key] = value
    return output


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(), object_pairs_hook=_reject_duplicate_keys)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise AdmissionError(f"cannot read canonical JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise AdmissionError(f"JSON root must be an object: {path}")
    return value


def canonical_bytes(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        raise AdmissionError(
            f"{label} keys mismatch: missing={sorted(expected - actual)} "
            f"extra={sorted(actual - expected)}"
        )


def validate_contract(document: dict[str, Any], repo_root: Path) -> None:
    _require_keys(document, CONTRACT_KEYS, "contract")
    if document["schema"] != SCHEMA or document["status"] != "PREPARED_HUMAN_GATE_REQUIRED":
        raise AdmissionError("contract schema/status is not execution-prepared")

    repository = document["repository"]
    if repository != {
        "branch": "feat/017-rust-native-inference-runtime",
        "execution_code_head": repository.get("execution_code_head"),
        "clean_worktree_required": True,
        "local_remote_parity_required": True,
    } or not re.fullmatch(r"[0-9a-f]{40}", repository["execution_code_head"]):
        raise AdmissionError("repository authority is incomplete")

    checkpoint = document["checkpoint"]
    manifest_path = repo_root / checkpoint["manifest_path"]
    if sha256_path(manifest_path) != checkpoint["manifest_sha256"]:
        raise AdmissionError("checkpoint manifest hash mismatch")
    manifest = load_json(manifest_path)
    if manifest.get("checkpoint_set_sha256") != checkpoint["set_sha256"]:
        raise AdmissionError("checkpoint set authority mismatch")
    expected = checkpoint["shards"]
    actual = [
        {"filename": row["filename"], "sha256": row["sha256"], "size_bytes": row["size_bytes"]}
        for row in manifest.get("files", [])
    ]
    if actual != expected or len(expected) != 6:
        raise AdmissionError("checkpoint shard census mismatch")
    if checkpoint["fallback"] != "PROHIBITED":
        raise AdmissionError("checkpoint fallback must be prohibited")

    runtime = document["runtime"]
    if runtime["mlx_version"] != "0.31.2" or runtime["mlx_c_version"] != "0.6.0":
        raise AdmissionError("pinned native MLX versions changed")
    if runtime["require_native_env"] != "PULSAR_REQUIRE_NATIVE_MLX=1":
        raise AdmissionError("native MLX fail-closed environment missing")
    for binding in runtime["bound_files"]:
        path = repo_root / binding["path"]
        if sha256_path(path) != binding["sha256"]:
            raise AdmissionError(f"runtime source binding mismatch: {binding['path']}")

    memory = document["memory"]
    if memory != {
        "minimum_free_bytes": MIN_FREE_BYTES,
        "source": "mach_vm_statistics64",
        "maximum_sample_age_seconds": MAX_MEMORY_SAMPLE_AGE_SECONDS,
        "caller_supplied_values_authoritative": False,
    }:
        raise AdmissionError("memory gate was weakened")

    p1 = document["p1"]
    if p1["prompt_token"] != PROMPT_TOKEN or p1["expected_token"] != EXPECTED_TOKEN:
        raise AdmissionError("P1 vector changed")
    if p1["attempts"] != 1 or p1["retries"] != 0 or p1["resume"] is not False:
        raise AdmissionError("P1 is not exactly-once")
    if p1["mandatory_stop"] != "AFTER_FIRST_GENERATED_TOKEN_AND_TERMINALIZATION":
        raise AdmissionError("mandatory stop was removed")
    if p1["scope"] != "ONE_BOUNDED_M1_ULTRA_P1":
        raise AdmissionError("P1 scope expanded")
    if not isinstance(p1["argv"], list) or not p1["argv"]:
        raise AdmissionError("P1 executable argv is not bound")
    executor_relative = Path(p1["executor_path"])
    if executor_relative.is_absolute() or ".." in executor_relative.parts:
        raise AdmissionError("P1 executor path must be repository-relative")
    executor_path = repo_root / executor_relative
    if (
        not executor_path.is_file()
        or executor_path.is_symlink()
        or not os.access(executor_path, os.X_OK)
        or not executor_path.resolve(strict=True).is_relative_to(repo_root.resolve(strict=True))
        or sha256_path(executor_path) != p1["executor_sha256"]
    ):
        raise AdmissionError("P1 executor identity mismatch")
    if p1["argv"][0] != str(executor_path):
        raise AdmissionError("P1 argv[0] is not the bound executor")
    if p1["receipt_schema"] != "pulsarmlx.f017.p1-execution-receipt/1.0.0":
        raise AdmissionError("P1 receipt schema is not bound")

    accounting = document["accounting"]
    if set(accounting["required_counters"]) != REQUIRED_COUNTERS:
        raise AdmissionError("accounting counter census mismatch")
    if accounting["observation"] != "MECHANICAL_PRE_POST_FROM_BOUND_EXECUTOR":
        raise AdmissionError("accounting observations may not be supplied manually")
    if accounting["stream_authority_fields"] != [
        "semantic_stream_origin",
        "native_handle_owned",
        "deallocation_responsibility",
    ]:
        raise AdmissionError("stream authority separation is incomplete")

    authorization = document["authorization"]
    if authorization["schema"] != AUTH_SCHEMA or authorization["live_authorization_present"]:
        raise AdmissionError("live authorization must not exist in the reviewed contract")
    if authorization["approval_statement"] != APPROVAL_STATEMENT:
        raise AdmissionError("human approval statement changed")
    if authorization["normal_validation_can_authorize"]:
        raise AdmissionError("validation may not mint authorization")

    if document["state"] != {
        "root": "/Users/mhedhli/.local/share/pulsarmlx/f017/m1-ultra-p1-admission-v1",
        "lifecycle": ["PREPARED", "AUTHORIZED", "CONSUMING", "CONSUMED_TERMINAL"],
        "exclusive_attempt_claim": True,
        "durable_ownership": True,
        "immutable_prior_state": True,
        "automatic_retry": False,
    }:
        raise AdmissionError("durable one-shot lifecycle changed")
    if document["prohibitions"] != {
        "full_model_inference": True,
        "second_p1": True,
        "p2_or_broader": True,
        "automatic_retry": True,
        "checkpoint_fallback": True,
    }:
        raise AdmissionError("mandatory P1 containment changed")


def validate_authorization(document: dict[str, Any], contract_sha256: str, head: str) -> None:
    _require_keys(document, AUTH_KEYS, "authorization")
    if document["schema"] != AUTH_SCHEMA:
        raise AdmissionError("authorization schema mismatch")
    if document["contract_sha256"] != contract_sha256 or document["reviewed_head"] != head:
        raise AdmissionError("authorization authority mismatch")
    if document["approval_statement"] != APPROVAL_STATEMENT:
        raise AdmissionError("operator approval statement mismatch")
    if not document["real_event_authorized"]:
        raise AdmissionError("inert authorization cannot execute")
    if document["attempts"] != 1 or document["retries"] != 0 or document["resume"] is not False:
        raise AdmissionError("authorization is not one-shot")
    if document["disposition"] != "EXECUTE_P1_ONCE_THEN_MANDATORY_STOP":
        raise AdmissionError("authorization disposition mismatch")
    for field in ("authorization_id", "attempt_id", "operator_identity"):
        if not isinstance(document[field], str) or not document[field]:
            raise AdmissionError(f"authorization {field} is empty")


def sample_free_memory_macos(
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    now: Callable[[], float] = time.time,
) -> dict[str, Any]:
    if platform.system() != "Darwin":
        raise AdmissionError("P1 memory admission requires macOS")
    result = runner(
        ["/usr/bin/vm_stat"], capture_output=True, text=True, check=True, timeout=5
    )
    page_match = re.search(r"page size of (\d+) bytes", result.stdout)
    if not page_match:
        raise AdmissionError("vm_stat page size unavailable")
    page_size = int(page_match.group(1))
    pages: dict[str, int] = {}
    for line in result.stdout.splitlines():
        match = re.fullmatch(r"([^:]+):\s+([0-9]+)\.", line.strip())
        if match:
            pages[match.group(1)] = int(match.group(2))
    required = ["Pages free", "Pages inactive", "Pages speculative"]
    if any(name not in pages for name in required):
        raise AdmissionError("vm_stat free-page census unavailable")
    free_bytes = sum(pages[name] for name in required) * page_size
    observed_at = now()
    if free_bytes < MIN_FREE_BYTES:
        raise AdmissionError(f"free memory {free_bytes} is below {MIN_FREE_BYTES}")
    return {
        "source": "mach_vm_statistics64",
        "free_bytes": free_bytes,
        "observed_at_unix": observed_at,
        "maximum_age_seconds": MAX_MEMORY_SAMPLE_AGE_SECONDS,
    }


def require_fresh_memory_sample(sample: dict[str, Any], now: float) -> None:
    if sample.get("source") != "mach_vm_statistics64":
        raise AdmissionError("memory sample source is not authoritative")
    age = now - float(sample.get("observed_at_unix", 0))
    if age < 0 or age > MAX_MEMORY_SAMPLE_AGE_SECONDS:
        raise AdmissionError("memory sample is stale")
    if int(sample.get("free_bytes", 0)) < MIN_FREE_BYTES:
        raise AdmissionError("memory floor failed")


def _git(repo_root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments], cwd=repo_root, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def verify_repository_state(contract: dict[str, Any], repo_root: Path) -> None:
    authority = contract["repository"]
    if _git(repo_root, "branch", "--show-current") != authority["branch"]:
        raise AdmissionError("authoritative branch mismatch")
    head = _git(repo_root, "rev-parse", "HEAD")
    if head != authority["execution_code_head"]:
        raise AdmissionError("execution head mismatch")
    remote = _git(repo_root, "rev-parse", f"origin/{authority['branch']}")
    if remote != head:
        raise AdmissionError("local/remote parity mismatch")
    if _git(repo_root, "status", "--porcelain"):
        raise AdmissionError("worktree is dirty")


def verify_checkpoint_payload(contract: dict[str, Any], checkpoint_root: Path) -> None:
    environment_name = contract["checkpoint"]["path_environment"]
    configured = os.environ.get(environment_name)
    if not configured:
        raise AdmissionError(f"checkpoint environment {environment_name} is absent")
    try:
        expected_root = Path(configured).resolve(strict=True)
        supplied_root = checkpoint_root.resolve(strict=True)
    except OSError as exc:
        raise AdmissionError(f"checkpoint root cannot be resolved: {exc}") from exc
    if supplied_root != expected_root:
        raise AdmissionError("caller-selected alternate checkpoint root rejected")
    if not checkpoint_root.is_dir() or checkpoint_root.is_symlink():
        raise AdmissionError("checkpoint root is not a real directory")
    for shard in contract["checkpoint"]["shards"]:
        path = checkpoint_root / shard["filename"]
        stat = path.lstat()
        if path.is_symlink() or not path.is_file() or stat.st_size != shard["size_bytes"]:
            raise AdmissionError(f"checkpoint shard geometry mismatch: {path.name}")
        if sha256_path(path) != shard["sha256"]:
            raise AdmissionError(f"checkpoint shard hash mismatch: {path.name}")


def _apple_cpu_brand(
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> str:
    try:
        result = runner(
            ["/usr/sbin/sysctl", "-n", "machdep.cpu.brand_string"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise AdmissionError(f"M1 Ultra sysctl observation failed: {exc}") from exc
    brand = result.stdout.rstrip("\r\n")
    if brand != "Apple M1 Ultra":
        raise AdmissionError(f"P1 device brand mismatch: {brand!r}")
    return brand


def verify_runtime_machine(
    contract: dict[str, Any],
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    machine: Callable[[], str] = platform.machine,
) -> None:
    runtime = contract["runtime"]
    if os.environ.get("PULSAR_REQUIRE_NATIVE_MLX") != "1":
        raise AdmissionError("PULSAR_REQUIRE_NATIVE_MLX=1 is required")
    if machine() != "arm64":
        raise AdmissionError("P1 architecture is not arm64")
    _apple_cpu_brand(runner)
    for binding in runtime["machine_files"]:
        path = Path(binding["path"])
        if path.is_symlink() or not path.is_file() or sha256_path(path) != binding["sha256"]:
            raise AdmissionError(f"machine runtime binding mismatch: {path}")


def _require_counter_snapshot(value: Any, label: str) -> dict[str, int]:
    if not isinstance(value, dict) or set(value) != REQUIRED_COUNTERS:
        raise AdmissionError(f"{label} counter census mismatch")
    for key, counter in value.items():
        if isinstance(counter, bool) or not isinstance(counter, int) or counter < 0:
            raise AdmissionError(f"{label}.{key} is not a non-negative integer")
    return value


def validate_execution_receipt(
    receipt: dict[str, Any],
    contract: dict[str, Any],
    authorization: dict[str, Any],
    contract_sha256: str,
) -> None:
    _require_keys(receipt, RECEIPT_KEYS, "receipt")
    if receipt.get("schema") != contract["p1"]["receipt_schema"]:
        raise AdmissionError("P1 execution receipt schema mismatch")
    if (
        receipt["authorization_id"] != authorization["authorization_id"]
        or receipt["attempt_id"] != authorization["attempt_id"]
        or receipt["contract_sha256"] != contract_sha256
        or receipt["executor_sha256"] != contract["p1"]["executor_sha256"]
        or receipt["git_head"] != contract["repository"]["execution_code_head"]
    ):
        raise AdmissionError("P1 receipt authority mismatch")
    checkpoint = receipt["checkpoint_identity"]
    _require_keys(checkpoint, CHECKPOINT_IDENTITY_KEYS, "receipt.checkpoint_identity")
    if checkpoint != {
        "manifest_sha256": contract["checkpoint"]["manifest_sha256"],
        "set_sha256": contract["checkpoint"]["set_sha256"],
    }:
        raise AdmissionError("P1 receipt checkpoint identity mismatch")
    runtime = receipt["runtime_identity"]
    _require_keys(runtime, RUNTIME_IDENTITY_KEYS, "receipt.runtime_identity")
    expected_machine_files = {
        row["path"]: row["sha256"] for row in contract["runtime"]["machine_files"]
    }
    if runtime != {
        "mlx_version": contract["runtime"]["mlx_version"],
        "mlx_c_version": contract["runtime"]["mlx_c_version"],
        "machine_file_sha256": expected_machine_files,
    }:
        raise AdmissionError("P1 receipt runtime identity mismatch")
    machine_identity = receipt["machine_identity"]
    _require_keys(machine_identity, MACHINE_IDENTITY_KEYS, "receipt.machine_identity")
    if machine_identity != {"architecture": "arm64", "brand": "Apple M1 Ultra"}:
        raise AdmissionError("P1 receipt machine identity mismatch")
    if receipt.get("prompt_token") != PROMPT_TOKEN or receipt.get("generated_tokens") != [EXPECTED_TOKEN]:
        raise AdmissionError("P1 token vector mismatch or execution exceeded one token")
    if receipt["expected_token"] != EXPECTED_TOKEN:
        raise AdmissionError("P1 expected token binding mismatch")
    if receipt.get("mandatory_stop_observed") is not True:
        raise AdmissionError("P1 runner did not observe mandatory stop")
    if receipt["execution_result"] != "EXPECTED_TOKEN_MATCH" or receipt["terminal_state"] != "COMPLETE_MANDATORY_STOP":
        raise AdmissionError("P1 receipt result/terminal mismatch")
    for key in ("started_at_unix", "completed_at_unix"):
        if isinstance(receipt[key], bool) or not isinstance(receipt[key], (int, float)):
            raise AdmissionError(f"P1 receipt {key} type mismatch")
    if receipt["completed_at_unix"] < receipt["started_at_unix"]:
        raise AdmissionError("P1 receipt timestamps are reversed")
    before = _require_counter_snapshot(receipt["accounting_before"], "accounting_before")
    after = _require_counter_snapshot(receipt["accounting_after"], "accounting_after")
    for prefix in ("managed", "derived"):
        if after[f"{prefix}_created"] - before[f"{prefix}_created"] != after[f"{prefix}_destroyed"] - before[f"{prefix}_destroyed"]:
            raise AdmissionError(f"{prefix} ownership did not reconcile")
    for prefix in ("default_cpu_stream", "default_gpu_stream", "owned_stream"):
        if after[f"{prefix}_created"] - before[f"{prefix}_created"] != after[f"{prefix}_freed"] - before[f"{prefix}_freed"]:
            raise AdmissionError(f"{prefix} logical stream accounting did not reconcile")
    for logical, native in (
        ("default_cpu_stream_freed", "native_default_cpu_stream_freed"),
        ("default_gpu_stream_freed", "native_default_gpu_stream_freed"),
        ("owned_stream_freed", "native_owned_stream_freed"),
    ):
        if after[logical] - before[logical] != after[native] - before[native]:
            raise AdmissionError(f"logical/native free mismatch: {logical}")
    if after["native_live_stream_handles"] != before["native_live_stream_handles"]:
        raise AdmissionError("native stream handle leaked")
    if after["native_duplicate_free_attempts"] != before["native_duplicate_free_attempts"]:
        raise AdmissionError("native duplicate-free attempt observed")
    if after["native_origin_mismatches"] != before["native_origin_mismatches"]:
        raise AdmissionError("native stream origin mismatch observed")
    if after["context_active"] or after["in_flight_work"]:
        raise AdmissionError("P1 left an active context or in-flight work")
    if after["registrations"] - before["registrations"] != after["teardowns"] - before["teardowns"]:
        raise AdmissionError("registrations and teardowns did not reconcile")
    if after["stale_native_ready_generations"] != 0:
        raise AdmissionError("stale native-ready generation remains")


def verify_state_root(contract: dict[str, Any], state_root: Path) -> None:
    expected = Path(contract["state"]["root"])
    if not expected.is_absolute() or not state_root.is_absolute() or state_root != expected:
        raise AdmissionError("caller-selected alternate P1 state root rejected")
    current = Path(expected.anchor)
    for part in expected.parts[1:]:
        current = current / part
        if current.exists() or current.is_symlink():
            if current.is_symlink():
                raise AdmissionError(f"P1 state-root symlink rejected: {current}")
        else:
            if current != expected:
                raise AdmissionError(f"P1 state-root ancestor is absent: {current}")
            break
    if expected.exists():
        stat = expected.stat()
        if not expected.is_dir() or stat.st_uid != os.getuid() or stat.st_mode & 0o077:
            raise AdmissionError("P1 state root ownership or permissions are unsafe")
        if expected.resolve(strict=True) != expected:
            raise AdmissionError("P1 state root resolved identity mismatch")
    elif expected.parent.resolve(strict=True) != expected.parent:
        raise AdmissionError("P1 state-root parent resolved identity mismatch")


def _durable_json(path: Path, value: dict[str, Any], exclusive: bool = True) -> None:
    flags = os.O_WRONLY | os.O_CREAT | (os.O_EXCL if exclusive else os.O_TRUNC)
    descriptor = os.open(path, flags, 0o400)
    try:
        data = canonical_bytes(value)
        os.write(descriptor, data)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def claim_attempt(state_root: Path, authorization: dict[str, Any]) -> Path:
    state_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    # One reviewed contract admits at most one P1 in total, not one P1 per
    # caller-selected attempt id.  The durable contract-wide claim is created
    # before the attempt directory, so a second authorization (even with a new
    # attempt id) cannot consume this admission surface.
    claim = state_root / "p1-once.claim.json"
    try:
        _durable_json(
            claim,
            {
                "state": "CONSUMING",
                "authorization_id": authorization["authorization_id"],
                "attempt_id": authorization["attempt_id"],
                "owner_pid": os.getpid(),
                "started_at_unix": time.time(),
                "retry_permitted": False,
            },
        )
    except FileExistsError as exc:
        raise AdmissionError("P1 contract has already been consumed or claimed") from exc
    attempt_root = state_root / authorization["attempt_id"]
    try:
        attempt_root.mkdir(mode=0o700)
    except FileExistsError as exc:
        # The contract-wide claim remains durable and consumed.  Never remove
        # it to repair a malformed or colliding attempt id.
        raise AdmissionError("authorization attempt already consumed or in progress") from exc
    ownership = {
        "state": "CONSUMING",
        "authorization_id": authorization["authorization_id"],
        "attempt_id": authorization["attempt_id"],
        "owner_pid": os.getpid(),
        "started_at_unix": time.time(),
        "retry_permitted": False,
    }
    _durable_json(attempt_root / "attempt-start.json", ownership)
    return attempt_root


def terminalize(attempt_root: Path, authorization: dict[str, Any], disposition: str) -> Path:
    terminal = {
        "schema": TERMINAL_SCHEMA,
        "state": "CONSUMED_TERMINAL",
        "authorization_id": authorization["authorization_id"],
        "attempt_id": authorization["attempt_id"],
        "disposition": disposition,
        "retry_permitted": False,
        "mandatory_stop": True,
    }
    path = attempt_root / "terminal.json"
    _durable_json(path, terminal)
    return path


def execute_once(
    contract_path: Path,
    authorization_path: Path,
    repo_root: Path,
    checkpoint_root: Path,
    state_root: Path,
) -> None:
    contract = load_json(contract_path)
    validate_contract(contract, repo_root)
    verify_state_root(contract, state_root)
    authorization = load_json(authorization_path)
    validate_authorization(
        authorization,
        sha256_path(contract_path),
        contract["repository"]["execution_code_head"],
    )
    verify_repository_state(contract, repo_root)
    verify_runtime_machine(contract)
    verify_checkpoint_payload(contract, checkpoint_root)
    sample = sample_free_memory_macos()
    require_fresh_memory_sample(sample, time.time())

    attempt_root = claim_attempt(state_root, authorization)
    receipt_path = attempt_root / "execution-receipt.json"
    replacements = {
        "{checkpoint_root}": str(checkpoint_root),
        "{receipt_path}": str(receipt_path),
        "{attempt_id}": authorization["attempt_id"],
    }
    argv = [replacements.get(value, value) for value in contract["p1"]["argv"]]
    try:
        result = subprocess.run(argv, cwd=repo_root, check=False)
        if result.returncode != 0:
            raise AdmissionError(f"P1 executable exited {result.returncode}")
        validate_execution_receipt(
            load_json(receipt_path), contract, authorization, sha256_path(contract_path)
        )
        terminalize(attempt_root, authorization, "COMPLETE_MANDATORY_STOP")
    except BaseException:
        if not (attempt_root / "terminal.json").exists():
            terminalize(attempt_root, authorization, "TERMINAL_FAILURE_NO_RETRY")
        raise
    # There is intentionally no continuation or retry branch after terminalization.


def authorize_inert(contract_path: Path, output: Path) -> None:
    contract_sha = sha256_path(contract_path)
    contract = load_json(contract_path)
    value = {
        "schema": AUTH_SCHEMA,
        "authorization_id": "INERT-F017-P1-AUTHORIZATION",
        "contract_sha256": contract_sha,
        "reviewed_head": contract["repository"]["execution_code_head"],
        "attempt_id": "INERT-F017-P1-ATTEMPT",
        "approval_statement": "INERT FIXTURE - NOT OPERATOR APPROVAL",
        "operator_identity": "INERT",
        "real_event_authorized": False,
        "attempts": 1,
        "retries": 0,
        "resume": False,
        "disposition": "INERT_VALIDATION_ONLY",
    }
    output.write_bytes(canonical_bytes(value))


def _main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate-contract")
    validate.add_argument("--contract", type=Path, required=True)
    validate.add_argument("--repo-root", type=Path, required=True)
    inert = subparsers.add_parser("write-inert-fixture")
    inert.add_argument("--contract", type=Path, required=True)
    inert.add_argument("--output", type=Path, required=True)
    preflight = subparsers.add_parser("preflight")
    preflight.add_argument("--contract", type=Path, required=True)
    preflight.add_argument("--repo-root", type=Path, required=True)
    preflight.add_argument("--checkpoint-root", type=Path, required=True)
    execute = subparsers.add_parser("execute-once")
    execute.add_argument("--contract", type=Path, required=True)
    execute.add_argument("--authorization", type=Path, required=True)
    execute.add_argument("--repo-root", type=Path, required=True)
    execute.add_argument("--checkpoint-root", type=Path, required=True)
    execute.add_argument("--state-root", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "validate-contract":
        validate_contract(load_json(args.contract), args.repo_root)
        print("F017 P1 admission contract: VALID; live authorization: ABSENT")
        return 0
    if args.command == "write-inert-fixture":
        authorize_inert(args.contract, args.output)
        return 0
    if args.command == "preflight":
        contract = load_json(args.contract)
        validate_contract(contract, args.repo_root)
        verify_repository_state(contract, args.repo_root)
        verify_runtime_machine(contract)
        verify_checkpoint_payload(contract, args.checkpoint_root)
        sample = sample_free_memory_macos()
        require_fresh_memory_sample(sample, time.time())
        print("F017 P1 preflight: PASS; no attempt claimed")
        return 0
    if args.command == "execute-once":
        execute_once(
            args.contract,
            args.authorization,
            args.repo_root,
            args.checkpoint_root,
            args.state_root,
        )
        print("F017 P1: CONSUMED_TERMINAL; mandatory stop")
        return 0
    raise AdmissionError("unknown command")


if __name__ == "__main__":
    try:
        raise SystemExit(_main())
    except AdmissionError as exc:
        print(f"F017 P1 admission rejected: {exc}", file=sys.stderr)
        raise SystemExit(2)
