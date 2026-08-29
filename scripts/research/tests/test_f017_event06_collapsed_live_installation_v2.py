"""Sequence 14 collapsed-GO live-installation integration tests."""
from __future__ import annotations

import copy
import hashlib
import pickle
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RESEARCH = ROOT / "scripts/research"
sys.path.insert(0, str(RESEARCH))

from f017_event06_collapsed_go_path_v1 import COLLAPSED_GO_FIELDS
from f017_event06_collapsed_live_installation_v2 import (
    BoundSanitizedHumanDecisionV2,
    CheckpointBoundCandidateBundleV2,
    CollapsedLiveIntegrationStateV2,
    CollapsedLiveInstallationCapabilityV2,
    LiveCheckpointRootAuthorityV2,
    QualificationCheckpointRootAuthorityV2,
    QualificationInstallationCapabilityV2,
    commit_qualification_collapsed_installation,
    prepare_collapsed_production_installation,
    produce_checkpoint_bound_candidate_bundle,
    produce_collapsed_live_installation_capability,
    produce_qualification_installation_capability,
    resolve_live_checkpoint_root_authority,
)
from f017_event06_production_installation_v2 import FutureGoCapabilityV2
from f017_event06_sequence14_fixture_v1 import build_sequence14_qualification
from rehearse_f017_event06_collapsed_live_installation_no_access_v2 import rehearse


