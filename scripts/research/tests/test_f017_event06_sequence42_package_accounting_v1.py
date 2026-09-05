from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import errno
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
from typing import Iterator

import pytest

import f017_checkpoint_identity_producer_v12 as identity_producer
import f017_write_once_artifact_v1 as write_once_artifact
from f017_checkpoint_identity_lifecycle_v12 import (
    IdentityAccessCensus,
    IdentityAuthorityError,
    IdentityDescriptorDisposition,
)
import f017_event06_minimum_gate_path_v1 as path


_NOW = 42_000_000_000
_CHILD_CLOSEOUT = r"""
import json
from pathlib import Path
import sys
import f017_event06_minimum_gate_path_v1 as path

root = Path(sys.argv[1])
raw = bytes.fromhex(sys.argv[2])
profile = path._authority_profile(synthetic=True)
go = path._validate_go_non_temporal(raw, profile)
runtime = path._qualification_runtime(
    root,
    str(go.get("human_decision_sha256")),
    intercept=False,
)
result = path._invoke_public_closeout_qualification(
    raw, runtime, now_unix_ns=0
)
print(json.dumps(result, sort_keys=True), flush=True)
"""

_CHILD_START_AND_WAIT = r"""
from pathlib import Path
import sys
import time
import f017_event06_minimum_gate_path_v1 as path

root = Path(sys.argv[1])
raw = bytes.fromhex(sys.argv[2])
profile = path._authority_profile(synthetic=True)
go = path._validate_go_non_temporal(raw, profile)
runtime = path._qualification_runtime(
    root,
    str(go.get("human_decision_sha256")),
    intercept=False,
)
runtime.storage.prepare()
expected = path._derive_expected_package_start_receipt(go, runtime)
stop = path._StopBoundary(runtime.storage)
runtime.storage.bank_package_start(expected, stop)
print("READY", flush=True)
while True:
    time.sleep(60)
"""

_CHILD_START_AND_CRASH = r"""
from pathlib import Path
import os
import sys
import f017_event06_minimum_gate_path_v1 as path

root = Path(sys.argv[1])
raw = bytes.fromhex(sys.argv[2])
profile = path._authority_profile(synthetic=True)
go = path._validate_go_non_temporal(raw, profile)
runtime = path._qualification_runtime(
    root,
    str(go.get("human_decision_sha256")),
    intercept=False,
)
runtime.storage.prepare()
expected = path._derive_expected_package_start_receipt(go, runtime)
stop = path._StopBoundary(runtime.storage)
runtime.storage.bank_package_start(expected, stop)
os._exit(42)
"""

_CHILD_PUBLIC_DETERMINISM = r"""
from collections.abc import Mapping
import hashlib
import json
import os
from pathlib import Path
import sys

import f017_checkpoint_identity_producer_v12 as identity_producer
import f017_event06_minimum_gate_path_v1 as path


def canonical_sha256(value):
    return hashlib.sha256(path._canonical_bytes(value)).hexdigest()


def thaw(value):
    if isinstance(value, Mapping):
        return {str(key): thaw(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [thaw(item) for item in value]
    return value


root = Path(sys.argv[1])
raw = bytes.fromhex(sys.argv[2])
root.mkdir(mode=0o700)
profile = path._authority_profile(synthetic=True)
go = path._validate_go_bytes(raw, profile, now_unix_ns=42_000_000_000)
human = str(go.get("human_decision_sha256"))
runtime = path._qualification_runtime(root, human, intercept=False)
result = path._invoke_public_qualification(
    raw, runtime, now_unix_ns=42_000_000_000
)

assert path.__all__ == (
    "execute_event06_minimum_gate_path",
    "closeout_interrupted_event06_minimum_gate_path",
)
assert result["result"] == "PASS"
assert tuple(result["required_gates"]) == tuple(
    f"M{index:03d}" for index in range(1, 18)
)
protected_effects = {
    "original_checkpoint_root_resolutions": result[
        "original_checkpoint_root_resolutions"
    ],
    "original_checkpoint_opens": result["original_checkpoint_opens"],
    "real_numerical_executions": result["real_numerical_executions"],
}
assert protected_effects == {
    "original_checkpoint_root_resolutions": 0,
    "original_checkpoint_opens": 0,
    "real_numerical_executions": 0,
}
assert runtime.observed_effects["checkpoint_root_resolutions"] == 0
assert runtime.observed_effects["checkpoint_opens"] == 0
assert runtime.observed_effects["numerical_executions"] == 0

provider = runtime.checkpoint_effect
assert type(provider) is path._SyntheticCheckpointProvider
synthetic_access = {
    "physical_identity_producer_calls": provider.physical_identity_producer_calls,
    "producer_checkpoint_binding_checks": (
        provider.producer_checkpoint_binding_checks
    ),
    "producer_checkpoint_shard_opens": provider.producer_checkpoint_shard_opens,
    "producer_checkpoint_identity_hash_reads": (
        provider.producer_checkpoint_identity_hash_reads
    ),
}
assert synthetic_access == {
    "physical_identity_producer_calls": 1,
    "producer_checkpoint_binding_checks": 1,
    "producer_checkpoint_shard_opens": 6,
    "producer_checkpoint_identity_hash_reads": 6,
}

package = runtime.storage.package_directory
identity = package / "identity"


def load(directory, leaf):
    return path._parse_artifact_bytes((directory / leaf).read_bytes())


leaf_names = sorted(os.listdir(identity))
assert leaf_names == list(identity_producer.identity_success_evidence_leaves())
assert len(leaf_names) == 31

journal = load(identity, "access-journal.json")
census = journal["access_census"]
stable_census_keys = (
    "schema",
    "receipt_count",
    "checkpoint_shard_opens_lower_bound",
    "checkpoint_shard_opens_upper_bound",
    "checkpoint_shard_opens_unconfirmed",
    "checkpoint_identity_hash_reads_lower_bound",
    "checkpoint_identity_hash_reads_upper_bound",
    "checkpoint_identity_hash_reads_unconfirmed",
    "identity_hash_bytes_lower_bound",
    "identity_hash_bytes_upper_bound",
    "identity_hash_bytes_unconfirmed",
    "exact",
    "unresolved_operation",
    "unresolved_ordinal",
    "prefix_complete",
    "result",
)
stable_census = {key: census[key] for key in stable_census_keys}
assert stable_census == {
    "schema": "pulsarmlx.f017.checkpoint-identity-access-census/12.1.0",
    "receipt_count": 24,
    "checkpoint_shard_opens_lower_bound": 6,
    "checkpoint_shard_opens_upper_bound": 6,
    "checkpoint_shard_opens_unconfirmed": 0,
    "checkpoint_identity_hash_reads_lower_bound": 6,
    "checkpoint_identity_hash_reads_upper_bound": 6,
    "checkpoint_identity_hash_reads_unconfirmed": 0,
    "identity_hash_bytes_lower_bound": 0,
    "identity_hash_bytes_upper_bound": 0,
    "identity_hash_bytes_unconfirmed": 0,
    "exact": True,
    "unresolved_operation": None,
    "unresolved_ordinal": 0,
    "prefix_complete": True,
    "result": "PASS",
}

stable_access_receipt_keys = (
    "schema",
    "authorization_id",
    "package_attempt_id",
    "checkpoint_identity_contract_sha256",
    "checkpoint_set_sha256",
    "sequence",
    "ordinal",
    "shard_name",
    "role",
    "operation",
    "phase",
    "expected_bytes",
    "observed_bytes",
    "effect_count",
    "observed_sha256",
    "disposition",
    "result",
)
stable_access_receipts = []
for sequence in range(1, 25):
    receipt = load(identity, f"access-prefix-{sequence:02d}.json")
    assert set(receipt) == identity_producer._ACCESS_RECEIPT_KEYS
    stable_access_receipts.append({
        key: receipt[key] for key in stable_access_receipt_keys
    })
assert [item["sequence"] for item in stable_access_receipts] == list(range(1, 25))

package_start = load(package, "package-start.json")
stable_package_start_keys = (
    "schema",
    "stage",
    "authorization_id",
    "package_attempt_id",
    "primary_event_id",
    "secondary_event_id",
    "attempts",
    "retries",
    "resume",
    "result",
)
stable_package_start = {
    key: package_start[key] for key in stable_package_start_keys
}

stable_stage_receipts = []
for leaf in (
    "primary-start-receipt.json",
    "secondary-start-receipt.json",
    "release-start-receipt.json",
):
    receipt = load(package, leaf)
    assert set(receipt) == {
        "schema",
        "stage",
        "authorization_id",
        "package_attempt_id",
        "stage_event_id",
        "package_start_sha256",
        "stage_authority_sha256",
        "result",
    }
    stable_stage_receipts.append({
        key: receipt[key]
        for key in (
            "schema",
            "stage",
            "authorization_id",
            "package_attempt_id",
            "stage_event_id",
            "result",
        )
    })

lease_manifest = load(identity, "lease-manifest.json")
identity_core = load(identity, "identity-core.json")
identity_manifest = load(identity, "identity-manifest.json")
identity_receipt = load(identity, "identity-receipt.json")
identity_terminal = load(identity, "identity-terminal.json")
shard_receipts = load(identity, "shard-receipts.json")
stable_identity_evidence = {
    "leaf_names": leaf_names,
    "access_receipts": stable_access_receipts,
    "access_journal": {
        key: journal[key]
        for key in (
            "schema",
            "authorization_id",
            "package_attempt_id",
            "checkpoint_identity_contract_sha256",
            "checkpoint_set_sha256",
            "entries",
            "access_prefix_receipt_count",
            "checkpoint_shard_opens",
            "checkpoint_identity_hash_reads",
            "result",
        )
    },
    "access_census": stable_census,
    "shard_receipts": {
        key: shard_receipts[key]
        for key in (
            "schema",
            "package_attempt_id",
            "access_prefix_receipt_count",
            "receipts",
            "result",
        )
    },
    "lease_manifest": {
        key: lease_manifest[key]
        for key in (
            "schema",
            "package_attempt_id",
            "identity_only_retained_count",
            "retained_lease_count",
            "result",
        )
    },
    "identity_core": {
        key: identity_core[key]
        for key in (
            "schema",
            "authority_scope",
            "operation_class",
            "checkpoint_set_sha256",
            "ordered_shard_digests",
            "shard_roles",
            "shard_sizes",
            "identity_only_retained_count",
            "retained_lease_count",
            "access_prefix_receipt_count",
        )
    },
    "identity_manifest": {
        key: identity_manifest[key]
        for key in (
            "schema",
            "authorization_id",
            "package_attempt_id",
            "access_prefix_receipt_count",
            "result",
        )
    },
    "identity_receipt": {
        key: identity_receipt[key]
        for key in (
            "schema",
            "authorization_id",
            "package_attempt_id",
            "result",
        )
    },
    "identity_terminal": {
        key: identity_terminal[key]
        for key in (
            "schema",
            "package_attempt_id",
            "state",
            "result",
        )
    },
}

accounting = load(package, "receipt-derived-accounting.json")
stable_accounting_keys = (
    "schema",
    "authorization_id",
    "package_attempt_id",
    "primary_event_id",
    "secondary_event_id",
    "identity_read_receipts",
    "identity_read_receipt_root_sha256",
    "identity_read_receipt_count",
    "identity_bytes_read",
    "authorization_delta",
    "package_delta",
    "primary_delta",
    "secondary_delta",
    "historical_master_ledger_before",
    "historical_master_ledger_after",
    "attempted_closures",
    "successful_closures",
    "duplicate_closes",
    "unknown_leases",
    "live_leases",
    "stage",
    "result",
)
stable_accounting = {key: accounting[key] for key in stable_accounting_keys}
assert stable_accounting["identity_read_receipt_count"] == 6
assert stable_accounting["identity_bytes_read"] == 0
assert (
    stable_accounting["authorization_delta"],
    stable_accounting["package_delta"],
    stable_accounting["primary_delta"],
    stable_accounting["secondary_delta"],
) == (0, 1, 1, 1)
assert (
    stable_accounting["attempted_closures"],
    stable_accounting["successful_closures"],
    stable_accounting["duplicate_closes"],
    stable_accounting["unknown_leases"],
    stable_accounting["live_leases"],
) == (5, 5, 0, 0, 0)

normalization_excludes = [
    "installed_authority.checkpoint_root",
    "package-start.json.package_start_gate_sha256",
    "*-start-receipt.json.package_start_sha256",
    "*-start-receipt.json.stage_authority_sha256",
    "identity/access-prefix-*.json.predecessor_sha256",
    "identity/access-prefix-*.json.descriptor_identity_sha256",
    "identity/access-census.{genesis_sha256,head_sha256}",
    "identity/lease-manifest.json.descriptors",
    "identity/base-leaf transitive SHA-256 bindings",
    "receipt-derived-accounting.json.consumed_package_start_gate_sha256",
    "receipt-derived-accounting.json.receipt_bindings",
    "receipt-derived-accounting.json.receipt_root_sha256",
    "public-result terminal/receipt/accounting SHA-256 bindings",
]
normalized_components = {
    "collapsed_go": path._parse_artifact_bytes(raw),
    "public_contract": {
        "exports": list(path.__all__),
        "entry": "execute_event06_minimum_gate_path",
        "result": result["result"],
        "required_gates": list(result["required_gates"]),
        "protected_effects": protected_effects,
        "synthetic_access": synthetic_access,
    },
    "package_authority": stable_package_start,
    "stage_authority": stable_stage_receipts,
    "identity_evidence": stable_identity_evidence,
    "receipt_derived_accounting": stable_accounting,
    "comparison": thaw(result["comparison"]),
}
component_sha256s = {
    key: canonical_sha256(value)
    for key, value in normalized_components.items()
}
normalized_identity_sha256 = canonical_sha256(normalized_components)
print(json.dumps({
    "process_id": os.getpid(),
    "collapsed_go_sha256": hashlib.sha256(raw).hexdigest(),
    "normalized_identity_sha256": normalized_identity_sha256,
    "component_sha256s": component_sha256s,
    "normalization_excludes": normalization_excludes,
    "public_exports": list(path.__all__),
    "result": result["result"],
    "required_gate_count": len(result["required_gates"]),
    "identity_leaf_count": len(leaf_names),
    "access_receipt_count": stable_census["receipt_count"],
    "synthetic_checkpoint_shard_opens": (
        stable_census["checkpoint_shard_opens_lower_bound"]
    ),
    "synthetic_checkpoint_identity_hash_reads": (
        stable_census["checkpoint_identity_hash_reads_lower_bound"]
    ),
    "protected_effects": protected_effects,
}, sort_keys=True), flush=True)
"""


