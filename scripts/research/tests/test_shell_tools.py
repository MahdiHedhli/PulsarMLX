from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
RESEARCH_SCRIPTS = REPOSITORY_ROOT / "scripts" / "research"


def run_command(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


class SetupTests(unittest.TestCase):
    def make_repository(self, root: Path) -> Path:
        repository = root / "repository"
        script_dir = repository / "scripts" / "research"
        script_dir.mkdir(parents=True)
        shutil.copy2(RESEARCH_SCRIPTS / "setup.sh", script_dir / "setup.sh")
        (repository / "Cargo.lock").write_text("fixture\n", encoding="utf-8")
        (repository / "uv.lock").write_text("fixture\n", encoding="utf-8")
        (repository / ".specify").mkdir()
        (repository / ".specify" / "feature.json").write_text("{}\n", encoding="utf-8")
        (repository / ".gitignore").write_text(".pulsarmlx-local/\n", encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(repository)], check=True)
        return repository

    def test_setup_is_idempotent_and_ignores_a_model_environment_value(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            repository = self.make_repository(temporary_root)
            env = os.environ.copy()
            env["PULSARMLX_MODEL_GGUF"] = str(temporary_root / "does-not-exist.gguf")

            first = run_command(["sh", str(repository / "scripts/research/setup.sh")], env=env)
            second = run_command(["sh", str(repository / "scripts/research/setup.sh")], env=env)

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            state = repository / ".pulsarmlx-local" / "research-work"
            self.assertEqual(
                sorted(path.name for path in state.iterdir()),
                ["cache", "candidates", "logs", "oracle-build", "tmp"],
            )
            self.assertFalse((temporary_root / "does-not-exist.gguf").exists())

    def test_setup_refuses_a_symbolic_link_in_local_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            repository = self.make_repository(temporary_root)
            external = temporary_root / "external"
            external.mkdir()
            local_root = repository / ".pulsarmlx-local"
            local_root.mkdir()
            (local_root / "research-work").symlink_to(external, target_is_directory=True)

            result = run_command(["sh", str(repository / "scripts/research/setup.sh")])

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(list(external.iterdir()), [])
            self.assertNotIn(str(external), result.stderr)


class PrepareModelTests(unittest.TestCase):
    def valid_arguments(self, root: Path) -> list[str]:
        evidence_root = root / "evidence"
        return [
            "--model",
            str(root / "models" / "fixture.gguf"),
            "--inspection",
            str(evidence_root / "router-inspection.json"),
            "--oracle-work",
            str(root / "work" / "oracle"),
            "--oracle-output",
            str(evidence_root / "oracle"),
            "--oracle",
            str(evidence_root / "oracle" / "oracle.json"),
            "--evidence-dir",
            str(evidence_root / "experiments"),
            "--fixture-evidence",
            str(evidence_root / "fixtures.json"),
        ]

    def test_accepts_nonexistent_disjoint_external_paths_without_creating_them(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "external-fixture"
            result = run_command(
                ["sh", str(RESEARCH_SCRIPTS / "prepare_model.sh"), *self.valid_arguments(root)]
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("model bytes untouched", result.stdout)
            self.assertNotIn(str(root), result.stdout + result.stderr)
            self.assertFalse(root.exists())

    def test_rejects_relative_repository_and_alias_paths_without_disclosure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "external-fixture"
            base = self.valid_arguments(root)

            relative = base.copy()
            relative[relative.index("--model") + 1] = "relative.gguf"
            relative_result = run_command(
                ["sh", str(RESEARCH_SCRIPTS / "prepare_model.sh"), *relative]
            )
            self.assertNotEqual(relative_result.returncode, 0)

            repository_path = base.copy()
            repository_path[repository_path.index("--model") + 1] = str(
                REPOSITORY_ROOT / "private-model.gguf"
            )
            repository_result = run_command(
                ["sh", str(RESEARCH_SCRIPTS / "prepare_model.sh"), *repository_path]
            )
            self.assertNotEqual(repository_result.returncode, 0)
            self.assertNotIn(str(REPOSITORY_ROOT), repository_result.stderr)

            aliased = base.copy()
            aliased[aliased.index("--oracle-work") + 1] = aliased[
                aliased.index("--oracle-output") + 1
            ]
            alias_result = run_command(
                ["sh", str(RESEARCH_SCRIPTS / "prepare_model.sh"), *aliased]
            )
            self.assertNotEqual(alias_result.returncode, 0)
            self.assertNotIn(str(root), alias_result.stderr)


class StagedScannerTests(unittest.TestCase):
    def make_repository(self, root: Path) -> Path:
        repository = root / "scan-repository"
        repository.mkdir()
        subprocess.run(["git", "init", "-q", str(repository)], check=True)
        return repository

    def scan(self, repository: Path) -> subprocess.CompletedProcess[str]:
        return run_command(
            [
                "sh",
                str(RESEARCH_SCRIPTS / "check_staged.sh"),
                "--repository",
                str(repository),
            ]
        )

    def stage_text(self, repository: Path, relative: str, content: str) -> None:
        destination = repository / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
        subprocess.run(["git", "-C", str(repository), "add", "--", relative], check=True)

    def test_accepts_a_small_text_only_staged_change(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = self.make_repository(Path(temporary))
            self.stage_text(repository, "docs/result.md", "# Fixture-only result\n")

            result = self.scan(repository)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "staged safety scan: passed\n")

    def test_accepts_the_shell_tooling_sources_as_a_staged_slice(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = self.make_repository(Path(temporary))
            relative_paths = [
                Path("scripts/research/setup.sh"),
                Path("scripts/research/prepare_model.sh"),
                Path("scripts/research/check_staged.sh"),
                Path("scripts/research/tests/test_shell_tools.py"),
            ]
            for relative in relative_paths:
                destination = repository / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(REPOSITORY_ROOT / relative, destination)
                subprocess.run(
                    ["git", "-C", str(repository), "add", "--", str(relative)],
                    check=True,
                )

            result = self.scan(repository)

            self.assertEqual(result.returncode, 0, result.stderr)

    def test_rejects_secret_private_path_and_model_filename_without_echoing_values(self) -> None:
        cases = [
            ("docs/secret.md", "github_" + "pat_" + "A" * 24),
            ("docs/assignment.md", "API_" + "KEY=" + "fixturevalue" * 2),
            ("docs/quoted.md", "SECRET='" + "fixturevalue" * 2 + "'"),
            ("docs/path.md", str(Path("/", "Users", "fixture-user", "private", "file"))),
            (
                "docs/identifier.json",
                '{"hardware_'
                + 'uuid":"12345678-'
                + '1234-4123-8123-123456789abc"}',
            ),
            ("fixtures/weight.gguf", "not model bytes"),
        ]
        for relative, forbidden in cases:
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as temporary:
                repository = self.make_repository(Path(temporary))
                self.stage_text(repository, relative, forbidden + "\n")

                result = self.scan(repository)

                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn(forbidden, result.stdout + result.stderr)

    def test_rejects_binary_large_cache_and_platform_selection_changes(self) -> None:
        cases: list[tuple[str, bytes]] = [
            ("fixtures/blob.dat", b"fixture\x00binary"),
            ("docs/large.txt", b"x" * (1048576 + 1)),
            ("scripts/__pycache__/cached.pyc", b"cache"),
            ("crates/example/src/lib.rs", b'#[cfg(target_os = "linux")]\nfn selected() {}\n'),
        ]
        for relative, content in cases:
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as temporary:
                repository = self.make_repository(Path(temporary))
                destination = repository / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)
                subprocess.run(["git", "-C", str(repository), "add", "--", relative], check=True)

                result = self.scan(repository)

                self.assertNotEqual(result.returncode, 0)

    def test_rejects_a_staged_symbolic_link(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repository = self.make_repository(Path(temporary))
            destination = repository / "docs" / "external-link"
            destination.parent.mkdir(parents=True)
            destination.symlink_to("../outside")
            subprocess.run(
                ["git", "-C", str(repository), "add", "--", "docs/external-link"],
                check=True,
            )

            result = self.scan(repository)

            self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
