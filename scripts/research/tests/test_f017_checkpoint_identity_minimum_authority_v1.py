from __future__ import annotations

import ast
import errno
import hashlib
import json
import os
from pathlib import Path
import socket
from unittest import mock

import pytest

import f017_checkpoint_identity_producer_v12 as identity_producer
from f017_canonical_serialization_v10 import canonical_bytes
from f017_checkpoint_identity_authority_v12 import (
    MINIMUM_INSTALLED_KEYS,
    MINIMUM_INSTALLED_SCHEMA,
    ValidatedIdentityAuthority,
    validate_minimum_installed_bytes,
)
from f017_checkpoint_identity_lifecycle_v12 import IdentityAuthorityError
from f017_checkpoint_identity_producer_v12 import (
    _minimum_gate_produce,
    _qualification_produce,
    _runtime_revalidate,
    produce,
)


CONTRACT = (
    "specs/017-rust-native-inference-runtime/contracts/"
    "f017-synthetic-checkpoint-identity-v12.json"
)
MIXED_CONTRACT = (
    "specs/017-rust-native-inference-runtime/contracts/"
    "f017-synthetic-checkpoint-identity-mixed-v12.json"
)
PRODUCTION_CONTRACT = (
    "specs/017-rust-native-inference-runtime/contracts/"
    "f017-corrected-oracle-checkpoint-identity-v12.json"
)
PRODUCER = "scripts/research/f017_checkpoint_identity_producer_v12.py"
VALIDATOR = "scripts/research/f017_checkpoint_identity_authority_v12.py"
ROOT = Path(__file__).resolve().parents[3]


def _sha(relative: str) -> str:
    return hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()


def minimum_installed(tmp_path: Path) -> dict[str, object]:
    return {
        "schema": MINIMUM_INSTALLED_SCHEMA,
        "authority_scope": "SYNTHETIC",
        "operation_class": "CHECKPOINT_IDENTITY_QUALIFICATION",
        "generation": "V12",
        "authorization_id": "F017-EVENT06-MINIMUM-AUTH-01",
        "package_attempt_id": "F017-EVENT06-MINIMUM-PACKAGE-01",
        "checkpoint_set_sha256": (
            "cb6a2be7988809ca48e3ba10a80bf8f482ae7381f51385f748844de77fe18ee1"
        ),
        "checkpoint_root": str(tmp_path / "unopened-synthetic-checkpoint"),
        "checkpoint_identity_contract_path": CONTRACT,
        "checkpoint_identity_contract_sha256": _sha(CONTRACT),
        "measured_producer_path": PRODUCER,
        "measured_producer_sha256": _sha(PRODUCER),
        "measured_validator_path": VALIDATOR,
        "measured_validator_sha256": _sha(VALIDATOR),
        "expected_shard_count": 6,
        "expected_identity_only_shard_count": 1,
        "expected_graph_payload_shard_count": 5,
        "expected_total_bytes": 0,
        "attempts": 1,
        "retries": 0,
        "resume": False,
    }


def runnable_minimum_installed(
    tmp_path: Path, *, mixed: bool = False
) -> tuple[ValidatedIdentityAuthority, dict[str, object], Path, dict]:
    contract_path = MIXED_CONTRACT if mixed else CONTRACT
    contract = json.loads((ROOT / contract_path).read_text(encoding="utf-8"))
    value = minimum_installed(tmp_path)
    value.update(
        checkpoint_set_sha256=contract["checkpoint_set_sha256"],
        checkpoint_identity_contract_path=contract_path,
        checkpoint_identity_contract_sha256=_sha(contract_path),
        expected_total_bytes=contract["derived_census"]["expected_total_bytes"],
    )
    root = Path(str(value["checkpoint_root"]))
    root.mkdir()
    for shard in contract["shards"]:
        (root / shard["filename"]).write_bytes(
            bytes([shard["ordinal"]]) * shard["size_bytes"]
        )
    authority = validate_minimum_installed_bytes(canonical_bytes(value))
    return authority, value, root, contract


