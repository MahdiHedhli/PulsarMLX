#!/usr/bin/env python3
"""Append-only S2 release v2 facade with producer-specific manifest support.

The accepted v1 release mechanics are reused without editing their bytes.  V2
changes only release identities, fixed destinations, approval/review identity,
and the bound operand consumer.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

import f017_representative_s2_release_wrapper_v1 as mechanics


ROOT = Path(__file__).resolve().parents[2]
AUTHORIZATION = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-s2-construction-authorization-v1.json"
ARITHMETIC = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-s2-arithmetic-v1.json"
S1_REUSE = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-s1-output-reuse-authorization-v1.json"
FFN_REUSE = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-ffn-output-reuse-authorization-v1.json"
APPROVAL_CONTRACT = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-s2-release-approval-contract-v2.json"
EXECUTOR = ROOT / "scripts/research/f017_representative_s2_executor_v2.py"
RELEASE = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-representative-s2-single-use-release-v2.json"
APPROVAL = ROOT / "docs/architecture/reviews/evidence/f017-representative-s2-single-use-release-v2-independent-approval-v1.json"

AUTHORIZATION_SHA = "b85b255f8aa47968ec7a83cbe332d0ee8928874959685495d0c6e808e204185a"
ARITHMETIC_SHA = "abbf158320d1fdfade5b8553e9ea1871c34830f541e4186074262fc702776e86"
S1_REUSE_SHA = "5c6437f2ab6ae2d01acc765430880195211e892dfb612fbb3b4125d9038ffe13"
FFN_REUSE_SHA = "983b119970f8d60bddb887d4478455b4d9eb638c3dc90853319cc302f290cd06"
APPROVAL_CONTRACT_SHA = "fd97ad9bdd7ee513359011d93518a47f6e70cb14300b62c23139a07bb0b831d2"
EXECUTOR_SHA = "af0633716d8d4008824d0f6147dbbc26fba5bcb365680f8a0d600ed9384c8217"
EVENT_ID = "F017-REPRESENTATIVE-S2-PROOF-REFERENCE-DERIVED-1"
RELEASE_ID = EVENT_ID + "-RELEASE-2"
ATTEMPT_ID = EVENT_ID + "-ATTEMPT-1"
REVIEWER_IDENTITY = "CLAUDE_FABLE_5_INDEPENDENT_ADVERSARIAL_REVIEWER"
REVIEWER_MODEL = "claude-fable-5"
APPROVER_IDENTITY = "CLAUDE_FABLE_5_INDEPENDENT_APPROVER"
APPROVER_MODEL = "claude-fable-5"
REVIEW_RE = re.compile(r"f017-representative-s2-release-v2-cycle-[0-9]{2}-independent-review\.json")

ReleaseError = mechanics.ReleaseError
require = mechanics.require
load = mechanics.load
canonical = mechanics.canonical
sha256 = mechanics.sha256
sha256_path = mechanics.sha256_path
open_directory = mechanics.open_directory
publish = mechanics.publish
output_manifest = mechanics.output_manifest


def fixed_paths(home: Path | None = None) -> dict[str, Path]:
    anchor = home if home is not None else Path.home()
    release_root = anchor / ".local/share/pulsarmlx/f017/representative-s2-release-2"
    return {
        "s1_root": anchor / ".local/share/pulsarmlx/f017/representative-s1-materialization-release-2/outputs",
        "ffn_root": anchor / ".local/share/pulsarmlx/f017/representative-ffn-composition-release-2/outputs",
        "release_root": release_root,
        "state_root": release_root / "attempt-state",
        "output_root": release_root / "outputs",
        "output": release_root / "outputs" / mechanics.OUTPUT_NAME,
        "manifest": release_root / "outputs" / mechanics.MANIFEST_NAME,
        "receipt": release_root / "attempt-state/s2-execution-receipt.json",
        "terminal": release_root / "attempt-state/terminal.json",
        "token": release_root / "go-token.json",
        "approval": APPROVAL,
    }


def operand_specs(authorization: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    s1 = authorization["inputs"]["s1"]
    ffn = authorization["inputs"]["ffn"]
    s1_spec = {
        "manifest_kind": "S1_SINGULAR_PRODUCER_V1",
        "manifest": {
            "relative_path": s1["private_manifest_relative_path"],
            "sha256": s1["private_manifest_sha256"],
            "byte_length": 427,
        },
        "artifact": {
            "relative_path": s1["relative_path"],
            "sha256": s1["sha256"],
            "semantic_role": s1["semantic_role"],
            "producer_semantic_role": s1["stage_role"],
            "dtype": s1["dtype"],
            "shape": s1["shape"],
            "byte_length": s1["byte_length"],
        },
    }
    ffn_spec = {
        "manifest_kind": "FFN_PLURAL_PRODUCER_V1",
        "manifest": {
            "relative_path": ffn["private_manifest_relative_path"],
            "sha256": ffn["private_manifest_sha256"],
            "byte_length": 627,
        },
        "artifact": {
            "relative_path": ffn["relative_path"],
            "sha256": ffn["sha256"],
            "semantic_role": ffn["semantic_role"],
            "semantic_surface": ffn["semantic_surface"],
            "dtype": ffn["dtype"],
            "shape": ffn["shape"],
            "byte_length": ffn["byte_length"],
        },
    }
    return s1_spec, ffn_spec


def validate_release(release_path: Path) -> dict[str, Any]:
    require(release_path.resolve() == RELEASE.resolve(), "RELEASE_PATH")
    release = load(release_path)
    require(
        release.get("schema") == "pulsarmlx.f017.representative-s2-single-use-release"
        and release.get("schema_version") == "2.0.0",
        "RELEASE_SCHEMA",
    )
    require(
        (release.get("event_id"), release.get("release_id"), release.get("attempt_id"))
        == (EVENT_ID, RELEASE_ID, ATTEMPT_ID),
        "RELEASE_IDENTITY",
    )
    require(
        release.get("status") == "PREPARED_FOR_INDEPENDENT_APPROVAL"
        and release.get("real_event_authorized") is False,
        "RELEASE_STATE",
    )
    require(release.get("stop_boundary") == "AFTER_REPRESENTATIVE_S2_OUTPUT_ONLY", "STOP_BOUNDARY")
    mechanics.validate_bindings(release)
    return release


def validate_approval(release: dict[str, Any], approval_path: Path) -> dict[str, Any]:
    contract = load(APPROVAL_CONTRACT)
    approval = load(approval_path)
    require(list(approval.keys()) == contract["approval_exact_fields"], "APPROVAL_EXACT_FIELDS_AND_ORDER")
    require(all(approval.get(key) == value for key, value in contract["required_constants"].items()), "APPROVAL_CONSTANTS")
    require((approval["event_id"], approval["release_id"], approval["attempt_id"]) == (EVENT_ID, RELEASE_ID, ATTEMPT_ID), "APPROVAL_IDENTITY")
    require(approval["release_sha256"] == sha256_path(RELEASE), "APPROVAL_RELEASE")
    require(approval["authorization_sha256"] == AUTHORIZATION_SHA and approval["arithmetic_contract_sha256"] == ARITHMETIC_SHA, "APPROVAL_CONTRACT_BINDING")
    require(approval["execution_code_head"] == release["authoritative_execution_code_head"], "APPROVAL_CODE_HEAD")
    review_rel = Path(approval["release_review_path"])
    require(not review_rel.is_absolute() and review_rel.parent.as_posix() == "docs/architecture/reviews/evidence" and REVIEW_RE.fullmatch(review_rel.name) is not None, "REVIEW_PATH")
    review_path = ROOT / review_rel
    require(sha256_path(review_path) == approval["release_review_sha256"], "REVIEW_SHA")
    review = load(review_path)
    require(set(review) == {
        "schema", "schema_version", "reviewer_identity", "reviewer_model", "reviewed_head",
        "release_path", "release_sha256", "authorization_sha256", "arithmetic_contract_sha256",
        "execution_code_head", "verdict", "blocking_findings", "non_blocking_required_findings",
        "defense_in_depth_findings", "statement",
    }, "REVIEW_EXACT_FIELDS")
    require(review.get("schema") == "pulsarmlx.f017.representative-s2-single-use-release-v2-independent-review" and review.get("schema_version") == "2.0.0", "REVIEW_SCHEMA")
    require(review.get("reviewer_identity") == approval["release_reviewer_identity"] == REVIEWER_IDENTITY, "REVIEWER_IDENTITY")
    require(review.get("reviewer_model") == approval["release_reviewer_model"] == REVIEWER_MODEL, "REVIEWER_MODEL")
    require(review.get("reviewed_head") == approval["reviewed_head"], "REVIEWED_HEAD")
    require(review.get("release_path") == RELEASE.relative_to(ROOT).as_posix(), "REVIEW_RELEASE_PATH")
    require(review.get("release_sha256") == approval["release_sha256"], "REVIEW_RELEASE_SHA")
    require(review.get("authorization_sha256") == AUTHORIZATION_SHA and review.get("arithmetic_contract_sha256") == ARITHMETIC_SHA, "REVIEW_AUTHORITY_BINDING")
    require(review.get("execution_code_head") == approval["execution_code_head"], "REVIEW_CODE_HEAD")
    require(review.get("verdict") == "ACCEPT" and review.get("blocking_findings") == [] and review.get("non_blocking_required_findings") == [], "REVIEW_VERDICT")
    release_rel = RELEASE.relative_to(ROOT).as_posix()
    require(sha256(mechanics.git_bytes(approval["reviewed_head"], release_rel)) == approval["release_sha256"], "REVIEWED_RELEASE_BYTES")
    require(approval["approver_identity"] == APPROVER_IDENTITY and approval["approver_model"] == APPROVER_MODEL, "APPROVER")
    return approval


# Configure the immutable v1 mechanics module as a v2 release substrate.
for name, value in {
    "AUTHORIZATION": AUTHORIZATION, "ARITHMETIC": ARITHMETIC, "S1_REUSE": S1_REUSE,
    "FFN_REUSE": FFN_REUSE, "APPROVAL_CONTRACT": APPROVAL_CONTRACT, "EXECUTOR": EXECUTOR,
    "RELEASE": RELEASE, "APPROVAL": APPROVAL, "AUTHORIZATION_SHA": AUTHORIZATION_SHA,
    "ARITHMETIC_SHA": ARITHMETIC_SHA, "S1_REUSE_SHA": S1_REUSE_SHA,
    "FFN_REUSE_SHA": FFN_REUSE_SHA, "APPROVAL_CONTRACT_SHA": APPROVAL_CONTRACT_SHA,
    "EXECUTOR_SHA": EXECUTOR_SHA, "EVENT_ID": EVENT_ID, "RELEASE_ID": RELEASE_ID,
    "ATTEMPT_ID": ATTEMPT_ID, "REVIEWER_IDENTITY": REVIEWER_IDENTITY,
    "REVIEWER_MODEL": REVIEWER_MODEL, "APPROVER_IDENTITY": APPROVER_IDENTITY,
    "APPROVER_MODEL": APPROVER_MODEL, "REVIEW_RE": REVIEW_RE,
    "fixed_paths": fixed_paths, "operand_specs": operand_specs,
    "validate_release": validate_release, "validate_approval": validate_approval,
}.items():
    setattr(mechanics, name, value)

validate_token = mechanics.validate_token
static_preflight = mechanics.static_preflight
load_executor = mechanics.load_executor
execute = mechanics.execute


def main() -> int:
    return mechanics.main()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ReleaseError, FileNotFoundError, PermissionError, OSError, KeyError, TypeError, ValueError) as error:
        print(json.dumps({"result": "FAIL_CLOSED", "error": f"{type(error).__name__}:{error}",
            "ledger": 175, "checkpoint_reads": 0, "shard_opens": 0}, sort_keys=True))
        raise SystemExit(2)
