#!/usr/bin/env python3
"""Fail-closed validation for the separately authorized M1-D attempt 2."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

RUNTIME_SHA = "258127d4b5e4d2cca592c8b3ec5403a98e39f29f"
FAILED_ATTEMPT_SHA = "a5aefaaf59583dad87765303e159986c895017c20ea80eb874cd447ad80f9a62"
HANDOFF_PATH = "docs/architecture/reviews/f017-m1-d-attempt-2-handoff.md"
PACKET_PATH = "docs/architecture/reviews/f017-m1-d-attempt-2-authorization.md"
BINDING_PATH = "docs/architecture/reviews/evidence/f017-m1-d-attempt-2-authorization-v1.json"

DIRECT_BINDINGS = {
    "m1_a_evidence": "aa0e480261db437eaa788f0dfcba10eba9c32b6e1448c566e5c426df62e5a805",
    "m1_b_evidence": "9f9bd444e0fcc2dce3c6bcc119c6113e1c7885eb863459bf73cacce1ff285770",
    "m1_c_evidence": "343548afefd4edbe844f0645c63cf0b9cb53edfcdbfc3b3d8e4b15f7c6c3041e",
    "checkpoint_set": "d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee",
    "catalog": "0f0425106a240c5062acab9fc41b1b2651680c6ad06fe476214f88a8d2a177f0",
    "tensor_map": "ea0786f0e890af01dc111d355ef64aec1ca4898de5432197258bacccfaecc223",
    "boundary": "d4333ab9a6cd8638434f61c4c78f729869c5690305cc6de7ba86add611443613",
    "activation": "dfc1df6cc6efa38c5c0f5bf086757ed78baf4cfc6f721da1e0ae7f73560193c2",
    "decoder": "aac49f628446cc41c295e690114632673aefc4e3f08663bd11216db9fd9cfbdd",
    "scaffold": "3948039430cf48509a63757d97a21099b6e08ea46fcf6f022df06493a5f8a6b5",
    "tier_b": "f93e7a90684c93e78c03e054f62be932b3e16a120e63f41ba1d64f6d6e26a28b",
    "repeat_integrity": "1e8ceff5bca49d8c22c38342c3e938af189b819333c075558e1e242869a6685f",
    "oracle_ordering": "f8b2d48d4a3ff4ef502c33c4b29c4f2390f80ff4d03a2964c988a189ea341528",
    "path_resolution": "40c66a00ea9dcc2b58dc01c7f336cdb5a9098c0ea59920c384727e6ef9cc360d",
    "package_schema": "eec3ae97ac8c2ecb04ac982abe8b1bcec313a57888fa5bb66370e31485fc2e2a",
}

PROVENANCE = {
    "activation_generation_source": "29c5c51a8f440e06d6584a71e0b79283d2bd6f806a2435c15ff93f3a0cae7984",
    "fixture_finalization_source": "0299066d46211d1921ded772ab907fcd9e9f1c8e3d2c497d979914a30c3dbd92",
    "real_reference_preparer_source": "0d1d70671ab424e0dc9bead70dfba58756126bd6d6669cb08fe5e022ed4761d4",
}

CONTENT_PATHS = {
    "boundary": "specs/017-rust-native-inference-runtime/contracts/m1d-projection-boundary-v1.json",
    "decoder": "specs/017-rust-native-inference-runtime/contracts/m1d-q8-0-decoder-v1.json",
    "scaffold": "specs/017-rust-native-inference-runtime/contracts/m1d-exact-scaffold-v1.json",
    "tier_b": "specs/017-rust-native-inference-runtime/contracts/production-m1d-projection-tier-b-v1.json",
    "repeat_integrity": "specs/017-rust-native-inference-runtime/contracts/m1d-repeat-integrity-v1.json",
    "oracle_ordering": "specs/017-rust-native-inference-runtime/contracts/m1d-oracle-ordering-v1.json",
    "path_resolution": "specs/017-rust-native-inference-runtime/contracts/m1d-artifact-path-resolution-v1.json",
    "package_schema": "specs/017-rust-native-inference-runtime/contracts/m1d-projection-package-v2.schema.json",
}

ALLOWED_POST_TOOLING = {
    HANDOFF_PATH,
    PACKET_PATH,
    BINDING_PATH,
    "docs/architecture/reviews/f017-m1-d-package-root-remediation-review.md",
    "docs/architecture/reviews/evidence/f017-dogfood-readiness-v1.json",
    "specs/017-rust-native-inference-runtime/tasks.md",
}


class ValidationError(ValueError):
    pass


def require(value: bool, message: str) -> None:
    if not value:
        raise ValidationError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def load(path: Path) -> dict:
    def pairs(items: list[tuple[str, object]]) -> dict:
        result = {}
        for key, value in items:
            if key in result:
                raise ValidationError(f"duplicate key: {key}")
            result[key] = value
        return result

    value = json.loads(path.read_text(), object_pairs_hook=pairs)
    require(isinstance(value, dict), "authorization must be an object")
    return value


def validate(document: dict, repo: Path, *, validate_git: bool = True, validate_packet: bool = True) -> None:
    require(set(document) == {
        "schema", "schema_version", "status", "attempt", "runtime_sha", "tooling_sha",
        "failed_attempt", "handoff", "path_contract", "direct_bindings", "provenance",
        "execution", "stop_policy"
    }, "authorization fields mismatch")
    require(document["schema"] == "pulsarmlx.f017.m1d-attempt-2-authorization", "schema mismatch")
    require(document["schema_version"] == "1.0.0", "schema version mismatch")
    require(document["status"] == "authorized_exactly_one_attempt_2_not_executed", "status mismatch")
    require(document["attempt"] == 2, "attempt mismatch")
    require(document["runtime_sha"] == RUNTIME_SHA, "runtime SHA mismatch")
    tooling = document["tooling_sha"]
    require(
        isinstance(tooling, str)
        and len(tooling) == 40
        and tooling != "0" * 40
        and all(character in "0123456789abcdef" for character in tooling),
        "tooling SHA mismatch",
    )
    require(document["failed_attempt"] == {
        "attempt": 1,
        "verdict": "rejected",
        "failure_code": "m1d_contract_read",
        "evidence_sha256": FAILED_ATTEMPT_SHA,
        "authorization_consumed": True,
    }, "failed attempt preservation mismatch")
    handoff = document["handoff"]
    require(handoff.get("path") == HANDOFF_PATH, "handoff path mismatch")
    require(sha256(repo / HANDOFF_PATH) == handoff.get("sha256"), "handoff hash mismatch")
    require(document["path_contract"] == {
        "version": "f017-m1d-artifact-path-resolution-v1",
        "sha256": DIRECT_BINDINGS["path_resolution"],
        "package_schema_version": "2.0.0",
        "repository_root": "explicit_git_identity_verified",
        "package_root": "canonical_package_parent",
    }, "path contract mismatch")
    require(document["direct_bindings"] == DIRECT_BINDINGS, "direct bindings mismatch")
    for name, path in CONTENT_PATHS.items():
        require(sha256(repo / path) == DIRECT_BINDINGS[name], f"{name} content mismatch")
    require(document["provenance"] == PROVENANCE, "provenance mismatch")
    require(sha256(repo / "scripts/research/prepare_f017_m1d_real_reference.py") == PROVENANCE["real_reference_preparer_source"], "preparer content mismatch")
    require(document["execution"] == {
        "conceptual_projection_count": 1,
        "production_repeat_count": 10,
        "all_repeat_hashes_equal_required": True,
        "oracle_finalized_before_candidate_required": True,
    }, "execution scope mismatch")
    require(document["stop_policy"] == {
        "no_auto_retry": True,
        "mandatory_stop_before_m1_e": True,
    }, "stop policy mismatch")
    if validate_git:
        git(repo, "cat-file", "-e", f"{tooling}^{{commit}}")
        require(git(repo, "merge-base", "--is-ancestor", RUNTIME_SHA, tooling) == "", "runtime is not an ancestor of tooling")
        head = git(repo, "rev-parse", "HEAD")
        require(git(repo, "merge-base", "--is-ancestor", tooling, head) == "", "tooling is not an ancestor of head")
        changed = set(filter(None, git(repo, "diff", "--name-only", f"{tooling}..{head}").splitlines()))
        require(changed <= ALLOWED_POST_TOOLING, "post-tooling runtime drift")
    if validate_packet:
        packet = (repo / PACKET_PATH).read_text()
        required = [RUNTIME_SHA, tooling, handoff["sha256"], FAILED_ATTEMPT_SHA]
        required.extend(DIRECT_BINDINGS.values())
        required.extend(PROVENANCE.values())
        for value in required:
            require(value in packet, f"packet omits {value}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("binding", type=Path)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    validate(load(args.binding), args.repo.resolve())
    print("F017 M1-D attempt-2 authorization: valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
