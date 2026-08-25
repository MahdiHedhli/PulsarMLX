from __future__ import annotations

import json
import os
from pathlib import Path
import sys

import pytest

RESEARCH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RESEARCH))

from f017_accounting_root_continuity_v1 import AccountingRootAuthority, open_directory_no_symlinks
from f017_bounded_artifact_decode_v1 import (
    ArtifactDecodeError,
    ArtifactLimits,
    DEFAULT_LIMITS,
    parse_artifact_bytes,
)
from f017_canonical_serialization_v10 import canonical_bytes
from execute_f017_corrected_oracle_event_v10 import _terminalize
from check_f017_bounded_artifact_decode_policy_v1 import inspect_source
from f017_corrected_oracle_event_accounting_v10 import derive


def _authority(tmp_path: Path) -> AccountingRootAuthority:
    return AccountingRootAuthority.create(
        tmp_path / "state",
        tmp_path / "fallback",
        "F017-V10-ROOT-TEST-PACKAGE",
        "a" * 64,
        "b" * 64,
    )


def _bank_starts(authority: AccountingRootAuthority, *, primary: bool = False,
                 secondary: bool = False) -> None:
    authority.bank_artifact(
        "package-durable-start.json", "package_durable_start", {"delta": 1},
        "PACKAGE_DURABLE_START",
    )
    if primary:
        authority.bank_artifact(
            "primary-durable-start.json", "primary_durable_start", {"delta": 1},
            "PRIMARY_DURABLE_START",
        )
    if secondary:
        authority.bank_artifact(
            "secondary-durable-start.json", "secondary_durable_start", {"delta": 1},
            "SECONDARY_DURABLE_START",
        )


@pytest.mark.parametrize("attack", ["RENAME", "RECREATE", "SYMLINK", "FILE_REPLACEMENT"])
@pytest.mark.parametrize("primary,secondary", [(False, False), (True, False), (True, True)])
def test_root_path_substitution_never_produces_false_zero(
    tmp_path: Path, attack: str, primary: bool, secondary: bool,
) -> None:
    authority = _authority(tmp_path)
    try:
        _bank_starts(authority, primary=primary, secondary=secondary)
        original = tmp_path / "state"
        retained = tmp_path / "retained-state"
        original.rename(retained)
        if attack == "RENAME":
            pass
        elif attack == "RECREATE":
            original.mkdir()
        elif attack == "SYMLINK":
            attacker = tmp_path / "attacker"; attacker.mkdir()
            original.symlink_to(attacker, target_is_directory=True)
        else:
            original.write_text("not a directory", encoding="utf-8")
        accounting = authority.accounting_lower_bound()
        assert accounting["package"] == 1
        assert accounting["primary"] == int(primary)
        assert accounting["secondary"] == int(secondary)
        assert accounting["fallback_used_as_accounting_source"] is False
        assert accounting["path_identity_status"] in {"AUTHORITY_UNAVAILABLE", "IDENTITY_MISMATCH"}
    finally:
        authority.close()


def test_missing_or_corrupt_start_artifact_preserves_journal_lower_bound(tmp_path: Path) -> None:
    authority = _authority(tmp_path)
    try:
        _bank_starts(authority, primary=True, secondary=True)
        os.unlink("package-durable-start.json", dir_fd=authority.primary_fd)
        primary = os.open("primary-durable-start.json", os.O_WRONLY | os.O_TRUNC, dir_fd=authority.primary_fd)
        try:
            os.write(primary, b"{" * 10_000)
            os.fsync(primary)
        finally:
            os.close(primary)
        accounting = authority.accounting_lower_bound()
        assert accounting["package"] == accounting["primary"] == accounting["secondary"] == 1
        assert accounting["observations"]["package"] == "OBSERVED_ABSENT"
        assert accounting["observations"]["primary"] == "AUTHORITY_CORRUPT"
    finally:
        authority.close()


