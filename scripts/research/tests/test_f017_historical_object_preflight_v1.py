from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

import pytest

# Keep this focused test runnable without relying on the repository-wide
# PYTHONPATH setup used by the CI harness.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from f017_historical_object_preflight_v1 import (
    HistoricalObjectLookupError,
    preflight_historical_object,
    read_historical_blob,
    write_diagnostic,
)
from generate_f017_event06_authority_dag_v2 import build
from validate_f017_event06_authority_dag_v2 import validate_document

ROOT = Path(__file__).resolve().parents[3]
HISTORICAL_COMMIT = "9bfe3c0af88d774df15d595389f7f2778cea7806"
HISTORICAL_PATH = "scripts/research/f017_event06_readiness_authority_v3.py"
HISTORICAL_SHA256 = "7e2d3e37abb12ef373bebd5f40b23a69fa8e2d291cda5546986f28760afe6790"


def _environment(diagnostic: Path, **updates: str) -> dict[str, str]:
    environment = os.environ.copy()
    environment["PULSARMLX_MODEL_GGUF"] = ""
    environment["PULSARMLX_F017_HISTORY_DIAGNOSTIC"] = str(diagnostic)
    environment.update(updates)
    return environment


def _read_diagnostic(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _git_output(repository: Path, *arguments: str) -> str:
    environment = os.environ.copy()
    environment["GIT_CONFIG_NOSYSTEM"] = "1"
    return subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        env=environment,
        stdout=subprocess.PIPE,
        text=True,
    ).stdout.strip()


def _make_git_repository(root: Path) -> tuple[Path, str, bytes, bytes]:
    repository = root / "repository"
    repository.mkdir()
    environment = os.environ.copy()
    environment["GIT_CONFIG_NOSYSTEM"] = "1"
    subprocess.run(["git", "init", "-q", str(repository)], check=True, env=environment)
    subprocess.run(
        ["git", "-C", str(repository), "config", "user.email", "fixture@example.invalid"],
        check=True,
        env=environment,
    )
    subprocess.run(
        ["git", "-C", str(repository), "config", "user.name", "Fixture"],
        check=True,
        env=environment,
    )
    source = repository / "source.py"
    directory = repository / "directory"
    directory.mkdir()
    (directory / "file.txt").write_text("tree content\n")
    old = b"old historical source\n"
    current = b"current source\n"
    source.write_bytes(old)
    subprocess.run(["git", "-C", str(repository), "add", "."], check=True, env=environment)
    subprocess.run(
        ["git", "-C", str(repository), "commit", "-q", "-m", "historical"],
        check=True,
        env=environment,
    )
    historical = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        check=True,
        env=environment,
        stdout=subprocess.PIPE,
        text=True,
    ).stdout.strip()
    source.write_bytes(current)
    subprocess.run(["git", "-C", str(repository), "add", "."], check=True, env=environment)
    subprocess.run(
        ["git", "-C", str(repository), "commit", "-q", "-m", "current"],
        check=True,
        env=environment,
    )
    return repository, historical, old, current


def test_green_preflight_records_exact_historical_object_and_safe_command_evidence(tmp_path):
    diagnostic = tmp_path / "green-diagnostic.json"
    environment = _environment(diagnostic)
    envelope = preflight_historical_object(
        ROOT,
        HISTORICAL_COMMIT,
        HISTORICAL_PATH,
        environment=environment,
    )
    write_diagnostic(diagnostic, envelope)

    assert envelope["result"] == "PASS"
    assert envelope["model_environment_empty"] is True
    assert envelope["revision"] == HISTORICAL_COMMIT
    assert envelope["relative_path"] == HISTORICAL_PATH
    assert envelope["commands"]["revision_check"]["returncode"] == 0
    assert envelope["commands"]["path_check"]["returncode"] == 0
    assert envelope["commands"]["cat_file_exists"]["returncode"] == 0
    assert envelope["commands"]["show"]["returncode"] == 0
    assert envelope["commands"]["show"]["stderr_bytes"] == 0
    assert envelope["commands"]["show"]["stdout_bytes"] == 3229
    assert envelope["commands"]["show"]["stdout_sha256"] == HISTORICAL_SHA256
    assert _read_diagnostic(diagnostic)["schema"] == envelope["schema"]
    assert "HEAD" not in json.dumps(envelope, sort_keys=True)


def test_wrong_revision_and_path_fail_closed_with_diagnostic(tmp_path):
    for label, revision, relative_path in (
        ("revision", "0" * 40, HISTORICAL_PATH),
        ("path", HISTORICAL_COMMIT, "scripts/research/does-not-exist.py"),
    ):
        diagnostic = tmp_path / f"{label}.json"
        environment = _environment(diagnostic)
        with pytest.raises(HistoricalObjectLookupError, match="historical repository blob"):
            read_historical_blob(ROOT, revision, relative_path, environment=environment)
        envelope = _read_diagnostic(diagnostic)
        assert envelope["result"] == "FAIL"
        assert envelope["revision"] == revision
        assert envelope["relative_path"] == relative_path
        assert envelope["commands"]["show"]["returncode"] != 0
        assert all(
            "HEAD" not in argv
            for command in envelope["commands"].values()
            for argv in (command["argv"],)
        )


