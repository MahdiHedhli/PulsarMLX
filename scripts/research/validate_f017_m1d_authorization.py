#!/usr/bin/env python3
"""Fail-closed validator for the one-attempt F017 M1-D authorization binding."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

RUNTIME_SHA = "d68cb10758693dc61d3af7cf76b8019f6b3b235d"
PREVIOUS_TOOLING_SHA = "9d355cc3e1da55696a47b02170b40bd7bb5aeea7"
ACTIVATION_SHA = "dfc1df6cc6efa38c5c0f5bf086757ed78baf4cfc6f721da1e0ae7f73560193c2"

EXPECTED_HASHES = {
    "m1_a_evidence": "aa0e480261db437eaa788f0dfcba10eba9c32b6e1448c566e5c426df62e5a805",
    "m1_b_evidence": "9f9bd444e0fcc2dce3c6bcc119c6113e1c7885eb863459bf73cacce1ff285770",
    "m1_c_evidence": "343548afefd4edbe844f0645c63cf0b9cb53edfcdbfc3b3d8e4b15f7c6c3041e",
    "checkpoint_set": "d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee",
    "catalog": "0f0425106a240c5062acab9fc41b1b2651680c6ad06fe476214f88a8d2a177f0",
    "tensor_map": "ea0786f0e890af01dc111d355ef64aec1ca4898de5432197258bacccfaecc223",
    "boundary": "d4333ab9a6cd8638434f61c4c78f729869c5690305cc6de7ba86add611443613",
    "activation_payload": ACTIVATION_SHA,
    "decoder": "aac49f628446cc41c295e690114632673aefc4e3f08663bd11216db9fd9cfbdd",
    "scaffold": "3948039430cf48509a63757d97a21099b6e08ea46fcf6f022df06493a5f8a6b5",
    "tier_b": "f93e7a90684c93e78c03e054f62be932b3e16a120e63f41ba1d64f6d6e26a28b",
}

PROVENANCE = {
    "activation_generation_source": {
        "path": "scripts/research/generate_f017_m1d_projection_oracle.py",
        "git_commit": "992081315073d8eb4eb31a2bb2f1b7b77b9c0ccd",
        "sha256": "29c5c51a8f440e06d6584a71e0b79283d2bd6f806a2435c15ff93f3a0cae7984",
    },
    "fixture_finalization_source": {
        "path": "scripts/research/generate_f017_m1d_projection_oracle.py",
        "git_commit": RUNTIME_SHA,
        "sha256": "0299066d46211d1921ded772ab907fcd9e9f1c8e3d2c497d979914a30c3dbd92",
    },
    "real_reference_preparer_source": {
        "path": "scripts/research/prepare_f017_m1d_real_reference.py",
        "git_commit": RUNTIME_SHA,
        "sha256": "bdcf8b999de5426872cb31f971b455028746959b30fb2bdf4c2f750f335b7fea",
    },
}

CONTRACT_PATHS = {
    "boundary": "specs/017-rust-native-inference-runtime/contracts/m1d-projection-boundary-v1.json",
    "decoder": "specs/017-rust-native-inference-runtime/contracts/m1d-q8-0-decoder-v1.json",
    "scaffold": "specs/017-rust-native-inference-runtime/contracts/m1d-exact-scaffold-v1.json",
    "tier_b": "specs/017-rust-native-inference-runtime/contracts/production-m1d-projection-tier-b-v1.json",
    "repeat_integrity": "specs/017-rust-native-inference-runtime/contracts/m1d-repeat-integrity-v1.json",
    "oracle_ordering": "specs/017-rust-native-inference-runtime/contracts/m1d-oracle-ordering-v1.json",
}

ALLOWED_POST_TOOLING_PATHS = {
    "docs/architecture/reviews/f017-m1-d-fresh-authorization.md",
    "docs/architecture/reviews/evidence/f017-m1-d-authorization-binding-v1.json",
    "docs/architecture/reviews/f017-m1-d-packet-provenance-closure.md",
    "docs/architecture/reviews/evidence/f017-dogfood-readiness-v1.json",
}
PACKET_PATH = "docs/architecture/reviews/f017-m1-d-fresh-authorization.md"


class ValidationError(ValueError):
    pass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, check=True, text=True, capture_output=True
    )
    return result.stdout.strip()


def git_bytes(repo: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True
    ).stdout


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def validate_document(document: dict, repo: Path, *, validate_git: bool = True) -> None:
    require(document.get("schema") == "pulsarmlx.f017.m1d-authorization-binding", "schema mismatch")
    require(document.get("schema_version") == "1.0.0", "schema version mismatch")
    require(document.get("status") == "authorized_exactly_one_not_executed", "status mismatch")
    require(document.get("runtime_sha") == RUNTIME_SHA, "runtime SHA mismatch")
    require(document.get("previous_tooling_sha") == PREVIOUS_TOOLING_SHA, "previous tooling SHA mismatch")
    tooling_sha = document.get("tooling_sha")
    require(isinstance(tooling_sha, str) and len(tooling_sha) == 40, "tooling SHA missing")
    try:
        git(repo, "cat-file", "-e", f"{tooling_sha}^{{commit}}")
    except subprocess.CalledProcessError as error:
        raise ValidationError("tooling SHA is not a commit") from error
    require(
        git(repo, "merge-base", "--is-ancestor", RUNTIME_SHA, tooling_sha) == "",
        "runtime is not ancestor of tooling",
    )

    handoff = document.get("handoff")
    require(isinstance(handoff, dict), "handoff binding missing")
    handoff_path = handoff.get("path")
    require(handoff_path == "docs/architecture/reviews/f017-m1-d-real-projection-handoff.md", "handoff path mismatch")
    require(sha256((repo / handoff_path).read_bytes()) == handoff.get("sha256"), "handoff SHA mismatch")

    direct = document.get("direct_bindings")
    require(isinstance(direct, dict), "direct bindings missing")
    for name, expected in EXPECTED_HASHES.items():
        require(direct.get(name) == expected, f"{name} binding mismatch")
    for name in ("repeat_integrity", "oracle_ordering"):
        require(name in direct and len(direct[name]) == 64, f"{name} binding missing")
        require(sha256((repo / CONTRACT_PATHS[name]).read_bytes()) == direct[name], f"{name} file mismatch")
    for name in ("boundary", "decoder", "scaffold", "tier_b"):
        require(sha256((repo / CONTRACT_PATHS[name]).read_bytes()) == direct[name], f"{name} file mismatch")

    provenance = document.get("provenance")
    require(isinstance(provenance, dict) and set(provenance) == set(PROVENANCE), "provenance roles ambiguous")
    for role, expected in PROVENANCE.items():
        require(provenance.get(role) == expected, f"{role} mismatch")
        if role == "activation_generation_source":
            historical = git_bytes(repo, "show", f"{expected['git_commit']}:{expected['path']}")
            require(sha256(historical) == expected["sha256"], "historical activation generator mismatch")
        else:
            require(sha256((repo / expected["path"]).read_bytes()) == expected["sha256"], f"{role} file mismatch")

    activation = document.get("activation")
    require(
        activation == {
            "payload_sha256": ACTIVATION_SHA,
            "element_count": 6144,
            "dtype": "little_endian_f32",
            "seed": 17017004,
            "prng": "PCG64",
            "python": "3.13.13",
            "numpy": "2.4.5",
            "bytes_changed_by_finalization_remediation": False,
        },
        "activation continuity mismatch",
    )
    execution = document.get("execution")
    require(
        execution == {
            "conceptual_projection_count": 1,
            "production_repeat_count": 10,
            "all_repeat_hashes_equal_required": True,
            "oracle_finalized_before_candidate_required": True,
            "mandatory_stop_before_m1_e": True,
        },
        "execution scope mismatch",
    )
    packet = (repo / PACKET_PATH).read_text()
    require("AUTHORIZED FOR EXACTLY ONE M1-D ATTEMPT / NOT EXECUTED" in packet, "packet status mismatch")
    packet_values = [RUNTIME_SHA, tooling_sha, handoff["sha256"], *direct.values()]
    packet_values.extend(role["sha256"] for role in provenance.values())
    for value in packet_values:
        require(value in packet, f"packet omits direct binding {value}")

    if validate_git:
        head = git(repo, "rev-parse", "HEAD")
        require(git(repo, "merge-base", "--is-ancestor", tooling_sha, head) == "", "tooling is not ancestor of head")
        changed = set(filter(None, git(repo, "diff", "--name-only", f"{tooling_sha}..{head}").splitlines()))
        require(changed <= ALLOWED_POST_TOOLING_PATHS, "post-tooling drift is not authorization/docs-only")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("binding", type=Path)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    document = json.loads(args.binding.read_text())
    validate_document(document, args.repo.resolve())
    print("F017 M1-D authorization binding: valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