class CollapsedLiveInstallationV2Tests(unittest.TestCase):
    def test_real_public_end_to_end_composition_before_review(self) -> None:
        with tempfile.TemporaryDirectory(prefix="f017-seq14-test-") as directory:
            package = build_sequence14_qualification(Path(directory))
        self.assertEqual(package["gate"].get("result"), "PASS")
        self.assertTrue(package["gate"].get("package_claim_eligible"))
        self.assertFalse(package["gate"].get("package_started"))
        self.assertIs(type(package["bundle"]), CheckpointBoundCandidateBundleV2)
        counters = package["state"].snapshot()
        for name in (
            "sanitized_human_decisions_from_live_go",
            "collapsed_live_go_tokens",
            "canonical_live_reservations",
            "live_checkpoint_root_resolutions",
            "live_installation_commit_calls",
            "live_authorities_or_capabilities",
            "package_starts",
            "original_checkpoint_shard_opens",
            "original_checkpoint_identity_hash_reads",
            "original_checkpoint_payload_reads",
            "original_checkpoint_mmaps_or_tensor_reads",
            "numerical_operations",
            "event06_identities_instantiated",
            "event06_identities_consumed",
            "authorization_delta",
            "package_delta",
            "primary_delta",
            "secondary_delta",
            "p1_actions",
        ):
            self.assertEqual(counters[name], 0, name)

    def test_historical_eight_field_token_is_unchanged(self) -> None:
        self.assertEqual(len(COLLAPSED_GO_FIELDS), 8)
        self.assertEqual(len(set(COLLAPSED_GO_FIELDS)), 8)
        self.assertEqual(
            hashlib.sha256(
                (RESEARCH / "f017_event06_collapsed_go_path_v1.py").read_bytes()
            ).hexdigest(),
            "44576569769697cd8f9bfb7bbc4d274637ff47ff51d9c4f05f3f0173f92fd27b",
        )

    def test_legacy_second_go_capability_is_not_accepted(self) -> None:
        self.assertNotIn(
            "FutureGoCapabilityV2",
            (RESEARCH / "f017_event06_collapsed_live_installation_v2.py").read_text(),
        )
        forged = object.__new__(FutureGoCapabilityV2)
        self.assertNotIsInstance(forged, QualificationInstallationCapabilityV2)
        self.assertNotIsInstance(forged, CollapsedLiveInstallationCapabilityV2)

    def test_root_modes_are_exact_separate_types(self) -> None:
        self.assertIsNot(QualificationCheckpointRootAuthorityV2, LiveCheckpointRootAuthorityV2)
        with tempfile.TemporaryDirectory(prefix="f017-seq14-root-") as directory:
            package = build_sequence14_qualification(Path(directory))
            with self.assertRaises(TypeError):
                produce_checkpoint_bound_candidate_bundle(
                    package["preparation"],
                    package["identity"],
                    package["go"],
                    package["readiness"],
                    package["plan"],
                    object.__new__(LiveCheckpointRootAuthorityV2),
                    state=package["state"],
                )

    def test_live_producers_require_live_state_and_decision(self) -> None:
        with tempfile.TemporaryDirectory(prefix="f017-seq14-live-reject-") as directory:
            package = build_sequence14_qualification(Path(directory))
            with self.assertRaises(TypeError):
                resolve_live_checkpoint_root_authority(
                    package["decision"], state=package["state"]
                )

    def test_qualification_chain_cannot_cross_into_live_mode(self) -> None:
        with tempfile.TemporaryDirectory(prefix="f017-seq14-cross-mode-") as directory:
            package = build_sequence14_qualification(Path(directory))
            live_state = object.__new__(CollapsedLiveIntegrationStateV2)
            object.__setattr__(live_state, "_mode", "LIVE_CANONICAL")
            with self.assertRaises(TypeError):
                resolve_live_checkpoint_root_authority(
                    package["decision"], state=live_state
                )
            with self.assertRaises(ValueError):
                prepare_collapsed_production_installation(
                    package["decision"],
                    package["go"],
                    package["approval"],
                    package["preparation"],
                    package["bundle"],
                    package["readiness"],
                    package["plan"],
                    state=live_state,
                )
            with self.assertRaises(TypeError):
                produce_collapsed_live_installation_capability(
                    package["prepared"],
                    package["bundle"],
                    package["target"],
                    target_leaf="forbidden-live",
                    expires_at_unix_ns=2**62,
                    state=package["state"],
                )

    def test_authority_objects_reject_copy_pickle_and_reinitialization(self) -> None:
        with tempfile.TemporaryDirectory(prefix="f017-seq14-closed-") as directory:
            package = build_sequence14_qualification(Path(directory))
        for value in (
            package["decision"],
            package["approval"],
            package["preparation"],
            package["identity"],
            package["bundle"],
            package["prepared"],
            package["root_authority"],
            package["installed"],
            package["gate"],
        ):
            for operation in (copy.copy, copy.deepcopy, pickle.dumps):
                with self.assertRaises(TypeError):
                    operation(value)
        with self.assertRaises(TypeError):
            BoundSanitizedHumanDecisionV2()

    def test_qualification_capability_is_consumed_before_commit(self) -> None:
        with tempfile.TemporaryDirectory(prefix="f017-seq14-consume-") as directory:
            package = build_sequence14_qualification(Path(directory))
            with self.assertRaises(TypeError):
                commit_qualification_collapsed_installation(
                    package["prepared"], object.__new__(QualificationInstallationCapabilityV2),
                    state=package["state"],
                )

    def test_one_prepared_package_cannot_issue_a_second_capability(self) -> None:
        with tempfile.TemporaryDirectory(prefix="f017-seq14-capability-") as directory:
            package = build_sequence14_qualification(Path(directory))
            with self.assertRaisesRegex(
                ValueError, "prepared installation capability already issued"
            ):
                produce_qualification_installation_capability(
                    package["prepared"],
                    package["bundle"],
                    package["target"],
                    target_leaf="second-installation-attempt",
                    expires_at_unix_ns=2**62,
                )

    def test_production_shaped_rehearsal_stops_before_every_live_boundary(self) -> None:
        result = rehearse()
        self.assertEqual(result["result"], "PASS")
        self.assertEqual(result["original_checkpoint_access"], "NONE")
        self.assertFalse(result["event_06_executed"])
        self.assertFalse(result["gate_package_started"])
        self.assertFalse(any(result["observed_production_boundary_counters"].values()))

    def test_same_human_decision_cannot_replay_after_readiness_change(self) -> None:
        with tempfile.TemporaryDirectory(prefix="f017-seq14-replay-") as directory:
            root = Path(directory).resolve()
            registry = root / "shared-reservation"
            registry.mkdir(mode=0o700)
            build_sequence14_qualification(
                root / "first",
                now_unix_ns=4_000_000_000_000_000_000,
                readiness_variant="sequence-14-first",
                reservation_root=registry,
            )
            with self.assertRaisesRegex(ValueError, "human decision already consumed"):
                build_sequence14_qualification(
                    root / "second",
                    now_unix_ns=4_000_000_000_000_000_000,
                    readiness_variant="sequence-14-second",
                    reservation_root=registry,
                )


if __name__ == "__main__":
    unittest.main()
