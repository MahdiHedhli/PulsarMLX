from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.research.validate_f017_native_domain_authority_v1 import (
    AuthorityError,
    _published_history_ref,
    validate,
)


ROOT = Path(__file__).resolve().parents[3]
CONTRACT = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-native-domain-cross-branch-authority-v1.json"

LEFT_REMOTE_HISTORY = "pinned historical authority left remote history"
BRANCH = "feat/demo-retired"
ARCHIVE_TAG = f"archive/2026-09-21/{BRANCH}"

_GIT_ENV = {
    **os.environ,
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
    "GIT_AUTHOR_NAME": "Test",
    "GIT_AUTHOR_EMAIL": "test@example.invalid",
    "GIT_COMMITTER_NAME": "Test",
    "GIT_COMMITTER_EMAIL": "test@example.invalid",
    "GIT_AUTHOR_DATE": "2026-09-21T00:00:00+00:00",
    "GIT_COMMITTER_DATE": "2026-09-21T00:00:00+00:00",
}


def _git(cwd: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-c", "commit.gpgsign=false", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        env=_GIT_ENV,
    )
    return done.stdout.decode().strip()


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
        result = validate(CONTRACT, ROOT)
        self.assertEqual(result["terminal_count"], 175)
        self.assertEqual(
            result["historical_head"],
            "f2a7aa38c96b85cf7939c8ed653076732f066222",
        )
        # Published either by the branch itself or, after its documented
        # close-out, by the archive tag that retired it.
        self.assertTrue(
            result["published_ref"] == "origin/feat/017-real-checkpoint-runner"
            or result["published_ref"].startswith("refs/tags/archive/"),
            result["published_ref"],
        )

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


class PublishedHistoryRefTests(unittest.TestCase):
    """The published ref that must still contain the pinned head.

    Each case builds a throwaway bare repository as `origin` and clones it, so
    nothing here touches the real repository or the network. The clone is taken
    while the branch still exists, then origin's refs are rewritten and the
    stale remote-tracking ref pruned -- which is exactly how a close-out
    reaches a working copy: the objects stay, the branch ref goes.
    """

    def setUp(self) -> None:
        directory = Path(tempfile.mkdtemp(prefix="f017-authority-origin-"))
        self.addCleanup(shutil.rmtree, directory)
        self.origin = directory / "origin.git"
        work = directory / "work"
        _git(directory, "init", "--bare", "--initial-branch=main", str(self.origin))
        _git(directory, "init", "--initial-branch=main", str(work))
        _git(work, "remote", "add", "origin", str(self.origin))

        def commit(message: str) -> str:
            (work / "file.txt").write_text(message + "\n")
            _git(work, "add", "file.txt")
            _git(work, "commit", "-m", message)
            return _git(work, "rev-parse", "HEAD")

        self.root_commit = commit("root")
        self.pinned = commit("pinned authority")
        self.tip = commit("later policy commit")
        _git(work, "push", "origin", f"HEAD:refs/heads/{BRANCH}")
        # A sibling line that branches off before the pinned commit, so a tag
        # placed here is published history that does NOT contain the pin.
        _git(work, "checkout", "-b", "sibling", self.root_commit)
        self.without_pin = commit("sibling line")
        _git(work, "push", "origin", "HEAD:refs/heads/sibling")

        self.clone = directory / "clone"
        _git(directory, "clone", str(self.origin), str(self.clone))
        self.work = work

    def _tag(self, name: str, commit: str, annotated: bool = True) -> None:
        if annotated:
            _git(self.work, "tag", "-a", name, "-m", name, commit)
        else:
            _git(self.work, "tag", name, commit)
        _git(self.work, "push", "origin", f"refs/tags/{name}")

    def _retire_branch(self) -> None:
        _git(self.work, "push", "origin", "--delete", BRANCH)
        _git(self.clone, "update-ref", "-d", f"refs/remotes/origin/{BRANCH}")

    def _resolve(self) -> str:
        return _published_history_ref(self.clone, BRANCH, self.pinned)

    def test_live_branch_path_is_unchanged(self) -> None:
        self.assertEqual(self._resolve(), f"origin/{BRANCH}")

    def test_archive_tag_containing_the_head_is_accepted(self) -> None:
        self._tag(ARCHIVE_TAG, self.tip)
        self._retire_branch()
        self.assertEqual(self._resolve(), f"refs/tags/{ARCHIVE_TAG}")

    def test_lightweight_archive_tag_is_accepted(self) -> None:
        self._tag(ARCHIVE_TAG, self.tip, annotated=False)
        self._retire_branch()
        self.assertEqual(self._resolve(), f"refs/tags/{ARCHIVE_TAG}")

    def test_archive_tag_without_the_head_is_refused(self) -> None:
        self._tag(ARCHIVE_TAG, self.without_pin)
        self._retire_branch()
        with self.assertRaises(AuthorityError) as caught:
            self._resolve()
        self.assertEqual(str(caught.exception), LEFT_REMOTE_HISTORY)

    def test_every_archive_tag_must_contain_the_head(self) -> None:
        self._tag(ARCHIVE_TAG, self.tip)
        self._tag(f"archive/2026-09-22/{BRANCH}", self.without_pin)
        self._retire_branch()
        with self.assertRaises(AuthorityError) as caught:
            self._resolve()
        self.assertEqual(str(caught.exception), LEFT_REMOTE_HISTORY)

    def test_no_branch_and_no_archive_tag_is_refused(self) -> None:
        self._retire_branch()
        with self.assertRaises(AuthorityError) as caught:
            self._resolve()
        self.assertEqual(str(caught.exception), LEFT_REMOTE_HISTORY)

    def test_unrelated_archive_tag_does_not_qualify(self) -> None:
        self._tag(f"archive/2026-09-21/{BRANCH}-other", self.without_pin)
        self._retire_branch()
        with self.assertRaises(AuthorityError) as caught:
            self._resolve()
        self.assertEqual(str(caught.exception), LEFT_REMOTE_HISTORY)


if __name__ == "__main__":
    unittest.main()