def test_object_store_visibility_denial_fails_closed(tmp_path):
    repository, historical, _old, _current = _make_git_repository(tmp_path)
    empty_object_store = tmp_path / "denied-objects"
    empty_object_store.mkdir()
    diagnostic = tmp_path / "object-denial.json"
    environment = _environment(
        diagnostic,
        GIT_OBJECT_DIRECTORY=str(empty_object_store),
    )

    with pytest.raises(HistoricalObjectLookupError):
        read_historical_blob(repository, historical, "source.py", environment=environment)
    envelope = _read_diagnostic(diagnostic)
    assert envelope["result"] == "FAIL"
    assert envelope["commands"]["cat_file_exists"]["returncode"] != 0
    assert envelope["commands"]["show"]["stderr_bytes"] > 0


def test_source_drift_and_current_substitution_are_not_accepted(tmp_path):
    repository, historical, old, current = _make_git_repository(tmp_path)
    diagnostic = tmp_path / "historical-drift.json"
    environment = _environment(diagnostic)

    historical_bytes = read_historical_blob(
        repository, historical, "source.py", environment=environment
    )
    assert historical_bytes == old
    assert historical_bytes != current
    assert hashlib.sha256(historical_bytes).hexdigest() != hashlib.sha256(current).hexdigest()
    assert (repository / "source.py").read_bytes() == current


def test_tree_path_is_rejected_and_diagnosed(tmp_path):
    repository, historical, _old, _current = _make_git_repository(tmp_path)
    diagnostic = tmp_path / "tree-path.json"
    environment = _environment(diagnostic)

    with pytest.raises(HistoricalObjectLookupError, match="historical repository blob"):
        read_historical_blob(repository, historical, "directory", environment=environment)

    envelope = _read_diagnostic(diagnostic)
    assert envelope["result"] == "FAIL"
    assert envelope["commands"]["show"]["returncode"] == 0
    assert envelope["commands"]["show"]["stderr_bytes"] == 0
    assert envelope["commands"]["revision_check"]["returncode"] == 0
    assert envelope["commands"]["cat_file_type"]["returncode"] == 0
    assert envelope["resolved"]["cat_file_type"] == "tree"
    assert envelope["historical_blob_is_blob"] is False


def test_non_commit_revision_is_rejected_and_diagnosed(tmp_path):
    repository, historical, _old, _current = _make_git_repository(tmp_path)
    tree_revision = _git_output(repository, "rev-parse", f"{historical}^{{tree}}")
    diagnostic = tmp_path / "non-commit-revision.json"
    environment = _environment(diagnostic)

    with pytest.raises(HistoricalObjectLookupError, match="historical repository blob"):
        read_historical_blob(repository, tree_revision, "source.py", environment=environment)

    envelope = _read_diagnostic(diagnostic)
    assert envelope["result"] == "FAIL"
    assert envelope["commands"]["show"]["returncode"] == 0
    assert envelope["commands"]["show"]["stderr_bytes"] == 0
    assert envelope["commands"]["revision_check"]["returncode"] != 0
    assert envelope["commands"]["cat_file_type"]["returncode"] == 0
    assert envelope["resolved"]["cat_file_type"] == "blob"


def test_source_blob_binding_drift_fails_before_historical_lookup():
    document = build()
    document["edges"][0]["source_blob_sha256"] = "0" * 64

    with pytest.raises(ValueError, match="DAG/source inventory divergence"):
        validate_document(document)


def test_denied_developer_path_fails_closed_on_macos(tmp_path):
    if sys.platform != "darwin" or not Path("/usr/bin/git").is_file():
        pytest.skip("the developer-path guard is macOS /usr/bin/git specific")
    denied = tmp_path / "missing-developer-tree"
    diagnostic = tmp_path / "developer-denial.json"
    environment = _environment(
        diagnostic,
        PATH="/usr/bin:/bin",
        DEVELOPER_DIR=str(denied),
    )

    with pytest.raises(HistoricalObjectLookupError):
        read_historical_blob(ROOT, HISTORICAL_COMMIT, HISTORICAL_PATH, environment=environment)
    envelope = _read_diagnostic(diagnostic)
    assert envelope["result"] == "FAIL"
    assert envelope["commands"]["show"]["returncode"] != 0
    assert envelope["commands"]["show"]["stderr_bytes"] > 0
    assert envelope["developer_tool_selection"]["developer_dir"]["path"] is None or (
        envelope["developer_tool_selection"]["developer_dir"]["exists"] is False
    )
