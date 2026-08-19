#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
WRAPPER = ROOT / "scripts/research/f017_representative_m1f0_release_wrapper_v2.py"
SPEC = importlib.util.spec_from_file_location("release_wrapper_v2", WRAPPER)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ReleaseWrapperV2Tests(unittest.TestCase):
    @staticmethod
    def authorization_sha() -> str:
        return hashlib.sha256(MODULE.DEFAULT_AUTHORIZATION.read_bytes()).hexdigest()

    def release_contract(self) -> dict:
        return {
            "schema": "pulsarmlx.f017.representative-m1f0-single-use-execution-release",
            "schema_version": "2.0.0",
            "status": "PREPARED_FOR_INDEPENDENT_APPROVAL",
            "release_id": MODULE.RELEASE_ID,
            "event_id": MODULE.EVENT_ID,
            "attempt_id": MODULE.ATTEMPT_ID,
            "accepted_bindings": {
                "authorization_v3": {"sha256": self.authorization_sha()},
                "ledger_adapter": {"sha256": MODULE.LEDGER_ADAPTER_SHA256},
                "ledger_adapter_contract": {"sha256": MODULE.EXPECTED_CONTRACT_SHA256},
            },
        }

    def test_public_preflight_and_actual_ledger_shape_pass(self) -> None:
        MODULE.public_preflight(MODULE.DEFAULT_AUTHORIZATION)
        value, observations = MODULE.ledger_adapter().read()
        self.assertEqual(166, value)
        self.assertEqual(2, len(observations))

    def test_cli_preflight_is_zero_access_and_reconstructs_166(self) -> None:
        result = subprocess.run(
            ["/opt/homebrew/bin/python3.14", str(WRAPPER), "--preflight-only"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        packet = json.loads(result.stdout)
        self.assertEqual("PRODUCTION_BINDINGS_RESOLVED", packet["result"])
        self.assertEqual(166, packet["ledger"])
        self.assertEqual(0, packet["checkpoint_reads"])
        self.assertEqual(0, packet["shard_opens"])
        self.assertFalse(packet["real_event_authorized"])

    def test_old_go_token_cannot_authorize_wrapper_v2(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            release_path = root / "release.json"
            release_path.write_text(json.dumps(self.release_contract()))
            old_token = {
                "approval_sha256": MODULE.OLD_RELEASE_APPROVAL_SHA256,
                "attempt_id": MODULE.ATTEMPT_ID,
                "authorization_sha256": self.authorization_sha(),
                "disposition": "GO_EXECUTE_ONCE_NO_RETRY",
                "event_id": MODULE.EVENT_ID,
                "real_event_authorized": True,
                "release_id": "F017-REPRESENTATIVE-M1F0-ATTENTION-ROUTE-RECOVERY-1-RELEASE-1",
                "release_sha256": "914e07f12b968df700aa8868ce0888183f83fd77c9c0684302801f8ad09ca1e4",
            }
            token_path = root / "token.json"
            token_path.write_text(json.dumps(old_token))
            with self.assertRaises(MODULE.EventError) as caught:
                MODULE.require_release(token_path, self.authorization_sha(), release_path)
            self.assertEqual("INDEPENDENT_RELEASE_GATE", caught.exception.code)

    def test_future_token_must_bind_exact_v2_release_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            release_path = root / "release.json"
            release_path.write_text(json.dumps(self.release_contract()))
            token = {
                "approval_sha256": "a" * 64,
                "attempt_id": MODULE.ATTEMPT_ID,
                "authorization_sha256": self.authorization_sha(),
                "disposition": "GO_EXECUTE_ONCE_NO_RETRY",
                "event_id": MODULE.EVENT_ID,
                "real_event_authorized": True,
                "release_id": MODULE.RELEASE_ID,
                "release_sha256": hashlib.sha256(release_path.read_bytes()).hexdigest(),
            }
            token_path = root / "token.json"
            token_path.write_text(json.dumps(token))
            self.assertEqual(token, MODULE.require_release(token_path, self.authorization_sha(), release_path))
            token["release_sha256"] = "0" * 64
            token_path.write_text(json.dumps(token))
            with self.assertRaises(MODULE.EventError):
                MODULE.require_release(token_path, self.authorization_sha(), release_path)


if __name__ == "__main__":
    unittest.main()