def run_minimum_identity_stage(
    authority: ValidatedIdentityAuthority,
    value: dict[str, object],
    *,
    evidence_directory: Path | None = None,
):
    return _minimum_gate_produce(
        authority,
        package_attempt_id=str(value["package_attempt_id"]),
        package_durable_start=True,
        evidence_directory=evidence_directory,
    )


def test_minimum_authority_is_one_installed_document(tmp_path: Path) -> None:
    value = minimum_installed(tmp_path)
    assert set(value) == MINIMUM_INSTALLED_KEYS
    assert [key for key in value if key == "measured_producer_path"] == [
        "measured_producer_path"
    ]
    assert [key for key in value if key == "measured_validator_path"] == [
        "measured_validator_path"
    ]
    authority = validate_minimum_installed_bytes(canonical_bytes(value))
    assert authority.posture == "INSTALLED"
    assert authority.get("schema") == MINIMUM_INSTALLED_SCHEMA


@pytest.mark.parametrize(
    "removed_key",
    [
        "event_identity_plan_sha256",
        "producer_capability_path",
        "producer_capability_sha256",
        "primary_candidate_validator_path",
        "secondary_candidate_validator_path",
        "identity_candidate_validator_path",
        "installed_authorization_sha256",
        "installation_receipt_sha256",
    ],
)
def test_removed_identity_ceremony_aliases_fail_closed(
    tmp_path: Path, removed_key: str
) -> None:
    value = minimum_installed(tmp_path)
    value[removed_key] = "a" * 64
    with pytest.raises(IdentityAuthorityError) as raised:
        validate_minimum_installed_bytes(canonical_bytes(value))
    assert raised.value.outcome_id == "F017_V12_IDENTITY_INSTALLED_AUTHORITY_MISMATCH"


@pytest.mark.parametrize(
    ("key", "replacement"),
    [
        ("attempts", True),
        ("retries", 1),
        ("resume", True),
        ("generation", "V11"),
        ("authority_scope", "PRODUCTION_EVENT_06"),
        ("measured_producer_sha256", "A" * 64),
        ("measured_validator_path", PRODUCER),
    ],
)
def test_minimum_authority_mutations_fail_closed(
    tmp_path: Path, key: str, replacement: object
) -> None:
    value = minimum_installed(tmp_path)
    value[key] = replacement
    with pytest.raises(IdentityAuthorityError):
        validate_minimum_installed_bytes(canonical_bytes(value))


def test_minimum_authority_reaches_runtime_revalidation_without_checkpoint_access(
    tmp_path: Path,
) -> None:
    value = minimum_installed(tmp_path)
    authority = validate_minimum_installed_bytes(canonical_bytes(value))
    with mock.patch(
        "f017_checkpoint_identity_producer_v12.open_directory_no_symlinks",
        side_effect=AssertionError("checkpoint root must remain unopened"),
    ) as checkpoint_open:
        observed, contract = _runtime_revalidate(
            authority, str(value["package_attempt_id"])
        )
    checkpoint_open.assert_not_called()
    assert observed == value
    assert contract["checkpoint_set_sha256"] == value["checkpoint_set_sha256"]


def test_public_producer_is_a_pre_effect_tombstone(tmp_path: Path) -> None:
    value = minimum_installed(tmp_path)
    authority = validate_minimum_installed_bytes(canonical_bytes(value))
    with mock.patch(
        "f017_checkpoint_identity_producer_v12.open_directory_no_symlinks",
        side_effect=AssertionError("checkpoint root must remain unopened"),
    ) as checkpoint_open:
        with pytest.raises(RuntimeError, match="superseded by F017 Sequence 39"):
            produce(
                authority,
                package_attempt_id=str(value["package_attempt_id"]),
                package_durable_start=False,
            )
    checkpoint_open.assert_not_called()


def test_qualification_alias_preserves_preopen_stop_boundary(tmp_path: Path) -> None:
    value = minimum_installed(tmp_path)
    authority = validate_minimum_installed_bytes(canonical_bytes(value))
    with mock.patch(
        "f017_checkpoint_identity_producer_v12.open_directory_no_symlinks",
        side_effect=AssertionError("checkpoint root must remain unopened"),
    ) as checkpoint_open:
        with pytest.raises(IdentityAuthorityError):
            _qualification_produce(
                authority,
                package_attempt_id=str(value["package_attempt_id"]),
                package_durable_start=False,
            )
    checkpoint_open.assert_not_called()


