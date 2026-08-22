from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.research.validate_f017_native_domain_authority_v1 import AuthorityError, validate


ROOT = Path(__file__).resolve().parents[3]
CONTRACT = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-native-domain-cross-branch-authority-v1.json"


class NativeDomainAuthorityTests(unittest.TestCase):
    def _mutated(self, mutation) -> Path:
        value = json.loads(CONTRACT.read_text())
        mutation(value)
        directory = Path(tempfile.mkdtemp(prefix="f017-authority-mutation-"))
        self.addCleanup(shutil.rmtree, directory)
        path = directory / "contract.json"
        path.write_text(json.dumps(value, sort_keys=True) + "\n")
        return path

    def test_committed_authority_resolves(self) -> None:
        self.assertEqual(validate(CONTRACT, ROOT)["terminal_count"], 175)

    def test_wrong_historical_sha_fails(self) -> None:
        path = self._mutated(lambda value: value["historical_authorities"][0].update(sha256="0" * 64))
        with self.assertRaises(AuthorityError):
            validate(path, ROOT)

    def test_manual_terminal_count_fails(self) -> None:
        path = self._mutated(lambda value: value["master_ledger_precondition"].update(terminal_count=176))
        with self.assertRaises(AuthorityError):
            validate(path, ROOT)

    def test_receipt_gap_fails(self) -> None:
        path = self._mutated(lambda value: value["master_ledger_precondition"].update(gaps=1))
        with self.assertRaises(AuthorityError):
            validate(path, ROOT)

    def test_competing_master_is_rejected(self) -> None:
        path = self._mutated(lambda value: value["native_ledger_chaining"].update(competing_master_count_permitted=True))
        with self.assertRaises(AuthorityError):
            validate(path, ROOT)

    def test_duplicate_json_key_fails(self) -> None:
        directory = Path(tempfile.mkdtemp(prefix="f017-authority-duplicate-"))
        self.addCleanup(shutil.rmtree, directory)
        path = directory / "contract.json"
        path.write_text('{"schema":"x","schema":"y"}\n')
        with self.assertRaises(AuthorityError):
            validate(path, ROOT)


if __name__ == "__main__":
    unittest.main()
