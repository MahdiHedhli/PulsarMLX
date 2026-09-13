from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any

import pytest

# Keep this focused test runnable without relying on the repository-wide
# PYTHONPATH setup used by the CI harness.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import run_f017_event06_sequence18_sandbox_v1 as sandbox_runner
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


def test_sandbox_context_ignores_local_credential_include_without_widening_reads():
    if sys.platform != "darwin" or not Path("/usr/bin/sandbox-exec").is_file():
        pytest.skip("the sandbox custody regression is macOS /usr/bin/sandbox-exec specific")

    with tempfile.TemporaryDirectory(prefix="f017-include-regression-", dir="/private/tmp") as raw:
        root = Path(raw)
        graph = root / "graph"
        graph.mkdir()
        repository, historical, old, _current = _make_git_repository(graph)
        denied = root / "denied"
        denied.mkdir()
        include = denied / "synthetic-credential.config"
        include.write_text("[synthetic]\n\tmarker = harmless\n", encoding="utf-8")
        environment = os.environ.copy()
        environment.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"})
        key = f"includeIf.gitdir:{repository}/.git.path"
        subprocess.run(
            ["git", "-C", str(repository), "config", "--local", key, str(include)],
            check=True,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        isolated_git, common_git = sandbox_runner._prepare_historical_git_context(repository, graph)
        profile, _rule_ids = sandbox_runner._profile(graph)
        child_environment = {
            "PATH": "/usr/bin:/bin",
            "TMPDIR": str(graph),
            "GIT_DIR": str(isolated_git),
            "GIT_COMMON_DIR": str(common_git),
            "GIT_WORK_TREE": str(repository),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
        }
        probes = (
            ["rev-parse", "--verify", f"{historical}^{{commit}}"],
            ["cat-file", "-t", f"{historical}:source.py"],
            ["show", f"{historical}:source.py"],
        )
        results = [
            subprocess.run(
                ["/usr/bin/sandbox-exec", "-p", profile, "/usr/bin/git", *arguments],
                cwd=repository,
                env=child_environment,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            for arguments in probes
        ]
        assert all(result.returncode == 0 and result.stderr == b"" for result in results), [
            (result.returncode, result.stdout, result.stderr) for result in results
        ]
        assert results[1].stdout == b"blob\n"
        assert results[2].stdout == old


def test_sandbox_child_git_environment_keeps_fixture_commands_cwd_local(tmp_path):
    fixture = tmp_path / "disposable-fixture"
    fixture.mkdir()
    isolated_git = tmp_path / "historical-gitdir"
    common_git = tmp_path / "historical-common-gitdir"
    base_environment = {
        "PATH": "/usr/bin:/bin",
        "TMPDIR": str(tmp_path),
        "PULSARMLX_MODEL_GGUF": "",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
    }

    historical_environment = sandbox_runner._historical_git_environment(
        base_environment,
        isolated_git=isolated_git,
        common_git=common_git,
        work_tree=tmp_path,
    )

    assert not set(base_environment) & sandbox_runner._HISTORICAL_GIT_LOCATOR_VARIABLES
    assert base_environment["GIT_CONFIG_GLOBAL"] == "/dev/null"
    assert base_environment["GIT_CONFIG_NOSYSTEM"] == "1"
    assert historical_environment["GIT_DIR"] == str(isolated_git)
    assert historical_environment["GIT_COMMON_DIR"] == str(common_git)
    assert historical_environment["GIT_WORK_TREE"] == str(tmp_path)
    assert historical_environment["GIT_CONFIG_GLOBAL"] == "/dev/null"
    assert historical_environment["GIT_CONFIG_NOSYSTEM"] == "1"
    completed = subprocess.run(
        ["git", "init", "-q"],
        cwd=fixture,
        env=base_environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert completed.returncode == 0
    assert completed.stderr == b""
    assert (fixture / ".git").is_dir()


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


def test_sandbox_preflight_failure_persists_sanitized_output_after_cleanup(
    tmp_path, monkeypatch, capsys
):
    if sys.platform != "darwin" or not Path("/usr/bin/sandbox-exec").is_file():
        pytest.skip("the sandbox custody regression is macOS /usr/bin/sandbox-exec specific")

    output = tmp_path / "qualification-failure.json"
    captured: dict[str, Path] = {}
    real_temporary_directory = sandbox_runner.tempfile.TemporaryDirectory

    class CapturedTemporaryDirectory:
        def __init__(self, *args, **kwargs):
            self.inner = real_temporary_directory(*args, **kwargs)

        def __enter__(self):
            raw = self.inner.__enter__()
            captured["path"] = Path(raw)
            return raw

        def __exit__(self, *args):
            return self.inner.__exit__(*args)

    monkeypatch.setattr(
        sandbox_runner.tempfile, "TemporaryDirectory", CapturedTemporaryDirectory
    )
    monkeypatch.setattr(sandbox_runner, "HISTORICAL_DAG_COMMIT", "0" * 40)

    with pytest.raises(RuntimeError, match="historical object preflight failed"):
        sandbox_runner.run(output=output)

    assert captured["path"].exists() is False
    assert output.is_file()
    envelope = json.loads(output.read_text(encoding="utf-8"))
    log = capsys.readouterr().err
    logged = json.loads(log)
    assert envelope["status"] == "FAIL"
    assert envelope["result"] == "FAIL"
    assert envelope["failure_stage"] == "HISTORICAL_PREFLIGHT"
    assert envelope["historical_preflight_exit_status"] != 0
    assert envelope["historical_preflight_diagnostic_available"] is True
    assert envelope["historical_preflight"]["result"] == "FAIL"
    assert envelope["historical_preflight"]["revision"] == "0" * 40
    assert logged == envelope
    assert len(log.encode("utf-8")) <= sandbox_runner.MAX_FAILURE_ENVELOPE_BYTES
    assert str(ROOT) not in log
    assert HISTORICAL_PATH not in log
    assert "argv" not in log
    assert "relative_path" not in log
    assert "controlled stderr" not in log
    assert "failed_command_names" in logged["historical_preflight"]


@pytest.mark.parametrize(
    ("diagnostic_contents", "expected_status"),
    ((None, "MISSING"), (b"not-json", "MALFORMED")),
)
def test_preflight_failure_without_diagnostic_retains_safe_metadata(
    tmp_path, diagnostic_contents, expected_status, capsys
):
    output = tmp_path / "metadata-only-failure.json"
    diagnostic_path = tmp_path / "diagnostic.json"
    if diagnostic_contents is not None:
        diagnostic_path.write_bytes(diagnostic_contents)
    preflight = subprocess.CompletedProcess(
        ["sandbox-exec", "python", "-c", "preflight"],
        23,
        b"safe stdout",
        b"secret stderr",
    )

    sandbox_runner._write_preflight_failure(
        output, preflight, diagnostic_path
    )

    raw = output.read_text(encoding="utf-8")
    log = capsys.readouterr().err
    envelope = json.loads(raw)
    assert json.loads(log) == envelope
    assert len(log.encode("utf-8")) <= sandbox_runner.MAX_FAILURE_ENVELOPE_BYTES
    assert envelope["status"] == "FAIL"
    assert envelope["result"] == "FAIL"
    assert envelope["failure_stage"] == "HISTORICAL_PREFLIGHT"
    assert envelope["historical_preflight_exit_status"] == 23
    assert envelope["historical_preflight_stdout_bytes"] == len(preflight.stdout)
    assert envelope["historical_preflight_stdout_sha256"] == hashlib.sha256(
        preflight.stdout
    ).hexdigest()
    assert envelope["historical_preflight_stderr_bytes"] == len(preflight.stderr)
    assert envelope["historical_preflight_stderr_sha256"] == hashlib.sha256(
        preflight.stderr
    ).hexdigest()
    assert envelope["historical_preflight_diagnostic_status"] == expected_status
    assert envelope["historical_preflight_diagnostic_available"] is False
    assert envelope["historical_preflight"] is None
    assert "diagnostic.json" not in log
    assert "argv" not in log
    assert "secret stderr" not in raw
    assert "secret stderr" not in log


def test_contradictory_success_diagnostic_uses_safe_fallback(tmp_path, capsys):
    diagnostic = tmp_path / "contradictory.json"
    diagnostic.write_text(
        json.dumps(
            {
                "schema": sandbox_runner._PREFLIGHT_SCHEMA,
                "result": "PASS",
                "revision": "a" * 40,
                "relative_path": "scripts/research/input.py",
                "model_environment_empty": True,
                "required_checks_clean": True,
                "historical_blob_is_blob": True,
                "commands": {
                    "show": {
                        "returncode": 0,
                        "stdout_bytes": 0,
                        "stdout_sha256": "a" * 64,
                        "stderr_bytes": 0,
                        "stderr_sha256": "b" * 64,
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    preflight = subprocess.CompletedProcess(
        ["sandbox-exec", "python", "-c", "preflight"],
        1,
        b"",
        b"",
    )

    sandbox_runner._write_preflight_failure(None, preflight, diagnostic)
    log = capsys.readouterr().err
    envelope = json.loads(log)
    assert envelope["historical_preflight_diagnostic_status"] == "MALFORMED"
    assert envelope["historical_preflight_diagnostic_available"] is False
    assert envelope["historical_preflight"] is None
    assert "input.py" not in log