def test_fallback_is_evidence_sink_not_accounting_source(tmp_path: Path) -> None:
    authority = _authority(tmp_path)
    try:
        _bank_starts(authority, primary=True)
        authority.bank_fallback_capsule("failure.json", {"reason": "PRIMARY_PATH_REPLACED"})
        accounting = authority.accounting_lower_bound()
        assert accounting["package"] == 1 and accounting["primary"] == 1
        assert accounting["secondary"] == 0
        assert accounting["fallback_used_as_accounting_source"] is False
    finally:
        authority.close()


def test_journal_leaf_replacement_cannot_replace_retained_accounting_authority(tmp_path: Path) -> None:
    authority = _authority(tmp_path)
    try:
        _bank_starts(authority, primary=True)
        os.unlink("accounting-transition-journal.ndjson", dir_fd=authority.primary_fd)
        replacement = os.open(
            "accounting-transition-journal.ndjson",
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
            dir_fd=authority.primary_fd,
        )
        try:
            os.write(replacement, canonical_bytes({"attacker": "empty accounting"}))
            os.fsync(replacement)
        finally:
            os.close(replacement)
        accounting = authority.accounting_lower_bound()
        assert accounting["journal_observation"] == "OBSERVED_PRESENT"
        assert accounting["package"] == accounting["primary"] == 1
        assert accounting["secondary"] == 0
    finally:
        authority.close()


def test_post_bind_artifact_banking_uses_retained_root_not_recreated_path(tmp_path: Path) -> None:
    authority = _authority(tmp_path)
    retained = tmp_path / "retained-state"
    try:
        _bank_starts(authority)
        (tmp_path / "state").rename(retained)
        (tmp_path / "state").mkdir()
        authority.bank_artifact("post-bind-failure.json", "post_bind_failure", {"result": "FAILURE"})
        assert (retained / "post-bind-failure.json").is_file()
        assert not (tmp_path / "state" / "post-bind-failure.json").exists()
    finally:
        authority.close()


def test_start_artifact_requires_exact_outer_schema_before_counting(tmp_path: Path) -> None:
    authority = _authority(tmp_path)
    try:
        authority.bank_artifact(
            "package-durable-start.json",
            "attacker_kind",
            {"delta": 1},
        )
        accounting = authority.accounting_lower_bound()
        assert accounting["observations"]["package"] == "AUTHORITY_CORRUPT"
        assert accounting["package"] == 0
    finally:
        authority.close()


@pytest.mark.parametrize(
    "source",
    [
        "import json as backend\nbackend.loads(b'{}')\n",
        "from json import loads\nloads(b'{}')\n",
        "import json\ndecoder = json.loads\ndecoder(b'{}')\n",
        "import json\nbackend = json\nbackend.loads(b'{}')\n",
        "import json\ngetattr(json, 'loads')(b'{}')\n",
        "import json\nglobals()['json'].loads(b'{}')\n",
        "import importlib\nimportlib.import_module('json').loads(b'{}')\n",
        "import json\njson.load(None)\n",
        "import sys\nsys.modules['json'].loads(b'{}')\n",
        "import sys\ngetattr(sys.modules['json'], 'loads')(b'{}')\n",
        "import builtins\nbuiltins.__import__('json').loads(b'{}')\n",
        "import sys\nsys.__dict__['modules']['json'].loads(b'{}')\n",
        "import sys\ngetattr(sys, 'modules')['json'].loads(b'{}')\n",
        "import sys as runtime\nruntime.__dict__['modules']['json'].loads(b'{}')\n",
        "import sys as runtime\ngetattr(runtime, 'modules')['json'].loads(b'{}')\n",
        "from sys import modules\nmodules['json'].loads(b'{}')\n",
        "import sys\nregistry = sys\nregistry.modules['json'].loads(b'{}')\n",
        "import sys\nvars(sys)['modules']['json'].loads(b'{}')\n",
        "getattr(__builtins__, '__import__')('json').loads(b'{}')\n",
        "import os\nos.sys.modules['json'].loads(b'{}')\n",
        "import os\ngetattr(os, 'sys').modules['json'].loads(b'{}')\n",
        "().__class__.__base__.__subclasses__()\n",
    ],
)
def test_direct_parser_policy_rejects_representation_independent_bypasses(source: str) -> None:
    violations, _ = inspect_source("scripts/research/attacker_runtime.py", source)
    assert violations


