#!/usr/bin/env python3
"""Operator-only one-shot authorization builder for the accepted F017 P1 domain.

Normal validation and template generation cannot create an execution authority.
The authorize command requires a separately committed human approval that binds
the final domain declaration, final Fable review, exact readiness head, and
exact contract. This script is not invoked during domain qualification.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

APPROVAL_SCHEMA = "pulsarmlx.f017.native-bounded-p1-human-approval/1.0.0"
DECISION = "AUTHORIZE_EXACTLY_ONE_BOUNDED_M1_ULTRA_P1"
STATEMENT = "AUTHORIZE EXACTLY ONE REVIEWED BOUNDED M1 ULTRA P1; NO RETRY; MANDATORY STOP"


def strict_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load(path: Path) -> tuple[dict[str, object], str]:
    raw = path.read_bytes()
    value = json.loads(raw, object_pairs_hook=strict_object)
    if not isinstance(value, dict):
        raise ValueError("JSON root must be an object")
    return value, hashlib.sha256(raw).hexdigest()


def file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["/usr/bin/git", *args], cwd=root, check=True, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout.strip()


def exact_keys(value: dict[str, object], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{label} key census mismatch")


def validate_authority_identifier(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 128 \
            or any(not (character.isascii() and (character.isalnum() or character in "-_")) for character in value):
        raise ValueError(f"unsafe {label}")
    return value


def validate_binding(root: Path, value: object, label: str) -> tuple[Path, str]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} binding")
    exact_keys(value, {"path", "sha256"}, label)
    relative, expected = value["path"], value["sha256"]
    if not isinstance(relative, str) or not isinstance(expected, str):
        raise ValueError(f"{label} binding types")
    path = root / relative
    if Path(relative).is_absolute() or path.is_symlink() or file_sha(path) != expected:
        raise ValueError(f"{label} binding mismatch")
    return path, expected


def approval_template(contract_path: Path, out: Path) -> None:
    _, contract_sha = load(contract_path)
    value = {
        "schema": APPROVAL_SCHEMA,
        "decision": "NOT_AUTHORIZED_TEMPLATE",
        "statement": "INERT TEMPLATE; DOES NOT AUTHORIZE EXECUTION",
        "authorization_id": "FUTURE_HUMAN_ASSIGNED",
        "attempt_id": "F017-NATIVE-BOUNDED-P1-ATTEMPT-1",
        "branch": "feat/017-rust-native-inference-runtime",
        "readiness_head": "FUTURE_ACCEPTED_HEAD",
        "contract_sha256": contract_sha,
        "domain_declaration": {"path": "FUTURE_COMMITTED_PATH", "sha256": "FUTURE_SHA256"},
        "final_review": {
            "path": "FUTURE_COMMITTED_PATH", "sha256": "FUTURE_SHA256",
            "reviewer_model": "claude-fable-5", "verdict": "FUTURE_ACCEPT_OR_REJECT",
            "blocking_count": None, "non_blocking_required_count": None
        }
    }
    out.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def authorize(repo: Path, approval_path: Path, contract_path: Path) -> Path:
    approval, approval_sha = load(approval_path)
    contract, contract_sha = load(contract_path)
    exact_keys(approval, {
        "schema", "decision", "statement", "authorization_id", "attempt_id", "branch",
        "readiness_head", "contract_sha256", "domain_declaration", "final_review"
    }, "human approval")
    if approval["schema"] != APPROVAL_SCHEMA or approval["decision"] != DECISION \
            or approval["statement"] != STATEMENT or approval["contract_sha256"] != contract_sha:
        raise ValueError("human approval authority mismatch")
    validate_authority_identifier(approval["authorization_id"], "authorization identity")
    validate_authority_identifier(approval["attempt_id"], "attempt identity")
    final_review = approval["final_review"]
    if not isinstance(final_review, dict):
        raise ValueError("final review binding")
    exact_keys(final_review, {"path", "sha256", "reviewer_model", "verdict", "blocking_count", "non_blocking_required_count"}, "final review")
    if final_review["reviewer_model"] != "claude-fable-5" or final_review["verdict"] != "ACCEPT" \
            or final_review["blocking_count"] != 0 or final_review["non_blocking_required_count"] != 0:
        raise ValueError("final review is not accepting")
    declaration_path, declaration_sha = validate_binding(repo, approval["domain_declaration"], "domain declaration")
    review_path, review_sha = validate_binding(repo, {"path": final_review["path"], "sha256": final_review["sha256"]}, "final review")
    del declaration_path, review_path
    branch, head = approval["branch"], approval["readiness_head"]
    if branch != contract["branch"] or not isinstance(head, str) or len(head) != 40:
        raise ValueError("readiness identity mismatch")
    if git(repo, "branch", "--show-current") != branch or git(repo, "rev-parse", "HEAD") != head \
            or git(repo, "rev-parse", f"origin/{branch}") != head or git(repo, "status", "--porcelain"):
        raise ValueError("repository is not the accepted clean readiness head")
    state_root = Path(str(contract["state_root"]))
    parent = state_root.parent.resolve(strict=True)
    if parent / state_root.name != state_root or state_root.exists():
        raise ValueError("state root is not a fresh exact path")
    state_root.mkdir(mode=0o700)
    output = state_root / "authorization.json"
    authorities = contract["authorities"]
    checkpoint = contract["checkpoint"]
    one = contract["one_shot"]
    if approval["attempt_id"] != one["attempt_id"]:
        raise ValueError("attempt identity mismatch")
    value = {
        "authorization_id": approval["authorization_id"],
        "attempt_id": approval["attempt_id"],
        "domain_declaration_sha256": declaration_sha,
        "final_review_sha256": review_sha,
        "human_approval_sha256": approval_sha,
        "contract_sha256": contract_sha,
        "executor_sha256": contract["executor"]["sha256"],
        "git_head": head,
        "historical_master_ledger_sha256": authorities["historical_master_ledger_sha256"],
        "d0_sha256": authorities["d0"]["sha256"],
        "d1_sha256": authorities["d1"]["sha256"],
        "d2_sha256": authorities["d2"]["sha256"],
        "d3_5_result_sha256": authorities["d3_5_result"]["sha256"],
        "d3_5_acceptance_sha256": authorities["d3_5_acceptance"]["sha256"],
        "synthetic_full_graph_result_sha256": authorities["synthetic_full_graph_result"]["sha256"],
        "checkpoint_manifest_sha256": checkpoint["manifest"]["sha256"],
        "checkpoint_catalog_sha256": checkpoint["catalog"]["sha256"],
        "checkpoint_set_sha256": checkpoint["checkpoint_set_sha256"],
        "historical_master_terminal_value": authorities["historical_master_terminal_value"],
        "prompt_token": one["prompt_token"], "expected_token": one["expected_token"],
        "attempts": one["attempts"], "retries": one["retries"], "resume": one["resume"],
        "mandatory_stop": one["mandatory_stop"], "real_event_authorized": True
    }
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(output, flags, stat.S_IRUSR)
    try:
        os.write(fd, (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode())
        os.fsync(fd)
    finally:
        os.close(fd)
    parent_fd = os.open(state_root, os.O_RDONLY)
    try:
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)
    return output


def main() -> None:
    if len(sys.argv) == 4 and sys.argv[1] == "template":
        approval_template(Path(sys.argv[2]), Path(sys.argv[3]))
        return
    if len(sys.argv) == 4 and sys.argv[1] == "authorize":
        print(authorize(Path.cwd(), Path(sys.argv[2]), Path(sys.argv[3])))
        return
    raise SystemExit("usage: f017_native_p1_authorization.py template CONTRACT OUT | authorize HUMAN_APPROVAL CONTRACT")


if __name__ == "__main__":
    main()