def _unseal_tree(root: Path) -> None:
    """Make graph-owned Darwin test artifacts removable by pytest cleanup."""
    if not root.exists():
        return
    for current, directories, files in os.walk(root, topdown=False):
        current_path = Path(current)
        for name in files:
            target = current_path / name
            try:
                if target.is_symlink():
                    continue
                descriptor = os.open(target, os.O_RDONLY | os.O_NOFOLLOW)
                try:
                    path._set_user_immutable(descriptor, False)
                finally:
                    os.close(descriptor)
            except OSError:
                pass
        for name in directories:
            target = current_path / name
            try:
                if target.is_symlink():
                    continue
                descriptor = os.open(
                    target,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                )
                try:
                    path._set_user_immutable(descriptor, False)
                finally:
                    os.close(descriptor)
            except OSError:
                pass
        try:
            descriptor = os.open(
                current_path,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            )
            try:
                path._set_user_immutable(descriptor, False)
            finally:
                os.close(descriptor)
        except OSError:
            pass


@pytest.fixture
def synthetic_root(tmp_path: Path) -> Iterator[Path]:
    yield tmp_path
    _unseal_tree(tmp_path)


def _go(root: Path, label: str) -> tuple[bytes, object, str]:
    profile = path._authority_profile(synthetic=True)
    seed = b"F017-SEQUENCE42-PACKAGE-ACCOUNTING\x00" + label.encode("ascii")
    raw = path._qualification_go(profile, seed, now_unix_ns=_NOW)
    validated = path._validate_go_bytes(raw, profile, now_unix_ns=_NOW)
    human = str(validated.get("human_decision_sha256"))
    assert human != path._sha(b"F017-EVENT06-SEQUENCE40-CONSUMED-DECISION")
    return raw, validated, human


def _started_package(root: Path, label: str):
    raw, go, human = _go(root, label)
    runtime = path._qualification_runtime(root, human, intercept=False)
    runtime.storage.prepare()
    expected = path._derive_expected_package_start_receipt(go, runtime)
    expected_raw = path._canonical_bytes(expected)
    stop = path._StopBoundary(runtime.storage)
    start_sha = runtime.storage.bank_package_start(expected, stop)
    assert stop.package_started is True
    assert start_sha == path._sha(expected_raw)
    return raw, go, runtime, stop, expected, expected_raw, start_sha


def _release_owner_without_synthetic_cleanup(runtime: object) -> None:
    # Models process death: close the held descriptors without qualification's
    # convenience unsealing pass.
    path._StorageBinding.close(runtime.storage)


def _closeout_runtime(root: Path, raw: bytes, human: str) -> dict[str, object]:
    runtime = path._qualification_runtime(root, human, intercept=False)
    return path._invoke_public_closeout_qualification(
        raw, runtime, now_unix_ns=0
    )