@pytest.mark.parametrize("source", ["import sys\nprint(sys.executable)\n", "import sys\nprint('x', file=sys.stderr)\n"])
def test_direct_parser_policy_retains_exact_legitimate_sys_members(source: str) -> None:
    violations, _ = inspect_source("scripts/research/legitimate_runtime.py", source)
    assert violations == []


def test_componentwise_directory_open_never_reopens_resolved_absolute_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "target"; target.mkdir(); (target / "root").mkdir()
    resolved = (target / "root").resolve(strict=True)
    calls: list[tuple[object, object]] = []
    real_open = os.open

    def observed_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
        calls.append((path, kwargs.get("dir_fd")))
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", observed_open)
    descriptor, opened = open_directory_no_symlinks(resolved)
    os.close(descriptor)
    assert opened == resolved
    assert calls[0] == (resolved.anchor, None)
    assert all(dir_fd is not None for _, dir_fd in calls[1:])
    assert all(str(path) != str(resolved) for path, _ in calls)


def test_offline_accounting_uses_one_retained_root_and_no_lstat(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    authority = _authority(tmp_path)
    try:
        _bank_starts(authority, primary=True)
    finally:
        authority.close()
    monkeypatch.setattr(Path, "lstat", lambda self: (_ for _ in ()).throw(AssertionError("lstat forbidden")))
    accounting = derive(tmp_path / "state")
    assert accounting["package"] == 1 and accounting["primary"] == 1 and accounting["secondary"] == 0


def _nested(depth: int) -> bytes:
    value = b"0"
    for _ in range(depth):
        value = b"[" + value + b"]"
    return value + b"\n"


@pytest.mark.parametrize("depth", [65, 128, 1024, 10_000])
def test_depth_over_limit_is_controlled_before_json_decode(depth: int) -> None:
    with pytest.raises(ArtifactDecodeError, match="nesting exceeds bound"):
        parse_artifact_bytes(_nested(depth), expected_top_level=None)


def test_depth_boundary_and_string_brackets_are_exact() -> None:
    limits = ArtifactLimits(**{**DEFAULT_LIMITS.__dict__, "require_canonical_bytes": False})
    parse_artifact_bytes(_nested(64), limits=limits, expected_top_level=None)
    value = {"text": "[\\\"{not structural}\\\"]"}
    assert parse_artifact_bytes(canonical_bytes(value)) == value


@pytest.mark.parametrize(
    "raw",
    [
        b"\xff\n",
        b'{"a":1,"a":2}\n',
        b'{"x":NaN}\n',
        b'{"x":"\\uZZZZ"}\n',
        b'{"x":1',
        canonical_bytes({"x": "a" * (DEFAULT_LIMITS.max_string_chars + 1)}),
        (b"{" + b" " * DEFAULT_LIMITS.max_bytes + b"}\n"),
        canonical_bytes({"x": int("9" * 128)}).replace(b"9" * 128, b"9" * 129),
    ],
)
def test_malformed_artifacts_have_one_controlled_failure_class(raw: bytes) -> None:
    with pytest.raises(ArtifactDecodeError):
        parse_artifact_bytes(raw)


@pytest.mark.parametrize("length", [257, 10_000, 1_000_000])
def test_float_token_is_lexically_bounded_before_conversion(length: int) -> None:
    raw = (b"1." + b"0" * length + b"\n")
    with pytest.raises(ArtifactDecodeError, match="float exceeds lexical bound"):
        parse_artifact_bytes(raw, expected_top_level=None)


def test_journal_in_place_truncation_cannot_reduce_start_lower_bound(tmp_path: Path) -> None:
    authority = _authority(tmp_path)
    try:
        _bank_starts(authority, primary=True, secondary=True)
        for leaf in ("package-durable-start.json", "primary-durable-start.json", "secondary-durable-start.json"):
            os.unlink(leaf, dir_fd=authority.primary_fd)
        os.ftruncate(authority._journal_fd, 0)
        os.fsync(authority._journal_fd)
        first = authority.accounting_lower_bound()
        second = authority.accounting_lower_bound()
        assert first["journal_observation"] == "AUTHORITY_CORRUPT"
        assert (first["package"], first["primary"], first["secondary"]) == (1, 1, 1)
        assert (second["package"], second["primary"], second["secondary"]) == (1, 1, 1)

    finally:
        authority.close()




def test_deep_durable_start_decode_cannot_escape_recursion_error(tmp_path: Path) -> None:
    authority = _authority(tmp_path)
    try:
        _bank_starts(authority)
        descriptor = os.open("package-durable-start.json", os.O_WRONLY | os.O_TRUNC, dir_fd=authority.primary_fd)
        try:
            os.write(descriptor, _nested(10_000))
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        result = authority.accounting_lower_bound()
        assert result["package"] == 1
        assert result["observations"]["package"] == "AUTHORITY_CORRUPT"
    finally:
        authority.close()


@pytest.mark.parametrize("attack", ["RECREATE", "SYMLINK", "MISSING"])
def test_terminalization_uses_bound_root_and_preserves_package_obligation(
    tmp_path: Path, attack: str,
) -> None:
    authority = _authority(tmp_path)
    retained = tmp_path / "retained"
    try:
        _bank_starts(authority, primary=True)
        (tmp_path / "state").rename(retained)
        if attack == "RECREATE":
            (tmp_path / "state").mkdir()
        elif attack == "SYMLINK":
            attacker = tmp_path / "attacker"; attacker.mkdir()
            (tmp_path / "state").symlink_to(attacker, target_is_directory=True)
        result = _terminalize(
            tmp_path / "state",
            tmp_path / "fallback",
            {},
            ValueError("injected root degradation"),
            None,
            "TERMINALIZATION",
            "PRIMARY_DURABLE_START",
            root_authority_status="BOUND_ROOT",
            accounting_authority=authority,
        )
        assert result["result"] == "CONTROLLED_FAILURE"
        assert result["accounting"]["package"] == 1
        assert result["accounting"]["primary"] == 1
        assert result["accounting"]["secondary"] == 0
        assert result["package_terminal_evidence"]["result"] == "PASS"
        assert result["terminal_evidence"]["target"] == "BOUND_PRIMARY"
        assert (retained / "failure-terminal-capsule.json").is_file()
        assert (retained / "package-terminal.json").is_file()
    finally:
        authority.close()


def test_deep_corrupt_start_terminalizes_in_bound_root_without_raw_recursion(tmp_path: Path) -> None:
    authority = _authority(tmp_path)
    try:
        _bank_starts(authority, primary=True)
        descriptor = os.open("package-durable-start.json", os.O_WRONLY | os.O_TRUNC, dir_fd=authority.primary_fd)
        try:
            os.write(descriptor, _nested(10_000))
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        result = _terminalize(
            tmp_path / "state",
            tmp_path / "fallback",
            {},
            ArtifactDecodeError("deep durable-start artifact"),
            None,
            "ACCOUNTING_DECODE",
            "PRIMARY_DURABLE_START",
            accounting_authority=authority,
        )
        assert result["result"] == "CONTROLLED_FAILURE"
        assert result["source_exception_class"] == "ArtifactDecodeError"
        assert result["accounting"]["package"] == result["accounting"]["primary"] == 1
        assert result["accounting_derivation"]["journal_observation"] == "OBSERVED_PRESENT"
        assert (tmp_path / "state" / "failure-terminal-capsule.json").is_file()
    finally:
        authority.close()
