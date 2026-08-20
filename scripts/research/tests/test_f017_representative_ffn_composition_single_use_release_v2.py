#!/usr/bin/env python3
"""Checkpoint-free approval-chain, mutation, race, and durability tests for FFN release v2."""

from __future__ import annotations

import copy
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
from unittest import mock
import sys


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/research"))


def module(name: str, relative: str):
    specification = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert specification and specification.loader
    value = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(value)
    return value


validator = module("f017_ffn_release_v2_validator", "scripts/research/validate_f017_representative_ffn_composition_single_use_release_v2.py")
wrapper = module("f017_ffn_release_v2_wrapper", "scripts/research/f017_representative_ffn_composition_release_wrapper_v2.py")
terminalizer = module("f017_ffn_release_v2_terminalizer", "scripts/research/f017_representative_ffn_composition_release_terminalizer_v2.py")


class Result:
    def __init__(self, returncode: int, stdout: bytes = b"") -> None:
        self.returncode = returncode
        self.stdout = stdout


class FFNReleaseV2Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.release = validator.load(validator.RELEASE_PATH)

    def reject_release(self, mutation) -> None:
        candidate = copy.deepcopy(self.release)
        mutation(candidate)
        with self.assertRaises((validator.ValidationError, KeyError, TypeError)):
            validator.validate(candidate, repo=True)

    def approval(self) -> dict:
        return {
            "schema": "pulsarmlx.f017.representative-ffn-composition-single-use-release-independent-approval",
            "schema_version": "2.0.0",
            "event_id": wrapper.EVENT_ID,
            "release_id": wrapper.RELEASE_ID,
            "attempt_id": wrapper.ATTEMPT_ID,
            "release_sha256": "a" * 64,
            "authorization_sha256": wrapper.AUTHORIZATION_SHA,
            "arithmetic_contract_sha256": wrapper.ARITHMETIC_SHA,
            "execution_code_head": self.release["authoritative_execution_code_head"],
            "reviewed_head": "b" * 40,
            "release_review_path": "docs/architecture/reviews/evidence/f017-representative-ffn-composition-release-v2-cycle-01-independent-review.json",
            "release_review_sha256": "c" * 64,
            "release_reviewer_identity": wrapper.REVIEWER_IDENTITY,
            "release_reviewer_model": wrapper.REVIEWER_MODEL,
            "approver_identity": wrapper.APPROVER_IDENTITY,
            "approver_model": wrapper.APPROVER_MODEL,
            "verdict": "ACCEPT",
            "statement": "REPRESENTATIVE FFN COMPOSITION SINGLE-USE RELEASE V2 APPROVED",
            "approval_does_not_execute": True,
            "approval_is_not_token": True,
            "real_event_authorized": False,
            "ledger": 175,
            "checkpoint_read_budget": 0,
            "shard_open_budget": 0,
            "future_ffn_compositions": 1,
            "s1_materializations": 0,
            "s2_constructions": 0,
            "stop_boundary": "AFTER_REPRESENTATIVE_FFN_OUTPUT_ONLY",
        }

    def test_repository_release_passes(self) -> None:
        validator.validate(copy.deepcopy(self.release), repo=True)

    def test_release_load_bearing_mutations_reject(self) -> None:
        mutations = [
            lambda d: d.__setitem__("release_v1_disposition", "VALID_FOR_EXECUTION"),
            lambda d: d.__setitem__("authoritative_execution_code_head", "0" * 40),
            lambda d: d["bindings"]["ffn_authorization"].__setitem__("sha256", "0" * 64),
            lambda d: d["bindings"]["arithmetic_contract"].__setitem__("sha256", "0" * 64),
            lambda d: d["bindings"]["approval_contract"].__setitem__("sha256", "0" * 64),
            lambda d: d["bindings"]["v1_supersession"].__setitem__("sha256", "0" * 64),
            lambda d: d["bindings"]["release_wrapper"].__setitem__("sha256", "0" * 64),
            lambda d: d["bindings"]["terminalizer"].__setitem__("sha256", "0" * 64),
            lambda d: d["retained_inputs"]["routed"].__setitem__("sha256", "0" * 64),
            lambda d: d["retained_inputs"]["shared"].__setitem__("sha256", "0" * 64),
            lambda d: d["numerical_surface"].__setitem__("classification", "PRODUCTION_SERIAL_F32"),
            lambda d: d["numerical_surface"].__setitem__("shared_promotion", "f32"),
            lambda d: d["single_use"].__setitem__("retry", True),
            lambda d: d["single_use"].__setitem__("second_attempt", True),
            lambda d: d["output_banking"].__setitem__("dtype", "little-endian-f32"),
            lambda d: d["accounting"].__setitem__("starting_ledger", 174),
            lambda d: d["accounting"].__setitem__("checkpoint_reads", 1),
            lambda d: d["accounting"].__setitem__("future_ffn_compositions", 2),
            lambda d: d["accounting"].__setitem__("s1_materializations", 1),
            lambda d: d["accounting"].__setitem__("s2_constructions", 1),
            lambda d: d["prohibitions"].__setitem__("s1_input_interface", False),
            lambda d: d["prohibitions"].__setitem__("s2_construction", False),
            lambda d: d.__setitem__("stop_boundary", "AFTER_S2"),
            lambda d: d["future_approval"].__setitem__("release_review_sha256_required", False),
            lambda d: d["future_approval"].__setitem__("reviewed_head_enforced", False),
        ]
        for index, mutation in enumerate(mutations):
            with self.subTest(index=index):
                self.reject_release(mutation)

    def test_exact_approval_schema_and_authority_fields(self) -> None:
        approval = self.approval()
        approval["release_sha256"] = wrapper.sha256_path(wrapper.RELEASE)
        wrapper.validate_approval_document(self.release, approval, wrapper.sha256_path(wrapper.RELEASE))
        mutations = [
            lambda d: d.pop("release_review_sha256"),
            lambda d: d.__setitem__("extra", True),
            lambda d: d.__setitem__("release_sha256", "0" * 64),
            lambda d: d.__setitem__("authorization_sha256", "0" * 64),
            lambda d: d.__setitem__("arithmetic_contract_sha256", "0" * 64),
            lambda d: d.__setitem__("execution_code_head", "0" * 40),
            lambda d: d.__setitem__("release_id", wrapper.EVENT_ID + "-RELEASE-1"),
            lambda d: d.__setitem__("schema_version", "1.0.0"),
            lambda d: d.__setitem__("approver_model", "claude-opus-4"),
            lambda d: d.__setitem__("future_ffn_compositions", 2),
            lambda d: d.__setitem__("s1_materializations", 1),
            lambda d: d.__setitem__("s2_constructions", 1),
        ]
        for index, mutation in enumerate(mutations):
            candidate = copy.deepcopy(approval)
            mutation(candidate)
            with self.subTest(index=index), self.assertRaises(wrapper.ReleaseError):
                wrapper.validate_approval_document(self.release, candidate, wrapper.sha256_path(wrapper.RELEASE))

    def test_review_sha_head_and_reviewer_are_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            release_path = root / "release.json"
            release_raw = wrapper.canonical_json({"release": "v2"})
            release_path.write_bytes(release_raw)
            wrapper_raw = b"wrapper-v2"
            minimal_release = {
                "authoritative_execution_code_head": "d" * 40,
                "bindings": {"release_wrapper": {"path": wrapper.WRAPPER_RELATIVE_PATH, "sha256": hashlib.sha256(wrapper_raw).hexdigest()}},
            }
            review_path = root / "review.json"
            review = {
                "schema": "pulsarmlx.f017.representative-ffn-composition-single-use-release-v2-independent-review",
                "schema_version": "1.0.0",
                "reviewer_identity": wrapper.REVIEWER_IDENTITY,
                "reviewer_model": wrapper.REVIEWER_MODEL,
                "reviewed_head": "d" * 40,
                "release_path": wrapper.RELEASE_RELATIVE_PATH,
                "release_sha256": hashlib.sha256(release_raw).hexdigest(),
                "execution_code_head": "d" * 40,
                "verdict": "ACCEPT",
                "blocking_findings": [],
                "non_blocking_required_findings": [],
                "defense_in_depth_findings": [],
                "statement": "REPRESENTATIVE FFN COMPOSITION SINGLE-USE RELEASE V2 ACCEPTED FOR SEPARATE APPROVAL",
            }
            review_raw = wrapper.canonical_json(review)
            review_path.write_bytes(review_raw)
            approval = self.approval()
            approval.update({
                "release_sha256": hashlib.sha256(release_raw).hexdigest(),
                "execution_code_head": "d" * 40,
                "reviewed_head": "d" * 40,
                "release_review_sha256": hashlib.sha256(review_raw).hexdigest(),
            })

            def git_bytes(_head, path):
                return release_raw if path == wrapper.RELEASE_RELATIVE_PATH else wrapper_raw

            def run(args, **_kwargs):
                if "merge-base" in args:
                    return Result(0)
                return Result(0, review_raw)

            with mock.patch.object(wrapper, "RELEASE", release_path), mock.patch.object(wrapper, "require_review_path", return_value=review_path), mock.patch.object(wrapper, "git_bytes", side_effect=git_bytes), mock.patch.object(wrapper.subprocess, "run", side_effect=run):
                wrapper.validate_review_chain(minimal_release, approval)
                cases = [
                    ("incorrect review SHA", lambda a, r: a.__setitem__("release_review_sha256", "0" * 64)),
                    ("stale v1 review SHA", lambda a, r: a.__setitem__("release_review_sha256", wrapper.V1_REVIEW_SHA)),
                    ("wrong reviewed head", lambda a, r: a.__setitem__("reviewed_head", "e" * 40)),
                    ("head changed review unchanged", lambda a, r: a.__setitem__("reviewed_head", "f" * 40)),
                    ("wrong reviewer identity", lambda a, r: a.__setitem__("release_reviewer_identity", "FORGED")),
                    ("wrong reviewer model", lambda a, r: a.__setitem__("release_reviewer_model", "claude-opus-4")),
                ]
                for label, mutation in cases:
                    candidate = copy.deepcopy(approval)
                    mutated_review = copy.deepcopy(review)
                    mutation(candidate, mutated_review)
                    with self.subTest(label=label), self.assertRaises(wrapper.ReleaseError):
                        wrapper.validate_review_chain(minimal_release, candidate)

    def test_forged_and_stale_go_tokens_reject(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            release_path = root / "release.json"
            approval_path = root / "approval.json"
            token_path = root / "token.json"
            release_path.write_bytes(wrapper.canonical_json(self.release))
            approval = self.approval()
            approval["release_sha256"] = wrapper.sha256_path(release_path)
            approval_path.write_bytes(wrapper.canonical_json(approval))
            token = {
                "approval_sha256": wrapper.sha256_path(approval_path),
                "attempt_id": wrapper.ATTEMPT_ID,
                "authorization_sha256": wrapper.AUTHORIZATION_SHA,
                "disposition": "GO_EXECUTE_ONCE_NO_RETRY",
                "event_id": wrapper.EVENT_ID,
                "real_event_authorized": True,
                "release_id": wrapper.RELEASE_ID,
                "release_sha256": wrapper.sha256_path(release_path),
            }
            token_path.write_bytes(wrapper.canonical_json(token))
            with mock.patch.object(wrapper, "validate_review_chain"):
                wrapper.authorize(release_path, approval_path, token_path)
                for field, value in (("approval_sha256", "0" * 64), ("release_id", wrapper.EVENT_ID + "-RELEASE-1"), ("release_sha256", "0" * 64), ("disposition", "GO_RETRY")):
                    candidate = copy.deepcopy(token)
                    candidate[field] = value
                    token_path.write_bytes(wrapper.canonical_json(candidate))
                    with self.subTest(field=field), self.assertRaises(wrapper.ReleaseError):
                        wrapper.authorize(release_path, approval_path, token_path)

    def test_concurrent_attempt_has_exactly_one_winner_and_zero_computation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = wrapper.fixed_paths(Path(temporary))
            paths["release_root"].mkdir(parents=True, mode=0o700)
            paths["output_root"].mkdir(mode=0o700)
            release = Path(temporary) / "release.json"
            approval = Path(temporary) / "approval.json"
            token = Path(temporary) / "token.json"
            release.write_text("{}\n", encoding="utf-8")
            approval.write_bytes(wrapper.canonical_json({"release_review_sha256": "a" * 64, "reviewed_head": "b" * 40}))
            token.write_text("{}\n", encoding="utf-8")

            def start():
                try:
                    wrapper.begin_attempt(paths, release, approval, token)
                    return "WIN"
                except (wrapper.ReleaseError, FileExistsError):
                    return "LOSE"

            with ThreadPoolExecutor(max_workers=2) as pool:
                outcomes = list(pool.map(lambda _: start(), range(2)))
            self.assertEqual(sorted(outcomes), ["LOSE", "WIN"])
            self.assertTrue((paths["state_root"] / "attempt-start.json").is_file())
            self.assertFalse((paths["state_root"] / "ffn-start.json").exists())
            result = terminalizer.reconcile(paths["state_root"], paths["output"], paths["output_manifest"], release)
            self.assertEqual(result["disposition"], "INTERRUPTED_AFTER_ATTEMPT_START_BEFORE_FFN")
            self.assertEqual(result["ffn_compositions"], 0)

    def test_durable_ffn_start_and_terminal_failure_count_truthfully(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = wrapper.fixed_paths(Path(temporary))
            paths["release_root"].mkdir(parents=True, mode=0o700)
            paths["output_root"].mkdir(mode=0o700)
            release = Path(temporary) / "release.json"
            approval = Path(temporary) / "approval.json"
            token = Path(temporary) / "token.json"
            release.write_text("{}\n", encoding="utf-8")
            approval.write_bytes(wrapper.canonical_json({"release_review_sha256": "a" * 64, "reviewed_head": "b" * 40}))
            token.write_text("{}\n", encoding="utf-8")
            wrapper.begin_attempt(paths, release, approval, token)
            wrapper.begin_ffn(paths, release)
            wrapper.write_terminal(paths, "TERMINAL_FAILURE", None, None, None, "synthetic")
            result = terminalizer.reconcile(paths["state_root"], paths["output"], paths["output_manifest"], release)
            self.assertEqual(result["disposition"], "TERMINAL_FAILURE_RECONSTRUCTED")
            self.assertEqual(result["ffn_compositions"], 1)
            self.assertFalse(result["output_authority"])

    def test_output_validation_rejects_wrong_geometry_and_nonfinite(self) -> None:
        with self.assertRaises(wrapper.ReleaseError):
            wrapper.validate_output(bytes(wrapper.OUTPUT_BYTES - 1))
        raw = bytearray(wrapper.OUTPUT_BYTES)
        struct.pack_into("<d", raw, 0, math.nan)
        with self.assertRaises(wrapper.ReleaseError):
            wrapper.validate_output(bytes(raw))


if __name__ == "__main__":
    unittest.main()