def _run_child(code: str, root: Path, raw: bytes, *, timeout: int = 60):
    completed = subprocess.run(
        [sys.executable, "-c", code, str(root), raw.hex()],
        cwd=Path(path.__file__).resolve().parents[2],
        env=os.environ.copy(),
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    return completed


def _parse_child_json(stdout: str) -> dict[str, object]:
    lines = [line for line in stdout.splitlines() if line.strip()]
    assert lines
    return json.loads(lines[-1])


def _mutate_json_leaf(target: Path, mutate) -> None:
    reader = os.open(target, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        original_mode = stat.S_IMODE(os.fstat(reader).st_mode)
        path._set_user_immutable(reader, False)
        if not original_mode & stat.S_IWUSR:
            os.fchmod(reader, original_mode | stat.S_IWUSR)
    finally:
        os.close(reader)
    descriptor = os.open(target, os.O_RDWR | os.O_NOFOLLOW)
    try:
        os.lseek(descriptor, 0, os.SEEK_SET)
        value = path._parse_artifact_bytes(os.read(descriptor, 1_048_576))
        mutated = mutate(dict(value))
        raw = path._canonical_bytes(mutated)
        os.ftruncate(descriptor, 0)
        os.lseek(descriptor, 0, os.SEEK_SET)
        written = 0
        while written < len(raw):
            written += os.write(descriptor, raw[written:])
        os.fchmod(descriptor, original_mode)
        os.fsync(descriptor)
        path._set_user_immutable(descriptor, True)
    finally:
        os.close(descriptor)


def _rebind_failure_accounting_in_terminal(
    package: Path,
    mutate,
) -> None:
    """Rewrite a terminal's embedded/leaf accounting with matching digests."""
    accounting_path = package / "failure-accounting.json"
    _mutate_json_leaf(accounting_path, mutate)
    accounting_raw = accounting_path.read_bytes()
    accounting = path._parse_artifact_bytes(accounting_raw)
    accounting_sha256 = path._sha(accounting_raw)

    def rebind(terminal):
        terminal["failure_accounting"] = accounting
        terminal["failure_accounting_sha256"] = accounting_sha256
        terminal["failure_accounting_leaf_sha256"] = accounting_sha256
        terminal["emergency_release_result"] = (
            accounting["emergency_release_outcome"].get("result")
            if accounting["emergency_release_outcome"] is not None
            else None
        )
        terminal["emergency_release_disposition"] = (
            accounting["emergency_release_outcome"].get("release_disposition")
            if accounting["emergency_release_outcome"] is not None
            else None
        )
        return terminal

    _mutate_json_leaf(package / "package-terminal.json", rebind)


def _access_fixture(root: Path, label: str):
    raw, go, human = _go(root, label)
    runtime = path._qualification_runtime(root, human, intercept=False)
    start = path._derive_expected_package_start_receipt(go, runtime)
    contract = path._parse_artifact_bytes(
        (path._ROOT / runtime.profile.checkpoint_contract_path).read_bytes()
    )
    bindings = {
        "authorization_id": start["authorization_id"],
        "package_attempt_id": start["package_attempt_id"],
        "checkpoint_identity_contract_sha256": (
            runtime.profile.checkpoint_authority_sha256
        ),
        "checkpoint_set_sha256": runtime.profile.checkpoint_set_sha256,
    }
    evidence = root / "identity-prefix"
    writer = identity_producer._AccessPrefixWriter(
        evidence, bindings, contract, write_once=True
    )
    return raw, runtime, bindings, contract, evidence, writer


def _bank_first_open_and_hash(writer: object, *, mismatch: bool = False) -> None:
    descriptor_sha = "1" * 64
    expected = writer.plan[3]
    writer.bank(
        operation="SHARD_OPEN",
        phase="INTENT",
        effect_count=0,
        observed_bytes=0,
        descriptor_identity_sha256=None,
        observed_sha256=None,
        disposition="SHARD_OPEN_INTENT",
        result="PENDING",
    )
    writer.bank(
        operation="SHARD_OPEN",
        phase="COMPLETE",
        effect_count=1,
        observed_bytes=0,
        descriptor_identity_sha256=descriptor_sha,
        observed_sha256=None,
        disposition="SHARD_OPEN_COMPLETE",
        result="PASS",
    )
    writer.bank(
        operation="IDENTITY_HASH_READ",
        phase="INTENT",
        effect_count=0,
        observed_bytes=0,
        descriptor_identity_sha256=descriptor_sha,
        observed_sha256=None,
        disposition="IDENTITY_HASH_READ_INTENT",
        result="PENDING",
    )
    writer.bank(
        operation="IDENTITY_HASH_READ",
        phase="COMPLETE",
        effect_count=1,
        observed_bytes=int(expected["expected_bytes"]),
        descriptor_identity_sha256=descriptor_sha,
        observed_sha256=("2" * 64 if mismatch else expected["expected_sha256"]),
        disposition=("IDENTITY_HASH_MISMATCH" if mismatch else "IDENTITY_HASH_COMPLETE"),
        result=("FAIL" if mismatch else "PASS"),
    )


class _OriginalPrestartError(RuntimeError):
    pass


@pytest.mark.parametrize(
    "boundary",
    (
        "exclusive-start-open",
        "first-write",
        "file-fsync",
        "post-write-fstat",
        "readback-lseek",
        "readback-read",
        "immutable-transition",
        "seal-fsync",
        "close",
        "package-directory-fsync",
        "in-memory-mark",
        "final-path-revalidation",
    ),
)
def test_package_start_fault_boundary_reopens_to_same_durable_classification(
    synthetic_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
) -> None:
    raw, go, human = _go(synthetic_root, "start-boundary-" + boundary)
    runtime = path._qualification_runtime(synthetic_root, human, intercept=False)
    runtime.storage.prepare()
    expected = path._derive_expected_package_start_receipt(go, runtime)
    expected_raw = path._canonical_bytes(expected)
    stop = path._StopBoundary(runtime.storage)
    marker = _OriginalPrestartError("package-start-boundary:" + boundary)
    state: dict[str, object] = {
        "start_fd": None,
        "start_fsyncs": 0,
        "start_closed": False,
        "write_complete": False,
        "injected": False,
    }

    real_open = path.os.open
    real_write = path.os.write
    real_fsync = path.os.fsync
    real_fstat = path.os.fstat
    real_lseek = path.os.lseek
    real_read = path.os.read
    real_close = path.os.close
    real_immutable = path._set_user_immutable
    real_mark = path._StopBoundary.mark_package_started
    real_verify = path._StorageBinding._verify_package_path_identity

    def inject() -> None:
        state["injected"] = True
        raise marker

    def tracked_open(target, flags, mode=0o777, *, dir_fd=None):
        if (
            target == "package-start.json"
            and flags & os.O_EXCL
            and boundary == "exclusive-start-open"
        ):
            inject()
        descriptor = real_open(target, flags, mode, dir_fd=dir_fd)
        if target == "package-start.json" and flags & os.O_EXCL:
            state["start_fd"] = descriptor
        return descriptor

    def tracked_write(descriptor, value):
        if descriptor == state["start_fd"] and boundary == "first-write":
            inject()
        count = real_write(descriptor, value)
        if descriptor == state["start_fd"] and count == len(value):
            state["write_complete"] = True
        return count

    def tracked_fsync(descriptor):
        if descriptor == state["start_fd"]:
            state["start_fsyncs"] = int(state["start_fsyncs"]) + 1
            if (
                boundary == "file-fsync"
                and state["start_fsyncs"] == 1
            ) or (
                boundary == "seal-fsync"
                and state["start_fsyncs"] == 2
            ):
                inject()
        if (
            descriptor == runtime.storage._package_fd
            and state["start_closed"]
            and boundary == "package-directory-fsync"
            and not state["injected"]
        ):
            inject()
        return real_fsync(descriptor)

    def tracked_fstat(descriptor):
        if (
            descriptor == state["start_fd"]
            and boundary == "post-write-fstat"
            and state["write_complete"]
            and not state["injected"]
        ):
            inject()
        return real_fstat(descriptor)

    def tracked_lseek(descriptor, offset, whence):
        if (
            descriptor == state["start_fd"]
            and boundary == "readback-lseek"
            and not state["injected"]
        ):
            inject()
        return real_lseek(descriptor, offset, whence)

    def tracked_read(descriptor, count):
        if (
            descriptor == state["start_fd"]
            and boundary == "readback-read"
            and not state["injected"]
        ):
            inject()
        return real_read(descriptor, count)

    def tracked_immutable(descriptor, enabled):
        if (
            descriptor == state["start_fd"]
            and enabled is True
            and boundary == "immutable-transition"
            and not state["injected"]
        ):
            inject()
        return real_immutable(descriptor, enabled)

    def tracked_close(descriptor):
        if descriptor == state["start_fd"]:
            state["start_fd"] = None
            state["start_closed"] = True
            real_close(descriptor)
            if boundary == "close" and not state["injected"]:
                inject()
            return None
        return real_close(descriptor)

    def tracked_mark(current, digest, *, expected_raw=None):
        if boundary == "in-memory-mark" and not state["injected"]:
            inject()
        return real_mark(current, digest, expected_raw=expected_raw)

    def tracked_verify(storage):
        if (
            boundary == "final-path-revalidation"
            and stop.package_started
            and not state["injected"]
        ):
            inject()
        return real_verify(storage)

    monkeypatch.setattr(path.os, "open", tracked_open)
    monkeypatch.setattr(path.os, "write", tracked_write)
    monkeypatch.setattr(path.os, "fsync", tracked_fsync)
    monkeypatch.setattr(path.os, "fstat", tracked_fstat)
    monkeypatch.setattr(path.os, "lseek", tracked_lseek)
    monkeypatch.setattr(path.os, "read", tracked_read)
    monkeypatch.setattr(path.os, "close", tracked_close)
    monkeypatch.setattr(path, "_set_user_immutable", tracked_immutable)
    monkeypatch.setattr(path._StopBoundary, "mark_package_started", tracked_mark)
    monkeypatch.setattr(
        path._StorageBinding, "_verify_package_path_identity", tracked_verify
    )

    with pytest.raises(_OriginalPrestartError) as raised:
        runtime.storage.bank_package_start(expected, stop)
    assert raised.value is marker
    assert state["injected"] is True

    post_write = boundary not in {"exclusive-start-open", "first-write"}
    fresh = path._qualification_runtime(synthetic_root, human, intercept=False)
    fresh.storage.prepare_existing()
    reopened = fresh.storage.observe_package_start(expected_raw)
    marker_path = runtime.storage.package_directory / "package-start.json"
    diagnostic = None
    if marker_path.exists():
        observed = marker_path.stat()
        diagnostic = {
            "size": observed.st_size,
            "mode": oct(stat.S_IMODE(observed.st_mode)),
            "raw_equal": marker_path.read_bytes() == expected_raw,
        }
    assert reopened == (
        "VALID_DURABLE_START" if post_write else "ABSENT"
    ), diagnostic
    assert stop.package_started is post_write
    if post_write:
        assert runtime.storage._terminal_claim_held is True
        stop.fail(marker, runtime, None)
        terminal = path._parse_artifact_bytes(
            (runtime.storage.package_directory / "package-terminal.json").read_bytes()
        )
        assert terminal["state"] == "TERMINAL_FAILURE"
        assert terminal["failure_accounting"]["package_delta"] == 1
    else:
        assert runtime.storage._terminal_fd is None
        assert not (
            runtime.storage.package_directory / "package-terminal.json"
        ).exists()
        assert not (
            runtime.storage.package_directory / "package-start.json"
        ).exists()
    assert runtime.observed_effects["checkpoint_opens"] == 0
    assert runtime.observed_effects["numerical_executions"] == 0
    path._StorageBinding.close(fresh.storage)
    _release_owner_without_synthetic_cleanup(runtime)


def test_prestart_exception_is_preserved_and_reservation_is_discarded(
    synthetic_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw, _go_value, human = _go(synthetic_root, "prestart-original-error")
    runtime = path._qualification_runtime(synthetic_root, human, intercept=False)
    original = path._StorageBinding._bank_leaf
    marker = _OriginalPrestartError("original-prestart-sentinel")

    def fail_before_start(storage, leaf, value, **kwargs):
        if leaf == "package-start.json":
            raise marker
        return original(storage, leaf, value, **kwargs)

    monkeypatch.setattr(path._StorageBinding, "_bank_leaf", fail_before_start)
    with pytest.raises(_OriginalPrestartError) as raised:
        path._invoke_public_qualification(raw, runtime, now_unix_ns=_NOW)
    assert raised.value is marker
    package = runtime.storage.package_directory
    assert not (package / "package-start.json").exists()
    assert not (package / "package-terminal.json").exists()
    assert not (package / "failure-accounting.json").exists()
    assert runtime.observed_effects["checkpoint_root_resolutions"] == 0
    assert runtime.observed_effects["checkpoint_opens"] == 0
    assert runtime.observed_effects["numerical_executions"] == 0


def test_reservation_cleanup_close_failure_preserves_original_exception(
    synthetic_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _raw, _go_value, human = _go(
        synthetic_root, "reservation-cleanup-original-exception"
    )
    runtime = path._qualification_runtime(synthetic_root, human, intercept=False)
    runtime.storage.prepare()
    stop = path._StopBoundary(runtime.storage)
    marker = _OriginalPrestartError("reservation-construction-sentinel")
    cleanup_marker = RuntimeError("reservation-cleanup-close-sentinel")
    real_verify = path._StorageBinding._verify_package_path_identity
    real_confirmed_close = path._StorageBinding._close_descriptor_confirmed
    state = {"verifications": 0, "cleanup_close_failed": False}

    def fail_after_reservation_is_durable(storage):
        if storage is runtime.storage:
            state["verifications"] += 1
            if state["verifications"] == 2:
                raise marker
        return real_verify(storage)

    def close_then_report_failure(descriptor):
        real_confirmed_close(descriptor)
        state["cleanup_close_failed"] = True
        raise cleanup_marker

    monkeypatch.setattr(
        path._StorageBinding,
        "_verify_package_path_identity",
        fail_after_reservation_is_durable,
    )
    monkeypatch.setattr(
        path._StorageBinding,
        "_close_descriptor_confirmed",
        staticmethod(close_then_report_failure),
    )

    with pytest.raises(_OriginalPrestartError) as raised:
        runtime.storage._reserve_package_terminal(stop)
    assert raised.value is marker
    assert state == {"verifications": 2, "cleanup_close_failed": True}
    package = runtime.storage.package_directory
    assert not (package / "package-terminal.json").exists()
    assert not (package / "package-start.json").exists()
    runtime.storage.close()


def test_post_durable_start_revalidation_failure_retains_and_terminalizes(
    synthetic_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw, go, human = _go(synthetic_root, "post-durable-revalidation")
    runtime = path._qualification_runtime(synthetic_root, human, intercept=False)
    runtime.storage.prepare()
    expected = path._derive_expected_package_start_receipt(go, runtime)
    stop = path._StopBoundary(runtime.storage)
    original = path._StorageBinding._verify_package_path_identity
    marker = RuntimeError("post-durable-path-revalidation")

    def fail_after_marker(storage):
        if stop.package_started:
            raise marker
        return original(storage)

    monkeypatch.setattr(
        path._StorageBinding, "_verify_package_path_identity", fail_after_marker
    )
    with pytest.raises(RuntimeError) as raised:
        runtime.storage.bank_package_start(expected, stop)
    assert raised.value is marker
    assert stop.package_started is True
    assert runtime.storage._terminal_claim_held is True

    monkeypatch.setattr(
        path._StorageBinding, "_verify_package_path_identity", original
    )
    stop.fail(marker, runtime, None)
    terminal = path._parse_artifact_bytes(
        (runtime.storage.package_directory / "package-terminal.json").read_bytes()
    )
    assert terminal["state"] == "TERMINAL_FAILURE"
    assert terminal["terminal_origin"] == "IN_PROCESS_STOP_BOUNDARY"
    assert terminal["failure_accounting"]["package_delta"] == 1
    _release_owner_without_synthetic_cleanup(runtime)


@pytest.mark.parametrize(
    ("case", "expected_state"),
    (
        ("empty-reservation", "EMPTY_RESERVATION_WITHOUT_START"),
        ("invalid-start", "INVALID_START_WITH_RESERVATION"),
        (
            "valid-start-without-reservation",
            "VALID_START_WITHOUT_VALID_RESERVED_TERMINAL",
        ),
    ),
)
def test_named_reopen_states_are_fail_closed_without_adoption(
    synthetic_root: Path, case: str, expected_state: str
) -> None:
    raw, go, human = _go(synthetic_root, f"named-{case}")
    runtime = path._qualification_runtime(synthetic_root, human, intercept=False)
    runtime.storage.prepare()
    expected = path._derive_expected_package_start_receipt(go, runtime)
    if case == "valid-start-without-reservation":
        stop = path._StopBoundary(runtime.storage)
        runtime.storage.bank_package_start(expected, stop)
        assert runtime.storage._terminal_fd is not None
        path._set_user_immutable(runtime.storage._terminal_fd, False)
        os.unlink("package-terminal.json", dir_fd=runtime.storage._package_fd)
        os.fsync(runtime.storage._package_fd)
    else:
        terminal = os.open(
            "package-terminal.json",
            os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=runtime.storage._package_fd,
        )
        os.fsync(terminal)
        os.close(terminal)
        if case == "invalid-start":
            start = os.open(
                "package-start.json",
                os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                0o600,
                dir_fd=runtime.storage._package_fd,
            )
            os.write(start, b"{}\n")
            os.fsync(start)
            os.close(start)
        os.fsync(runtime.storage._package_fd)
    path._StorageBinding.close(runtime.storage)

    reopened = path._qualification_runtime(synthetic_root, human, intercept=False)
    reopened.storage.prepare_existing()
    before = sorted(os.listdir(reopened.storage._package_fd))
    state = reopened.storage.acquire_interrupted_terminal(
        path._canonical_bytes(expected)
    )
    after = sorted(os.listdir(reopened.storage._package_fd))
    assert state == expected_state
    assert before == after
    assert reopened.storage._terminal_fd is None
    assert reopened.observed_effects["checkpoint_opens"] == 0
    assert reopened.observed_effects["numerical_executions"] == 0
    reopened.storage.close()


def test_missing_package_closeout_creates_nothing(synthetic_root: Path) -> None:
    raw, _go_value, human = _go(synthetic_root, "missing-package")
    before = set(synthetic_root.iterdir())
    result = _closeout_runtime(synthetic_root, raw, human)
    assert result == {
        "result": "NO_DURABLE_PACKAGE_START",
        "terminal_written": False,
        "checkpoint_effects": 0,
        "numerical_effects": 0,
    }
    assert set(synthetic_root.iterdir()) == before


def test_release_authority_mismatch_closeout_is_named_and_write_free(
    synthetic_root: Path,
) -> None:
    raw, _go_value, human = _go(synthetic_root, "release-mismatch")
    value = path._parse_artifact_bytes(raw)
    value["release_authority_sha256"] = "0" * 64
    mismatched = path._canonical_bytes(value)
    runtime = path._qualification_runtime(synthetic_root, human, intercept=False)
    result = path._invoke_public_closeout_qualification(
        mismatched, runtime, now_unix_ns=0
    )
    assert result["result"] == "SOURCE_RELEASE_AUTHORITY_MISMATCH_CLOSEOUT"
    assert result["terminal_written"] is False
    assert result["checkpoint_effects"] == result["numerical_effects"] == 0
    assert list(synthetic_root.iterdir()) == []


def test_live_owner_blocks_restart_closeout_until_kernel_releases_claim(
    synthetic_root: Path,
) -> None:
    raw, _go_value, human = _go(synthetic_root, "live-owner")
    owner = subprocess.Popen(
        [
            sys.executable,
            "-c",
            _CHILD_START_AND_WAIT,
            str(synthetic_root),
            raw.hex(),
        ],
        cwd=Path(path.__file__).resolve().parents[2],
        env=os.environ.copy(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        assert owner.stdout is not None
        assert owner.stdout.readline().strip() == "READY"
        package = synthetic_root / f"minimum-gate-{human}"
        before = {
            item.name: (item.stat().st_ino, item.stat().st_size)
            for item in package.iterdir()
        }
        blocked = _closeout_runtime(synthetic_root, raw, human)
        after = {
            item.name: (item.stat().st_ino, item.stat().st_size)
            for item in package.iterdir()
        }
        assert blocked["result"] == "EXECUTING_OWNER_ACTIVE"
        assert blocked["terminal_written"] is False
        assert blocked["checkpoint_effects"] == blocked["numerical_effects"] == 0
        assert before == after
    finally:
        owner.terminate()
        owner.wait(timeout=20)

    closed = _closeout_runtime(synthetic_root, raw, human)
    assert closed["result"] == "TERMINAL_FAILURE_BANKED"
    assert closed["terminal_written"] is True
    assert closed["primary_delta"] == closed["secondary_delta"] == 0
    repeated = _closeout_runtime(synthetic_root, raw, human)
    assert repeated["result"] == "ALREADY_TERMINAL"
    assert repeated["terminal_written"] is False
    assert repeated["package_terminal_sha256"] == closed[
        "package_terminal_sha256"
    ]


def test_abrupt_subprocess_exit_after_durable_start_is_restart_closeable_once(
    synthetic_root: Path,
) -> None:
    raw, _go_value, human = _go(synthetic_root, "abrupt-start")
    crashed = _run_child(_CHILD_START_AND_CRASH, synthetic_root, raw)
    assert crashed.returncode == 42
    result = _closeout_runtime(synthetic_root, raw, human)
    assert result["result"] == "TERMINAL_FAILURE_BANKED"
    terminal = path._parse_artifact_bytes(
        (
            synthetic_root
            / f"minimum-gate-{human}"
            / "package-terminal.json"
        ).read_bytes()
    )
    assert terminal["terminal_origin"] == "RESTART_CLOSEOUT"
    assert terminal["failure_type"] == "PROCESS_INTERRUPTION_AFTER_PACKAGE_START"
    assert terminal["failure_accounting"]["package_delta"] == 1
    assert terminal["failure_accounting"]["authorization_delta"] == 0


def test_already_terminal_rederives_access_census_from_fixed_receipt_prefix(
    synthetic_root: Path,
) -> None:
    raw, _go_value, runtime, stop, start, _start_raw, _start_sha = (
        _started_package(synthetic_root, "terminal-access-rederivation")
    )
    contract = path._parse_artifact_bytes(
        (path._ROOT / runtime.profile.checkpoint_contract_path).read_bytes()
    )
    bindings = {
        "authorization_id": start["authorization_id"],
        "package_attempt_id": start["package_attempt_id"],
        "checkpoint_identity_contract_sha256": (
            runtime.profile.checkpoint_authority_sha256
        ),
        "checkpoint_set_sha256": runtime.profile.checkpoint_set_sha256,
    }
    writer = identity_producer._AccessPrefixWriter(
        runtime.storage.package_directory / "identity",
        bindings,
        contract,
        write_once=True,
    )
    _bank_first_open_and_hash(writer)
    stop.fail(RuntimeError("terminal-access-rederivation"), runtime, None)
    package = runtime.storage.package_directory
    prefix_before = {
        item.name: item.read_bytes()
        for item in (package / "identity").iterdir()
    }
    _release_owner_without_synthetic_cleanup(runtime)

    def forge_access(accounting):
        access = dict(accounting["checkpoint_access_census"])
        access["checkpoint_shard_opens_lower_bound"] += 1
        access["checkpoint_shard_opens_upper_bound"] += 1
        accounting["checkpoint_access_census"] = access
        accounting["original_checkpoint_opens_lower_bound"] += 1
        accounting["original_checkpoint_opens_upper_bound"] += 1
        return accounting

    _rebind_failure_accounting_in_terminal(package, forge_access)
    prefix_after = {
        item.name: item.read_bytes()
        for item in (package / "identity").iterdir()
    }
    assert prefix_after == prefix_before

    human = str(path._validate_go_non_temporal(
        raw, path._authority_profile(synthetic=True)
    ).get("human_decision_sha256"))
    result = _closeout_runtime(synthetic_root, raw, human)
    assert result["result"] == "VALID_START_WITHOUT_VALID_RESERVED_TERMINAL"
    assert result["terminal_written"] is False
    assert result["checkpoint_effects"] == result["numerical_effects"] == 0


def test_already_terminal_binds_release_report_value_not_only_digest(
    synthetic_root: Path,
) -> None:
    raw, _go_value, runtime, stop, _start, _start_raw, _start_sha = (
        _started_package(synthetic_root, "terminal-release-value")
    )
    release = {
        "attempted_closures": 0,
        "successful_closures": 0,
        "duplicate_closures": 0,
        "unknown_leases": 0,
        "live_leases_after_release": 0,
        "result": "NO_LEASES_ACQUIRED",
    }
    report_sha256 = runtime.storage.bank_failure(
        "emergency-release-report.json",
        path._emergency_release_value("PACKAGE_START", release),
    )
    stop.fail(
        RuntimeError("terminal-release-value"),
        runtime,
        report_sha256,
        release,
    )
    package = runtime.storage.package_directory
    report_before = (package / "emergency-release-report.json").read_bytes()
    _release_owner_without_synthetic_cleanup(runtime)

    def forge_release(accounting):
        outcome = dict(accounting["emergency_release_outcome"])
        outcome["attempted_closures"] = 1
        accounting["emergency_release_outcome"] = outcome
        return accounting

    _rebind_failure_accounting_in_terminal(package, forge_release)
    assert (package / "emergency-release-report.json").read_bytes() == report_before

    human = str(path._validate_go_non_temporal(
        raw, path._authority_profile(synthetic=True)
    ).get("human_decision_sha256"))
    result = _closeout_runtime(synthetic_root, raw, human)
    assert result["result"] == "VALID_START_WITHOUT_VALID_RESERVED_TERMINAL"
    assert result["terminal_written"] is False
    assert result["checkpoint_effects"] == result["numerical_effects"] == 0


def test_identity_failure_descriptor_disposition_reaches_outer_release_evidence(
    synthetic_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw, _go_value, human = _go(
        synthetic_root,
        "identity-descriptor-disposition",
    )
    runtime = path._qualification_runtime(
        synthetic_root,
        human,
        intercept=False,
    )
    marker = IdentityAuthorityError(
        "F017_V12_IDENTITY_DESCRIPTOR_CHANGED",
        "modeled producer descriptor retirement",
        checkpoint_access="RECEIPT_DERIVED",
        descriptor_disposition=IdentityDescriptorDisposition(
            opened=3,
            closed=2,
            close_failures=0,
            retained_leases=1,
        ),
        evidence_failure_type="MODELED_DESCRIPTOR_RETENTION",
    )

    def fail_identity(_provider, _gate, _authority, _storage):
        raise marker

    monkeypatch.setattr(type(runtime.checkpoint_effect), "run", fail_identity)
    runtime.storage.preserve_terminal_for_closeout(path._SYNTHETIC_STORAGE_SEAL)
    with pytest.raises(IdentityAuthorityError) as raised:
        path._invoke_public_qualification(raw, runtime, now_unix_ns=_NOW)
    assert raised.value is marker

    package = runtime.storage.package_directory
    terminal = path._parse_artifact_bytes(
        (package / "package-terminal.json").read_bytes()
    )
    outcome = terminal["failure_accounting"]["emergency_release_outcome"]
    assert terminal["failure_type"] == marker.outcome_id
    assert terminal["failure_wrapper_type"] == "IdentityAuthorityError"
    assert outcome["release_disposition"] == (
        "IDENTITY_PRODUCER_FAILURE_DESCRIPTOR_DISPOSITION"
    )
    assert outcome["attempted_closures"] == 3
    assert outcome["successful_closures"] == 2
    assert outcome["live_leases_after_release"] == 1
    assert outcome["result"] == "FAIL"
    assert outcome["identity_failure"] == {
        "outcome_id": marker.outcome_id,
        "detail": marker.detail,
        "evidence_failure_type": marker.evidence_failure_type,
        "operation_observation": None,
        "access_census": None,
        "descriptor_disposition": marker.descriptor_disposition.evidence,
    }
    report = path._parse_artifact_bytes(
        (package / "emergency-release-report.json").read_bytes()
    )
    assert report == path._emergency_release_value("IDENTITY_TERMINAL", outcome)
    assert report["identity_failure"] == outcome["identity_failure"]
    assert report["live_leases"] == 1
    observer = path._qualification_runtime(
        synthetic_root,
        human,
        intercept=False,
    )
    observer.storage.prepare_existing()
    terminal_raw = observer.storage._read_held_leaf(
        "package-terminal.json",
        maximum_bytes=1_048_576,
    )
    expected_start_raw = path._canonical_bytes(
        path._derive_expected_package_start_receipt(
            path._validate_go_non_temporal(
                raw,
                path._authority_profile(synthetic=True),
            ),
            observer,
        )
    )
    path._validate_existing_package_terminal(
        observer.storage,
        path._parse_artifact_bytes(terminal_raw),
        terminal_raw,
        expected_start_raw,
        runtime=observer,
    )
    observer.storage.close()
    repeated = _closeout_runtime(synthetic_root, raw, human)
    assert repeated["result"] == "ALREADY_TERMINAL"
    assert repeated["terminal_written"] is False


def test_identity_completion_failure_preserves_maximal_durable_access_prefix(
    synthetic_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw, _go_value, human = _go(
        synthetic_root,
        "identity-completion-prefix",
    )
    runtime = path._qualification_runtime(
        synthetic_root,
        human,
        intercept=False,
    )
    captured: dict[str, object] = {}

    def fail_after_completion(_provider, _gate, authority, storage):
        contract = path._parse_artifact_bytes(
            (path._ROOT / runtime.profile.checkpoint_contract_path).read_bytes()
        )
        bindings = {
            "authorization_id": authority.get("authorization_id"),
            "package_attempt_id": authority.get("package_attempt_id"),
            "checkpoint_identity_contract_sha256": (
                runtime.profile.checkpoint_authority_sha256
            ),
            "checkpoint_set_sha256": runtime.profile.checkpoint_set_sha256,
        }
        writer = identity_producer._AccessPrefixWriter(
            storage.package_directory / "identity",
            bindings,
            contract,
            write_once=True,
        )
        _bank_first_open_and_hash(writer)
        access_census = identity_producer._validate_banked_identity_access_prefix(
            storage.package_directory / "identity",
            bindings,
            contract,
        )
        captured["access_census"] = access_census
        raise IdentityAuthorityError(
            "F017_V12_IDENTITY_SHARD_READ_FAILURE",
            "modeled completion-evidence failure",
            checkpoint_access="RECEIPT_DERIVED",
            access_census=access_census,
            descriptor_disposition=IdentityDescriptorDisposition(
                opened=1,
                closed=1,
                close_failures=0,
                retained_leases=0,
            ),
            evidence_failure_type="MODELED_COMPLETION_EVIDENCE_FAILURE",
        )

    monkeypatch.setattr(
        type(runtime.checkpoint_effect),
        "run",
        fail_after_completion,
    )
    runtime.storage.preserve_terminal_for_closeout(path._SYNTHETIC_STORAGE_SEAL)
    with pytest.raises(IdentityAuthorityError):
        path._invoke_public_qualification(raw, runtime, now_unix_ns=_NOW)

    terminal = path._parse_artifact_bytes(
        (runtime.storage.package_directory / "package-terminal.json").read_bytes()
    )
    access = terminal["failure_accounting"]["checkpoint_access_census"]
    expected = captured["access_census"].evidence
    assert {
        key: value
        for key, value in access.items()
        if key != "receipt_validation"
    } == expected
    assert access["receipt_validation"] == "PASS"
    assert access["receipt_count"] == 4
    assert access["checkpoint_shard_opens_lower_bound"] == 1
    assert access["checkpoint_identity_hash_reads_lower_bound"] == 1
    assert access["identity_hash_bytes_lower_bound"] == expected[
        "identity_hash_bytes_lower_bound"
    ]
    repeated = _closeout_runtime(synthetic_root, raw, human)
    assert repeated["result"] == "ALREADY_TERMINAL"


@pytest.mark.parametrize(
    (
        "fault",
        "expected_receipts",
        "expected_receipt_validation",
        "expected_opens",
        "expected_hashes",
    ),
    (
        ("hash-read-error", 4, "PASS", (1, 1), (0, 0)),
        ("access-receipt-write-error", 3, "FAIL", (1, 6), (0, 6)),
        ("access-receipt-fsync-error", 4, "PASS", (1, 1), (1, 1)),
        ("access-receipt-readback-error", 4, "PASS", (1, 1), (1, 1)),
        ("lease-set-construction-error", 24, "PASS", (6, 6), (6, 6)),
    ),
)
def test_identity_runtime_faults_are_terminally_receipt_accounted(
    synthetic_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
    expected_receipts: int,
    expected_receipt_validation: str,
    expected_opens: tuple[int, int],
    expected_hashes: tuple[int, int],
) -> None:
    """Exercise missing physical/read/evidence/lease failures after start.

    The synthetic checkpoint is graph-owned and contains no model payload.
    Each injection is below the public Event 06 call boundary, after the
    durable package start, so the terminal must derive access truth only from
    the predecessor-linked receipt prefix left by the real producer.
    """
    raw, _go_value, human = _go(synthetic_root, "runtime-fault-" + fault)
    runtime = path._qualification_runtime(
        synthetic_root,
        human,
        intercept=False,
    )
    injected = {"count": 0, "primitive_calls": 0}

    if fault == "hash-read-error":
        real_pread = identity_producer.os.pread

        def fail_pread(
            descriptor: int, byte_count: int, offset: int
        ) -> bytes:
            del descriptor, byte_count, offset
            injected["primitive_calls"] += 1
            raise OSError(errno.EIO, "injected identity hash read error")

        def hash_through_failing_read(
            descriptor: int,
            expected_size: int,
            *,
            require_single_link: bool,
        ) -> tuple[str, os.stat_result]:
            del expected_size, require_single_link
            injected["count"] += 1
            monkeypatch.setattr(identity_producer.os, "pread", fail_pread)
            try:
                identity_producer.os.pread(descriptor, 1, 0)
            except OSError as exc:
                raise identity_producer.failure(
                    "F017_V12_IDENTITY_SHARD_READ_FAILURE",
                    "injected hash read error",
                    checkpoint_access="RECEIPT_DERIVED",
                    operation_observation=identity_producer.IdentityOperationObservation(
                        0,
                        0,
                        path._sha(b""),
                        "READ_FAILURE",
                    ),
                ) from exc
            finally:
                monkeypatch.setattr(identity_producer.os, "pread", real_pread)
            raise AssertionError("injected pread unexpectedly returned")

        monkeypatch.setattr(
            identity_producer,
            "_hash_descriptor",
            hash_through_failing_read,
        )
    elif fault.startswith("access-receipt-"):
        real_bank = identity_producer._bank_exclusive_write_once
        primitive_name = {
            "access-receipt-write-error": "write",
            "access-receipt-fsync-error": "fsync",
            "access-receipt-readback-error": "read",
        }[fault]

        def bank_through_failing_primitive(
            target: Path, value: object
        ) -> str:
            if target.name != "access-prefix-04.json":
                return real_bank(target, value)
            injected["count"] += 1
            real_primitive = getattr(write_once_artifact.os, primitive_name)

            def fail_primitive(*args: object, **kwargs: object) -> object:
                del args, kwargs
                injected["primitive_calls"] += 1
                raise OSError(
                    errno.EIO,
                    f"injected access receipt {primitive_name} error",
                )

            setattr(write_once_artifact.os, primitive_name, fail_primitive)
            try:
                return real_bank(target, value)
            finally:
                setattr(write_once_artifact.os, primitive_name, real_primitive)

        monkeypatch.setattr(
            identity_producer,
            "_bank_exclusive_write_once",
            bank_through_failing_primitive,
        )
    else:
        assert fault == "lease-set-construction-error"

        def fail_lease_set(*args: object, **kwargs: object) -> object:
            del args, kwargs
            injected["count"] += 1
            injected["primitive_calls"] += 1
            raise RuntimeError("injected LeaseSet construction error")

        monkeypatch.setattr(identity_producer, "LeaseSet", fail_lease_set)

    runtime.storage.preserve_terminal_for_closeout(path._SYNTHETIC_STORAGE_SEAL)
    with pytest.raises(Exception):
        path._invoke_public_qualification(raw, runtime, now_unix_ns=_NOW)

    assert injected == {"count": 1, "primitive_calls": 1}
    package = runtime.storage.package_directory
    terminal = path._parse_artifact_bytes(
        (package / "package-terminal.json").read_bytes()
    )
    accounting = terminal["failure_accounting"]
    census = accounting["checkpoint_access_census"]
    assert accounting["package_delta"] == 1
    assert accounting["primary_delta"] == 0
    assert accounting["secondary_delta"] == 0
    assert accounting["historical_master_ledger_before"] == 175
    assert accounting["historical_master_ledger_after"] == 175
    assert accounting["real_numerical_executions_observed_in_process"] == 0
    assert census["receipt_count"] == expected_receipts
    assert census["receipt_validation"] == expected_receipt_validation
    assert (
        census["checkpoint_shard_opens_lower_bound"],
        census["checkpoint_shard_opens_upper_bound"],
    ) == expected_opens
    assert (
        census["checkpoint_identity_hash_reads_lower_bound"],
        census["checkpoint_identity_hash_reads_upper_bound"],
    ) == expected_hashes

    provider = runtime.checkpoint_effect
    assert type(provider) is path._SyntheticCheckpointProvider
    assert (
        expected_opens[0]
        <= provider.producer_checkpoint_shard_opens
        <= expected_opens[1]
    )
    assert (
        expected_hashes[0]
        <= provider.producer_checkpoint_identity_hash_reads
        <= expected_hashes[1]
    )
    assert runtime.observed_effects["checkpoint_root_resolutions"] == 0
    assert runtime.observed_effects["checkpoint_opens"] == 0
    assert runtime.observed_effects["numerical_executions"] == 0

    observer = path._qualification_runtime(
        synthetic_root,
        human,
        intercept=False,
    )
    observer.storage.prepare_existing()
    terminal_raw = observer.storage._read_held_leaf(
        "package-terminal.json",
        maximum_bytes=1_048_576,
    )
    expected_start_raw = path._canonical_bytes(
        path._derive_expected_package_start_receipt(
            path._validate_go_non_temporal(
                raw,
                path._authority_profile(synthetic=True),
            ),
            observer,
        )
    )
    path._validate_existing_package_terminal(
        observer.storage,
        path._parse_artifact_bytes(terminal_raw),
        terminal_raw,
        expected_start_raw,
        runtime=observer,
    )
    observer.storage.close()

    repeated = _closeout_runtime(synthetic_root, raw, human)
    assert repeated["result"] == "ALREADY_TERMINAL"
    assert repeated["terminal_written"] is False


def test_durable_prefix_prevents_exception_census_inflation(
    synthetic_root: Path,
) -> None:
    _raw, _go_value, runtime, _stop, start, _start_raw, _start_sha = (
        _started_package(synthetic_root, "exception-census-inflation")
    )
    contract = path._parse_artifact_bytes(
        (path._ROOT / runtime.profile.checkpoint_contract_path).read_bytes()
    )
    bindings = {
        "authorization_id": start["authorization_id"],
        "package_attempt_id": start["package_attempt_id"],
        "checkpoint_identity_contract_sha256": (
            runtime.profile.checkpoint_authority_sha256
        ),
        "checkpoint_set_sha256": runtime.profile.checkpoint_set_sha256,
    }
    writer = identity_producer._AccessPrefixWriter(
        runtime.storage.package_directory / "identity",
        bindings,
        contract,
        write_once=True,
    )
    _bank_first_open_and_hash(writer)
    actual = identity_producer._validate_banked_identity_access_prefix(
        runtime.storage.package_directory / "identity",
        bindings,
        contract,
    )
    inflated = IdentityAccessCensus(
        actual.genesis_sha256,
        actual.head_sha256,
        actual.receipt_count,
        2,
        2,
        0,
        2,
        2,
        0,
        actual.identity_hash_bytes_lower_bound,
        actual.identity_hash_bytes_lower_bound,
        0,
        True,
        None,
        0,
        False,
    )
    error = IdentityAuthorityError(
        "F017_V12_IDENTITY_SHARD_READ_FAILURE",
        "inflated exception census",
        checkpoint_access="RECEIPT_DERIVED",
        access_census=inflated,
    )
    derived = path._derive_access_progress_for_failure(
        runtime.storage,
        runtime,
        error,
    )
    assert derived["receipt_validation"] == "PASS"
    assert derived["checkpoint_shard_opens_lower_bound"] == 1
    assert derived["checkpoint_identity_hash_reads_lower_bound"] == 1
    assert derived["head_sha256"] == actual.head_sha256
    runtime.storage.close()


def test_exception_census_cannot_replace_missing_durable_identity_directory(
    synthetic_root: Path,
) -> None:
    _raw, _go_value, runtime, _stop, _start, _start_raw, _start_sha = (
        _started_package(synthetic_root, "missing-prefix-exception-census")
    )
    carried = IdentityAccessCensus(
        "1" * 64,
        "2" * 64,
        8,
        2,
        2,
        0,
        2,
        2,
        0,
        17,
        17,
        0,
        True,
        None,
        0,
        False,
    )
    error = IdentityAuthorityError(
        "F017_V12_IDENTITY_SHARD_READ_FAILURE",
        "missing durable identity directory",
        checkpoint_access="RECEIPT_DERIVED",
        access_census=carried,
    )
    derived = path._derive_access_progress_for_failure(
        runtime.storage,
        runtime,
        error,
    )
    assert derived["checkpoint_shard_opens_lower_bound"] == 0
    assert derived["checkpoint_shard_opens_upper_bound"] == 6
    assert derived["checkpoint_identity_hash_reads_lower_bound"] == 0
    assert derived["checkpoint_identity_hash_reads_upper_bound"] == 6
    assert derived["identity_hash_bytes_lower_bound"] == 0
    # The frozen synthetic checkpoint contract has zero-byte shards; its
    # durable-authority upper bound is therefore zero, never the carried 17.
    assert derived["identity_hash_bytes_upper_bound"] == 0
    assert derived["head_sha256"] != "2" * 64
    assert derived["exact"] is False
    assert derived["receipt_validation"] == "FAIL"
    assert derived["validation_failure_type"] == "FileNotFoundError"
    assert derived["result"] == "FAIL"
    runtime.storage.close()


def test_twenty_four_concurrent_restart_closeouts_have_one_terminal_winner(
    synthetic_root: Path,
) -> None:
    raw, _go_value, runtime, _stop, _expected, _expected_raw, _start_sha = (
        _started_package(synthetic_root, "twenty-four-closeouts")
    )
    human = str(path._validate_go_non_temporal(
        raw, path._authority_profile(synthetic=True)
    ).get("human_decision_sha256"))
    _release_owner_without_synthetic_cleanup(runtime)

    def contender(_index: int) -> dict[str, object]:
        completed = _run_child(_CHILD_CLOSEOUT, synthetic_root, raw, timeout=90)
        assert completed.returncode == 0, completed.stderr
        return _parse_child_json(completed.stdout)

    with ThreadPoolExecutor(max_workers=24) as pool:
        results = list(pool.map(contender, range(24)))
    winners = [item for item in results if item["result"] == "TERMINAL_FAILURE_BANKED"]
    assert len(winners) == 1
    assert all(
        item["result"]
        in {"TERMINAL_FAILURE_BANKED", "EXECUTING_OWNER_ACTIVE", "ALREADY_TERMINAL"}
        for item in results
    )
    final = _closeout_runtime(synthetic_root, raw, human)
    assert final["result"] == "ALREADY_TERMINAL"
    assert final["package_terminal_sha256"] == winners[0][
        "package_terminal_sha256"
    ]
    assert all(item.get("checkpoint_effects", 0) == 0 for item in results)
    assert all(item.get("numerical_effects", 0) == 0 for item in results)


@pytest.mark.parametrize(
    ("stages", "expected_primary", "expected_secondary", "expected_failed"),
    (
        (("PRIMARY",), 1, 0, "PRIMARY_RESULT_TERMINAL"),
        (("PRIMARY", "SECONDARY"), 1, 1, "SECONDARY_RESULT_TERMINAL"),
    ),
)
def test_restart_closeout_derives_consumer_deltas_from_durable_stage_receipts(
    synthetic_root: Path,
    stages: tuple[str, ...],
    expected_primary: int,
    expected_secondary: int,
    expected_failed: str,
) -> None:
    label = "restart-stage-" + "-".join(stages).lower()
    raw, _go_value, runtime, _stop, expected, _raw, start_sha = (
        _started_package(synthetic_root, label)
    )
    for stage in stages:
        path._bank_stage_receipt(runtime.storage, stage, expected, start_sha)
    # The package key is the human-decision digest, not the typed package ID.
    human = str(path._validate_go_non_temporal(
        raw, path._authority_profile(synthetic=True)
    ).get("human_decision_sha256"))
    _release_owner_without_synthetic_cleanup(runtime)
    result = _closeout_runtime(synthetic_root, raw, human)
    assert result["result"] == "TERMINAL_FAILURE_BANKED"
    assert result["primary_delta"] == expected_primary
    assert result["secondary_delta"] == expected_secondary
    assert result["failed_stage"] == expected_failed


@pytest.mark.parametrize(
    ("stages", "expected_primary", "expected_secondary"),
    (
        (("PRIMARY",), 1, 0),
        (("PRIMARY", "SECONDARY"), 1, 1),
    ),
)
def test_in_process_failure_uses_receipts_banked_before_any_memory_record(
    synthetic_root: Path,
    stages: tuple[str, ...],
    expected_primary: int,
    expected_secondary: int,
) -> None:
    label = "in-process-stage-" + "-".join(stages).lower()
    _raw, _go_value, runtime, stop, expected, _expected_raw, start_sha = (
        _started_package(synthetic_root, label)
    )
    assert stop.receipts == [("PACKAGE_START", start_sha)]
    for stage in stages:
        path._bank_stage_receipt(runtime.storage, stage, expected, start_sha)
    stop.fail(RuntimeError("failure-before-in-memory-record"), runtime, None)
    terminal = path._parse_artifact_bytes(
        (runtime.storage.package_directory / "package-terminal.json").read_bytes()
    )
    accounting = terminal["failure_accounting"]
    assert accounting["primary_delta"] == expected_primary
    assert accounting["secondary_delta"] == expected_secondary
    assert stop.receipts == [("PACKAGE_START", start_sha)]
    runtime.storage.close()


@pytest.mark.parametrize(
    "mutation",
    (
        "stage-authority-sha",
        "schema",
        "stage",
        "authorization-id",
        "package-id",
        "event-id",
        "package-start-sha",
        "result",
        "extra-key",
        "missing-key",
        "secondary-without-primary",
    ),
)
def test_mutated_stage_receipts_are_rejected_not_counted(
    synthetic_root: Path, mutation: str
) -> None:
    raw, _go_value, runtime, _stop, expected, _expected_raw, start_sha = (
        _started_package(synthetic_root, "mutated-stage-" + mutation)
    )
    stage = "SECONDARY" if mutation == "secondary-without-primary" else "PRIMARY"
    path._bank_stage_receipt(runtime.storage, stage, expected, start_sha)
    target = runtime.storage.package_directory / f"{stage.lower()}-start-receipt.json"
    if mutation != "secondary-without-primary":
        field_and_value = {
            "stage-authority-sha": ("stage_authority_sha256", "0" * 64),
            "schema": ("schema", "pulsarmlx.invalid/0"),
            "stage": ("stage", "SECONDARY"),
            "authorization-id": ("authorization_id", "F017-MUTATED-AUTH"),
            "package-id": ("package_attempt_id", "F017-MUTATED-PACKAGE"),
            "event-id": ("stage_event_id", "F017-MUTATED-EVENT"),
            "package-start-sha": ("package_start_sha256", "0" * 64),
            "result": ("result", "FAIL"),
        }
        if mutation == "extra-key":
            _mutate_json_leaf(target, lambda value: {**value, "alias": True})
        elif mutation == "missing-key":
            def remove_stage_authority(value):
                value.pop("stage_authority_sha256")
                return value

            _mutate_json_leaf(target, remove_stage_authority)
        else:
            key, replacement = field_and_value[mutation]
            _mutate_json_leaf(
                target, lambda value: {**value, key: replacement}
            )
    human = str(path._validate_go_non_temporal(
        raw, path._authority_profile(synthetic=True)
    ).get("human_decision_sha256"))
    _release_owner_without_synthetic_cleanup(runtime)
    result = _closeout_runtime(synthetic_root, raw, human)
    assert result["primary_delta"] == 0
    terminal = path._parse_artifact_bytes(
        (runtime.storage.package_directory / "package-terminal.json").read_bytes()
    )
    assert terminal["failure_accounting"]["invalid_durable_receipts"] == [
        f"{stage.lower()}-start-receipt.json"
    ]


@pytest.mark.parametrize(
    "mutation",
    (
        "gap",
        "unknown-leaf",
        "predecessor",
        "sequence",
        "ordinal",
        "shard-name",
        "schema",
        "authorization",
        "package",
        "checkpoint-contract",
        "checkpoint-set",
        "effect-count",
        "result",
        "phase",
        "operation",
        "future",
    ),
)
def test_access_prefix_chain_mutations_fail_closed(
    synthetic_root: Path, mutation: str
) -> None:
    (
        _raw,
        _runtime,
        bindings,
        contract,
        evidence,
        writer,
    ) = _access_fixture(synthetic_root, "prefix-mutation-" + mutation)
    _bank_first_open_and_hash(writer)
    if mutation == "gap":
        target = evidence / "access-prefix-01.json"
        descriptor = os.open(target, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            path._set_user_immutable(descriptor, False)
        finally:
            os.close(descriptor)
        target.unlink()
    elif mutation == "unknown-leaf":
        (evidence / "access-prefix-99.json").write_bytes(b"{}\n")
    else:
        target = evidence / "access-prefix-02.json"
        field_and_value = {
            "predecessor": ("predecessor_sha256", "0" * 64),
            "sequence": ("sequence", 19),
            "ordinal": ("ordinal", 2),
            "shard-name": ("shard_name", "substituted.bin"),
            "schema": ("schema", "pulsarmlx.invalid/0"),
            "authorization": ("authorization_id", "F017-CROSS-PACKAGE"),
            "package": ("package_attempt_id", "F017-CROSS-PACKAGE"),
            "checkpoint-contract": (
                "checkpoint_identity_contract_sha256",
                "0" * 64,
            ),
            "checkpoint-set": ("checkpoint_set_sha256", "0" * 64),
            "effect-count": ("effect_count", 2),
            "result": ("result", "PENDING"),
            "phase": ("phase", "INTENT"),
            "operation": ("operation", "IDENTITY_HASH_READ"),
            "future": ("sequence", 24),
        }[mutation]
        key, replacement = field_and_value
        _mutate_json_leaf(
            target, lambda value: {**value, key: replacement}
        )
    with pytest.raises(ValueError):
        identity_producer.validate_banked_identity_access_prefix(
            evidence, bindings, contract
        )


@pytest.mark.parametrize(
    ("prefix_kind", "expected"),
    (
        (
            "open-intent",
            {
                "opens": (0, 1, 1),
                "hashes": (0, 0, 0),
                "exact": False,
                "operation": "SHARD_OPEN",
            },
        ),
        (
            "open-failure",
            {
                "opens": (0, 0, 0),
                "hashes": (0, 0, 0),
                "exact": True,
                "operation": None,
            },
        ),
        (
            "hash-intent",
            {
                "opens": (1, 1, 0),
                "hashes": (0, 1, 1),
                "exact": False,
                "operation": "IDENTITY_HASH_READ",
            },
        ),
        (
            "hash-mismatch",
            {
                "opens": (1, 1, 0),
                "hashes": (1, 1, 0),
                "exact": True,
                "operation": None,
            },
        ),
    ),
)
def test_access_prefix_bounds_distinguish_confirmed_and_unconfirmed_effects(
    synthetic_root: Path, prefix_kind: str, expected: dict[str, object]
) -> None:
    (
        _raw,
        _runtime,
        bindings,
        contract,
        evidence,
        writer,
    ) = _access_fixture(synthetic_root, "prefix-bounds-" + prefix_kind)
    descriptor_sha = "1" * 64
    writer.bank(
        operation="SHARD_OPEN",
        phase="INTENT",
        effect_count=0,
        observed_bytes=0,
        descriptor_identity_sha256=None,
        observed_sha256=None,
        disposition="SHARD_OPEN_INTENT",
        result="PENDING",
    )
    if prefix_kind != "open-intent":
        if prefix_kind == "open-failure":
            writer.bank(
                operation="SHARD_OPEN",
                phase="COMPLETE",
                effect_count=0,
                observed_bytes=0,
                descriptor_identity_sha256=None,
                observed_sha256=None,
                disposition="SHARD_OPEN_FAILURE",
                result="FAIL",
            )
        else:
            writer.bank(
                operation="SHARD_OPEN",
                phase="COMPLETE",
                effect_count=1,
                observed_bytes=0,
                descriptor_identity_sha256=descriptor_sha,
                observed_sha256=None,
                disposition="SHARD_OPEN_COMPLETE",
                result="PASS",
            )
            writer.bank(
                operation="IDENTITY_HASH_READ",
                phase="INTENT",
                effect_count=0,
                observed_bytes=0,
                descriptor_identity_sha256=descriptor_sha,
                observed_sha256=None,
                disposition="IDENTITY_HASH_READ_INTENT",
                result="PENDING",
            )
            if prefix_kind == "hash-mismatch":
                step = writer.plan[3]
                writer.bank(
                    operation="IDENTITY_HASH_READ",
                    phase="COMPLETE",
                    effect_count=1,
                    observed_bytes=int(step["expected_bytes"]),
                    descriptor_identity_sha256=descriptor_sha,
                    observed_sha256="2" * 64,
                    disposition="IDENTITY_HASH_MISMATCH",
                    result="FAIL",
                )
    census = identity_producer.validate_banked_identity_access_prefix(
        evidence, bindings, contract
    )
    assert (
        census["checkpoint_shard_opens_lower_bound"],
        census["checkpoint_shard_opens_upper_bound"],
        census["checkpoint_shard_opens_unconfirmed"],
    ) == expected["opens"]
    assert (
        census["checkpoint_identity_hash_reads_lower_bound"],
        census["checkpoint_identity_hash_reads_upper_bound"],
        census["checkpoint_identity_hash_reads_unconfirmed"],
    ) == expected["hashes"]
    assert census["exact"] is expected["exact"]
    assert census["unresolved_operation"] == expected["operation"]


@pytest.mark.parametrize("receipt_count", range(25))
def test_every_access_prefix_crash_window_bounds_physical_effects(
    synthetic_root: Path, receipt_count: int
) -> None:
    (
        _raw,
        _runtime,
        bindings,
        contract,
        evidence,
        writer,
    ) = _access_fixture(synthetic_root, f"all-prefix-windows-{receipt_count:02d}")
    descriptor_by_ordinal: dict[int, str] = {}
    for expected in writer.plan[:receipt_count]:
        operation = str(expected["operation"])
        phase = str(expected["phase"])
        ordinal = int(expected["ordinal"])
        descriptor_sha = descriptor_by_ordinal.get(ordinal)
        if operation == "SHARD_OPEN" and phase == "INTENT":
            writer.bank(
                operation=operation,
                phase=phase,
                effect_count=0,
                observed_bytes=0,
                descriptor_identity_sha256=None,
                observed_sha256=None,
                disposition="SHARD_OPEN_INTENT",
                result="PENDING",
            )
        elif operation == "SHARD_OPEN":
            descriptor_sha = path._sha(
                f"sequence42-descriptor-{ordinal}".encode("ascii")
            )
            descriptor_by_ordinal[ordinal] = descriptor_sha
            writer.bank(
                operation=operation,
                phase=phase,
                effect_count=1,
                observed_bytes=0,
                descriptor_identity_sha256=descriptor_sha,
                observed_sha256=None,
                disposition="SHARD_OPEN_COMPLETE",
                result="PASS",
            )
        elif phase == "INTENT":
            assert descriptor_sha is not None
            writer.bank(
                operation=operation,
                phase=phase,
                effect_count=0,
                observed_bytes=0,
                descriptor_identity_sha256=descriptor_sha,
                observed_sha256=None,
                disposition="IDENTITY_HASH_READ_INTENT",
                result="PENDING",
            )
        else:
            assert descriptor_sha is not None
            writer.bank(
                operation=operation,
                phase=phase,
                effect_count=1,
                observed_bytes=int(expected["expected_bytes"]),
                descriptor_identity_sha256=descriptor_sha,
                observed_sha256=expected["expected_sha256"],
                disposition="IDENTITY_HASH_COMPLETE",
                result="PASS",
            )

    census = identity_producer.validate_banked_identity_access_prefix(
        evidence, bindings, contract
    )
    completed_groups, remainder = divmod(receipt_count, 4)
    opens_lower = completed_groups + int(remainder >= 2)
    opens_upper = opens_lower + int(remainder == 1)
    hashes_lower = completed_groups
    hashes_upper = hashes_lower + int(remainder == 3)
    assert census["receipt_count"] == receipt_count
    assert (
        census["checkpoint_shard_opens_lower_bound"],
        census["checkpoint_shard_opens_upper_bound"],
    ) == (opens_lower, opens_upper)
    assert (
        census["checkpoint_identity_hash_reads_lower_bound"],
        census["checkpoint_identity_hash_reads_upper_bound"],
    ) == (hashes_lower, hashes_upper)
    assert opens_lower <= opens_upper
    assert hashes_lower <= hashes_upper
    # At an intent boundary, both possible crash-time physical observations
    # (operation not yet called versus operation returned) are contained.
    if remainder == 1:
        assert {opens_lower, opens_lower + 1} <= set(
            range(
                census["checkpoint_shard_opens_lower_bound"],
                census["checkpoint_shard_opens_upper_bound"] + 1,
            )
        )
    if remainder == 3:
        assert {hashes_lower, hashes_lower + 1} <= set(
            range(
                census["checkpoint_identity_hash_reads_lower_bound"],
                census["checkpoint_identity_hash_reads_upper_bound"] + 1,
            )
        )
    assert census["exact"] is (remainder not in {1, 3})
    assert census["prefix_complete"] is (receipt_count == 24)


def test_complete_synthetic_public_path_projects_exact_six_by_six_access(
    synthetic_root: Path,
) -> None:
    raw, _go_value, human = _go(synthetic_root, "complete-six-by-six")
    runtime = path._qualification_runtime(synthetic_root, human, intercept=False)
    result = path._invoke_public_qualification(raw, runtime, now_unix_ns=_NOW)
    assert result["result"] == "PASS"
    accounting = path._parse_artifact_bytes(
        (
            runtime.storage.package_directory
            / "receipt-derived-accounting.json"
        ).read_bytes()
    )
    assert accounting["package_delta"] == 1
    assert accounting["primary_delta"] == 1
    assert accounting["secondary_delta"] == 1
    package = runtime.storage.package_directory
    access = path._parse_artifact_bytes(
        (package / "identity" / "access-journal.json").read_bytes()
    )["access_census"]
    assert access["checkpoint_shard_opens_lower_bound"] == 6
    assert access["checkpoint_shard_opens_upper_bound"] == 6
    assert access["checkpoint_identity_hash_reads_lower_bound"] == 6
    assert access["checkpoint_identity_hash_reads_upper_bound"] == 6
    assert access["exact"] is True
    assert set((package / "identity").iterdir()) == {
        package / "identity" / leaf
        for leaf in path._SUCCESS_PHYSICAL_IDENTITY_FILES
    }
    assert len(path._SUCCESS_PHYSICAL_IDENTITY_FILES) == 31
    assert runtime.observed_effects["checkpoint_root_resolutions"] == 0
    assert runtime.observed_effects["checkpoint_opens"] == 0
    assert runtime.observed_effects["numerical_executions"] == 0


def test_twenty_fresh_process_roots_are_deterministic_for_identical_public_input(
    synthetic_root: Path,
) -> None:
    raw, _go_value, _human = _go(
        synthetic_root, "identical-current-public-path"
    )
    records: list[dict[str, object]] = []
    roots: list[Path] = []
    for index in range(20):
        root = synthetic_root / f"fresh-public-process-{index:02d}"
        assert not root.exists()
        completed = _run_child(
            _CHILD_PUBLIC_DETERMINISM,
            root,
            raw,
            timeout=180,
        )
        assert completed.returncode == 0, completed.stderr
        roots.append(root.resolve(strict=True))
        records.append(_parse_child_json(completed.stdout))

    assert len(set(roots)) == 20
    assert len({record["process_id"] for record in records}) == 20
    assert {record["collapsed_go_sha256"] for record in records} == {
        path._sha(raw)
    }
    assert {record["result"] for record in records} == {"PASS"}
    assert {record["required_gate_count"] for record in records} == {17}
    assert {record["identity_leaf_count"] for record in records} == {31}
    assert {record["access_receipt_count"] for record in records} == {24}
    assert {
        record["synthetic_checkpoint_shard_opens"] for record in records
    } == {6}
    assert {
        record["synthetic_checkpoint_identity_hash_reads"]
        for record in records
    } == {6}
    assert {tuple(record["public_exports"]) for record in records} == {
        (
            "execute_event06_minimum_gate_path",
            "closeout_interrupted_event06_minimum_gate_path",
        )
    }
    assert all(
        record["protected_effects"]
        == {
            "original_checkpoint_root_resolutions": 0,
            "original_checkpoint_opens": 0,
            "real_numerical_executions": 0,
        }
        for record in records
    )

    expected_exclusions = (
        "installed_authority.checkpoint_root",
        "package-start.json.package_start_gate_sha256",
        "*-start-receipt.json.package_start_sha256",
        "*-start-receipt.json.stage_authority_sha256",
        "identity/access-prefix-*.json.predecessor_sha256",
        "identity/access-prefix-*.json.descriptor_identity_sha256",
        "identity/access-census.{genesis_sha256,head_sha256}",
        "identity/lease-manifest.json.descriptors",
        "identity/base-leaf transitive SHA-256 bindings",
        "receipt-derived-accounting.json.consumed_package_start_gate_sha256",
        "receipt-derived-accounting.json.receipt_bindings",
        "receipt-derived-accounting.json.receipt_root_sha256",
        "public-result terminal/receipt/accounting SHA-256 bindings",
    )
    assert {
        tuple(record["normalization_excludes"]) for record in records
    } == {expected_exclusions}
    assert len({record["normalized_identity_sha256"] for record in records}) == 1

    component_names = {
        "collapsed_go",
        "public_contract",
        "package_authority",
        "stage_authority",
        "identity_evidence",
        "receipt_derived_accounting",
        "comparison",
    }
    assert all(set(record["component_sha256s"]) == component_names for record in records)
    assert all(
        len({record["component_sha256s"][name] for record in records}) == 1
        for name in component_names
    )


_CHILD_PACKAGE_START_HARD_CRASH = r"""
from pathlib import Path
import os
import sys

import f017_event06_minimum_gate_path_v1 as path


root = Path(sys.argv[1])
raw = bytes.fromhex(sys.argv[2])
boundary = sys.argv[3]
hard_exit = os._exit
profile = path._authority_profile(synthetic=True)
go = path._validate_go_non_temporal(raw, profile)
runtime = path._qualification_runtime(
    root,
    str(go.get("human_decision_sha256")),
    intercept=False,
)
runtime.storage.prepare()
expected = path._derive_expected_package_start_receipt(go, runtime)
expected_raw = path._canonical_bytes(expected)
stop = path._StopBoundary(runtime.storage)
state = {
    "start_fd": None,
    "start_fsyncs": 0,
    "start_closed": False,
    "written": 0,
    "read_back": 0,
    "marked": False,
}

real_open = path.os.open
real_write = path.os.write
real_fsync = path.os.fsync
real_read = path.os.read
real_close = path.os.close
real_immutable = path._set_user_immutable
real_mark = path._StopBoundary.mark_package_started
real_verify = path._StorageBinding._verify_package_path_identity


def crash():
    hard_exit(86)


def tracked_open(target, flags, mode=0o777, *, dir_fd=None):
    descriptor = real_open(target, flags, mode, dir_fd=dir_fd)
    if target == "package-start.json" and flags & os.O_EXCL:
        state["start_fd"] = descriptor
        if boundary == "post-create":
            crash()
    return descriptor


def tracked_write(descriptor, value):
    if descriptor == state["start_fd"] and boundary == "partial-write":
        prefix_length = max(1, len(value) // 2)
        real_write(descriptor, value[:prefix_length])
        crash()
    count = real_write(descriptor, value)
    if descriptor == state["start_fd"]:
        state["written"] += count
        if boundary == "post-write" and state["written"] == len(expected_raw):
            crash()
    return count


def tracked_fsync(descriptor):
    result = real_fsync(descriptor)
    if descriptor == state["start_fd"]:
        state["start_fsyncs"] += 1
        if boundary == "post-file-fsync" and state["start_fsyncs"] == 1:
            crash()
        if boundary == "post-seal-fsync" and state["start_fsyncs"] == 2:
            crash()
    if (
        descriptor == runtime.storage._package_fd
        and state["start_closed"]
        and boundary == "post-directory-fsync"
    ):
        crash()
    return result


def tracked_read(descriptor, count):
    chunk = real_read(descriptor, count)
    if descriptor == state["start_fd"] and chunk:
        state["read_back"] += len(chunk)
        if boundary == "post-readback" and state["read_back"] == len(expected_raw):
            crash()
    return chunk


def tracked_immutable(descriptor, enabled):
    result = real_immutable(descriptor, enabled)
    if (
        descriptor == state["start_fd"]
        and enabled is True
        and boundary == "post-immutability"
    ):
        crash()
    return result


def tracked_close(descriptor):
    if descriptor == state["start_fd"]:
        state["start_fd"] = None
        state["start_closed"] = True
        result = real_close(descriptor)
        if boundary == "post-close":
            crash()
        return result
    return real_close(descriptor)


def tracked_mark(current, digest, *, expected_raw=None):
    result = real_mark(current, digest, expected_raw=expected_raw)
    state["marked"] = True
    if boundary == "post-mark":
        crash()
    return result


def tracked_verify(storage):
    result = real_verify(storage)
    if boundary == "post-final-revalidation" and state["marked"]:
        crash()
    return result


path.os.open = tracked_open
path.os.write = tracked_write
path.os.fsync = tracked_fsync
path.os.read = tracked_read
path.os.close = tracked_close
path._set_user_immutable = tracked_immutable
path._StopBoundary.mark_package_started = tracked_mark
path._StorageBinding._verify_package_path_identity = tracked_verify

runtime.storage.bank_package_start(expected, stop)
hard_exit(87)
"""


@pytest.mark.parametrize(
    ("boundary", "expected_start_state", "closeout_writes_terminal"),
    (
        ("post-create", "INVALID_START_WITH_RESERVATION", False),
        ("partial-write", "INVALID_START_WITH_RESERVATION", False),
        ("post-write", "VALID_DURABLE_START", True),
        ("post-file-fsync", "VALID_DURABLE_START", True),
        ("post-readback", "VALID_DURABLE_START", True),
        ("post-immutability", "VALID_DURABLE_START", True),
        ("post-seal-fsync", "VALID_DURABLE_START", True),
        ("post-close", "VALID_DURABLE_START", True),
        ("post-directory-fsync", "VALID_DURABLE_START", True),
        ("post-mark", "VALID_DURABLE_START", True),
        ("post-final-revalidation", "VALID_DURABLE_START", True),
    ),
)
def test_hard_process_exit_at_package_start_durability_seams_is_closeable(
    synthetic_root: Path,
    boundary: str,
    expected_start_state: str,
    closeout_writes_terminal: bool,
) -> None:
    raw, go, human = _go(synthetic_root, "hard-package-start-" + boundary)
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            _CHILD_PACKAGE_START_HARD_CRASH,
            str(synthetic_root),
            raw.hex(),
            boundary,
        ],
        cwd=Path(path.__file__).resolve().parents[2],
        env=os.environ.copy(),
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 86, {
        "boundary": boundary,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }

    package = synthetic_root / f"minimum-gate-{human}"
    assert {item.name for item in package.iterdir()} == {
        "package-start.json",
        "package-terminal.json",
    }
    expected_raw = path._canonical_bytes(
        path._derive_expected_package_start_receipt(
            go,
            path._qualification_runtime(synthetic_root, human, intercept=False),
        )
    )
    fresh_observer = path._qualification_runtime(
        synthetic_root, human, intercept=False
    )
    fresh_observer.storage.prepare_existing()
    assert fresh_observer.storage.observe_package_start(expected_raw) == (
        expected_start_state
    )
    fresh_observer.storage.close()

    before_closeout = {
        item.name: (
            item.stat().st_ino,
            item.stat().st_size,
            stat.S_IMODE(item.stat().st_mode),
        )
        for item in package.iterdir()
    }
    first_runtime = path._qualification_runtime(
        synthetic_root, human, intercept=False
    )
    first = path._invoke_public_closeout_qualification(
        raw, first_runtime, now_unix_ns=0
    )
    assert first["checkpoint_effects"] == first["numerical_effects"] == 0
    assert first_runtime.observed_effects["checkpoint_root_resolutions"] == 0
    assert first_runtime.observed_effects["checkpoint_opens"] == 0
    assert first_runtime.observed_effects["numerical_executions"] == 0
    assert first_runtime.checkpoint_effect.physical_identity_producer_calls == 0
    assert first_runtime.checkpoint_effect.producer_checkpoint_binding_checks == 0
    assert first_runtime.checkpoint_effect.producer_checkpoint_shard_opens == 0
    assert (
        first_runtime.checkpoint_effect.producer_checkpoint_identity_hash_reads
        == 0
    )
    assert all(
        count == 0
        for count in first_runtime.numerical_effect.executions.values()
    )

    if closeout_writes_terminal:
        assert first["result"] == "TERMINAL_FAILURE_BANKED"
        assert first["terminal_written"] is True
        assert first["failed_stage"] == "PACKAGE_START"
        assert first["primary_delta"] == first["secondary_delta"] == 0
        terminal = path._parse_artifact_bytes(
            (package / "package-terminal.json").read_bytes()
        )
        assert terminal["state"] == "TERMINAL_FAILURE"
        assert terminal["terminal_origin"] == "RESTART_CLOSEOUT"
        assert (
            terminal["failure_type"]
            == "PROCESS_INTERRUPTION_AFTER_PACKAGE_START"
        )
        accounting = terminal["failure_accounting"]
        assert accounting["package_delta"] == 1
        assert accounting["authorization_delta"] == 0
        assert accounting["primary_delta"] == 0
        assert accounting["secondary_delta"] == 0
        access = accounting["checkpoint_access_census"]
        assert access["receipt_count"] == 0
        assert access["checkpoint_shard_opens_lower_bound"] == 0
        assert access["checkpoint_shard_opens_upper_bound"] <= 6
        assert access["checkpoint_identity_hash_reads_lower_bound"] == 0
        assert access["checkpoint_identity_hash_reads_upper_bound"] <= 6
        assert accounting["original_checkpoint_opens_lower_bound"] == 0
        assert accounting["original_checkpoint_opens_upper_bound"] <= 6
        assert (
            accounting["original_checkpoint_identity_hash_reads_lower_bound"]
            == 0
        )
        assert (
            accounting["original_checkpoint_identity_hash_reads_upper_bound"]
            <= 6
        )
        assert {item.name for item in package.iterdir()} == {
            "failure-accounting.json",
            "package-start.json",
            "package-terminal.json",
        }
    else:
        assert first["result"] == expected_start_state
        assert first["terminal_written"] is False
        assert before_closeout == {
            item.name: (
                item.stat().st_ino,
                item.stat().st_size,
                stat.S_IMODE(item.stat().st_mode),
            )
            for item in package.iterdir()
        }

    second_runtime = path._qualification_runtime(
        synthetic_root, human, intercept=False
    )
    second = path._invoke_public_closeout_qualification(
        raw, second_runtime, now_unix_ns=0
    )
    assert second["checkpoint_effects"] == second["numerical_effects"] == 0
    assert second_runtime.observed_effects["checkpoint_root_resolutions"] == 0
    assert second_runtime.observed_effects["checkpoint_opens"] == 0
    assert second_runtime.observed_effects["numerical_executions"] == 0
    if closeout_writes_terminal:
        assert second["result"] == "ALREADY_TERMINAL"
        assert second["terminal_written"] is False
        assert second["package_terminal_sha256"] == first[
            "package_terminal_sha256"
        ]
    else:
        assert second["result"] == expected_start_state
        assert second["terminal_written"] is False
        assert before_closeout == {
            item.name: (
                item.stat().st_ino,
                item.stat().st_size,
                stat.S_IMODE(item.stat().st_mode),
            )
            for item in package.iterdir()
        }

    assert path.__all__ == (
        "execute_event06_minimum_gate_path",
        "closeout_interrupted_event06_minimum_gate_path",
    )


_CHILD_IDENTITY_ACCESS_HARD_CRASH = r"""
from pathlib import Path
import os
import sys

import f017_checkpoint_identity_producer_v12 as identity_producer
import f017_event06_minimum_gate_path_v1 as path


root = Path(sys.argv[1])
raw = bytes.fromhex(sys.argv[2])
target_ordinal = int(sys.argv[3])
target_operation = sys.argv[4]
crash_point = sys.argv[5]
hard_exit = os._exit
profile = path._authority_profile(synthetic=True)
go = path._validate_go_bytes(raw, profile, now_unix_ns=42_000_000_000)
human = str(go.get("human_decision_sha256"))
runtime = path._qualification_runtime(root, human, intercept=False)
target_shard = next(
    item for item in profile.shards if item["ordinal"] == target_ordinal
)
target_name = str(target_shard["filename"])
expected_checkpoint_root = (
    runtime.storage.package_directory.parent / runtime.synthetic_checkpoint_leaf
)
state = {
    "target_descriptor": None,
    "open_intent_banked": False,
    "hash_intent_banked": False,
}

real_bank = identity_producer._AccessPrefixWriter.bank
real_open = identity_producer.os.open
real_hash_descriptor = identity_producer._hash_descriptor


def crash():
    hard_exit(88)


def is_bound_synthetic_root(descriptor):
    bound = identity_producer._QUALIFICATION_ROOT_DESCRIPTOR.get()
    if bound is None or descriptor is None or runtime.scope != "SYNTHETIC":
        return False
    try:
        candidate = os.fstat(descriptor)
        authority = os.fstat(bound)
    except OSError:
        return False
    return (candidate.st_dev, candidate.st_ino) == (
        authority.st_dev,
        authority.st_ino,
    )


def tracked_bank(writer, *args, **kwargs):
    expected = writer.plan[writer.receipt_count]
    result = real_bank(writer, *args, **kwargs)
    is_target_shard = (
        writer.directory == Path("identity")
        and writer.authority.get("authority_scope") == "SYNTHETIC"
        and writer.authority.get("checkpoint_root")
        == str(expected_checkpoint_root)
        and int(expected["ordinal"]) == target_ordinal
        and str(expected["shard_name"]) == target_name
    )
    if not is_target_shard:
        return result
    phase = str(expected["phase"])
    operation = str(expected["operation"])
    if phase == "INTENT":
        if operation == "SHARD_OPEN":
            state["open_intent_banked"] = True
        else:
            state["hash_intent_banked"] = True
        if operation == target_operation and crash_point == "AFTER_INTENT":
            crash()
    elif (
        operation == target_operation
        and phase == "COMPLETE"
        and crash_point == "AFTER_COMPLETION"
    ):
        crash()
    return result


def tracked_open(candidate, flags, mode=0o777, *, dir_fd=None):
    descriptor = real_open(candidate, flags, mode, dir_fd=dir_fd)
    is_target = (
        type(candidate) is str
        and candidate == target_name
        and is_bound_synthetic_root(dir_fd)
        and state["open_intent_banked"]
    )
    if is_target:
        state["target_descriptor"] = descriptor
        if (
            target_operation == "SHARD_OPEN"
            and crash_point == "AFTER_PHYSICAL_OPERATION"
        ):
            crash()
    return descriptor


def tracked_hash_descriptor(
    descriptor,
    expected_size,
    *,
    require_single_link,
):
    result = real_hash_descriptor(
        descriptor,
        expected_size,
        require_single_link=require_single_link,
    )
    if (
        target_operation == "IDENTITY_HASH_READ"
        and crash_point == "AFTER_PHYSICAL_OPERATION"
        and descriptor == state["target_descriptor"]
        and state["hash_intent_banked"]
        and identity_producer._QUALIFICATION_ROOT_DESCRIPTOR.get() is not None
    ):
        crash()
    return result


identity_producer._AccessPrefixWriter.bank = tracked_bank
identity_producer.os.open = tracked_open
identity_producer._hash_descriptor = tracked_hash_descriptor

path._invoke_public_qualification(
    raw,
    runtime,
    now_unix_ns=42_000_000_000,
)
hard_exit(89)
"""


@pytest.mark.parametrize("ordinal", range(1, 7))
@pytest.mark.parametrize(
    "operation", ("SHARD_OPEN", "IDENTITY_HASH_READ")
)
@pytest.mark.parametrize(
    "crash_point",
    ("AFTER_INTENT", "AFTER_PHYSICAL_OPERATION", "AFTER_COMPLETION"),
)
def test_hard_process_exit_at_every_identity_access_window_preserves_prefix(
    synthetic_root: Path,
    ordinal: int,
    operation: str,
    crash_point: str,
) -> None:
    label = (
        f"hard-access-{ordinal}-{operation.lower()}-{crash_point.lower()}"
    )
    raw, _go_value, human = _go(synthetic_root, label)
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            _CHILD_IDENTITY_ACCESS_HARD_CRASH,
            str(synthetic_root),
            raw.hex(),
            str(ordinal),
            operation,
            crash_point,
        ],
        cwd=Path(path.__file__).resolve().parents[2],
        env=os.environ.copy(),
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 88, {
        "ordinal": ordinal,
        "operation": operation,
        "crash_point": crash_point,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }

    package = synthetic_root / f"minimum-gate-{human}"
    identity = package / "identity"
    base_receipt_count = (ordinal - 1) * 4
    step_offset = {
        ("SHARD_OPEN", "AFTER_INTENT"): 1,
        ("SHARD_OPEN", "AFTER_PHYSICAL_OPERATION"): 1,
        ("SHARD_OPEN", "AFTER_COMPLETION"): 2,
        ("IDENTITY_HASH_READ", "AFTER_INTENT"): 3,
        ("IDENTITY_HASH_READ", "AFTER_PHYSICAL_OPERATION"): 3,
        ("IDENTITY_HASH_READ", "AFTER_COMPLETION"): 4,
    }[(operation, crash_point)]
    receipt_count = base_receipt_count + step_offset
    expected_names = {
        f"access-prefix-{sequence:02d}.json"
        for sequence in range(1, receipt_count + 1)
    }
    assert {item.name for item in identity.iterdir()} == expected_names
    prefix_before = {
        name: (identity / name).read_bytes() for name in sorted(expected_names)
    }

    profile = path._authority_profile(synthetic=True)
    contract = path._parse_artifact_bytes(
        (path._ROOT / profile.checkpoint_contract_path).read_bytes()
    )
    package_start = path._parse_artifact_bytes(
        (package / "package-start.json").read_bytes()
    )
    bindings = {
        "authorization_id": package_start["authorization_id"],
        "package_attempt_id": package_start["package_attempt_id"],
        "checkpoint_identity_contract_sha256": (
            profile.checkpoint_authority_sha256
        ),
        "checkpoint_set_sha256": profile.checkpoint_set_sha256,
    }
    census = identity_producer.validate_banked_identity_access_prefix(
        identity, bindings, contract
    )
    assert census["receipt_count"] == receipt_count

    physical_open_count = ordinal - 1
    physical_hash_count = ordinal - 1
    if operation == "SHARD_OPEN":
        physical_open_count += int(crash_point != "AFTER_INTENT")
    else:
        physical_open_count += 1
        physical_hash_count += int(crash_point != "AFTER_INTENT")
    assert (
        census["checkpoint_shard_opens_lower_bound"]
        <= physical_open_count
        <= census["checkpoint_shard_opens_upper_bound"]
    )
    assert (
        census["checkpoint_identity_hash_reads_lower_bound"]
        <= physical_hash_count
        <= census["checkpoint_identity_hash_reads_upper_bound"]
    )
    assert census["exact"] is (crash_point == "AFTER_COMPLETION")
    assert census["unresolved_operation"] == (
        None if crash_point == "AFTER_COMPLETION" else operation
    )
    assert census["unresolved_ordinal"] == (
        0 if crash_point == "AFTER_COMPLETION" else ordinal
    )
    assert census["prefix_complete"] is (
        ordinal == 6
        and operation == "IDENTITY_HASH_READ"
        and crash_point == "AFTER_COMPLETION"
    )

    closeout_runtime = path._qualification_runtime(
        synthetic_root, human, intercept=False
    )
    first = path._invoke_public_closeout_qualification(
        raw, closeout_runtime, now_unix_ns=0
    )
    assert first["result"] == "TERMINAL_FAILURE_BANKED"
    assert first["terminal_written"] is True
    assert first["failed_stage"] == "IDENTITY_TERMINAL"
    assert first["primary_delta"] == first["secondary_delta"] == 0
    assert first["checkpoint_effects"] == first["numerical_effects"] == 0
    assert closeout_runtime.observed_effects["checkpoint_root_resolutions"] == 0
    assert closeout_runtime.observed_effects["checkpoint_opens"] == 0
    assert closeout_runtime.observed_effects["numerical_executions"] == 0
    assert closeout_runtime.checkpoint_effect.physical_identity_producer_calls == 0
    assert closeout_runtime.checkpoint_effect.producer_checkpoint_binding_checks == 0
    assert closeout_runtime.checkpoint_effect.producer_checkpoint_shard_opens == 0
    assert closeout_runtime.checkpoint_effect.producer_checkpoint_hash_attempts == 0
    assert (
        closeout_runtime.checkpoint_effect.producer_checkpoint_identity_hash_reads
        == 0
    )
    assert all(
        count == 0
        for count in closeout_runtime.numerical_effect.executions.values()
    )
    assert {
        name: (identity / name).read_bytes() for name in sorted(expected_names)
    } == prefix_before
    assert {item.name for item in identity.iterdir()} == expected_names

    terminal = path._parse_artifact_bytes(
        (package / "package-terminal.json").read_bytes()
    )
    assert terminal["terminal_origin"] == "RESTART_CLOSEOUT"
    assert terminal["failure_type"] == "PROCESS_INTERRUPTION_AFTER_PACKAGE_START"
    accounting = terminal["failure_accounting"]
    assert accounting["package_delta"] == 1
    assert accounting["primary_delta"] == 0
    assert accounting["secondary_delta"] == 0
    expected_accounting_census = dict(census)
    expected_accounting_census["receipt_validation"] = "PASS"
    assert accounting["checkpoint_access_census"] == expected_accounting_census
    assert accounting["original_checkpoint_opens_lower_bound"] == census[
        "checkpoint_shard_opens_lower_bound"
    ]
    assert accounting["original_checkpoint_opens_upper_bound"] == census[
        "checkpoint_shard_opens_upper_bound"
    ]
    assert (
        accounting["original_checkpoint_identity_hash_reads_lower_bound"]
        == census["checkpoint_identity_hash_reads_lower_bound"]
    )
    assert (
        accounting["original_checkpoint_identity_hash_reads_upper_bound"]
        == census["checkpoint_identity_hash_reads_upper_bound"]
    )

    repeated_runtime = path._qualification_runtime(
        synthetic_root, human, intercept=False
    )
    repeated = path._invoke_public_closeout_qualification(
        raw, repeated_runtime, now_unix_ns=0
    )
    assert repeated["result"] == "ALREADY_TERMINAL"
    assert repeated["terminal_written"] is False
    assert repeated["package_terminal_sha256"] == first[
        "package_terminal_sha256"
    ]
    assert repeated["checkpoint_effects"] == repeated["numerical_effects"] == 0
    assert repeated_runtime.observed_effects["checkpoint_root_resolutions"] == 0
    assert repeated_runtime.observed_effects["checkpoint_opens"] == 0
    assert repeated_runtime.observed_effects["numerical_executions"] == 0
    assert {
        name: (identity / name).read_bytes() for name in sorted(expected_names)
    } == prefix_before
    assert {item.name for item in identity.iterdir()} == expected_names


_CHILD_TERMINAL_POST_RENAME_HARD_CRASH = r"""
from pathlib import Path
import os
import sys

import f017_event06_minimum_gate_path_v1 as path


root = Path(sys.argv[1])
raw = bytes.fromhex(sys.argv[2])
profile = path._authority_profile(synthetic=True)
go = path._validate_go_non_temporal(raw, profile)
human = str(go.get("human_decision_sha256"))
runtime = path._qualification_runtime(root, human, intercept=False)
package = runtime.storage.package_directory
stage_prefix = f".{package.name}.terminal-stage-"
hard_exit = os._exit
real_rename = path.os.rename


def tracked_rename(
    source,
    target,
    *,
    src_dir_fd=None,
    dst_dir_fd=None,
):
    result = real_rename(
        source,
        target,
        src_dir_fd=src_dir_fd,
        dst_dir_fd=dst_dir_fd,
    )
    if (
        type(source) is str
        and source.startswith(stage_prefix)
        and target == "package-terminal.json"
        and dst_dir_fd == runtime.storage._package_fd
        and src_dir_fd is not None
    ):
        source_parent = os.fstat(src_dir_fd)
        canonical_parent = os.stat(package.parent, follow_symlinks=False)
        if (source_parent.st_dev, source_parent.st_ino) == (
            canonical_parent.st_dev,
            canonical_parent.st_ino,
        ):
            hard_exit(90)
    return result


path.os.rename = tracked_rename
path._invoke_public_closeout_qualification(raw, runtime, now_unix_ns=0)
hard_exit(91)
"""


def test_hard_exit_after_atomic_terminal_rename_is_resealed_without_rewrite(
    synthetic_root: Path,
) -> None:
    raw, _go_value, human = _go(
        synthetic_root, "terminal-post-rename-hard-exit"
    )
    started = _run_child(_CHILD_START_AND_CRASH, synthetic_root, raw)
    assert started.returncode == 42, started.stderr
    renamed = _run_child(
        _CHILD_TERMINAL_POST_RENAME_HARD_CRASH,
        synthetic_root,
        raw,
    )
    assert renamed.returncode == 90, {
        "returncode": renamed.returncode,
        "stdout": renamed.stdout,
        "stderr": renamed.stderr,
    }

    package = synthetic_root / f"minimum-gate-{human}"
    terminal_path = package / "package-terminal.json"
    terminal_before = terminal_path.read_bytes()
    terminal_sha256 = path._sha(terminal_before)
    identity_before = terminal_path.stat()
    assert stat.S_IMODE(identity_before.st_mode) == 0o400
    assert not bool(identity_before.st_flags & stat.UF_IMMUTABLE)
    assert {item.name for item in package.iterdir()} == {
        "failure-accounting.json",
        "package-start.json",
        "package-terminal.json",
    }
    assert not any(
        item.name.startswith(f".{package.name}.terminal-stage-")
        for item in synthetic_root.iterdir()
    )

    fresh = path._qualification_runtime(synthetic_root, human, intercept=False)
    recovered = path._invoke_public_closeout_qualification(
        raw, fresh, now_unix_ns=0
    )
    assert recovered["result"] == "ALREADY_TERMINAL"
    assert recovered["terminal_written"] is False
    assert recovered["package_terminal_sha256"] == terminal_sha256
    assert recovered["checkpoint_effects"] == recovered["numerical_effects"] == 0
    assert fresh.observed_effects["checkpoint_root_resolutions"] == 0
    assert fresh.observed_effects["checkpoint_opens"] == 0
    assert fresh.observed_effects["numerical_executions"] == 0
    assert fresh.checkpoint_effect.physical_identity_producer_calls == 0
    assert fresh.checkpoint_effect.producer_checkpoint_binding_checks == 0
    assert fresh.checkpoint_effect.producer_checkpoint_shard_opens == 0
    assert fresh.checkpoint_effect.producer_checkpoint_hash_attempts == 0
    assert fresh.checkpoint_effect.producer_checkpoint_identity_hash_reads == 0

    identity_after = terminal_path.stat()
    assert terminal_path.read_bytes() == terminal_before
    assert path._sha(terminal_path.read_bytes()) == terminal_sha256
    assert (identity_after.st_dev, identity_after.st_ino) == (
        identity_before.st_dev,
        identity_before.st_ino,
    )
    assert stat.S_IMODE(identity_after.st_mode) == 0o400
    assert bool(identity_after.st_flags & stat.UF_IMMUTABLE)


def test_published_staging_inode_retains_kernel_claim_until_writer_retirement(
    synthetic_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw, _go_value, runtime, _stop, _start, _start_raw, _start_sha = (
        _started_package(synthetic_root, "published-staging-claim")
    )
    human = str(path._validate_go_non_temporal(
        raw, path._authority_profile(synthetic=True)
    ).get("human_decision_sha256"))
    _release_owner_without_synthetic_cleanup(runtime)

    real_rename = path.os.rename
    contender: dict[str, object] = {}

    def probe_after_publication(
        source,
        target,
        *,
        src_dir_fd=None,
        dst_dir_fd=None,
    ):
        result = real_rename(
            source,
            target,
            src_dir_fd=src_dir_fd,
            dst_dir_fd=dst_dir_fd,
        )
        if (
            type(source) is str
            and source.startswith(
                f".minimum-gate-{human}.terminal-stage-"
            )
            and target == "package-terminal.json"
        ):
            child = _run_child(_CHILD_CLOSEOUT, synthetic_root, raw)
            contender["returncode"] = child.returncode
            contender["stderr"] = child.stderr
            contender["result"] = _parse_child_json(child.stdout)
        return result

    monkeypatch.setattr(path.os, "rename", probe_after_publication)
    winner = _closeout_runtime(synthetic_root, raw, human)
    assert winner["result"] == "TERMINAL_FAILURE_BANKED"
    assert contender["returncode"] == 0, contender.get("stderr")
    assert contender["result"]["result"] == "EXECUTING_OWNER_ACTIVE"
    assert contender["result"]["terminal_written"] is False
    assert contender["result"]["checkpoint_effects"] == 0
    assert contender["result"]["numerical_effects"] == 0

    repeated = _closeout_runtime(synthetic_root, raw, human)
    assert repeated["result"] == "ALREADY_TERMINAL"
    assert repeated["package_terminal_sha256"] == winner[
        "package_terminal_sha256"
    ]


_CHILD_TERMINAL_PUBLICATION_HARD_CRASH = r"""
from pathlib import Path
import os
import stat
import sys

import f017_event06_minimum_gate_path_v1 as path


root = Path(sys.argv[1])
raw = bytes.fromhex(sys.argv[2])
boundary = sys.argv[3]
profile = path._authority_profile(synthetic=True)
go = path._validate_go_non_temporal(raw, profile)
human = str(go.get("human_decision_sha256"))
runtime = path._qualification_runtime(root, human, intercept=False)
package = runtime.storage.package_directory
stage_prefix = f".{package.name}.terminal-stage-"
hard_exit = os._exit

real_open = path.os.open
real_read = path.os.read
real_fsync = path.os.fsync
real_rename = path.os.rename
real_immutable = path._set_user_immutable
real_close = path.os.close
state = {
    "stage_fd": None,
    "final_fd": None,
    "renamed": False,
    "terminal_synced": False,
    "package_synced": False,
}


def crash():
    hard_exit(92)


def tracked_open(target, flags, mode=0o777, *, dir_fd=None):
    descriptor = real_open(target, flags, mode, dir_fd=dir_fd)
    if (
        type(target) is str
        and target.startswith(stage_prefix)
        and flags & os.O_EXCL
    ):
        state["stage_fd"] = descriptor
    elif (
        state["renamed"]
        and target == "package-terminal.json"
        and dir_fd == runtime.storage._package_fd
        and not flags & os.O_EXCL
    ):
        state["final_fd"] = descriptor
        if boundary == "post-final-open":
            crash()
    return descriptor


def tracked_rename(source, target, *, src_dir_fd=None, dst_dir_fd=None):
    result = real_rename(
        source,
        target,
        src_dir_fd=src_dir_fd,
        dst_dir_fd=dst_dir_fd,
    )
    if (
        type(source) is str
        and source.startswith(stage_prefix)
        and target == "package-terminal.json"
        and dst_dir_fd == runtime.storage._package_fd
    ):
        state["renamed"] = True
        if boundary == "post-rename":
            crash()
    return result


def tracked_immutable(descriptor, enabled):
    result = real_immutable(descriptor, enabled)
    if not state["renamed"]:
        if (
            boundary == "pre-rename-package-unsealed"
            and descriptor == runtime.storage._package_fd
            and enabled is False
            and state["stage_fd"] is not None
        ):
            crash()
        return result
    if (
        boundary == "post-terminal-seal"
        and descriptor == state["stage_fd"]
        and enabled is True
    ):
        crash()
    if (
        boundary == "post-package-seal"
        and descriptor == runtime.storage._package_fd
        and enabled is True
    ):
        crash()
    return result


def tracked_fsync(descriptor):
    result = real_fsync(descriptor)
    if not state["renamed"]:
        return result
    if descriptor == state["stage_fd"]:
        state["terminal_synced"] = True
        if boundary == "post-terminal-fsync":
            crash()
    elif descriptor == runtime.storage._package_fd:
        state["package_synced"] = True
        if boundary == "post-package-fsync":
            crash()
    elif state["terminal_synced"] and state["package_synced"]:
        if boundary == "post-parent-fsync":
            crash()
    return result


def tracked_read(descriptor, count):
    chunk = real_read(descriptor, count)
    if (
        boundary == "post-final-readback"
        and state["renamed"]
        and descriptor == state["final_fd"]
        and chunk
    ):
        crash()
    return chunk


def tracked_close(descriptor):
    if (
        boundary == "post-stage-close"
        and state["renamed"]
        and descriptor == state["stage_fd"]
    ):
        real_close(descriptor)
        crash()
    return real_close(descriptor)


path.os.open = tracked_open
path.os.read = tracked_read
path.os.fsync = tracked_fsync
path.os.rename = tracked_rename
path.os.close = tracked_close
path._set_user_immutable = tracked_immutable
path._invoke_public_closeout_qualification(raw, runtime, now_unix_ns=0)
hard_exit(93)
"""


@pytest.mark.parametrize(
    ("boundary", "first_result"),
    (
        ("pre-rename-package-unsealed", "TERMINAL_FAILURE_BANKED"),
        ("post-rename", "ALREADY_TERMINAL"),
        ("post-terminal-seal", "ALREADY_TERMINAL"),
        ("post-package-seal", "ALREADY_TERMINAL"),
        ("post-terminal-fsync", "ALREADY_TERMINAL"),
        ("post-package-fsync", "ALREADY_TERMINAL"),
        ("post-parent-fsync", "ALREADY_TERMINAL"),
        ("post-final-open", "ALREADY_TERMINAL"),
        ("post-final-readback", "ALREADY_TERMINAL"),
        ("post-stage-close", "ALREADY_TERMINAL"),
    ),
)
def test_hard_exit_at_terminal_publication_boundaries_is_restart_closeable(
    synthetic_root: Path,
    boundary: str,
    first_result: str,
) -> None:
    raw, _go_value, human = _go(
        synthetic_root, "terminal-publication-" + boundary
    )
    started = _run_child(_CHILD_START_AND_CRASH, synthetic_root, raw)
    assert started.returncode == 42, started.stderr
    crashed = subprocess.run(
        [
            sys.executable,
            "-c",
            _CHILD_TERMINAL_PUBLICATION_HARD_CRASH,
            str(synthetic_root),
            raw.hex(),
            boundary,
        ],
        cwd=Path(path.__file__).resolve().parents[2],
        env=os.environ.copy(),
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert crashed.returncode == 92, {
        "boundary": boundary,
        "returncode": crashed.returncode,
        "stdout": crashed.stdout,
        "stderr": crashed.stderr,
    }

    package = synthetic_root / f"minimum-gate-{human}"
    first_runtime = path._qualification_runtime(
        synthetic_root, human, intercept=False
    )
    first = path._invoke_public_closeout_qualification(
        raw, first_runtime, now_unix_ns=0
    )
    assert first["result"] == first_result
    assert first["checkpoint_effects"] == first["numerical_effects"] == 0
    assert first_runtime.observed_effects["checkpoint_root_resolutions"] == 0
    assert first_runtime.observed_effects["checkpoint_opens"] == 0
    assert first_runtime.observed_effects["numerical_executions"] == 0

    terminal_path = package / "package-terminal.json"
    terminal_raw = terminal_path.read_bytes()
    terminal = path._parse_artifact_bytes(terminal_raw)
    assert path._canonical_bytes(terminal) == terminal_raw
    assert terminal["state"] == "TERMINAL_FAILURE"
    assert terminal["terminal_origin"] == "RESTART_CLOSEOUT"
    assert stat.S_IMODE(terminal_path.stat().st_mode) == 0o400
    assert bool(terminal_path.stat().st_flags & stat.UF_IMMUTABLE)
    assert bool(package.stat().st_flags & stat.UF_IMMUTABLE)

    repeated_runtime = path._qualification_runtime(
        synthetic_root, human, intercept=False
    )
    repeated = path._invoke_public_closeout_qualification(
        raw, repeated_runtime, now_unix_ns=0
    )
    assert repeated["result"] == "ALREADY_TERMINAL"
    assert repeated["terminal_written"] is False
    assert repeated["package_terminal_sha256"] == path._sha(terminal_raw)
    assert repeated["checkpoint_effects"] == repeated["numerical_effects"] == 0