def test_private_minimum_gate_entrypoint_has_exact_surface() -> None:
    import inspect

    assert tuple(inspect.signature(_minimum_gate_produce).parameters) == (
        "authority",
        "package_attempt_id",
        "package_durable_start",
        "evidence_directory",
    )


def test_qualification_alias_rejects_production_before_checkpoint_access(
    tmp_path: Path,
) -> None:
    value = minimum_installed(tmp_path)
    value["authority_scope"] = "PRODUCTION"
    forged = ValidatedIdentityAuthority(
        tuple(sorted(value.items())), "a" * 64, "INSTALLED"
    )
    with mock.patch(
        "f017_checkpoint_identity_producer_v12.open_directory_no_symlinks",
        side_effect=AssertionError("checkpoint root must remain unopened"),
    ) as checkpoint_open:
        with pytest.raises(IdentityAuthorityError):
            _qualification_produce(
                forged,
                package_attempt_id=str(value["package_attempt_id"]),
                package_durable_start=True,
            )
    checkpoint_open.assert_not_called()


@pytest.mark.parametrize(
    "leaf_kind", ["regular", "directory", "symlink", "fifo"]
)
def test_root_census_accepts_unrelated_leaf_without_opening_it(
    tmp_path: Path, leaf_kind: str
) -> None:
    authority, value, root, contract = runnable_minimum_installed(tmp_path)
    extra = root / f"unrelated-{leaf_kind}"
    if leaf_kind == "regular":
        extra.write_bytes(b"unrelated")
    elif leaf_kind == "directory":
        extra.mkdir()
    elif leaf_kind == "symlink":
        extra.symlink_to("unrelated-dangling-target")
    else:
        os.mkfifo(extra)

    real_open = os.open
    real_stat = os.stat
    real_lstat = os.lstat
    real_readlink = os.readlink
    real_hash_descriptor = identity_producer._hash_descriptor
    real_lease_record = identity_producer.LeaseRecord
    opened_names: list[str] = []
    stated_names: list[str] = []
    followed_names: list[str] = []
    descriptor_names: dict[int, str] = {}
    hashed_names: list[str] = []
    leased_ordinals: list[int] = []

    def tracked_open(path, flags, mode=0o777, *, dir_fd=None):
        descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        if type(path) is str:
            opened_names.append(path)
            descriptor_names[descriptor] = path
        return descriptor

    def tracked_stat(path, *, dir_fd=None, follow_symlinks=True):
        if type(path) is str:
            stated_names.append(path)
        return real_stat(path, dir_fd=dir_fd, follow_symlinks=follow_symlinks)

    def tracked_lstat(path, *, dir_fd=None):
        if type(path) is str:
            stated_names.append(path)
        return real_lstat(path, dir_fd=dir_fd)

    def tracked_readlink(path, *, dir_fd=None):
        if type(path) is str:
            followed_names.append(path)
        return real_readlink(path, dir_fd=dir_fd)

    def tracked_hash(descriptor, expected_size, *, require_single_link):
        hashed_names.append(descriptor_names[descriptor])
        return real_hash_descriptor(
            descriptor,
            expected_size,
            require_single_link=require_single_link,
        )

    def tracked_lease(identity, descriptor):
        leased_ordinals.append(identity["shard_ordinal"])
        return real_lease_record(identity, descriptor)

    evidence = tmp_path / "identity-evidence"
    with (
        mock.patch.object(identity_producer.os, "open", side_effect=tracked_open),
        mock.patch.object(identity_producer.os, "stat", side_effect=tracked_stat),
        mock.patch.object(identity_producer.os, "lstat", side_effect=tracked_lstat),
        mock.patch.object(
            identity_producer.os, "readlink", side_effect=tracked_readlink
        ),
        mock.patch.object(
            identity_producer, "_hash_descriptor", side_effect=tracked_hash
        ),
        mock.patch.object(identity_producer, "LeaseRecord", side_effect=tracked_lease),
    ):
        leases, report = run_minimum_identity_stage(
            authority, value, evidence_directory=evidence
        )
    try:
        expected_names = [shard["filename"] for shard in contract["shards"]]
        assert [name for name in opened_names if name in expected_names] == expected_names
        assert extra.name not in opened_names
        assert extra.name not in stated_names
        assert extra.name not in followed_names
        assert hashed_names == expected_names
        assert leased_ordinals == [2, 3, 4, 5, 6]
        assert report["checkpoint_shard_opens"] == 6
        assert report["checkpoint_identity_hash_reads"] == 6
        assert all(extra.name.encode("utf-8") not in item.read_bytes() for item in evidence.iterdir())
    finally:
        release = leases.release()
    assert release["result"] == "PASS"
    assert release["live_leases_after_release"] == 0


