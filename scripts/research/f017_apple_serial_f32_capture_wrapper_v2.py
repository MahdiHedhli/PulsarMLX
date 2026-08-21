#!/usr/bin/env python3
"""RN1-owned future Apple serial-f32 capture wrapper.

No authorization or GO token is banked by this retained-only phase.  A later
operator phase must provide both exact artifacts before --execute can create
the exclusive attempt root.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys


class GateError(RuntimeError):
    pass


STAGE_IDS = [
    "input_hidden", "attention_normalized", "query_rank", "query_rank_normalized",
    "query_heads", "kv_raw", "kv_normalized", "key_nope", "attention_scores",
    "attention_weights", "value_heads", "attention_output", "post_attention_residual",
    "router_normalized", "router_logits", "router_probabilities", "router_scores",
    "ranking", "selected_ids", "routing_weights", "routed_gate", "routed_up",
    "routed_silu", "routed_gate_up_product", "routed_weighted_hidden",
    "routed_down_outputs", "routed_aggregate", "shared_gate", "shared_up",
    "shared_silu", "shared_gate_up_product", "shared_expert_output", "production_ffn",
    "production_s2",
]


def load_unique(path: Path):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise GateError(f"DUPLICATE_JSON_KEY:{key}")
            out[key] = value
        return out
    try:
        return json.loads(path.read_text(), object_pairs_hook=pairs)
    except (OSError, json.JSONDecodeError) as exc:
        raise GateError(f"JSON:{path}:{exc}") from exc


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fsync_dir(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def durable_create(path: Path, value: dict, mode: int = 0o400) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        os.write(descriptor, data)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    fsync_dir(path.parent)
    return hashlib.sha256(data).hexdigest()


def verify_binding(repo: Path, binding: dict) -> Path:
    path = repo / binding["path"]
    if not path.is_file() or sha(path) != binding["sha256"]:
        raise GateError(f"BINDING:{binding.get('path')}")
    return path


def validate_release(repo: Path, release_path: Path) -> dict:
    release = load_unique(release_path)
    if release.get("schema") != "pulsarmlx.f017.apple-production-serial-f32-capture-release" or release.get("schema_version") != "2.0.0":
        raise GateError("RELEASE_SCHEMA")
    if release.get("ledger") != {"start": 175, "terminal": 175}:
        raise GateError("LEDGER")
    zeros = release.get("execution_budgets", {})
    for key in ("checkpoint_reads", "shard_opens", "attention_executions", "expert_executions", "aggregate_executions", "shared_expert_executions", "ffn_compositions", "s1_materializations", "s2_constructions"):
        if zeros.get(key) != 0:
            raise GateError(f"BUDGET:{key}")
    if zeros.get("production_equivalence_executions") != 1 or release.get("real_event_authorized") is not False:
        raise GateError("EXECUTION_AUTHORITY")
    if release.get("stop_boundary") != "AFTER_APPLE_PRODUCTION_SERIAL_F32_CAPTURE_AND_COMPARISON_ONLY":
        raise GateError("STOP_BOUNDARY")
    manifest_path = verify_binding(repo, release["code_manifest"])
    manifest = load_unique(manifest_path)
    if manifest.get("schema") != "pulsarmlx.f017.apple-production-serial-f32-code-manifest":
        raise GateError("CODE_MANIFEST_SCHEMA")
    for binding in manifest.get("artifacts", []):
        verify_binding(repo, binding)
    verify_binding(repo, release["authorization_schema"])
    runtime_path = verify_binding(repo, release["runtime_binding"])
    runtime = load_unique(runtime_path)
    for family in ("mlx", "mlx_c"):
        for key in ("library", "version_header"):
            binding = runtime[family][key]
            if sha(Path(binding["path"])) != binding["sha256"]:
                raise GateError(f"RUNTIME_IDENTITY:{family}:{key}")
    umbrella = runtime["mlx_c"]["umbrella_header"]
    if sha(Path(umbrella["path"])) != umbrella["sha256"]:
        raise GateError("RUNTIME_IDENTITY:mlx_c:umbrella_header")
    for binding in release.get("bound_contracts", []):
        verify_binding(repo, binding)
    runner = repo / release["runner_path"]
    if not runner.is_file() or runner.is_symlink():
        raise GateError("EXECUTOR_FILE")
    if sha(runner) != release["executor_sha256"]:
        raise GateError("EXECUTOR_SHA")
    return release


def validate_authorization(repo: Path, release_path: Path, release: dict, approval_path: Path, token_path: Path) -> tuple[dict, dict]:
    approval = load_unique(approval_path)
    token = load_unique(token_path)
    approval_keys = set(release["approval_schema_fields"])
    token_keys = set(release["go_token_schema_fields"])
    if set(approval) != approval_keys or set(token) != token_keys:
        raise GateError("AUTHORITY_FIELD_CENSUS")
    release_sha = sha(release_path)
    if approval["release_sha256"] != release_sha or token["release_sha256"] != release_sha:
        raise GateError("RELEASE_SHA")
    if token["approval_sha256"] != sha(approval_path):
        raise GateError("APPROVAL_SHA")
    for field in ("event_id", "release_id", "attempt_id"):
        if approval[field] != release[field] or token[field] != release[field]:
            raise GateError(f"IDENTITY:{field}")
    if approval["code_manifest_sha256"] != release["code_manifest"]["sha256"]:
        raise GateError("CODE_AUTHORITY")
    if approval["verdict"] != "ACCEPT" or approval["approval_does_not_execute"] is not True or approval["approval_is_not_token"] is not True:
        raise GateError("APPROVAL_DISPOSITION")
    if token["disposition"] != "GO_EXECUTE_ONCE_NO_RETRY" or token["real_event_authorized"] is not True:
        raise GateError("TOKEN_DISPOSITION")
    return approval, token


def owner_matches(root: Path, invocation_id: str, owner_sha: str) -> bool:
    owner = root / "owner.json"
    if not owner.is_file() or sha(owner) != owner_sha:
        return False
    data = load_unique(owner)
    return data.get("invocation_id") == invocation_id and data.get("attempt_id") is not None


def terminalize_owned_failure(root: Path, invocation_id: str, owner_sha: str, reason: str, process_exit: int | None) -> None:
    if not owner_matches(root, invocation_id, owner_sha):
        raise GateError("TERMINALIZATION_NOT_OWNED")
    receipts = root / "payload-receipts"
    receipt_rows = [] if not receipts.exists() else sorted(p for p in receipts.iterdir() if p.is_file())
    for path in receipt_rows:
        value = load_unique(path)
        if value.get("schema") != "pulsarmlx.f017.real-payload-receipt":
            raise GateError("RECEIPT_SCHEMA")
    terminal = {
        "schema": "pulsarmlx.f017.apple-production-serial-f32-terminal",
        "schema_version": "2.0.0",
        "status": "TERMINAL_FAILURE",
        "reason": reason,
        "invocation_id": invocation_id,
        "owner_sha256": owner_sha,
        "consumed_reads": len(receipt_rows),
        "receipt_inventory": [{"path": p.name, "sha256": sha(p)} for p in receipt_rows],
        "ledger_before": 175,
        "ledger_after": 175 + len(receipt_rows),
        "process_exit": process_exit,
        "no_retry": True,
    }
    durable_create(root / "terminal.json", terminal)
    rows = [
        {"path": path.name, "sha256": sha(path)}
        for path in sorted(p for p in root.iterdir() if p.is_file() and p.name != "artifact-inventory.json")
    ]
    durable_create(root / "artifact-inventory.json", {
        "schema": "pulsarmlx.f017.apple-production-serial-f32-attempt-inventory",
        "schema_version": "2.0.0",
        "invocation_id": invocation_id,
        "owner_sha256": owner_sha,
        "artifacts": rows,
    })


def validate_capture(root: Path) -> dict:
    manifest_path = root / "capture-manifest.json"
    manifest = load_unique(manifest_path)
    stages = manifest.get("stages")
    if manifest.get("schema") != "pulsarmlx.f017.apple-production-serial-f32-capture-manifest" or not isinstance(stages, list) or len(stages) != 34:
        raise GateError("CAPTURE_MANIFEST")
    seen = set()
    inventory = []
    for ordinal, row in enumerate(stages):
        if not isinstance(row, dict) or row.get("ordinal") != ordinal or row.get("stage_id") in seen:
            raise GateError("CAPTURE_CENSUS")
        if row["stage_id"] != STAGE_IDS[ordinal]:
            raise GateError("CAPTURE_STAGE_ORDER")
        seen.add(row["stage_id"])
        path = root / row.get("path", "")
        if path.parent != root or not path.is_file() or sha(path) != row.get("sha256"):
            raise GateError("CAPTURE_IDENTITY")
        stat = path.stat()
        if stat.st_nlink != 1 or stat.st_mode & 0o222 or path.is_symlink() or stat.st_size != row.get("byte_length"):
            raise GateError("CAPTURE_FILE_POLICY")
        inventory.append({"path": path.name, "sha256": row["sha256"]})
    allowed = {"capture-manifest.json", *(row["path"] for row in stages)}
    if {path.name for path in root.iterdir()} != allowed:
        raise GateError("CAPTURE_UNMANIFESTED_OR_MISSING_FILE")
    return {
        "capture_manifest_sha256": sha(manifest_path),
        "stage_count": len(stages),
        "stage_inventory": inventory,
        "production_s2_sha256": manifest.get("s2_sha256"),
    }


def terminalize_owned_success(root: Path, capture_root: Path, invocation_id: str, owner_sha: str) -> None:
    if not owner_matches(root, invocation_id, owner_sha):
        raise GateError("SUCCESS_TERMINALIZATION_NOT_OWNED")
    capture = validate_capture(capture_root)
    receipt = {
        "schema": "pulsarmlx.f017.apple-production-serial-f32-execution-receipt",
        "schema_version": "2.0.0",
        "invocation_id": invocation_id,
        "owner_sha256": owner_sha,
        "capture": capture,
        "checkpoint_reads": 0,
        "shard_opens": 0,
        "production_equivalence_executions": 1,
    }
    receipt_sha = durable_create(root / "execution-receipt.json", receipt)
    terminal = {
        "schema": "pulsarmlx.f017.apple-production-serial-f32-terminal",
        "schema_version": "2.0.0",
        "status": "COMPLETE",
        "invocation_id": invocation_id,
        "owner_sha256": owner_sha,
        "consumed_reads": 0,
        "receipt_inventory": [],
        "ledger_before": 175,
        "ledger_after": 175,
        "checkpoint_reads": 0,
        "shard_opens": 0,
        "production_equivalence_executions": 1,
        "execution_receipt_sha256": receipt_sha,
        "capture_manifest_sha256": capture["capture_manifest_sha256"],
        "output_authority": True,
        "no_retry": True,
    }
    durable_create(root / "terminal.json", terminal)
    rows = []
    for path in sorted(p for p in root.iterdir() if p.is_file() and p.name != "artifact-inventory.json"):
        rows.append({"path": path.name, "sha256": sha(path)})
    durable_create(root / "artifact-inventory.json", {
        "schema": "pulsarmlx.f017.apple-production-serial-f32-attempt-inventory",
        "schema_version": "2.0.0",
        "invocation_id": invocation_id,
        "owner_sha256": owner_sha,
        "artifacts": rows,
    })


def execute(repo: Path, release_path: Path, release: dict, approval_path: Path, token_path: Path) -> int:
    validate_authorization(repo, release_path, release, approval_path, token_path)
    attempt_root = Path(release["machine_local_paths"]["attempt_root"])
    invocation_id = secrets.token_hex(24)
    try:
        os.mkdir(attempt_root, 0o700)
    except FileExistsError as exc:
        raise GateError("ATTEMPT_ALREADY_EXISTS_NO_RETRY") from exc
    fsync_dir(attempt_root.parent)
    owner = {
        "schema": "pulsarmlx.f017.apple-production-serial-f32-owned-lock",
        "schema_version": "2.0.0",
        "event_id": release["event_id"],
        "release_id": release["release_id"],
        "attempt_id": release["attempt_id"],
        "invocation_id": invocation_id,
        "pid": os.getpid(),
        "ownership": "EXCLUSIVE_DURABLE_UNTIL_TERMINAL",
    }
    owner_sha = durable_create(attempt_root / "owner.json", owner)
    try:
        start = {
            "schema": "pulsarmlx.f017.apple-production-serial-f32-attempt-start",
            "schema_version": "2.0.0",
            "attempt_id": release["attempt_id"],
            "invocation_id": invocation_id,
            "owner_sha256": owner_sha,
            "wrapper_sha256": release["wrapper_sha256"],
            "executor_sha256": release["executor_sha256"],
            "contract_sha256": sha(release_path),
            "expected_starting_ledger": 175,
            "authorization_sha256": sha(approval_path),
            "git_head": release["execution_code_head"],
            "environment_identity": release["runtime_binding"],
        }
        durable_create(attempt_root / "attempt-start.json", start)
        (attempt_root / "payload-receipts").mkdir(mode=0o700)
        fsync_dir(attempt_root)
        durable_create(attempt_root / "comparison-start.json", {
            "schema": "pulsarmlx.f017.apple-production-serial-f32-comparison-start",
            "attempt_id": release["attempt_id"], "invocation_id": invocation_id,
            "owner_sha256": owner_sha, "production_equivalence_executions": 1,
        })
        env = dict(os.environ)
        env["PULSARMLX_F017_OWNED_ATTEMPT_SHA256"] = owner_sha
        command = [str(repo / release["runner_path"]), "--package", release["machine_local_paths"]["package_manifest"], "--execute"]
        completed = subprocess.run(command, cwd=repo, env=env, check=False)
        if completed.returncode != 0:
            terminalize_owned_failure(attempt_root, invocation_id, owner_sha, "RUNNER_EXIT", completed.returncode)
            return completed.returncode
        terminalize_owned_success(
            attempt_root,
            Path(release["machine_local_paths"]["capture_root"]),
            invocation_id,
            owner_sha,
        )
        return 0
    except BaseException as exc:
        if owner_matches(attempt_root, invocation_id, owner_sha) and not (attempt_root / "terminal.json").exists():
            terminalize_owned_failure(attempt_root, invocation_id, owner_sha, type(exc).__name__, None)
        raise


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", required=True, type=Path)
    parser.add_argument("--approval", type=Path)
    parser.add_argument("--go-token", type=Path)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--preflight-only", action="store_true")
    group.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    try:
        release = validate_release(repo, args.release)
        if args.preflight_only:
            attempt_root = Path(release["machine_local_paths"]["attempt_root"])
            if attempt_root.exists():
                raise GateError("ATTEMPT_STATE_PRESENT")
            print("APPLE_SERIAL_F32_RELEASE_SCHEMA_PREFLIGHT_PASS_NO_ARITHMETIC")
            return 0
        if args.approval is None or args.go_token is None:
            raise GateError("SEPARATE_APPROVAL_AND_GO_TOKEN_REQUIRED")
        return execute(repo, args.release, release, args.approval, args.go_token)
    except GateError as exc:
        print(f"FAIL:{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