@pytest.mark.parametrize("missing_ordinal", range(1, 7))
def test_each_missing_required_shard_fails_before_any_shard_open(
    tmp_path: Path, missing_ordinal: int
) -> None:
    authority, value, root, contract = runnable_minimum_installed(tmp_path)
    (root / f"synthetic-v12-shard-{missing_ordinal}.bin").unlink()
    expected_names = {shard["filename"] for shard in contract["shards"]}

    real_open = os.open
    with mock.patch.object(identity_producer.os, "open", wraps=real_open) as opened:
        with pytest.raises(IdentityAuthorityError) as raised:
            run_minimum_identity_stage(authority, value)

    shard_open_attempts = [
        call.args[0]
        for call in opened.call_args_list
        if call.args and call.args[0] in expected_names
    ]
    assert shard_open_attempts == []
    assert raised.value.outcome_id == "F017_V12_IDENTITY_SHARD_OPEN_FAILURE"
    assert raised.value.evidence["checkpoint_access"] == 0
    assert raised.value.detail.startswith("checkpoint root leaf census")


@pytest.mark.parametrize(
    ("fault", "expected_outcome"),
    [
        ("symlink", "F017_V12_IDENTITY_SHARD_OPEN_FAILURE"),
        ("wrong_type", "F017_V12_IDENTITY_DESCRIPTOR_CHANGED"),
        ("wrong_size", "F017_V12_IDENTITY_SHARD_SIZE_MISMATCH"),
        ("hash_mismatch", "F017_V12_IDENTITY_SHARD_HASH_MISMATCH"),
    ],
)
def test_expected_shard_name_still_enforces_descriptor_identity(
    tmp_path: Path, fault: str, expected_outcome: str
) -> None:
    authority, value, root, _contract = runnable_minimum_installed(
        tmp_path, mixed=True
    )
    target = root / "synthetic-v12-shard-6.bin"
    target.unlink()
    if fault == "symlink":
        target.symlink_to("synthetic-v12-shard-5.bin")
    elif fault == "wrong_type":
        target.mkdir()
    elif fault == "wrong_size":
        target.write_bytes(b"short")
    else:
        target.write_bytes(b"\t" * 6)

    with pytest.raises(IdentityAuthorityError) as raised:
        run_minimum_identity_stage(authority, value)
    assert raised.value.outcome_id == expected_outcome
    assert raised.value.evidence["generic_fallback"] is False


def test_root_census_listdir_failure_closes_root_descriptor(tmp_path: Path) -> None:
    authority, value, _root, _contract = runnable_minimum_installed(tmp_path)
    real_open_root = identity_producer.open_directory_no_symlinks
    captured_root_fd: int | None = None

    def capture_root_descriptor(path: Path) -> tuple[int, Path]:
        nonlocal captured_root_fd
        captured_root_fd, opened = real_open_root(path)
        return captured_root_fd, opened

    with mock.patch.object(
        identity_producer,
        "open_directory_no_symlinks",
        side_effect=capture_root_descriptor,
    ), mock.patch.object(
        identity_producer.os,
        "listdir",
        side_effect=OSError(errno.EIO, "injected root census failure"),
    ):
        with pytest.raises(IdentityAuthorityError) as raised:
            run_minimum_identity_stage(authority, value)

    assert raised.value.outcome_id == "F017_V12_IDENTITY_SHARD_OPEN_FAILURE"
    assert raised.value.evidence["checkpoint_access"] == 0
    assert captured_root_fd is not None
    with pytest.raises(OSError) as closed:
        os.fstat(captured_root_fd)
    assert closed.value.errno == errno.EBADF


@pytest.mark.parametrize(
    "variant",
    ["SYNTHETIC-v12-shard-6.bin", "synthetic-v12-shard-６.bin"],
)
def test_variant_leaf_cannot_replace_exact_required_name(
    tmp_path: Path, variant: str
) -> None:
    authority, value, root, contract = runnable_minimum_installed(tmp_path)
    (root / "synthetic-v12-shard-6.bin").unlink()
    (root / variant).touch()
    expected_names = {shard["filename"] for shard in contract["shards"]}
    real_open = os.open
    shard_opens: list[str] = []

    def tracked_open(path, flags, mode=0o777, *, dir_fd=None):
        if path in expected_names:
            shard_opens.append(path)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    with mock.patch.object(identity_producer.os, "open", side_effect=tracked_open):
        with pytest.raises(IdentityAuthorityError) as raised:
            run_minimum_identity_stage(authority, value)
    assert shard_opens == []
    assert raised.value.outcome_id == "F017_V12_IDENTITY_SHARD_OPEN_FAILURE"
    assert variant not in raised.value.detail
    assert "required=6 present=5 missing=1" in raised.value.detail


def test_checkpoint_census_uses_one_descriptor_relative_listing(
    tmp_path: Path,
) -> None:
    authority, value, _root, _contract = runnable_minimum_installed(tmp_path)
    real_listdir = os.listdir
    real_open_root = identity_producer.open_directory_no_symlinks
    real_resolve = Path.resolve
    listdir_targets: list[object] = []
    resolves_after_root_open: list[Path] = []
    captured_root_fd: int | None = None
    root_opened = False

    def tracked_listdir(target):
        listdir_targets.append(target)
        return real_listdir(target)

    def tracked_open_root(path: Path) -> tuple[int, Path]:
        nonlocal captured_root_fd, root_opened
        captured_root_fd, opened = real_open_root(path)
        root_opened = True
        return captured_root_fd, opened

    def tracked_resolve(path: Path, *args, **kwargs) -> Path:
        if root_opened:
            resolves_after_root_open.append(path)
        return real_resolve(path, *args, **kwargs)

    with (
        mock.patch.object(
            identity_producer.os, "listdir", side_effect=tracked_listdir
        ),
        mock.patch.object(
            identity_producer,
            "open_directory_no_symlinks",
            side_effect=tracked_open_root,
        ),
        mock.patch.object(Path, "resolve", new=tracked_resolve),
    ):
        leases, _report = run_minimum_identity_stage(authority, value)
    assert captured_root_fd is not None
    assert listdir_targets == [captured_root_fd]
    assert type(listdir_targets[0]) is int
    assert resolves_after_root_open == []
    assert leases.release()["result"] == "PASS"


def test_exact_equality_census_mutant_rejects_a_benign_extra(tmp_path: Path) -> None:
    authority, value, root, _contract = runnable_minimum_installed(tmp_path)
    (root / "unrelated-regular").touch()

    def exact_equality_mutant(root_fd: int, required_names: tuple[str, ...]) -> None:
        if set(os.listdir(root_fd)) != set(required_names):
            raise identity_producer.failure(
                "F017_V12_IDENTITY_SHARD_OPEN_FAILURE",
                "mutated exact equality",
                checkpoint_access=0,
            )

    with mock.patch.object(
        identity_producer,
        "_require_checkpoint_root_membership",
        side_effect=exact_equality_mutant,
    ):
        with pytest.raises(IdentityAuthorityError, match="mutated exact equality"):
            run_minimum_identity_stage(authority, value)


def test_deleted_membership_mutant_reaches_forbidden_shard_open(
    tmp_path: Path,
) -> None:
    authority, value, root, contract = runnable_minimum_installed(tmp_path)
    (root / "synthetic-v12-shard-6.bin").unlink()
    required = {shard["filename"] for shard in contract["shards"]}
    real_open = os.open

    def reject_any_shard_open(path, flags, mode=0o777, *, dir_fd=None):
        if path in required:
            raise AssertionError("membership mutant reached a shard open")
        return real_open(path, flags, mode, dir_fd=dir_fd)

    with (
        mock.patch.object(
            identity_producer,
            "_require_checkpoint_root_membership",
            return_value=None,
        ),
        mock.patch.object(
            identity_producer.os, "open", side_effect=reject_any_shard_open
        ),
    ):
        with pytest.raises(AssertionError, match="membership mutant reached"):
            run_minimum_identity_stage(authority, value)


def test_contract_name_derivation_and_source_open_surface_are_exact() -> None:
    for relative in (PRODUCTION_CONTRACT, CONTRACT, MIXED_CONTRACT):
        contract = json.loads((ROOT / relative).read_text(encoding="utf-8"))
        names = identity_producer._required_shard_names(contract)
        assert len(names) == len(set(names)) == 6
        assert all(Path(name).name == name and name not in {".", ".."} for name in names)

    source = Path(identity_producer.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    minimum = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_minimum_gate_produce"
    )
    calls = [node for node in ast.walk(minimum) if isinstance(node, ast.Call)]
    shard_opens = [
        node
        for node in calls
        if isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "os"
        and node.func.attr == "open"
    ]
    assert len(shard_opens) == 1
    assert ast.unparse(shard_opens[0].args[0]) == "shard['filename']"
    assert ast.unparse(shard_opens[0].args[1]) == "os.O_RDONLY | os.O_NOFOLLOW"
    assert {
        keyword.arg: ast.unparse(keyword.value) for keyword in shard_opens[0].keywords
    } == {"dir_fd": "root_fd"}
    assert not any(
        isinstance(node.func, ast.Attribute)
        and node.func.attr in {"glob", "rglob", "scandir"}
        for node in calls
    )


def test_contract_name_derivation_rejects_shard_order_drift() -> None:
    contract = json.loads((ROOT / CONTRACT).read_text(encoding="utf-8"))
    contract["shards"][0], contract["shards"][1] = (
        contract["shards"][1],
        contract["shards"][0],
    )
    with pytest.raises(IdentityAuthorityError, match="required shard order"):
        identity_producer._required_shard_names(contract)


def test_expected_name_socket_and_descriptor_mutation_fail_closed(
    tmp_path: Path,
) -> None:
    authority, value, root, _contract = runnable_minimum_installed(
        tmp_path, mixed=True
    )
    socket_leaf = root / "synthetic-v12-shard-6.bin"
    socket_leaf.unlink()
    bound = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    previous_directory = os.getcwd()
    try:
        os.chdir(root)
        bound.bind(socket_leaf.name)
    finally:
        os.chdir(previous_directory)
    try:
        with pytest.raises(IdentityAuthorityError) as socket_failure:
            run_minimum_identity_stage(authority, value)
        assert socket_failure.value.outcome_id in {
            "F017_V12_IDENTITY_SHARD_OPEN_FAILURE",
            "F017_V12_IDENTITY_DESCRIPTOR_CHANGED",
        }
    finally:
        bound.close()

    socket_leaf.unlink()
    socket_leaf.write_bytes(bytes([6]) * 6)
    original_pread = os.pread
    mutated = False

    def mutating_pread(descriptor: int, count: int, offset: int) -> bytes:
        nonlocal mutated
        block = original_pread(descriptor, count, offset)
        if not mutated:
            with (root / "synthetic-v12-shard-1.bin").open("ab") as stream:
                stream.write(b"x")
                stream.flush()
                os.fsync(stream.fileno())
            mutated = True
        return block

    with mock.patch.object(
        identity_producer.os, "pread", side_effect=mutating_pread
    ):
        with pytest.raises(IdentityAuthorityError) as mutation_failure:
            run_minimum_identity_stage(authority, value)
    assert (
        mutation_failure.value.outcome_id
        == "F017_V12_IDENTITY_DESCRIPTOR_CHANGED"
    )
