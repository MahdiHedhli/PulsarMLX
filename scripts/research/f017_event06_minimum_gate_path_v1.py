#!/usr/bin/env python3
"""Minimum, one-shot Event 06 production composition.

The only public production input is the canonical eight-field collapsed GO.
All filesystem locations and irreversible-effect implementations are selected
inside this module.  Qualification uses the same private coordinator and may
replace exactly three irreversible boundaries: storage, checkpoint access,
and numerical execution.
"""
from __future__ import annotations

import ast
from contextvars import ContextVar
import ctypes
from dataclasses import dataclass, field
import errno
import hashlib
import importlib.util
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time
from types import MappingProxyType
from typing import Callable, Final, Mapping, Never, TypeVar, cast

from f017_binary_comparison_authority_v11 import (
    MAX_ABS_LIMIT as _MAX_ABS_LIMIT,
    RMSE_LIMIT as _RMSE_LIMIT,
    COSINE_MINIMUM as _COSINE_MINIMUM,
    derive_summary as _derive_comparison,
    validate_summary as _validate_comparison,
)
from f017_bounded_artifact_decode_v1 import parse_artifact_bytes as _parse_artifact_bytes
from f017_canonical_serialization_v10 import canonical_bytes as _canonical_bytes
from f017_checkpoint_identity_authority_v12 import (
    MINIMUM_INSTALLED_SCHEMA as _IDENTITY_INSTALLED_SCHEMA,
    ValidatedIdentityAuthority as _ValidatedIdentityAuthority,
    validate_minimum_installed_bytes as _validate_installed_bytes,
)
from f017_checkpoint_identity_producer_v12 import (
    _minimum_gate_produce as _run_identity_stage,
    validate_banked_identity_evidence as _validate_banked_identity_evidence,
)
from f017_corrected_oracle_primary_wrapper_v11 import (
    _minimum_gate_execute_target_and_bank as _execute_primary_target,
)
from f017_corrected_oracle_secondary_wrapper_v11 import (
    _minimum_gate_execute_target_and_bank as _execute_secondary_target,
)
from f017_descriptor_lease_manager_v10 import (
    LeaseRecord as _LeaseRecord,
    LeaseSet as _LeaseSet,
    validate_descriptors as _validate_descriptors,
)
from f017_event06_minimum_gate_contract_v1 import (
    HISTORICAL_MASTER_LEDGER as _HISTORICAL_MASTER_LEDGER,
    REQUIRED_MECHANISM_IDS as _REQUIRED_MECHANISM_IDS,
    STAGE_VOCABULARY as _STAGE_VOCABULARY,
    _build_accounting_closure,
    _build_package_start_gate,
    _build_package_terminal,
    canonical_sha256 as _contract_sha256,
    _consume_package_start_gate,
    minimum_gate_contract as _minimum_gate_contract,
    _validate_accounting_closure,
    validate_minimum_gate_contract as _validate_minimum_gate_contract,
    _validate_package_start_gate,
    _validate_consumed_package_start_gate,
    _validate_package_terminal,
)
from f017_result_bundle_builder_v11 import (
    _minimum_gate_bank_output_bundle as _bank_output_bundle,
)
from f017_result_bundle_authority_v11 import validate_bundle as _validate_bundle
from f017_write_once_artifact_v1 import _set_user_immutable

__all__ = ("execute_event06_minimum_gate_path",)


_ROOT: Final = Path(__file__).resolve().parents[2]
_LIVE_PACKAGE_PARENT: Final = Path(
    "/Users/Shared/PulsarMLX/f017-event06-v12/minimum-gate-packages"
)
_LIVE_CHECKPOINT_ROOT: Final = Path(
    "/Users/mhedhli/Models/PulsarMLX/GLM-5.2-UD-IQ2_XXS"
)
_CHECKPOINT_CONTRACT: Final = (
    "specs/017-rust-native-inference-runtime/contracts/"
    "f017-corrected-oracle-checkpoint-identity-v12.json"
)
_SYNTHETIC_CHECKPOINT_CONTRACT: Final = (
    "specs/017-rust-native-inference-runtime/contracts/"
    "f017-synthetic-checkpoint-identity-v12.json"
)
_TENSOR_PLAN: Final = (
    "specs/017-rust-native-inference-runtime/contracts/"
    "f017-corrected-oracle-production-tensor-plan-v9.json"
)
_NUMERICAL_CONTRACT: Final = (
    "specs/017-rust-native-inference-runtime/contracts/"
    "f017-corrected-full-checkpoint-oracle-numerical-contract-v4.json"
)
_RESULT_AUTHORITY: Final = (
    "specs/017-rust-native-inference-runtime/contracts/"
    "f017-corrected-oracle-result-authority-v11-v2.json"
)
_PRIMARY_CORE: Final = "scripts/research/f017_corrected_oracle_primary_numerics_v3.py"
_SECONDARY_CORE: Final = "scripts/research/f017_corrected_oracle_secondary_numerics_v3.py"
_COMPARISON_AUTHORITY: Final = "scripts/research/f017_binary_comparison_authority_v11.py"
_RESULT_BUILDER: Final = "scripts/research/f017_result_bundle_builder_v11.py"
_IDENTITY_PRODUCER: Final = (
    "scripts/research/f017_checkpoint_identity_producer_v12.py"
)
_IDENTITY_VALIDATOR: Final = (
    "scripts/research/f017_checkpoint_identity_authority_v12.py"
)
_MINIMUM_CONTRACT: Final = (
    "scripts/research/f017_event06_minimum_gate_contract_v1.py"
)
_MINIMUM_PATH: Final = "scripts/research/f017_event06_minimum_gate_path_v1.py"

_SEQUENCE39_PROMPT_COMMIT: Final = (
    "781bd71faa9bf546b479a5544d6f69c33440df13"
)
_SEQUENCE39_PROMPT_PATH: Final = (
    "Prompts/F017/Mac-Studio-M1-Ultra/"
    "039__F017__Mac-Studio-M1-Ultra__Event-06-minimum-gate-path-"
    "simplification-and-no-access-composition__prompt.md"
)
_SEQUENCE39_PROMPT_SHA256: Final = (
    "3a3a763532223fe7db38dd3f8069d109396a9ca5352a694d625c20bfee765835"
)
_TARGET_MACHINE: Final = "MAC_STUDIO_M1_ULTRA"
_TARGET_MACHINE_BRAND: Final = "Apple M1 Ultra"
_TARGET_ARCHITECTURE: Final = "arm64"

_COLLAPSED_GO_SCHEMA: Final = (
    "pulsarmlx.f017.event06-v12-collapsed-one-shot-go/1.0.0"
)
_COLLAPSED_GO_DECISION: Final = "GO_EVENT06_ONCE"
_COLLAPSED_GO_SCOPE: Final = (
    "ONE_PACKAGE_ONE_PRIMARY_ONE_SECONDARY_ZERO_RETRY_NO_RESUME"
)
_COLLAPSED_GO_FIELDS: Final = (
    "schema",
    "decision",
    "human_decision_sha256",
    "release_authority_sha256",
    "one_shot_nonce_sha256",
    "issued_at_unix_ns",
    "expires_at_unix_ns",
    "scope",
)
_HEX64 = re.compile(r"[0-9a-f]{64}")
_STAGES: Final = tuple(_STAGE_VOCABULARY)
_SUCCESS_COMMON_ROOT_FILES: Final = frozenset({
    "comparison-receipt.json",
    "comparison-summary.json",
    "comparison-terminal.json",
    "package-receipt.json",
    "package-start.json",
    "package-terminal.json",
    "primary-start-receipt.json",
    "receipt-derived-accounting.json",
    "release-receipt.json",
    "release-report.json",
    "release-start-receipt.json",
    "release-terminal.json",
    "secondary-start-receipt.json",
    "v11-result-closure.json",
})
_SUCCESS_SYNTHETIC_IDENTITY_FILES: Final = frozenset({
    "identity-access-census.json",
    "identity-read-receipts.json",
    "identity-receipt.json",
    "identity-terminal.json",
})
_SUCCESS_PRODUCTION_IDENTITY_FILES: Final = frozenset({
    "access-journal.json",
    "identity-core.json",
    "identity-manifest.json",
    "identity-receipt.json",
    "identity-terminal.json",
    "lease-manifest.json",
    "shard-receipts.json",
})
_SUCCESS_ROLE_FILE_SUFFIXES: Final = frozenset({
    "consumer-terminal.json",
    "final_hidden.bin",
    "final_normalized.bin",
    "full_logits.bin",
    "payload-manifest.json",
    "result-receipt.json",
    "result-terminal.json",
    "routing-manifest.json",
    "top32-summary.json",
})
_RUNTIME_SEAL = object()
_GO_SEAL = object()
_BRIDGE_SEAL = object()
_SYNTHETIC_STORAGE_SEAL = object()
_SYNTHETIC_CHECKPOINT_SEAL = object()
_SYNTHETIC_NUMERICAL_SEAL = object()
_QUALIFICATION_INVOCATION_SEAL = object()
_ONE_SHOT_STATE_SEAL = object()
_AnchoredResult = TypeVar("_AnchoredResult")


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _deep_immutable(value: object) -> object:
    """Detach and freeze an authority value before it crosses the public API."""
    if type(value) is dict:
        return MappingProxyType({
            str(key): _deep_immutable(item) for key, item in value.items()
        })
    if type(value) in {list, tuple}:
        return tuple(_deep_immutable(item) for item in value)
    return value


def _pthread_fchdir_callable() -> Callable[[int], int]:
    """Resolve the fixed Darwin thread-local directory-anchor primitive."""
    if sys.platform != "darwin":
        raise RuntimeError("Darwin thread-local directory anchor required")
    libc = ctypes.CDLL(None, use_errno=True)
    try:
        function = libc.pthread_fchdir_np
    except AttributeError as exc:
        raise RuntimeError("pthread_fchdir_np unavailable") from exc
    function.argtypes = [ctypes.c_int]
    function.restype = ctypes.c_int
    return cast(Callable[[int], int], function)


def _observe_target_machine() -> Mapping[str, str]:
    """Read the host identity from fixed operating-system interfaces."""
    observed = subprocess.run(
        ["/usr/sbin/sysctl", "-n", "machdep.cpu.brand_string"],
        check=False,
        capture_output=True,
        text=True,
        timeout=5,
    )
    if observed.returncode != 0 or observed.stderr:
        raise RuntimeError("target-machine observation failed")
    return MappingProxyType(
        {
            "target_machine": _TARGET_MACHINE,
            "brand": observed.stdout.strip(),
            "architecture": os.uname().machine,
        }
    )


def _file_sha(relative: str) -> str:
    path = _ROOT / relative
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"bound implementation file: {relative}")
    return _sha(path.read_bytes())


def _runtime_source_closure() -> tuple[dict[str, str], ...]:
    """Derive repository-local imports reachable from production source.

    Imports nested exclusively below qualification or synthetic definitions are
    deliberately excluded: their bytes are not live-GO authority.  Global
    imports and imports under ordinary production definitions remain in the
    transitive closure.
    """
    research = _ROOT / "scripts/research"
    pending = [Path(_MINIMUM_PATH).stem]
    observed: dict[str, str] = {}

    def production_imports(tree: ast.AST) -> set[str]:
        imported: set[str] = set()

        class Visitor(ast.NodeVisitor):
            def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                if node.name.startswith(("_qualification", "_run_no_access")):
                    return
                self.generic_visit(node)

            visit_AsyncFunctionDef = visit_FunctionDef

            def visit_ClassDef(self, node: ast.ClassDef) -> None:
                if node.name.startswith("_Synthetic"):
                    return
                self.generic_visit(node)

            def visit_Import(self, node: ast.Import) -> None:
                imported.update(alias.name.split(".")[0] for alias in node.names)

            def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
                if node.module:
                    imported.add(node.module.split(".")[0])

        Visitor().visit(tree)
        return imported

    while pending:
        module = pending.pop()
        if module in observed:
            continue
        source_path = research / f"{module}.py"
        if not source_path.is_file() or source_path.is_symlink():
            continue
        relative = source_path.relative_to(_ROOT).as_posix()
        raw = source_path.read_bytes()
        observed[module] = relative
        tree = ast.parse(raw, filename=relative)
        imported = production_imports(tree)
        pending.extend(
            name
            for name in sorted(imported, reverse=True)
            if (research / f"{name}.py").is_file() and name not in observed
        )
    return tuple(
        {"path": relative, "sha256": _file_sha(relative)}
        for _module, relative in sorted(observed.items(), key=lambda item: item[1])
    )


def _validate_loaded_runtime_origins(
    closure: tuple[dict[str, str], ...],
) -> tuple[dict[str, str], ...]:
    """Bind Python's resolved modules to the repository bytes in the closure."""
    rows: list[dict[str, str]] = []
    for binding in closure:
        relative = str(binding["path"])
        expected = (_ROOT / relative).resolve(strict=True)
        module_name = expected.stem
        loaded = sys.modules.get(module_name)
        if loaded is not None:
            origin_raw = getattr(loaded, "__file__", None)
        else:
            specification = importlib.util.find_spec(module_name)
            origin_raw = None if specification is None else specification.origin
        if type(origin_raw) is not str:
            raise RuntimeError(f"runtime module origin unavailable: {module_name}")
        origin = Path(origin_raw).resolve(strict=True)
        if origin != expected or _sha(origin.read_bytes()) != binding["sha256"]:
            raise RuntimeError(f"runtime module origin drift: {module_name}")
        rows.append(
            {
                "module": module_name,
                "path": relative,
                "sha256": str(binding["sha256"]),
            }
        )
    return tuple(rows)


class _ClosedMapping:
    __slots__ = ("_items", "sha256")

    def _initialize(self, value: Mapping[str, object]) -> None:
        object.__setattr__(self, "_items", tuple(sorted(dict(value).items())))
        object.__setattr__(self, "sha256", _sha(_canonical_bytes(dict(value))))

    def __setattr__(self, name: str, value: object) -> Never:
        del name, value
        raise TypeError("minimum-path authorities are immutable")

    def get(self, name: str) -> object:
        for key, value in self._items:
            if key == name:
                return value
        raise KeyError(name)

    def as_dict(self) -> dict[str, object]:
        return dict(self._items)


class _ValidatedCollapsedGo(_ClosedMapping):
    __slots__ = ()

    def __new__(cls, seal: object = None, value: object = None):
        del value
        if seal is not _GO_SEAL:
            raise TypeError("collapsed GO is validator-created")
        return super().__new__(cls)

    def __init__(self, seal: object, value: Mapping[str, object]) -> None:
        del seal
        self._initialize(value)


class _ValidatedBridge(_ClosedMapping):
    __slots__ = ()

    def __new__(cls, seal: object = None, value: object = None):
        del value
        if seal is not _BRIDGE_SEAL:
            raise TypeError("numerical bridge is coordinator-created")
        return super().__new__(cls)

    def __init__(self, seal: object, value: Mapping[str, object]) -> None:
        del seal
        self._initialize(value)


@dataclass(frozen=True)
class _AuthorityProfile:
    minimum_contract: Mapping[str, object]
    release_authority_sha256: str
    checkpoint_contract_path: str
    checkpoint_authority_sha256: str
    checkpoint_set_sha256: str
    numerical_acceptance_contract_sha256: str
    comparison_rules_sha256: str
    result_authority_sha256: str
    tensor_plan_sha256: str
    primary_numerical_sha256: str
    secondary_numerical_sha256: str
    result_builder_sha256: str
    shards: tuple[Mapping[str, object], ...]
    release_authority: Mapping[str, object]
    authority_scope: str


def _authority_profile(*, synthetic: bool) -> _AuthorityProfile:
    minimum = _validate_minimum_gate_contract(_minimum_gate_contract())
    runtime_source_closure = _runtime_source_closure()
    loaded_runtime_bindings = _validate_loaded_runtime_origins(
        runtime_source_closure
    )
    contract_path = _SYNTHETIC_CHECKPOINT_CONTRACT if synthetic else _CHECKPOINT_CONTRACT
    checkpoint = _parse_artifact_bytes((_ROOT / contract_path).read_bytes())
    if type(checkpoint) is not dict or type(checkpoint.get("shards")) is not list:
        raise ValueError("checkpoint identity contract")
    production_checkpoint = _parse_artifact_bytes(
        (_ROOT / _CHECKPOINT_CONTRACT).read_bytes()
    )
    if type(production_checkpoint) is not dict:
        raise ValueError("production checkpoint identity contract")
    release_authority = {
        "schema": (
            "pulsarmlx.f017.event06-v12-minimum-gate-release-authority/1.0.0"
        ),
        "target_machine": _TARGET_MACHINE,
        "target_machine_brand": _TARGET_MACHINE_BRAND,
        "target_architecture": _TARGET_ARCHITECTURE,
        "generation": "V12",
        "authority_scope": "SYNTHETIC" if synthetic else "PRODUCTION",
        "sequence39_prompt_commit": _SEQUENCE39_PROMPT_COMMIT,
        "sequence39_prompt_path": _SEQUENCE39_PROMPT_PATH,
        "sequence39_prompt_sha256": _SEQUENCE39_PROMPT_SHA256,
        "minimum_gate_contract_path": _MINIMUM_CONTRACT,
        "minimum_gate_contract_sha256": _file_sha(_MINIMUM_CONTRACT),
        "minimum_gate_semantic_sha256": _contract_sha256(minimum),
        "minimum_gate_path": _MINIMUM_PATH,
        "minimum_gate_path_sha256": _file_sha(_MINIMUM_PATH),
        "runtime_source_closure": list(runtime_source_closure),
        "runtime_source_closure_sha256": _contract_sha256(
            list(runtime_source_closure)
        ),
        "loaded_runtime_bindings": list(loaded_runtime_bindings),
        "loaded_runtime_bindings_sha256": _contract_sha256(
            list(loaded_runtime_bindings)
        ),
        "checkpoint_identity_contract_path": _CHECKPOINT_CONTRACT,
        "checkpoint_identity_contract_sha256": _file_sha(_CHECKPOINT_CONTRACT),
        "selected_checkpoint_identity_contract_path": contract_path,
        "selected_checkpoint_identity_contract_sha256": _file_sha(contract_path),
        "production_checkpoint_root": str(_LIVE_CHECKPOINT_ROOT),
        "selected_checkpoint_root": (
            "SEALED_SYNTHETIC_RUNTIME_DERIVED"
            if synthetic else str(_LIVE_CHECKPOINT_ROOT)
        ),
        "checkpoint_set_sha256": str(
            production_checkpoint["checkpoint_set_sha256"]
        ),
        "checkpoint_identity_producer_path": _IDENTITY_PRODUCER,
        "checkpoint_identity_producer_sha256": _file_sha(_IDENTITY_PRODUCER),
        "checkpoint_identity_validator_path": _IDENTITY_VALIDATOR,
        "checkpoint_identity_validator_sha256": _file_sha(_IDENTITY_VALIDATOR),
        "tensor_plan_path": _TENSOR_PLAN,
        "tensor_plan_sha256": _file_sha(_TENSOR_PLAN),
        "numerical_contract_path": _NUMERICAL_CONTRACT,
        "numerical_contract_sha256": _file_sha(_NUMERICAL_CONTRACT),
        "primary_numerical_path": _PRIMARY_CORE,
        "primary_numerical_sha256": _file_sha(_PRIMARY_CORE),
        "secondary_numerical_path": _SECONDARY_CORE,
        "secondary_numerical_sha256": _file_sha(_SECONDARY_CORE),
        "result_authority_path": _RESULT_AUTHORITY,
        "result_authority_sha256": _file_sha(_RESULT_AUTHORITY),
        "result_builder_path": _RESULT_BUILDER,
        "result_builder_sha256": _file_sha(_RESULT_BUILDER),
        "comparison_authority_path": _COMPARISON_AUTHORITY,
        "comparison_authority_sha256": _file_sha(_COMPARISON_AUTHORITY),
        "collapsed_go_schema": _COLLAPSED_GO_SCHEMA,
        "collapsed_go_fields": list(_COLLAPSED_GO_FIELDS),
        "collapsed_go_decision": _COLLAPSED_GO_DECISION,
        "collapsed_go_scope": _COLLAPSED_GO_SCOPE,
        "identity_derivation": "SHA256_COLLAPSED_GO_DOMAIN_PREFIXED_FOUR_ROLES",
        "attempts": 1,
        "retries": 0,
        "resume": False,
        "result": "PASS",
    }
    return _AuthorityProfile(
        minimum_contract=MappingProxyType(dict(minimum)),
        release_authority_sha256=_contract_sha256(release_authority),
        checkpoint_contract_path=contract_path,
        checkpoint_authority_sha256=_file_sha(contract_path),
        checkpoint_set_sha256=str(checkpoint["checkpoint_set_sha256"]),
        numerical_acceptance_contract_sha256=_file_sha(_NUMERICAL_CONTRACT),
        comparison_rules_sha256=_file_sha(_COMPARISON_AUTHORITY),
        result_authority_sha256=_file_sha(_RESULT_AUTHORITY),
        tensor_plan_sha256=_file_sha(_TENSOR_PLAN),
        primary_numerical_sha256=_file_sha(_PRIMARY_CORE),
        secondary_numerical_sha256=_file_sha(_SECONDARY_CORE),
        result_builder_sha256=_file_sha(_RESULT_BUILDER),
        shards=tuple(MappingProxyType(dict(item)) for item in checkpoint["shards"]),
        release_authority=MappingProxyType(release_authority),
        authority_scope="SYNTHETIC" if synthetic else "PRODUCTION",
    )


def _open_directory_chain(path: Path, *, create: bool) -> int:
    """Open an absolute directory one component at a time without symlinks."""
    if not path.is_absolute() or path == Path("/"):
        raise ValueError("fixed absolute directory chain")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    current = os.open("/", flags)
    try:
        for component in path.parts[1:]:
            if component in {"", ".", ".."} or "/" in component:
                raise ValueError("canonical directory component")
            if create:
                try:
                    os.mkdir(component, mode=0o700, dir_fd=current)
                except FileExistsError:
                    pass
            following = os.open(component, flags, dir_fd=current)
            observed = os.fstat(following)
            if not stat.S_ISDIR(observed.st_mode):
                os.close(following)
                raise ValueError("directory-chain identity")
            os.close(current)
            current = following
        return current
    except BaseException:
        os.close(current)
        raise


class _StorageBinding:
    __slots__ = (
        "package_directory",
        "scope",
        "_package_fd",
        "_package_identity",
        "_terminal_fd",
        "_terminal_identity",
        "_terminal_writer_retired",
    )

    def __init__(self, package_directory: Path, scope: str) -> None:
        if not isinstance(package_directory, Path) or not package_directory.is_absolute():
            raise TypeError("internally derived absolute package directory required")
        self.package_directory = package_directory
        self.scope = scope
        self._package_fd: int | None = None
        self._package_identity: tuple[int, int] | None = None
        self._terminal_fd: int | None = None
        self._terminal_identity: tuple[int, int] | None = None
        self._terminal_writer_retired = False

    def prepare(self) -> None:
        if self._package_fd is not None:
            return
        parent_fd = _open_directory_chain(
            self.package_directory.parent, create=True
        )
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        try:
            try:
                os.mkdir(
                    self.package_directory.name,
                    mode=0o700,
                    dir_fd=parent_fd,
                )
            except FileExistsError:
                pass
            package_fd = os.open(
                self.package_directory.name, flags, dir_fd=parent_fd
            )
            observed = os.fstat(package_fd)
            if (
                not stat.S_ISDIR(observed.st_mode)
                or observed.st_uid != os.getuid()
            ):
                os.close(package_fd)
                raise ValueError("package directory authority")
            os.fsync(parent_fd)
            self._package_fd = package_fd
            self._package_identity = (observed.st_dev, observed.st_ino)
        finally:
            os.close(parent_fd)

    def close(self) -> None:
        """Release the package-directory descriptor exactly once."""
        terminal_descriptor = self._terminal_fd
        descriptor = self._package_fd
        self._terminal_fd = None
        self._terminal_identity = None
        self._terminal_writer_retired = False
        self._package_fd = None
        self._package_identity = None
        terminal_error: BaseException | None = None
        if terminal_descriptor is not None:
            try:
                os.close(terminal_descriptor)
            except BaseException as exc:
                terminal_error = exc
        if descriptor is not None:
            try:
                os.close(descriptor)
            except BaseException:
                if terminal_error is None:
                    raise
        if terminal_error is not None:
            raise terminal_error

    def _verify_package_path_identity(self) -> None:
        """Require the canonical package leaf to name the held directory."""
        if self._package_fd is None or self._package_identity is None:
            raise RuntimeError("package storage is not prepared")
        parent_fd = _open_directory_chain(
            self.package_directory.parent, create=False
        )
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        resolved_fd: int | None = None
        try:
            resolved_fd = os.open(
                self.package_directory.name, flags, dir_fd=parent_fd
            )
            resolved = os.fstat(resolved_fd)
            held = os.fstat(self._package_fd)
            if (
                not stat.S_ISDIR(resolved.st_mode)
                or (resolved.st_dev, resolved.st_ino) != self._package_identity
                or (held.st_dev, held.st_ino) != self._package_identity
            ):
                raise RuntimeError("canonical package directory identity changed")
        finally:
            if resolved_fd is not None:
                os.close(resolved_fd)
            os.close(parent_fd)

    def _bank_leaf(
        self,
        leaf: str,
        value: Mapping[str, object],
        *,
        require_canonical_path: bool,
        durable_start: _StopBoundary | None = None,
    ) -> str:
        if "/" in leaf or "\\" in leaf or leaf in {"", ".", ".."}:
            raise ValueError("canonical package leaf")
        if self._package_fd is None or self._package_identity is None:
            raise RuntimeError("package storage is not prepared")
        if durable_start is not None and type(durable_start) is not _StopBoundary:
            raise TypeError("durable package-start marker")
        if require_canonical_path:
            self._verify_package_path_identity()
        raw = _canonical_bytes(dict(value))
        digest = _sha(raw)
        flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        descriptor = os.open(leaf, flags, 0o600, dir_fd=self._package_fd)
        try:
            view = memoryview(raw)
            written = 0
            while written < len(view):
                count = os.write(descriptor, view[written:])
                if count <= 0:
                    raise OSError("short package evidence write")
                written += count
            os.fsync(descriptor)
            observed = os.fstat(descriptor)
            if (
                not stat.S_ISREG(observed.st_mode)
                or observed.st_nlink != 1
                or observed.st_size != len(raw)
            ):
                raise ValueError("package evidence identity")
            os.lseek(descriptor, 0, os.SEEK_SET)
            chunks: list[bytes] = []
            remaining = len(raw)
            while remaining > 0:
                chunk = os.read(descriptor, min(65_536, remaining))
                if not chunk:
                    raise OSError("short package evidence readback")
                chunks.append(chunk)
                remaining -= len(chunk)
            if os.read(descriptor, 1) or b"".join(chunks) != raw:
                raise ValueError("package evidence readback")
            # Close each write-once control leaf before returning it to the
            # coordinator.  This prevents a later terminal hook from acquiring
            # a writable predecessor descriptor that survives the final seal.
            _set_user_immutable(descriptor, True)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.fsync(self._package_fd)
        if durable_start is not None:
            # Both file contents and the containing directory entry are now
            # durable.  Mark the package before any subsequent pathname check
            # can fail so every post-durability outcome terminalizes.
            durable_start.package_started = True
            durable_start.record("PACKAGE_START", digest)
        if require_canonical_path:
            self._verify_package_path_identity()
        return digest

    def bank(self, leaf: str, value: Mapping[str, object]) -> str:
        return self._bank_leaf(
            leaf, value, require_canonical_path=True
        )

    def bank_package_start(
        self, value: Mapping[str, object], stop: _StopBoundary
    ) -> str:
        """Select one terminal owner, then durably mark the package winner."""
        self._reserve_package_terminal(stop)
        try:
            return self._bank_leaf(
                "package-start.json",
                value,
                require_canonical_path=True,
                durable_start=stop,
            )
        except BaseException:
            if not stop.package_started:
                self._discard_prestart_terminal_reservation()
            raise

    def bank_failure(self, leaf: str, value: Mapping[str, object]) -> str:
        """Bank terminal failure evidence to the held post-start authority."""
        return self._bank_leaf(
            leaf,
            value,
            require_canonical_path=False,
        )

    def _set_existing_leaf_immutability(
        self,
        enabled: bool,
        *,
        reserved_terminal_descriptor: int | None = None,
        verify_canonical_path: bool = True,
    ) -> None:
        """Seal or unseal the bounded, one-level package artifact surface.

        Event 06 has no recursively nested authority directories.  Deliberately
        avoid a recursive walker here: an unbound hostile directory must not be
        able to exhaust Python's recursion depth while the sole package terminal
        is being recovered.
        """
        if self._package_fd is None or self._package_identity is None:
            raise RuntimeError("package storage is not prepared")
        if reserved_terminal_descriptor is not None and (
            not enabled or type(reserved_terminal_descriptor) is not int
        ):
            raise TypeError("reserved success terminal descriptor")
        if type(verify_canonical_path) is not bool:
            raise TypeError("canonical path verification policy")
        if verify_canonical_path:
            self._verify_package_path_identity()
        flags = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        reserved_identity: tuple[int, int] | None = None
        if reserved_terminal_descriptor is not None:
            reserved = os.fstat(reserved_terminal_descriptor)
            reserved_identity = (reserved.st_dev, reserved.st_ino)
        def process_files(directory_fd: int, *, root: bool) -> None:
            for leaf in sorted(os.listdir(directory_fd)):
                try:
                    entry = os.stat(
                        leaf, dir_fd=directory_fd, follow_symlinks=False
                    )
                except OSError:
                    if enabled:
                        raise
                    continue
                if stat.S_ISDIR(entry.st_mode):
                    if not root and enabled:
                        raise ValueError("package closure nesting")
                    continue
                if not stat.S_ISREG(entry.st_mode):
                    if enabled:
                        raise ValueError("package closure leaf identity")
                    continue
                try:
                    descriptor = os.open(leaf, flags, dir_fd=directory_fd)
                except OSError:
                    if enabled:
                        raise
                    continue
                try:
                    observed = os.fstat(descriptor)
                    if (
                        not stat.S_ISREG(observed.st_mode)
                        or observed.st_nlink != 1
                        or observed.st_uid != os.getuid()
                    ):
                        if enabled:
                            raise ValueError("package closure leaf identity")
                        continue
                    if (
                        reserved_identity is not None
                        and root
                        and leaf == "package-terminal.json"
                    ):
                        if (observed.st_dev, observed.st_ino) != reserved_identity:
                            raise ValueError("reserved package terminal identity")
                        # The empty terminal stays writable only through its
                        # already-held descriptor.  The immutable root keeps
                        # its directory entry fixed until the final bytes are
                        # written, verified, sealed, and synced.
                        continue
                    _set_user_immutable(descriptor, enabled)
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)

        process_files(self._package_fd, root=True)
        directory_flags = flags | os.O_DIRECTORY
        for leaf in sorted(os.listdir(self._package_fd)):
            try:
                entry = os.stat(
                    leaf, dir_fd=self._package_fd, follow_symlinks=False
                )
            except OSError:
                if enabled:
                    raise
                continue
            if not stat.S_ISDIR(entry.st_mode):
                continue
            try:
                directory_fd = os.open(
                    leaf, directory_flags, dir_fd=self._package_fd
                )
            except OSError:
                if enabled:
                    raise
                continue
            try:
                observed = os.fstat(directory_fd)
                if (
                    not stat.S_ISDIR(observed.st_mode)
                    or observed.st_uid != os.getuid()
                ):
                    if enabled:
                        raise ValueError("package closure directory identity")
                    continue
                if not enabled:
                    _set_user_immutable(directory_fd, False)
                process_files(directory_fd, root=False)
                _set_user_immutable(directory_fd, enabled)
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        os.fsync(self._package_fd)
        if verify_canonical_path:
            self._verify_package_path_identity()

    @staticmethod
    def _seal_held_directory_tree(directory_fd: int) -> None:
        """Close one flat, freshly produced child as write-once authority."""
        if type(directory_fd) is not int:
            raise TypeError("held child directory descriptor")
        flags = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        for leaf in sorted(os.listdir(directory_fd)):
            observed = os.stat(
                leaf, dir_fd=directory_fd, follow_symlinks=False
            )
            if not stat.S_ISREG(observed.st_mode):
                raise ValueError("produced directory must be flat and regular")
            descriptor = os.open(leaf, flags, dir_fd=directory_fd)
            try:
                held = os.fstat(descriptor)
                if (
                    not stat.S_ISREG(held.st_mode)
                    or held.st_nlink != 1
                    or held.st_uid != os.getuid()
                ):
                    raise ValueError("produced directory leaf identity")
                _set_user_immutable(descriptor, True)
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        _set_user_immutable(directory_fd, True)
        os.fsync(directory_fd)

    def _reserve_package_terminal(self, stop: _StopBoundary) -> None:
        """Reserve the sole terminal leaf before package durable start."""
        if self._package_fd is None or self._package_identity is None:
            raise RuntimeError("package storage is not prepared")
        if (
            type(stop) is not _StopBoundary
            or stop.package_started
            or stop.terminal_banked
            or self._terminal_fd is not None
            or self._terminal_identity is not None
            or self._terminal_writer_retired
        ):
            raise TypeError("uncommitted package stop boundary required")
        self._verify_package_path_identity()
        flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        descriptor = os.open(
            "package-terminal.json", flags, 0o400, dir_fd=self._package_fd
        )
        terminal_immutable = False
        try:
            observed = os.fstat(descriptor)
            if (
                not stat.S_ISREG(observed.st_mode)
                or observed.st_nlink != 1
                or observed.st_uid != os.getuid()
                or observed.st_size != 0
            ):
                raise ValueError("reserved package terminal identity")
            _set_user_immutable(descriptor, True)
            terminal_immutable = True
            os.fsync(descriptor)
            os.fsync(self._package_fd)
            self._verify_package_path_identity()
            self._terminal_fd = descriptor
            self._terminal_identity = (observed.st_dev, observed.st_ino)
            self._terminal_writer_retired = False
            return None
        except BaseException:
            if terminal_immutable:
                try:
                    _set_user_immutable(descriptor, False)
                except BaseException:
                    pass
            try:
                os.close(descriptor)
            finally:
                try:
                    os.unlink("package-terminal.json", dir_fd=self._package_fd)
                except BaseException:
                    pass
            raise

    def _discard_prestart_terminal_reservation(self) -> None:
        """Remove only this instance's empty terminal before durable start."""
        descriptor = self._terminal_fd
        identity = self._terminal_identity
        self._terminal_fd = None
        self._terminal_identity = None
        self._terminal_writer_retired = False
        if descriptor is None or identity is None:
            return
        try:
            observed = os.fstat(descriptor)
            canonical = os.stat(
                "package-terminal.json",
                dir_fd=self._package_fd,
                follow_symlinks=False,
            )
            if (
                (observed.st_dev, observed.st_ino) != identity
                or (canonical.st_dev, canonical.st_ino) != identity
                or observed.st_size != 0
            ):
                raise ValueError("prestart terminal reservation identity")
            _set_user_immutable(descriptor, False)
            os.unlink("package-terminal.json", dir_fd=self._package_fd)
            os.fsync(self._package_fd)
        finally:
            os.close(descriptor)

    def _verify_exact_success_inventory(
        self, reserved_terminal_descriptor: int
    ) -> None:
        """Reject every unbound file or directory while the namespace is sealed."""
        if self._package_fd is None or self._package_identity is None:
            raise RuntimeError("package storage is not prepared")
        if type(reserved_terminal_descriptor) is not int:
            raise TypeError("reserved success terminal descriptor")
        self._verify_package_path_identity()
        package = os.fstat(self._package_fd)
        if not bool(package.st_flags & stat.UF_IMMUTABLE):
            raise ValueError("package root is not immutable")

        root_files = set(_SUCCESS_COMMON_ROOT_FILES)
        root_directories = {"primary", "secondary"}
        if self.scope == "SYNTHETIC":
            root_files.update(_SUCCESS_SYNTHETIC_IDENTITY_FILES)
        elif self.scope == "PRODUCTION":
            root_directories.add("identity")
        else:
            raise ValueError("package success inventory scope")
        expected_root = root_files | root_directories
        if set(os.listdir(self._package_fd)) != expected_root:
            raise ValueError("package success root entry census")

        open_flags = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW
        directory_flags = open_flags | os.O_DIRECTORY
        if hasattr(os, "O_CLOEXEC"):
            open_flags |= os.O_CLOEXEC
            directory_flags |= os.O_CLOEXEC
        reserved = os.fstat(reserved_terminal_descriptor)
        seen_file_identities: set[tuple[int, int]] = set()

        def validate_file(directory_fd: int, leaf: str, *, terminal: bool) -> None:
            descriptor = os.open(leaf, open_flags, dir_fd=directory_fd)
            try:
                observed = os.fstat(descriptor)
                identity = (observed.st_dev, observed.st_ino)
                if (
                    not stat.S_ISREG(observed.st_mode)
                    or observed.st_nlink != 1
                    or observed.st_uid != os.getuid()
                    or identity in seen_file_identities
                ):
                    raise ValueError("package success leaf identity")
                if terminal:
                    if (
                        identity != (reserved.st_dev, reserved.st_ino)
                        or observed.st_size != 0
                    ):
                        raise ValueError("reserved package terminal identity")
                elif not bool(observed.st_flags & stat.UF_IMMUTABLE):
                    raise ValueError("package success leaf is not immutable")
                seen_file_identities.add(identity)
            finally:
                os.close(descriptor)

        for leaf in sorted(root_files):
            validate_file(
                self._package_fd,
                leaf,
                terminal=leaf == "package-terminal.json",
            )

        for role in ("primary", "secondary"):
            directory_fd = os.open(role, directory_flags, dir_fd=self._package_fd)
            try:
                observed = os.fstat(directory_fd)
                if (
                    not stat.S_ISDIR(observed.st_mode)
                    or observed.st_uid != os.getuid()
                    or not bool(observed.st_flags & stat.UF_IMMUTABLE)
                ):
                    raise ValueError("package result directory identity")
                role_files = {
                    f"{role}-{suffix}" for suffix in _SUCCESS_ROLE_FILE_SUFFIXES
                }
                if set(os.listdir(directory_fd)) != role_files:
                    raise ValueError("package result directory entry census")
                for leaf in sorted(role_files):
                    validate_file(directory_fd, leaf, terminal=False)
            finally:
                os.close(directory_fd)

        if self.scope == "PRODUCTION":
            directory_fd = os.open(
                "identity", directory_flags, dir_fd=self._package_fd
            )
            try:
                observed = os.fstat(directory_fd)
                if (
                    not stat.S_ISDIR(observed.st_mode)
                    or observed.st_uid != os.getuid()
                    or not bool(observed.st_flags & stat.UF_IMMUTABLE)
                ):
                    raise ValueError("package identity directory identity")
                if set(os.listdir(directory_fd)) != set(
                    _SUCCESS_PRODUCTION_IDENTITY_FILES
                ):
                    raise ValueError("package identity directory entry census")
                for leaf in sorted(_SUCCESS_PRODUCTION_IDENTITY_FILES):
                    validate_file(directory_fd, leaf, terminal=False)
            finally:
                os.close(directory_fd)

    def _abort_success_commit(self, descriptor: int) -> None:
        """Restore the reserved terminal and namespace for failure banking."""
        errors: list[BaseException] = []
        try:
            _set_user_immutable(self._package_fd, False)
        except BaseException as exc:
            errors.append(exc)
        try:
            # Every durable predecessor remains sealed.  A retired terminal
            # writer is already an irreversible complete outcome and is never
            # routed here.  Otherwise the original O_RDWR reservation remains
            # the exact rollback authority even though its pathname mode is
            # deliberately read-only.
            current = self._terminal_fd
            identity = self._terminal_identity
            if (
                current is None
                or identity is None
                or current != descriptor
                or self._terminal_writer_retired
            ):
                raise RuntimeError("held package terminal required")
            observed = os.fstat(current)
            canonical = os.stat(
                "package-terminal.json",
                dir_fd=self._package_fd,
                follow_symlinks=False,
            )
            if (
                (observed.st_dev, observed.st_ino) != identity
                or (canonical.st_dev, canonical.st_ino) != identity
            ):
                raise ValueError("reserved package terminal identity")
            _set_user_immutable(current, False)
            if observed.st_size != 0:
                os.ftruncate(current, 0)
                os.fsync(current)
            if os.lseek(current, 0, os.SEEK_SET) != 0:
                raise OSError("package terminal rollback offset")
            os.fchmod(current, 0o400)
            _set_user_immutable(current, True)
            os.fsync(current)
        except BaseException as exc:
            errors.append(exc)
        if errors:
            raise RuntimeError("package success commit rollback") from errors[0]

    def _seal_failure_durable_prefix(self, terminal_descriptor: int) -> None:
        """Seal the bounded graph-owned durable prefix without recursion."""
        if self._package_fd is None or self._terminal_identity is None:
            raise RuntimeError("package storage is not prepared")
        if terminal_descriptor != self._terminal_fd:
            raise ValueError("held package terminal authority")
        flags = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC

        def seal_regular_leaves(directory_fd: int) -> None:
            for leaf in sorted(os.listdir(directory_fd)):
                try:
                    observed = os.stat(
                        leaf, dir_fd=directory_fd, follow_symlinks=False
                    )
                except OSError:
                    # A hostile, unbound entry must not suppress the sole
                    # truthful failure terminal.
                    continue
                if not stat.S_ISREG(observed.st_mode):
                    continue
                try:
                    descriptor = os.open(leaf, flags, dir_fd=directory_fd)
                except OSError:
                    continue
                try:
                    held = os.fstat(descriptor)
                    held_identity = (held.st_dev, held.st_ino)
                    if held_identity == self._terminal_identity:
                        continue
                    if (
                        stat.S_ISREG(held.st_mode)
                        and held.st_uid == os.getuid()
                        and held.st_nlink == 1
                    ):
                        _set_user_immutable(descriptor, True)
                        os.fsync(descriptor)
                finally:
                    os.close(descriptor)

        seal_regular_leaves(self._package_fd)
        directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            directory_flags |= os.O_CLOEXEC
        # These are the only authority-owned child directories in the frozen
        # package DAG.  Unknown or recursively nested hostile directories are
        # not traversed and therefore cannot prevent truthful terminalization.
        for child in ("primary", "secondary", "identity"):
            try:
                child_fd = os.open(
                    child, directory_flags, dir_fd=self._package_fd
                )
            except OSError:
                continue
            try:
                observed = os.fstat(child_fd)
                if (
                    not stat.S_ISDIR(observed.st_mode)
                    or observed.st_uid != os.getuid()
                ):
                    continue
                seal_regular_leaves(child_fd)
                _set_user_immutable(child_fd, True)
                os.fsync(child_fd)
            finally:
                os.close(child_fd)
        os.fsync(self._package_fd)

    def _commit_reserved_success_terminal(
        self,
        descriptor: int,
        value: Mapping[str, object],
        stop: _StopBoundary,
        expected_sha256: str,
    ) -> None:
        """Commit an immutable success terminal with no mutable durability gap."""
        if self._package_fd is None or self._package_identity is None:
            raise RuntimeError("package storage is not prepared")
        if type(stop) is not _StopBoundary or stop.terminal_banked:
            raise TypeError("uncommitted package stop boundary required")
        if type(descriptor) is not int:
            raise TypeError("reserved success terminal descriptor")
        if (
            descriptor != self._terminal_fd
            or self._terminal_identity is None
        ):
            raise ValueError("held package terminal authority")
        raw = _canonical_bytes(dict(value))
        digest = _sha(raw)
        if digest != expected_sha256 or _HEX64.fullmatch(digest) is None:
            raise ValueError("package terminal digest")
        package = os.fstat(self._package_fd)
        if not bool(package.st_flags & stat.UF_IMMUTABLE):
            raise ValueError("package root is not immutable")
        observed = os.fstat(descriptor)
        canonical = os.stat(
            "package-terminal.json",
            dir_fd=self._package_fd,
            follow_symlinks=False,
        )
        if (
            (observed.st_dev, observed.st_ino) != self._terminal_identity
            or (canonical.st_dev, canonical.st_ino) != self._terminal_identity
            or observed.st_size != 0
            or not bool(observed.st_flags & stat.UF_IMMUTABLE)
        ):
            raise ValueError("reserved package terminal identity")
        _set_user_immutable(descriptor, False)
        if os.lseek(descriptor, 0, os.SEEK_SET) != 0:
            raise OSError("package success terminal offset")
        view = memoryview(raw)
        written = 0
        while written < len(view):
            count = os.write(descriptor, view[written:])
            if count <= 0:
                raise OSError("short package terminal write")
            written += count
        observed = os.fstat(descriptor)
        if (
            not stat.S_ISREG(observed.st_mode)
            or observed.st_nlink != 1
            or observed.st_size != len(raw)
        ):
            raise ValueError("package terminal identity")
        # Seal before the authoritative readback.  Even a mutation racing the
        # seal transition is therefore rejected or detected by the exact
        # size/content check.
        _set_user_immutable(descriptor, True)
        sealed = os.fstat(descriptor)
        if sealed.st_size != len(raw):
            raise ValueError("package terminal sealed identity")
        os.lseek(descriptor, 0, os.SEEK_SET)
        chunks: list[bytes] = []
        remaining = len(raw)
        while remaining:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                raise OSError("short package terminal readback")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1) or b"".join(chunks) != raw:
            raise ValueError("package terminal readback")
        os.fsync(descriptor)
        os.fsync(self._package_fd)
        self._downgrade_terminal_to_read_only(descriptor, len(raw))
        stop.terminal_banked = True

    def _downgrade_terminal_to_read_only(
        self, writer_descriptor: int, expected_size: int
    ) -> None:
        """Close terminal write authority before an outcome becomes terminal."""
        if (
            self._package_fd is None
            or self._terminal_fd != writer_descriptor
            or self._terminal_identity is None
            or type(expected_size) is not int
            or expected_size < 1
        ):
            raise ValueError("terminal writer downgrade authority")
        flags = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        reader = os.open(
            "package-terminal.json", flags, dir_fd=self._package_fd
        )
        try:
            observed = os.fstat(reader)
            if (
                (observed.st_dev, observed.st_ino) != self._terminal_identity
                or not stat.S_ISREG(observed.st_mode)
                or observed.st_nlink != 1
                or observed.st_uid != os.getuid()
                or observed.st_size != expected_size
                or not bool(observed.st_flags & stat.UF_IMMUTABLE)
            ):
                raise ValueError("terminal read-only identity")
            try:
                os.close(writer_descriptor)
            except BaseException as close_error:
                # POSIX close errors can leave descriptor state ambiguous, and
                # a diagnostic wrapper may report failure after the kernel has
                # already retired the descriptor.  Retain the verified reader,
                # determine the old writer's actual state, and use the kernel
                # close primitive once if it remains live.  A confirmed EBADF
                # means the write authority is gone and must not reclassify the
                # already durable terminal.
                try:
                    os.fstat(writer_descriptor)
                except OSError as state_error:
                    if state_error.errno != errno.EBADF:
                        raise close_error
                else:
                    libc = ctypes.CDLL(None, use_errno=True)
                    kernel_close = libc.close
                    kernel_close.argtypes = [ctypes.c_int]
                    kernel_close.restype = ctypes.c_int
                    if kernel_close(writer_descriptor) != 0:
                        kernel_error = ctypes.get_errno()
                        try:
                            os.fstat(writer_descriptor)
                        except OSError as state_error:
                            if state_error.errno != errno.EBADF:
                                raise close_error
                        else:
                            raise OSError(
                                kernel_error,
                                os.strerror(kernel_error),
                            ) from close_error
        except BaseException:
            os.close(reader)
            raise
        self._terminal_fd = reader
        # This assignment is the in-memory commit discriminator.  Every
        # fallible identity, content, immutability, and durability check has
        # already passed, and no writable terminal descriptor remains.
        self._terminal_writer_retired = True

    def _bank_failure_terminal(self, value: Mapping[str, object]) -> None:
        """Commit one failure outcome through the package-start reservation."""
        descriptor = self._terminal_fd
        identity = self._terminal_identity
        if (
            self._package_fd is None
            or descriptor is None
            or identity is None
        ):
            raise RuntimeError("reserved package terminal required")
        raw = _canonical_bytes(dict(value))
        observed = os.fstat(descriptor)
        canonical = os.stat(
            "package-terminal.json",
            dir_fd=self._package_fd,
            follow_symlinks=False,
        )
        if (
            (observed.st_dev, observed.st_ino) != identity
            or (canonical.st_dev, canonical.st_ino) != identity
            or observed.st_size != 0
            or not bool(observed.st_flags & stat.UF_IMMUTABLE)
        ):
            raise ValueError("reserved package terminal identity")
        _set_user_immutable(self._package_fd, True)
        self._seal_failure_durable_prefix(descriptor)
        _set_user_immutable(descriptor, False)
        if os.lseek(descriptor, 0, os.SEEK_SET) != 0:
            raise OSError("package failure terminal offset")
        view = memoryview(raw)
        written = 0
        while written < len(view):
            count = os.write(descriptor, view[written:])
            if count <= 0:
                raise OSError("short package failure terminal write")
            written += count
        _set_user_immutable(descriptor, True)
        os.lseek(descriptor, 0, os.SEEK_SET)
        chunks: list[bytes] = []
        remaining = len(raw)
        while remaining:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                raise OSError("short package failure terminal readback")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1) or b"".join(chunks) != raw:
            raise ValueError("package failure terminal readback")
        os.fsync(descriptor)
        os.fsync(self._package_fd)
        self._downgrade_terminal_to_read_only(descriptor, len(raw))

    def read(self, leaf: str, *, maximum_bytes: int = 1_048_576) -> bytes:
        """Read one package-root leaf through the held package descriptor."""
        if (
            type(leaf) is not str
            or leaf in {"", ".", ".."}
            or "/" in leaf
            or "\\" in leaf
            or type(maximum_bytes) is not int
            or maximum_bytes < 1
        ):
            raise ValueError("canonical package read")
        if self._package_fd is None:
            raise RuntimeError("package storage is not prepared")
        self._verify_package_path_identity()
        flags = os.O_RDONLY | os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        descriptor = os.open(leaf, flags, dir_fd=self._package_fd)
        try:
            before = os.fstat(descriptor)
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_nlink != 1
                or before.st_size > maximum_bytes
            ):
                raise ValueError("package read identity")
            chunks: list[bytes] = []
            remaining = before.st_size
            while remaining:
                chunk = os.read(descriptor, min(65_536, remaining))
                if not chunk:
                    raise OSError("short package read")
                chunks.append(chunk)
                remaining -= len(chunk)
            if os.read(descriptor, 1):
                raise ValueError("package read excess bytes")
            after = os.fstat(descriptor)
            canonical = os.stat(
                leaf, dir_fd=self._package_fd, follow_symlinks=False
            )
            identity = lambda item: (
                item.st_dev,
                item.st_ino,
                item.st_mode,
                item.st_size,
                item.st_mtime_ns,
                item.st_ctime_ns,
            )
            if identity(before) != identity(after) or (
                canonical.st_dev,
                canonical.st_ino,
            ) != (after.st_dev, after.st_ino):
                raise RuntimeError("package read identity changed")
            return b"".join(chunks)
        finally:
            os.close(descriptor)
            self._verify_package_path_identity()

    def anchored_path_call(
        self, child: str, operation: Callable[[Path], _AnchoredResult]
    ) -> _AnchoredResult:
        """Run a path-only API below a descriptor-held package directory.

        Darwin's ``pthread_fchdir_np`` supplies a thread-local working
        directory.  The unchanged legacy path-only APIs therefore resolve the
        relative child below the held package descriptor without changing the
        process-wide working directory or relying on non-traversable
        ``/dev/fd/<directory>`` paths.
        """
        if (
            type(child) is not str
            or child in {"", ".", ".."}
            or "/" in child
            or "\\" in child
        ):
            raise ValueError("canonical anchored child")
        if self._package_fd is None:
            raise RuntimeError("package storage is not prepared")
        flags = os.O_RDONLY | os.O_DIRECTORY
        flags |= os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        try:
            os.mkdir(child, mode=0o700, dir_fd=self._package_fd)
        except FileExistsError:
            pass
        target_fd = os.open(child, flags, dir_fd=self._package_fd)
        pthread_fchdir = _pthread_fchdir_callable()
        anchored = False
        try:
            self._verify_package_path_identity()
            target_identity = os.fstat(target_fd)
            if (
                not stat.S_ISDIR(target_identity.st_mode)
                or target_identity.st_uid != os.getuid()
            ):
                raise ValueError("anchored child directory identity")
            if pthread_fchdir(self._package_fd) != 0:
                error = ctypes.get_errno()
                raise OSError(error, os.strerror(error))
            anchored = True
            result = operation(Path(child))
            after = os.fstat(target_fd)
            canonical_target = os.stat(
                child, dir_fd=self._package_fd, follow_symlinks=False
            )
            if (
                (after.st_dev, after.st_ino)
                != (target_identity.st_dev, target_identity.st_ino)
                or (canonical_target.st_dev, canonical_target.st_ino)
                != (after.st_dev, after.st_ino)
            ):
                raise RuntimeError("anchored child directory identity changed")
            self._seal_held_directory_tree(target_fd)
            self._verify_package_path_identity()
            return result
        finally:
            if anchored and pthread_fchdir(-1) != 0:
                error = ctypes.get_errno()
                os.close(target_fd)
                raise OSError(error, os.strerror(error))
            os.close(target_fd)

    def anchored_pair_call(
        self,
        first: str,
        second: str,
        operation: Callable[[Path, Path], _AnchoredResult],
    ) -> _AnchoredResult:
        """Invoke a two-directory consumer under one thread-local anchor."""
        for child in (first, second):
            if (
                type(child) is not str
                or child in {"", ".", ".."}
                or "/" in child
                or "\\" in child
            ):
                raise ValueError("canonical anchored child")
        if self._package_fd is None:
            raise RuntimeError("package storage is not prepared")
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        descriptors: list[int] = []
        identities: list[os.stat_result] = []
        pthread_fchdir = _pthread_fchdir_callable()
        anchored = False
        try:
            for child in (first, second):
                descriptor = os.open(child, flags, dir_fd=self._package_fd)
                observed = os.fstat(descriptor)
                if not stat.S_ISDIR(observed.st_mode):
                    os.close(descriptor)
                    raise ValueError("anchored pair directory identity")
                descriptors.append(descriptor)
                identities.append(observed)
            self._verify_package_path_identity()
            if pthread_fchdir(self._package_fd) != 0:
                error = ctypes.get_errno()
                raise OSError(error, os.strerror(error))
            anchored = True
            result = operation(Path(first), Path(second))
            for child, descriptor, before in zip(
                (first, second), descriptors, identities, strict=True
            ):
                after = os.fstat(descriptor)
                canonical = os.stat(
                    child, dir_fd=self._package_fd, follow_symlinks=False
                )
                if (
                    (after.st_dev, after.st_ino) != (before.st_dev, before.st_ino)
                    or (canonical.st_dev, canonical.st_ino)
                    != (after.st_dev, after.st_ino)
                ):
                    raise RuntimeError("anchored pair directory identity changed")
            self._verify_package_path_identity()
            return result
        finally:
            if anchored and pthread_fchdir(-1) != 0:
                error = ctypes.get_errno()
                for descriptor in reversed(descriptors):
                    os.close(descriptor)
                raise OSError(error, os.strerror(error))
            for descriptor in reversed(descriptors):
                os.close(descriptor)

    def anchored_new_path_call(
        self, child: str, operation: Callable[[Path], _AnchoredResult]
    ) -> _AnchoredResult:
        """Run an unchanged API that exclusively creates its directory."""
        if (
            type(child) is not str
            or child in {"", ".", ".."}
            or "/" in child
            or "\\" in child
        ):
            raise ValueError("canonical anchored child")
        if self._package_fd is None:
            raise RuntimeError("package storage is not prepared")
        try:
            os.stat(child, dir_fd=self._package_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise FileExistsError("anchored child already exists")
        pthread_fchdir = _pthread_fchdir_callable()
        anchored = False
        target_fd = -1
        try:
            self._verify_package_path_identity()
            if pthread_fchdir(self._package_fd) != 0:
                error = ctypes.get_errno()
                raise OSError(error, os.strerror(error))
            anchored = True
            result = operation(Path(child))
            flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
            if hasattr(os, "O_CLOEXEC"):
                flags |= os.O_CLOEXEC
            target_fd = os.open(child, flags, dir_fd=self._package_fd)
            target = os.fstat(target_fd)
            canonical = os.stat(
                child, dir_fd=self._package_fd, follow_symlinks=False
            )
            if (
                not stat.S_ISDIR(target.st_mode)
                or target.st_uid != os.getuid()
                or (canonical.st_dev, canonical.st_ino)
                != (target.st_dev, target.st_ino)
            ):
                raise RuntimeError("new anchored child directory identity")
            self._seal_held_directory_tree(target_fd)
            self._verify_package_path_identity()
            return result
        finally:
            if anchored and pthread_fchdir(-1) != 0:
                error = ctypes.get_errno()
                if target_fd >= 0:
                    os.close(target_fd)
                raise OSError(error, os.strerror(error))
            if target_fd >= 0:
                os.close(target_fd)


class _SyntheticStorageBinding(_StorageBinding):
    """The sole storage seam; it is sealed and qualification-only."""

    __slots__ = ("_qualification_root",)

    def __new__(cls, seal: object = None, *args: object):
        del args
        if seal is not _SYNTHETIC_STORAGE_SEAL:
            raise TypeError("synthetic storage is qualification-created")
        return super().__new__(cls)

    def __init__(self, seal: object, qualification_root: Path, package_key: str) -> None:
        del seal
        resolved = qualification_root.resolve(strict=True)
        live = _LIVE_PACKAGE_PARENT
        if (
            qualification_root.is_symlink()
            or not resolved.is_dir()
            or resolved == live
            or resolved in live.parents
            or live in resolved.parents
        ):
            raise ValueError("synthetic storage/live storage separation")
        package = resolved / f"minimum-gate-{package_key}"
        self._qualification_root = resolved
        super().__init__(package, "SYNTHETIC")

    def prepare(self) -> None:
        if self.scope != "SYNTHETIC":
            raise TypeError("synthetic storage authority")
        super().prepare()
        if not self.package_directory.resolve().is_relative_to(self._qualification_root):
            raise ValueError("synthetic storage escape")

    def close(self) -> None:
        """Unseal graph-owned test leaves only after the public path returns."""
        try:
            if self._package_fd is not None and self._terminal_fd is not None:
                _set_user_immutable(self._package_fd, False)
                self._set_existing_leaf_immutability(
                    False, verify_canonical_path=False
                )
        finally:
            super().close()


@dataclass(frozen=True)
class _IdentityOutcome:
    authority: _ValidatedIdentityAuthority
    leases: _LeaseSet
    report: Mapping[str, object]
    read_receipts: tuple[dict[str, object], ...]
    identity_receipt_sha256: str
    identity_terminal_sha256: str
    access_census_sha256: str


class _IdentityHandoffFailure(RuntimeError):
    """Carry descriptor-release evidence across a failed identity handoff."""

    def __init__(
        self,
        release_sha256: str | None,
        release_outcome: Mapping[str, object],
        cause: BaseException,
        release_evidence_error: BaseException | None,
    ) -> None:
        super().__init__("checkpoint identity evidence handoff failed")
        self.release_sha256 = release_sha256
        self.release_outcome = MappingProxyType(dict(release_outcome))
        self.cause_type = type(cause).__name__
        self.cause_detail = str(cause)
        self.release_evidence_error_type = (
            type(release_evidence_error).__name__
            if release_evidence_error is not None
            else None
        )


def _emergency_release_value(
    failed_stage: str, release: Mapping[str, object]
) -> dict[str, object]:
    no_leases = (
        release.get("result") == "NO_LEASES_ACQUIRED"
        and release.get("attempted_closures") == 0
        and release.get("successful_closures") == 0
        and release.get("duplicate_closures") == 0
        and release.get("unknown_leases") == 0
        and release.get("live_leases_after_release") == 0
    )
    complete_release = (
        release.get("result") == "PASS"
        and release.get("attempted_closures") == 5
        and release.get("successful_closures") == 5
        and release.get("duplicate_closures") == 0
        and release.get("unknown_leases") == 0
        and release.get("live_leases_after_release") == 0
    )
    return {
        "schema": "pulsarmlx.f017.event06-minimum-gate-emergency-release/1.0.0",
        "failed_stage": failed_stage,
        "attempted_closures": release.get("attempted_closures"),
        "successful_closures": release.get("successful_closures"),
        "duplicate_closes": release.get("duplicate_closures"),
        "unknown_leases": release.get("unknown_leases"),
        "live_leases": release.get("live_leases_after_release"),
        "release_result": release.get("result"),
        "release_disposition": release.get("release_disposition"),
        "result": "PASS" if no_leases or complete_release else "FAIL",
    }


class _ProductionCheckpointEffect:
    __slots__ = ("_qualification_interceptor",)

    def __init__(self, qualification_interceptor: object | None = None) -> None:
        if qualification_interceptor is not None and type(
            qualification_interceptor
        ) is not _SyntheticCheckpointProvider:
            raise TypeError("sealed checkpoint interceptor required")
        self._qualification_interceptor = qualification_interceptor

    def run(self, consumed_gate: object, authority: _ValidatedIdentityAuthority,
            storage: _StorageBinding) -> _IdentityOutcome:
        _require_consumed_gate(consumed_gate, authority)
        if self._qualification_interceptor is not None:
            self._qualification_interceptor.intercept_physical_call(
                _run_identity_stage, consumed_gate, authority, storage
            )
            raise AssertionError("checkpoint interceptor returned")
        leases: _LeaseSet | None = None

        def produce(evidence_directory: Path) -> tuple[_LeaseSet, dict[str, object]]:
            nonlocal leases
            outcome = _run_identity_stage(
                authority,
                package_attempt_id=str(authority.get("package_attempt_id")),
                package_durable_start=True,
                evidence_directory=evidence_directory,
            )
            leases = outcome[0]
            return outcome

        try:
            leases, report = cast(
                tuple[_LeaseSet, dict[str, object]],
                storage.anchored_new_path_call("identity", produce),
            )
            return _identity_outcome_from_report(
                authority, leases, report, storage
            )
        except BaseException as exc:
            if leases is None:
                raise
            release_sha256: str | None = None
            release_evidence_error: BaseException | None = None
            release: Mapping[str, object] = {
                "attempted_closures": 0,
                "successful_closures": sum(
                    record.state == "CLOSED" for record in leases.records
                ),
                "duplicate_closures": 0,
                "unknown_leases": sum(
                    record.state == "UNKNOWN" for record in leases.records
                ),
                "live_leases_after_release": sum(
                    record.state != "CLOSED" for record in leases.records
                ),
                "result": "NOT_ATTEMPTED",
            }
            if not leases.closed:
                try:
                    release = leases.release()
                except BaseException as release_error:
                    release_evidence_error = release_error
                    release = {
                        "attempted_closures": sum(
                            record.close_attempt_count > 0
                            for record in leases.records
                        ),
                        "successful_closures": sum(
                            record.state == "CLOSED" for record in leases.records
                        ),
                        "duplicate_closures": 0,
                        "unknown_leases": sum(
                            record.state == "UNKNOWN" for record in leases.records
                        ),
                        "live_leases_after_release": sum(
                            record.state != "CLOSED" for record in leases.records
                        ),
                        "result": "RELEASE_EXCEPTION",
                    }
                try:
                    release_sha256 = storage.bank_failure(
                        "emergency-release-report.json",
                        _emergency_release_value("IDENTITY_TERMINAL", release),
                    )
                except BaseException as bank_error:
                    if release_evidence_error is None:
                        release_evidence_error = bank_error
                    release_sha256 = None
            raise _IdentityHandoffFailure(
                release_sha256,
                release,
                exc,
                release_evidence_error,
            ) from exc


class _SyntheticCheckpointProvider:
    """The sole checkpoint seam; no production authority can reach it."""

    __slots__ = ("_intercept", "preopen_intercepted")

    def __new__(cls, seal: object = None, *args: object, **kwargs: object):
        del args, kwargs
        if seal is not _SYNTHETIC_CHECKPOINT_SEAL:
            raise TypeError("synthetic checkpoint provider is qualification-created")
        return super().__new__(cls)

    def __init__(self, seal: object, *, intercept: bool) -> None:
        del seal
        self._intercept = intercept
        self.preopen_intercepted = False

    def run(self, consumed_gate: object, authority: _ValidatedIdentityAuthority,
            storage: _StorageBinding) -> _IdentityOutcome:
        _require_consumed_gate(consumed_gate, authority)
        if authority.get("authority_scope") != "SYNTHETIC" or storage.scope != "SYNTHETIC":
            raise TypeError("synthetic checkpoint provider rejects production authority")
        root = Path(str(authority.get("checkpoint_root")))
        if not root.resolve(strict=True).is_relative_to(storage.package_directory.parent.resolve(strict=True)):
            raise ValueError("synthetic checkpoint root authority")
        # This is the immediate call boundary for the unchanged physical
        # identity producer.  The interception case proves the exact input and
        # deliberately does not invoke _run_identity_stage.
        if self._intercept:
            raise AssertionError("interception must traverse production call boundary")
        # The no-access case is bound only to the installed synthetic identity
        # authority.  It never borrows production shard metadata or resolves
        # the production root.
        shards = [dict(item) for item in _authority_profile(synthetic=True).shards]
        package = str(authority.get("package_attempt_id"))
        descriptors = [
            {
                "device": 39,
                "inode": 39_000 + ordinal,
                "mode": stat.S_IFREG | 0o600,
                "size": int(shards[ordinal - 1]["size_bytes"]),
                "mtime_ns": ordinal,
                "ctime_ns": ordinal,
                "shard_ordinal": ordinal,
                "role": "GRAPH_PAYLOAD",
                "lease_id": f"LEASE-{package}-{ordinal}",
            }
            for ordinal in range(2, 7)
        ]
        leases = _LeaseSet(
            [_LeaseRecord(item, 39_000 + int(item["shard_ordinal"])) for item in descriptors],
            str(shards[0]["sha256"]),
            [str(item["sha256"]) for item in shards[1:]],
        )
        read_receipts = tuple(
            {
                "schema": "pulsarmlx.f017.event06-minimum-identity-read-receipt/1.0.0",
                "ordinal": ordinal,
                "role": str(item["role"]),
                "byte_count": int(item["size_bytes"]),
                "sha256": str(item["sha256"]),
                "result": "PASS",
            }
            for ordinal, item in enumerate(shards, start=1)
        )
        read_receipt_document = {
            "schema": "pulsarmlx.f017.event06-minimum-identity-read-receipts/1.0.0",
            "package_attempt_id": package,
            "receipts": list(read_receipts),
            "result": "PASS",
        }
        read_receipt_sha = storage.bank(
            "identity-read-receipts.json", read_receipt_document
        )
        access_document = {
            "schema": "pulsarmlx.f017.event06-minimum-identity-access-census/1.0.0",
            "package_attempt_id": package,
            "checkpoint_root_resolutions": 0,
            "physical_checkpoint_opens": 0,
            "physical_checkpoint_reads": 0,
            "physical_checkpoint_mmaps": 0,
            "synthetic_receipt_count": 6,
            "result": "PASS",
        }
        access_sha = storage.bank("identity-access-census.json", access_document)
        identity_receipt = {
            "schema": "pulsarmlx.f017.event06-minimum-identity-receipt/1.0.0",
            "package_attempt_id": package,
            "identity_read_receipts_sha256": read_receipt_sha,
            "access_census_sha256": access_sha,
            "retained_graph_leases": 5,
            "result": "PASS",
        }
        identity_receipt_sha = storage.bank("identity-receipt.json", identity_receipt)
        identity_terminal = {
            "schema": "pulsarmlx.f017.event06-minimum-identity-terminal/1.0.0",
            "package_attempt_id": package,
            "identity_receipt_sha256": identity_receipt_sha,
            "state": "COMPLETE",
            "result": "PASS",
        }
        identity_terminal_sha = storage.bank("identity-terminal.json", identity_terminal)
        evidence = {
            "access_journal_sha256": access_sha,
            "shard_receipts_sha256": read_receipt_sha,
            "lease_manifest_sha256": _contract_sha256(descriptors),
            "deterministic_core_sha256": _contract_sha256(
                {"checkpoint_provider": "INTERPOSED", "physical_open": False}
            ),
            "identity_manifest_sha256": _contract_sha256(
                {"package_attempt_id": package, "receipts": list(read_receipts)}
            ),
            "identity_receipt_sha256": identity_receipt_sha,
            "identity_terminal_sha256": identity_terminal_sha,
            "identity_terminal_state": "COMPLETE",
        }
        report = {
            "result": "PASS",
            "authority_scope": "SYNTHETIC",
            "operation_class": "QUALIFICATION_IDENTITY_BOUNDARY_INTERPOSE",
            "generation": "V12",
            "ordered_shard_digests": [str(item["sha256"]) for item in shards],
            "checkpoint_shard_opens": 6,
            "checkpoint_identity_hash_reads": 6,
            "retained_lease_count": 5,
            "identity_only_retained_count": 0,
            "descriptor_identities": descriptors,
            "path_reopen_count": 0,
            "evidence": evidence,
        }
        return _IdentityOutcome(
            authority,
            leases,
            MappingProxyType(report),
            read_receipts,
            identity_receipt_sha,
            identity_terminal_sha,
            access_sha,
        )

    def intercept_physical_call(
        self,
        physical_callable: object,
        consumed_gate: object,
        authority: _ValidatedIdentityAuthority,
        storage: _StorageBinding,
    ) -> Never:
        """Abort at the instruction immediately preceding the physical call."""
        _require_consumed_gate(consumed_gate, authority)
        if (
            self._intercept is not True
            or physical_callable is not _run_identity_stage
            or authority.get("authority_scope") != "SYNTHETIC"
            or storage.scope != "SYNTHETIC"
        ):
            raise TypeError("exact synthetic pre-open interception authority")
        root = Path(str(authority.get("checkpoint_root"))).resolve(strict=True)
        if not root.is_relative_to(storage.package_directory.parent.resolve(strict=True)):
            raise ValueError("pre-open fixture substitution")
        self.preopen_intercepted = True
        raise RuntimeError("PREOPEN_INTERCEPTED")


class _ProductionNumericalEffect:
    __slots__ = ()

    def primary(self, bridge: _ValidatedBridge, identity: _IdentityOutcome,
                storage: _StorageBinding, start_sha256: str) -> dict[str, object]:
        candidate = _target_candidate(bridge)
        return cast(
            dict[str, object],
            storage.anchored_path_call(
                "primary",
                lambda output_directory: _execute_primary_target(
                    candidate,
                    identity.leases.descriptors,
                    identity.leases.inherited_fds(),
                    output_directory,
                    authorization_id=str(bridge.get("authorization_id")),
                    package_attempt_id=str(bridge.get("package_attempt_id")),
                    consumer_event_id=str(bridge.get("primary_event_id")),
                    producer_measurement_sha256=str(
                        bridge.get("primary_numerical_sha256")
                    ),
                    durable_start_sha256=start_sha256,
                    access_census_sha256=identity.access_census_sha256,
                ),
            ),
        )

    def secondary(self, bridge: _ValidatedBridge, identity: _IdentityOutcome,
                  primary: Mapping[str, object], storage: _StorageBinding,
                  start_sha256: str) -> dict[str, object]:
        candidate = _target_candidate(bridge)
        artifacts = primary["artifacts"]
        index = primary["index"]
        return cast(
            dict[str, object],
            storage.anchored_path_call(
                "secondary",
                lambda output_directory: _execute_secondary_target(
                    candidate,
                    identity.leases.descriptors,
                    identity.leases.inherited_fds(),
                    output_directory,
                    authorization_id=str(bridge.get("authorization_id")),
                    package_attempt_id=str(bridge.get("package_attempt_id")),
                    consumer_event_id=str(bridge.get("secondary_event_id")),
                    producer_measurement_sha256=str(
                        bridge.get("secondary_numerical_sha256")
                    ),
                    durable_start_sha256=start_sha256,
                    access_census_sha256=identity.access_census_sha256,
                    primary_terminal=artifacts["consumer_terminal"],
                    primary_result_terminal_sha256=index[
                        "result_terminal_sha256"
                    ],
                    primary_receipt_sha256=index["result_receipt_sha256"],
                    primary_manifest_sha256=index["manifest_sha256"],
                    use_mlx=False,
                ),
            ),
        )


class _SyntheticNumericalProvider:
    """The sole numerical seam; it banks real V11 bundles from fake outputs."""

    __slots__ = ("_seed", "executions")

    def __new__(cls, seal: object = None, *args: object):
        del args
        if seal is not _SYNTHETIC_NUMERICAL_SEAL:
            raise TypeError("synthetic numerical provider is qualification-created")
        return super().__new__(cls)

    def __init__(self, seal: object, seed: int = 39_001) -> None:
        del seal
        self._seed = seed
        self.executions = {"PRIMARY": 0, "SECONDARY": 0}

    def _bank(self, role: str, bridge: _ValidatedBridge, identity: _IdentityOutcome,
              storage: _StorageBinding, start_sha256: str) -> dict[str, object]:
        if bridge.get("authority_scope") != "SYNTHETIC" or storage.scope != "SYNTHETIC":
            raise TypeError("synthetic numerical provider rejects production authority")
        self.executions[role] += 1
        if self.executions[role] != 1:
            raise ValueError("synthetic numerical execution repeated")
        # Qualification-only fixture code is imported only after the sealed
        # synthetic provider has rejected every production authority.
        from f017_v11_full_geometry_fixture import make_output

        output = make_output(role, "SMALL_NORMALS", self._seed)
        return cast(
            dict[str, object],
            storage.anchored_path_call(
                role.lower(),
                lambda output_directory: _bank_output_bundle(
                    output,
                    output_directory,
                    authorization_id=str(bridge.get("authorization_id")),
                    package_attempt_id=str(bridge.get("package_attempt_id")),
                    consumer_event_id=str(bridge.get(f"{role.lower()}_event_id")),
                    producer_measurement_sha256=str(
                        bridge.get(f"{role.lower()}_numerical_sha256")
                    ),
                    durable_start_sha256=start_sha256,
                    access_census_sha256=identity.access_census_sha256,
                    numerical_contract_sha256=str(
                        bridge.get("numerical_acceptance_contract_sha256")
                    ),
                    _write_once=True,
                ),
            ),
        )

    def primary(self, bridge: _ValidatedBridge, identity: _IdentityOutcome,
                storage: _StorageBinding, start_sha256: str) -> dict[str, object]:
        return self._bank("PRIMARY", bridge, identity, storage, start_sha256)

    def secondary(self, bridge: _ValidatedBridge, identity: _IdentityOutcome,
                  primary: Mapping[str, object], storage: _StorageBinding,
                  start_sha256: str) -> dict[str, object]:
        if primary["artifacts"]["consumer_terminal"].get("result") != "COMPLETE":
            raise ValueError("secondary requires complete primary consumer terminal")
        return self._bank("SECONDARY", bridge, identity, storage, start_sha256)


class _MinimumOneShotState:
    """Single-purpose successor to the superseded live-installation ceremony."""

    __slots__ = ("scope", "_package_starts")

    def __new__(cls, seal: object = None, *args: object):
        del args
        if seal is not _ONE_SHOT_STATE_SEAL:
            raise TypeError("one-shot state is coordinator-created")
        return super().__new__(cls)

    def __init__(self, seal: object, scope: str) -> None:
        del seal
        if scope not in {"PRODUCTION", "SYNTHETIC"}:
            raise ValueError("one-shot state scope")
        self.scope = scope
        self._package_starts = 0

    def snapshot(self) -> MappingProxyType[str, int]:
        return MappingProxyType({"package_starts": self._package_starts})

    def consume_package_start(self) -> None:
        if self._package_starts != 0:
            raise RuntimeError("package-start authority already consumed")
        self._package_starts = 1


@dataclass(frozen=True)
class _Runtime:
    scope: str
    profile: _AuthorityProfile
    storage: _StorageBinding
    package_claim_sha256: str
    checkpoint_effect: object
    numerical_effect: object
    integration_state: object
    fault_stage: str | None = None
    observed_effects: dict[str, int] = field(default_factory=lambda: {
        "checkpoint_root_resolutions": 0,
        "checkpoint_opens": 0,
        "numerical_executions": 0,
        "synthetic_identities_instantiated": 0,
    })


@dataclass(frozen=True)
class _QualificationInvocation:
    """Context-local, sealed substitution for the three private test seams."""

    seal: object
    runtime: _Runtime
    now_unix_ns: int
    collapsed_go_sha256: str

    def __post_init__(self) -> None:
        runtime = self.runtime
        if (
            self.seal is not _QUALIFICATION_INVOCATION_SEAL
            or runtime.scope != "SYNTHETIC"
            or type(runtime.storage) is not _SyntheticStorageBinding
            or type(runtime.numerical_effect) is not _SyntheticNumericalProvider
            or type(self.now_unix_ns) is not int
            or self.now_unix_ns < 0
            or _HEX64.fullmatch(self.collapsed_go_sha256) is None
        ):
            raise TypeError("sealed synthetic qualification invocation")
        checkpoint = runtime.checkpoint_effect
        if type(checkpoint) is _SyntheticCheckpointProvider:
            pass
        elif (
            type(checkpoint) is not _ProductionCheckpointEffect
            or type(checkpoint._qualification_interceptor)
            is not _SyntheticCheckpointProvider
        ):
            raise TypeError("qualification checkpoint seam")
        package = runtime.storage.package_directory.resolve()
        if package == _LIVE_PACKAGE_PARENT or package.is_relative_to(_LIVE_PACKAGE_PARENT):
            raise ValueError("qualification may not address live package storage")


_QUALIFICATION_INVOCATION: ContextVar[_QualificationInvocation | None] = ContextVar(
    "f017_event06_minimum_gate_qualification_invocation", default=None
)


@dataclass
class _StopBoundary:
    storage: _StorageBinding
    package_started: bool = False
    terminal_banked: bool = False
    current_stage: str = "PREFLIGHT"
    receipts: list[tuple[str, str]] = field(default_factory=list)

    def enter(self, stage: str, runtime: _Runtime) -> None:
        if self.terminal_banked:
            raise RuntimeError("package already terminal")
        if stage not in _STAGES:
            raise ValueError("stage vocabulary")
        self.current_stage = stage
        if runtime.fault_stage == stage:
            raise RuntimeError(f"INJECTED_STOP_AT_{stage}")

    def record(self, kind: str, digest: str) -> None:
        if _HEX64.fullmatch(digest) is None:
            raise ValueError("receipt digest")
        self.receipts.append((kind, digest))

    def fail(
        self,
        exc: BaseException,
        runtime: _Runtime,
        emergency_release_sha256: str | None,
        emergency_release_outcome: Mapping[str, object] | None = None,
    ) -> None:
        if not self.package_started or self.terminal_banked:
            return
        if emergency_release_sha256 is not None:
            self.record("EMERGENCY_RELEASE_REPORT", emergency_release_sha256)
        receipt_kinds = {kind for kind, _digest in self.receipts}
        accounting = {
            "schema": (
                "pulsarmlx.f017.event06-minimum-gate-failure-accounting/1.0.0"
            ),
            "failed_stage": self.current_stage,
            "authorization_delta": 0,
            "package_delta": 1,
            "primary_delta": int("PRIMARY_START" in receipt_kinds),
            "secondary_delta": int("SECONDARY_START" in receipt_kinds),
            "historical_master_ledger_before": _HISTORICAL_MASTER_LEDGER,
            "historical_master_ledger_after": _HISTORICAL_MASTER_LEDGER,
            "durable_receipts": [
                {"kind": kind, "sha256": digest} for kind, digest in self.receipts
            ],
            "emergency_release_report_sha256": emergency_release_sha256,
            "emergency_release_outcome": (
                dict(emergency_release_outcome)
                if emergency_release_outcome is not None
                else None
            ),
            "original_checkpoint_root_resolutions": (
                runtime.observed_effects["checkpoint_root_resolutions"]
            ),
            "original_checkpoint_opens": runtime.observed_effects["checkpoint_opens"],
            "real_numerical_executions": runtime.observed_effects[
                "numerical_executions"
            ],
            "fabricated_successor_receipts": 0,
            "result": "FAIL",
        }
        accounting_sha = self.storage.bank_failure(
            "failure-accounting.json", accounting
        )
        value = {
            "schema": "pulsarmlx.f017.event06-minimum-gate-package-terminal/1.0.0",
            "state": "TERMINAL_FAILURE",
            "failed_stage": self.current_stage,
            "failure_type": (
                exc.cause_type
                if isinstance(exc, _IdentityHandoffFailure)
                else type(exc).__name__
            ),
            "failure_wrapper_type": (
                type(exc).__name__
                if isinstance(exc, _IdentityHandoffFailure)
                else None
            ),
            "failure_accounting_sha256": accounting_sha,
            "emergency_release_report_sha256": emergency_release_sha256,
            "emergency_release_result": (
                emergency_release_outcome.get("result")
                if emergency_release_outcome is not None
                else None
            ),
            "emergency_release_disposition": (
                emergency_release_outcome.get("release_disposition")
                if emergency_release_outcome is not None
                else None
            ),
            "fabricated_successor_receipts": 0,
            "result": "FAIL",
        }
        try:
            self.storage._bank_failure_terminal(value)
        except BaseException:
            if not self.storage._terminal_writer_retired:
                raise
        self.terminal_banked = True


def _production_runtime(package_claim_sha256: str, profile: _AuthorityProfile) -> _Runtime:
    # The legacy collapsed-installation state is superseded here because its
    # fixed-root reservation/stat machinery is outside the accepted 17-gate
    # path.  This successor carries only the consumed package-start fact.
    integration = _MinimumOneShotState(_ONE_SHOT_STATE_SEAL, "PRODUCTION")
    storage = _StorageBinding(
        _LIVE_PACKAGE_PARENT / f"package-{package_claim_sha256}", "PRODUCTION"
    )
    return _Runtime(
        "PRODUCTION", profile, storage, package_claim_sha256,
        _ProductionCheckpointEffect(),
        _ProductionNumericalEffect(), integration,
    )


def _qualification_runtime(root: Path, package_claim_sha256: str, *, intercept: bool,
                           fault_stage: str | None = None) -> _Runtime:
    integration = _MinimumOneShotState(_ONE_SHOT_STATE_SEAL, "SYNTHETIC")
    storage = _SyntheticStorageBinding(
        _SYNTHETIC_STORAGE_SEAL, root, package_claim_sha256
    )
    checkpoint_provider = _SyntheticCheckpointProvider(
        _SYNTHETIC_CHECKPOINT_SEAL, intercept=intercept
    )
    checkpoint_effect: object = checkpoint_provider
    if intercept:
        checkpoint_effect = _ProductionCheckpointEffect(checkpoint_provider)
    return _Runtime(
        "SYNTHETIC",
        _authority_profile(synthetic=True),
        storage,
        package_claim_sha256,
        checkpoint_effect,
        _SyntheticNumericalProvider(_SYNTHETIC_NUMERICAL_SEAL),
        integration,
        fault_stage=fault_stage,
    )


def _validate_go_bytes(raw: bytes, profile: _AuthorityProfile,
                       *, now_unix_ns: int | None = None) -> _ValidatedCollapsedGo:
    if type(raw) is not bytes:
        raise TypeError("exact collapsed GO bytes required")
    value = _parse_artifact_bytes(raw)
    if type(value) is not dict or tuple(sorted(value)) != tuple(sorted(_COLLAPSED_GO_FIELDS)):
        raise ValueError("collapsed GO exact eight-field census")
    if _canonical_bytes(value) != raw:
        raise ValueError("collapsed GO canonical bytes")
    if (
        value["schema"] != _COLLAPSED_GO_SCHEMA
        or value["decision"] != _COLLAPSED_GO_DECISION
        or value["scope"] != _COLLAPSED_GO_SCOPE
        or type(value["issued_at_unix_ns"]) is not int
        or type(value["expires_at_unix_ns"]) is not int
        or value["issued_at_unix_ns"] < 0
        or value["expires_at_unix_ns"] <= value["issued_at_unix_ns"]
    ):
        raise ValueError("collapsed GO typed predicate")
    for key in (
        "human_decision_sha256", "release_authority_sha256", "one_shot_nonce_sha256"
    ):
        if type(value[key]) is not str or _HEX64.fullmatch(value[key]) is None:
            raise ValueError(f"collapsed GO digest: {key}")
    if value["release_authority_sha256"] != profile.release_authority_sha256:
        raise ValueError("collapsed GO release authority")
    expected_nonce = _sha(
        b"F017-EVENT06-COLLAPSED-ONE-SHOT\x00"
        + str(value["human_decision_sha256"]).encode("ascii")
        + str(value["release_authority_sha256"]).encode("ascii")
    )
    if value["one_shot_nonce_sha256"] != expected_nonce:
        raise ValueError("collapsed GO one-shot nonce")
    now = time.time_ns() if now_unix_ns is None else now_unix_ns
    if type(now) is not int or now < value["issued_at_unix_ns"] or now >= value["expires_at_unix_ns"]:
        raise ValueError("collapsed GO validity")
    return _ValidatedCollapsedGo(_GO_SEAL, value)


def _validate_fresh_integration_state(state: object, scope: str) -> None:
    if type(state) is not _MinimumOneShotState:
        raise TypeError("minimum one-shot state required")
    snapshot = state.snapshot()
    if (
        scope not in {"PRODUCTION", "SYNTHETIC"}
        or state.scope != scope
        or type(snapshot) is not MappingProxyType
        or dict(snapshot) != {"package_starts": 0}
    ):
        raise ValueError("fresh minimum one-shot state")


def _identities(go: _ValidatedCollapsedGo) -> Mapping[str, str]:
    suffix = go.sha256[:24].upper()
    return MappingProxyType({
        "authorization_id": f"F017-EVENT06-AUTH-{suffix}",
        "package_attempt_id": f"F017-EVENT06-PACKAGE-{suffix}",
        "primary_event_id": f"F017-EVENT06-PRIMARY-{suffix}",
        "secondary_event_id": f"F017-EVENT06-SECONDARY-{suffix}",
    })


def _identity_installed_document(
    go: _ValidatedCollapsedGo,
    runtime: _Runtime,
    checkpoint_root: Path,
) -> dict[str, object]:
    """Build the retained checkpoint-identity authority without readiness ceremony."""
    selected_root = runtime.profile.release_authority.get(
        "selected_checkpoint_root"
    )
    if runtime.scope == "PRODUCTION":
        if selected_root != str(_LIVE_CHECKPOINT_ROOT) or checkpoint_root != _LIVE_CHECKPOINT_ROOT:
            raise ValueError("production checkpoint root authority")
    elif selected_root != "SEALED_SYNTHETIC_RUNTIME_DERIVED":
        raise ValueError("synthetic checkpoint root authority")
    ids = _identities(go)
    shards = runtime.profile.shards
    identity_only = sum(item.get("role") == "IDENTITY_ONLY" for item in shards)
    graph_payload = sum(item.get("role") == "GRAPH_PAYLOAD" for item in shards)
    return {
        "schema": _IDENTITY_INSTALLED_SCHEMA,
        "authority_scope": runtime.scope,
        "operation_class": (
            "CHECKPOINT_IDENTITY_QUALIFICATION"
            if runtime.scope == "SYNTHETIC"
            else "CORRECTED_FULL_CHECKPOINT_ORACLE"
        ),
        "generation": "V12",
        "authorization_id": ids["authorization_id"],
        "package_attempt_id": ids["package_attempt_id"],
        "checkpoint_set_sha256": runtime.profile.checkpoint_set_sha256,
        "checkpoint_root": str(checkpoint_root),
        "checkpoint_identity_contract_path": runtime.profile.checkpoint_contract_path,
        "checkpoint_identity_contract_sha256": (
            runtime.profile.checkpoint_authority_sha256
        ),
        "measured_producer_path": _IDENTITY_PRODUCER,
        "measured_producer_sha256": _file_sha(_IDENTITY_PRODUCER),
        "measured_validator_path": _IDENTITY_VALIDATOR,
        "measured_validator_sha256": _file_sha(_IDENTITY_VALIDATOR),
        "expected_shard_count": len(shards),
        "expected_identity_only_shard_count": identity_only,
        "expected_graph_payload_shard_count": graph_payload,
        "expected_total_bytes": sum(int(item["size_bytes"]) for item in shards),
        "attempts": 1,
        "retries": 0,
        "resume": False,
    }


def _build_installed_authority(go: _ValidatedCollapsedGo, runtime: _Runtime) -> _ValidatedIdentityAuthority:
    checkpoint_root = (
        runtime.storage.package_directory.parent / "synthetic-checkpoint"
        if runtime.scope == "SYNTHETIC" else _LIVE_CHECKPOINT_ROOT
    )
    if runtime.scope == "SYNTHETIC":
        checkpoint_root.mkdir(exist_ok=True)
    installed_value = _identity_installed_document(go, runtime, checkpoint_root)
    installed_expected = dict(installed_value)
    installed_expected.pop("schema")
    installed = _validate_installed_bytes(
        _canonical_bytes(installed_value), installed_expected
    )
    if runtime.scope == "SYNTHETIC":
        runtime.observed_effects["synthetic_identities_instantiated"] += 1
    return installed


def _package_gate(go: _ValidatedCollapsedGo, installed: _ValidatedIdentityAuthority,
                  runtime: _Runtime) -> object:
    ids = _identities(go)
    gate = _build_package_start_gate(
        authorization_id=ids["authorization_id"],
        package_attempt_id=ids["package_attempt_id"],
        primary_event_id=ids["primary_event_id"],
        secondary_event_id=ids["secondary_event_id"],
        collapsed_go_sha256=go.sha256,
        installed_authority_sha256=installed.source_sha256,
        checkpoint_authority_sha256=runtime.profile.checkpoint_authority_sha256,
        numerical_acceptance_contract_sha256=(
            runtime.profile.numerical_acceptance_contract_sha256
        ),
        comparison_rules_sha256=runtime.profile.comparison_rules_sha256,
        result_authority_sha256=runtime.profile.result_authority_sha256,
        preflight_passed=True,
    )
    return _validate_package_start_gate(gate)


def _require_consumed_gate(
    gate: object, authority: _ValidatedIdentityAuthority
) -> object:
    validated = _validate_consumed_package_start_gate(gate)
    if (
        validated.get("state") != "PACKAGE_STARTED"
        or type(authority) is not _ValidatedIdentityAuthority
        or authority.posture != "INSTALLED"
        or validated.get("package_attempt_id") != authority.get("package_attempt_id")
        or validated.get("authorization_id") != authority.get("authorization_id")
        or validated.get("installed_authority_sha256") != authority.source_sha256
        or validated.get("checkpoint_authority_sha256")
        != authority.get("checkpoint_identity_contract_sha256")
    ):
        raise TypeError("exact consumed package-start gate required")
    return validated


def _identity_outcome_from_report(authority: _ValidatedIdentityAuthority,
                                  leases: _LeaseSet, report: Mapping[str, object],
                                  storage: _StorageBinding) -> _IdentityOutcome:
    evidence = report.get("evidence")
    if type(evidence) is not dict:
        raise ValueError("identity evidence")
    validated_evidence = storage.anchored_path_call(
        "identity",
        lambda directory: _validate_banked_identity_evidence(
            directory, dict(report)
        ),
    )
    if (
        validated_evidence.get("result") != "PASS"
        or validated_evidence.get("leaf_count") != 7
        or validated_evidence.get("terminal_sha256")
        != evidence.get("identity_terminal_sha256")
        or validated_evidence.get("deterministic_core_sha256")
        != evidence.get("deterministic_core_sha256")
    ):
        raise ValueError("identity evidence closure")
    receipts_raw = cast(
        bytes,
        storage.anchored_path_call(
            "identity",
            lambda directory: (directory / "shard-receipts.json").read_bytes(),
        ),
    )
    if _sha(receipts_raw) != evidence.get("shard_receipts_sha256"):
        raise ValueError("identity shard-receipt evidence binding")
    receipts_value = _parse_artifact_bytes(receipts_raw)
    raw_receipts = receipts_value.get("receipts") if type(receipts_value) is dict else None
    if type(raw_receipts) is not list:
        raise ValueError("identity per-read receipts")
    receipts = tuple({
        "schema": "pulsarmlx.f017.event06-minimum-identity-read-receipt/1.0.0",
        "ordinal": int(item["ordinal"]),
        "role": str(item["role"]),
        "byte_count": int(item["bytes"]),
        "sha256": str(item["sha256"]),
        "result": "PASS",
    } for item in raw_receipts)
    return _IdentityOutcome(
        authority, leases, MappingProxyType(dict(report)), receipts,
        str(evidence["identity_receipt_sha256"]),
        str(evidence["identity_terminal_sha256"]),
        str(evidence["access_journal_sha256"]),
    )


def _read_banked_document(directory: Path, leaf: str) -> tuple[dict[str, object], str]:
    """Read one canonical control document relative to a stable directory FD."""
    if leaf in {"", ".", ".."} or "/" in leaf or "\\" in leaf:
        raise ValueError("canonical control-document leaf")
    directory_fd = os.open(
        directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    )
    descriptor = -1
    try:
        descriptor = os.open(leaf, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_size > 1_048_576
        ):
            raise ValueError("control-document identity")
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                raise OSError("short control-document read")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise ValueError("control-document excess bytes")
        after = os.fstat(descriptor)
        canonical = os.stat(leaf, dir_fd=directory_fd, follow_symlinks=False)
        identity = lambda item: (
            item.st_dev,
            item.st_ino,
            item.st_mode,
            item.st_size,
            item.st_mtime_ns,
            item.st_ctime_ns,
        )
        if identity(before) != identity(after) or (
            canonical.st_dev,
            canonical.st_ino,
        ) != (after.st_dev, after.st_ino):
            raise RuntimeError("control-document identity changed")
        raw = b"".join(chunks)
        value = _parse_artifact_bytes(raw)
        if type(value) is not dict or _canonical_bytes(value) != raw:
            raise ValueError("canonical control-document bytes")
        return value, _sha(raw)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(directory_fd)


def _validate_identity_evidence_closure(
    identity: _IdentityOutcome, storage: _StorageBinding
) -> dict[str, object]:
    """Revalidate raw identity evidence at each causal closure boundary."""
    evidence = identity.report.get("evidence")
    if type(evidence) is not dict:
        raise ValueError("identity evidence report")
    if identity.authority.get("authority_scope") == "PRODUCTION":
        result = storage.anchored_path_call(
            "identity",
            lambda directory: _validate_banked_identity_evidence(
                directory, dict(identity.report)
            ),
        )
        if (
            result.get("result") != "PASS"
            or result.get("leaf_count") != 7
            or result.get("terminal_sha256")
            != identity.identity_terminal_sha256
            or result.get("deterministic_core_sha256")
            != evidence.get("deterministic_core_sha256")
        ):
            raise ValueError("production identity evidence closure")
        return dict(result)

    names = {
        "identity-read-receipts.json": "read_receipts",
        "identity-access-census.json": "access",
        "identity-receipt.json": "receipt",
        "identity-terminal.json": "terminal",
    }
    documents: dict[str, dict[str, object]] = {}
    digests: dict[str, str] = {}
    for leaf, key in names.items():
        raw = storage.read(leaf)
        value = _parse_artifact_bytes(raw)
        if type(value) is not dict or _canonical_bytes(value) != raw:
            raise ValueError("synthetic identity evidence document")
        documents[key] = value
        digests[key] = _sha(raw)
    package = identity.authority.get("package_attempt_id")
    if (
        documents["read_receipts"].get("package_attempt_id") != package
        or documents["read_receipts"].get("receipts")
        != list(identity.read_receipts)
        or documents["access"].get("package_attempt_id") != package
        or documents["access"].get("checkpoint_root_resolutions") != 0
        or documents["access"].get("physical_checkpoint_opens") != 0
        or documents["access"].get("physical_checkpoint_reads") != 0
        or documents["access"].get("physical_checkpoint_mmaps") != 0
        or documents["receipt"].get("identity_read_receipts_sha256")
        != digests["read_receipts"]
        or documents["receipt"].get("access_census_sha256")
        != digests["access"]
        or documents["terminal"].get("identity_receipt_sha256")
        != digests["receipt"]
        or documents["terminal"].get("state") != "COMPLETE"
        or documents["terminal"].get("result") != "PASS"
        or digests["receipt"] != identity.identity_receipt_sha256
        or digests["terminal"] != identity.identity_terminal_sha256
        or digests["access"] != identity.access_census_sha256
    ):
        raise ValueError("synthetic identity evidence closure")
    return {
        "result": "PASS",
        "leaf_count": 4,
        "terminal_sha256": digests["terminal"],
        "synthetic_identity_evidence_sha256": _contract_sha256(digests),
    }


def _bridge_from_gate(gate: object, identity: _IdentityOutcome,
                      runtime: _Runtime) -> _ValidatedBridge:
    validated_gate = _require_consumed_gate(gate, identity.authority)
    ids = {
        key: str(gate.get(key)) for key in (
            "authorization_id", "package_attempt_id", "primary_event_id", "secondary_event_id"
        )
    }
    value = {
        "schema": "pulsarmlx.f017.event06-minimum-gate-numerical-bridge/1.0.0",
        "authority_scope": runtime.scope,
        **ids,
        "collapsed_go_sha256": validated_gate.get("collapsed_go_sha256"),
        "installed_authority_sha256": identity.authority.source_sha256,
        "checkpoint_set_sha256": str(identity.authority.get("checkpoint_set_sha256")),
        "identity_receipt_sha256": identity.identity_receipt_sha256,
        "identity_terminal_sha256": identity.identity_terminal_sha256,
        "access_census_sha256": identity.access_census_sha256,
        "descriptor_identity_sha256": _contract_sha256(identity.leases.descriptors),
        "primary_numerical_sha256": runtime.profile.primary_numerical_sha256,
        "secondary_numerical_sha256": runtime.profile.secondary_numerical_sha256,
        "numerical_acceptance_contract_sha256": (
            runtime.profile.numerical_acceptance_contract_sha256
        ),
        "comparison_rules_sha256": runtime.profile.comparison_rules_sha256,
        "result_authority_sha256": runtime.profile.result_authority_sha256,
        "result_builder_sha256": runtime.profile.result_builder_sha256,
        "attempts": 1,
        "retries": 0,
        "resume": False,
        "result": "PASS",
    }
    return _ValidatedBridge(_BRIDGE_SEAL, value)


def _target_candidate(bridge: _ValidatedBridge) -> dict[str, object]:
    profile = _parse_artifact_bytes((_ROOT / _CHECKPOINT_CONTRACT).read_bytes())
    if bridge.get("authority_scope") == "SYNTHETIC":
        profile = _parse_artifact_bytes((_ROOT / _SYNTHETIC_CHECKPOINT_CONTRACT).read_bytes())
    return {
        "active_generation": "V11",
        "primary_numerical_sha256": bridge.get("primary_numerical_sha256"),
        "secondary_numerical_sha256": bridge.get("secondary_numerical_sha256"),
        "tensor_catalog_path": str(_ROOT / _TENSOR_PLAN),
        "tensor_catalog_sha256": _file_sha(_TENSOR_PLAN),
        "shards": profile["shards"],
    }


def _bank_stage_receipt(storage: _StorageBinding, stage: str,
                        subject: Mapping[str, object]) -> str:
    value = {
        "schema": "pulsarmlx.f017.event06-minimum-gate-stage-receipt/1.0.0",
        "stage": stage,
        "subject_sha256": _contract_sha256(dict(subject)),
        "result": "PASS",
    }
    return storage.bank(f"{stage.lower()}-start-receipt.json", value)


def _comparison(primary: Mapping[str, object], secondary: Mapping[str, object],
                bridge: _ValidatedBridge, storage: _StorageBinding) -> tuple[dict[str, object], str, str]:
    pa = primary["artifacts"]
    sa = secondary["artifacts"]

    def derive_and_validate(
        primary_dir: Path, secondary_dir: Path
    ) -> dict[str, object]:
        candidate = _derive_comparison(
            primary_dir, pa["manifest"]["payloads"][2],
            secondary_dir, sa["manifest"]["payloads"][2],
            pa["routing"], sa["routing"], pa["manifest"], sa["manifest"],
            pa["top32"], sa["top32"], pa["receipt"], sa["receipt"],
            str(bridge.get("authorization_id")),
        )
        _validate_comparison(
            candidate,
            primary_dir, pa["manifest"]["payloads"][2],
            secondary_dir, sa["manifest"]["payloads"][2],
            pa["routing"], sa["routing"], pa["manifest"], sa["manifest"],
            pa["top32"], sa["top32"], pa["receipt"], sa["receipt"],
            str(bridge.get("authorization_id")),
        )
        return candidate

    value = storage.anchored_pair_call(
        "primary", "secondary", derive_and_validate
    )
    summary_sha = storage.bank("comparison-summary.json", value)
    receipt = {
        "schema": "pulsarmlx.f017.event06-minimum-gate-comparison-receipt/1.0.0",
        "comparison_summary_sha256": summary_sha,
        "package_attempt_id": bridge.get("package_attempt_id"),
        "result": "PASS",
    }
    receipt_sha = storage.bank("comparison-receipt.json", receipt)
    terminal = {
        "schema": "pulsarmlx.f017.event06-minimum-gate-comparison-terminal/1.0.0",
        "comparison_receipt_sha256": receipt_sha,
        "state": "COMPLETE",
        "result": "PASS",
    }
    terminal_sha = storage.bank("comparison-terminal.json", terminal)
    return value, receipt_sha, terminal_sha


def _document_sha(value: Mapping[str, object]) -> str:
    return _sha(_canonical_bytes(dict(value)))


def _gate_m001_one_shot_claim(
    gate: object,
    storage: _StorageBinding,
    integration_state: object,
    stop: _StopBoundary,
) -> tuple[object, str]:
    consumed = _consume_package_start_gate(gate)
    storage.prepare()
    receipt = consumed.get("package_start_receipt")
    if type(receipt) is not dict:
        raise TypeError("consumed gate package-start receipt")
    expected = _contract_sha256(receipt)
    if (
        _HEX64.fullmatch(expected) is None
        or expected != consumed.get("package_start_receipt_sha256")
    ):
        raise ValueError("package-start receipt identity")
    if type(integration_state) is not _MinimumOneShotState:
        raise TypeError("minimum one-shot state required")
    observed = storage.bank_package_start(receipt, stop)
    integration_state.consume_package_start()
    if integration_state.snapshot().get("package_starts") != 1:
        raise ValueError("collapsed integration package-start accounting")
    return consumed, observed


def _gate_m002_per_read_receipts(identity: _IdentityOutcome) -> None:
    receipts = identity.read_receipts
    if (
        len(receipts) != 6
        or [item.get("ordinal") for item in receipts] != [1, 2, 3, 4, 5, 6]
        or [item.get("role") for item in receipts]
        != ["IDENTITY_ONLY", *(["GRAPH_PAYLOAD"] * 5)]
    ):
        raise ValueError("per-read receipt census")
    for item in receipts:
        if (
            set(item) != {"schema", "ordinal", "role", "byte_count", "sha256", "result"}
            or item["schema"]
            != "pulsarmlx.f017.event06-minimum-identity-read-receipt/1.0.0"
            or type(item["byte_count"]) is not int
            or item["byte_count"] < 0
            or _HEX64.fullmatch(str(item["sha256"])) is None
            or item["result"] != "PASS"
        ):
            raise ValueError("per-read receipt authority")


def _gate_m003_fail_closed_preflight(raw: bytes, profile: _AuthorityProfile,
                                     *, now_unix_ns: int | None = None) -> _ValidatedCollapsedGo:
    if tuple(_REQUIRED_MECHANISM_IDS) != tuple(f"M{i:03d}" for i in range(1, 18)):
        raise ValueError("minimum gate contract inventory")
    validated = _validate_go_bytes(raw, profile, now_unix_ns=now_unix_ns)
    if profile.authority_scope == "PRODUCTION":
        _pthread_fchdir_callable()
        machine = _observe_target_machine()
        if machine != {
            "target_machine": _TARGET_MACHINE,
            "brand": _TARGET_MACHINE_BRAND,
            "architecture": _TARGET_ARCHITECTURE,
        }:
            raise ValueError("target-machine resource binding")
    return validated


def _gate_m004_stop_boundary(stop: _StopBoundary, stage: str, runtime: _Runtime) -> None:
    stop.enter(stage, runtime)


def _gate_m005_receipt_derived_ledger(consumed_gate: object, identity: _IdentityOutcome,
                                      primary_start: str, primary: Mapping[str, object],
                                      secondary_start: str, secondary: Mapping[str, object],
                                      comparison_receipt: str, comparison_terminal: str,
                                      release_start: str, release_report: Mapping[str, object],
                                      release_report_sha: str, release_receipt: str,
                                      release_terminal: str) -> object:
    pa = primary["artifacts"]
    sa = secondary["artifacts"]
    accounting = _build_accounting_closure(
        consumed_gate,
        identity_read_receipts=identity.read_receipts,
        identity_receipt_sha256=identity.identity_receipt_sha256,
        identity_terminal_sha256=identity.identity_terminal_sha256,
        primary_start_receipt_sha256=primary_start,
        primary_result_receipt_sha256=_document_sha(pa["receipt"]),
        primary_result_terminal_sha256=_document_sha(pa["result_terminal"]),
        primary_consumer_terminal_sha256=_document_sha(pa["consumer_terminal"]),
        secondary_start_receipt_sha256=secondary_start,
        secondary_result_receipt_sha256=_document_sha(sa["receipt"]),
        secondary_result_terminal_sha256=_document_sha(sa["result_terminal"]),
        secondary_consumer_terminal_sha256=_document_sha(sa["consumer_terminal"]),
        comparison_receipt_sha256=comparison_receipt,
        comparison_terminal_sha256=comparison_terminal,
        release_start_receipt_sha256=release_start,
        release_report_sha256=release_report_sha,
        release_receipt_sha256=release_receipt,
        release_terminal_sha256=release_terminal,
        attempted_closures=int(release_report["attempted_closures"]),
        successful_closures=int(release_report["successful_closures"]),
        duplicate_closes=int(release_report["duplicate_closures"]),
        unknown_leases=int(release_report["unknown_leases"]),
        live_leases=int(release_report["live_leases_after_release"]),
    )
    return _validate_accounting_closure(accounting)


def _gate_m006_no_retry_or_resume(gate: object) -> None:
    if gate.get("attempts") != 1 or gate.get("retries") != 0 or gate.get("resume") is not False:
        raise ValueError("retry or resume prohibited")


def _gate_m007_numeric_acceptance(bundle: Mapping[str, object], role: str) -> None:
    if bundle.get("result") != "PASS":
        raise ValueError("numerical bundle result")
    artifacts = bundle.get("artifacts")
    if type(artifacts) is not dict or artifacts.get("manifest", {}).get("role") != role:
        raise ValueError("numerical role authority")
    payloads = artifacts["manifest"].get("payloads")
    expected = (
        ((49_152, 49_152, 1_239_040), "f64le")
        if role == "PRIMARY" else ((24_576, 24_576, 619_520), "f32le")
    )
    if (
        type(payloads) is not list
        or tuple(item.get("observed_byte_count") for item in payloads) != expected[0]
        or any(item.get("dtype") != expected[1] for item in payloads)
    ):
        raise ValueError("numerical payload geometry")


def _gate_m008_comparison_rules(comparison: Mapping[str, object]) -> None:
    thresholds = comparison.get("thresholds")
    if thresholds != {
        "max_absolute_error": _MAX_ABS_LIMIT,
        "rmse": _RMSE_LIMIT,
        "cosine_minimum": _COSINE_MINIMUM,
    }:
        raise ValueError("comparison threshold authority")
    if comparison.get("classification") not in {
        "EXACT_EXPECTED_TOKEN_STABLE",
        "NUMERICALLY_STABLE_TOP_K_ONLY",
        "TOP1_UNSTABLE_WITHIN_FROZEN_UNCERTAINTY",
    }:
        raise ValueError("comparison classification is not numerically accepted")


def _gate_m009_stage_vocabulary() -> None:
    required = tuple(_STAGE_VOCABULARY)
    if required != _STAGES:
        raise ValueError("minimum path stage vocabulary")


def _gate_m010_accounting_units(accounting: object) -> None:
    if accounting.get("authorization_delta") != 0 or accounting.get("package_delta") != 1:
        raise ValueError("authorization/package accounting units")
    if accounting.get("primary_delta") != 1 or accounting.get("secondary_delta") != 1:
        raise ValueError("consumer accounting units")


def _gate_m011_historical_master_ledger(accounting: object) -> None:
    if (
        _HISTORICAL_MASTER_LEDGER != 175
        or accounting.get("historical_master_ledger_before") != 175
        or accounting.get("historical_master_ledger_after") != 175
    ):
        raise ValueError("historical master ledger")


def _gate_m012_fresh_human_package_authority(go: _ValidatedCollapsedGo,
                                             gate: object,
                                             profile: _AuthorityProfile) -> None:
    if (
        gate.get("collapsed_go_sha256") != go.sha256
        or go.get("decision") != _COLLAPSED_GO_DECISION
        or go.get("scope") != _COLLAPSED_GO_SCOPE
        or go.get("release_authority_sha256")
        != profile.release_authority_sha256
        or _contract_sha256(dict(profile.release_authority))
        != profile.release_authority_sha256
        or profile.release_authority.get("authority_scope")
        != profile.authority_scope
        or profile.release_authority.get(
            "selected_checkpoint_identity_contract_path"
        )
        != profile.checkpoint_contract_path
        or profile.release_authority.get(
            "selected_checkpoint_identity_contract_sha256"
        )
        != profile.checkpoint_authority_sha256
        or profile.release_authority.get("production_checkpoint_root")
        != str(_LIVE_CHECKPOINT_ROOT)
        or profile.release_authority.get("selected_checkpoint_root")
        != (
            str(_LIVE_CHECKPOINT_ROOT)
            if profile.authority_scope == "PRODUCTION"
            else "SEALED_SYNTHETIC_RUNTIME_DERIVED"
        )
    ):
        raise ValueError("fresh human decision/package authority")


def _gate_m013_checkpoint_identity_stability(
    identity: _IdentityOutcome,
    profile: _AuthorityProfile,
    storage: _StorageBinding,
) -> None:
    report = identity.report
    evidence = report.get("evidence")
    descriptors = identity.leases.descriptors
    authority = identity.authority
    if (
        type(authority) is not _ValidatedIdentityAuthority
        or authority.posture != "INSTALLED"
        or type(evidence) is not dict
        or type(descriptors) is not list
    ):
        raise TypeError("installed identity-stage authority")
    _validate_descriptors(descriptors)
    descriptor_sha256 = _contract_sha256(descriptors)
    expected_receipts = tuple(
        {
            "schema": (
                "pulsarmlx.f017.event06-minimum-identity-read-receipt/1.0.0"
            ),
            "ordinal": int(item["ordinal"]),
            "role": str(item["role"]),
            "byte_count": int(item["size_bytes"]),
            "sha256": str(item["sha256"]),
            "result": "PASS",
        }
        for item in profile.shards
    )
    for key in (
        "shard_receipts_sha256",
        "lease_manifest_sha256",
        "identity_manifest_sha256",
        "identity_receipt_sha256",
        "identity_terminal_sha256",
        "access_journal_sha256",
    ):
        if _HEX64.fullmatch(str(evidence.get(key))) is None:
            raise ValueError("identity evidence digest")
    if (
        report.get("result") != "PASS"
        or report.get("authority_scope") != authority.get("authority_scope")
        or (
            report.get("operation_class") != authority.get("operation_class")
            and not (
                authority.get("authority_scope") == "SYNTHETIC"
                and report.get("operation_class")
                == "QUALIFICATION_IDENTITY_BOUNDARY_INTERPOSE"
            )
        )
        or report.get("generation") != "V12"
        or report.get("ordered_shard_digests")
        != [str(item["sha256"]) for item in profile.shards]
        or report.get("checkpoint_shard_opens") != 6
        or report.get("checkpoint_identity_hash_reads") != 6
        or report.get("retained_lease_count") != 5
        or report.get("identity_only_retained_count") != 0
        or report.get("path_reopen_count") != 0
        or evidence.get("identity_terminal_state") != "COMPLETE"
        or report.get("descriptor_identities") != descriptors
        or [item.get("shard_ordinal") for item in descriptors]
        != [2, 3, 4, 5, 6]
        or any(
            item.get("lease_id")
            != (
                f"LEASE-{authority.get('package_attempt_id')}-"
                f"{item.get('shard_ordinal')}"
            )
            for item in descriptors
        )
        or authority.get("checkpoint_set_sha256")
        != profile.checkpoint_set_sha256
        or identity.read_receipts != expected_receipts
        or descriptor_sha256 != _contract_sha256(descriptors)
        or identity.identity_receipt_sha256
        != evidence.get("identity_receipt_sha256")
        or identity.identity_terminal_sha256
        != evidence.get("identity_terminal_sha256")
        or identity.access_census_sha256 != evidence.get("access_journal_sha256")
    ):
        raise ValueError("checkpoint identity/descriptor stability")
    _validate_identity_evidence_closure(identity, storage)


def _gate_m014_causal_prerequisite_order(primary: Mapping[str, object],
                                         secondary: Mapping[str, object] | None = None) -> None:
    p = primary["artifacts"]["consumer_terminal"]
    if p.get("result") != "COMPLETE" or p.get("secondary_eligible") is not True:
        raise ValueError("primary terminal prerequisite")
    if secondary is not None and secondary["artifacts"]["consumer_terminal"].get("result") != "COMPLETE":
        raise ValueError("secondary terminal prerequisite")


def _gate_m015_independent_primary_secondary(primary: Mapping[str, object],
                                             secondary: Mapping[str, object]) -> None:
    pa = primary["artifacts"]
    sa = secondary["artifacts"]
    if (
        pa["manifest"].get("role") != "PRIMARY"
        or sa["manifest"].get("role") != "SECONDARY"
        or primary is secondary
        or pa["manifest"]["payloads"][2]["sha256"]
        == sa["manifest"]["payloads"][2]["sha256"]
    ):
        raise ValueError("primary/secondary numerical independence")


def _validate_banked_bundle(
    bundle: Mapping[str, object],
    role: str,
    bridge: _ValidatedBridge,
    storage: _StorageBinding,
) -> dict[str, object]:
    artifacts = bundle.get("artifacts")
    index = bundle.get("index")
    if type(artifacts) is not dict or type(index) is not dict:
        raise TypeError("result bundle closure")
    role_leaf = role.lower()
    control_leaves = {
        "manifest": f"{role_leaf}-payload-manifest.json",
        "routing": f"{role_leaf}-routing-manifest.json",
        "top32": f"{role_leaf}-top32-summary.json",
        "receipt": f"{role_leaf}-result-receipt.json",
        "result_terminal": f"{role_leaf}-result-terminal.json",
        "consumer_terminal": f"{role_leaf}-consumer-terminal.json",
    }

    def validate(directory: Path) -> dict[str, object]:
        for key, leaf in control_leaves.items():
            observed, _digest = _read_banked_document(directory, leaf)
            if _canonical_bytes(observed) != _canonical_bytes(artifacts[key]):
                raise ValueError("banked result control-document drift")
        validated = _validate_bundle(
            directory,
            role=role,
            authorization_id=str(bridge.get("authorization_id")),
            package_attempt_id=str(bridge.get("package_attempt_id")),
            consumer_event_id=str(bridge.get(f"{role_leaf}_event_id")),
            manifest=artifacts["manifest"],
            top32=artifacts["top32"],
            routing=artifacts["routing"],
            receipt=artifacts["receipt"],
            result_terminal=artifacts["result_terminal"],
            consumer_terminal=artifacts["consumer_terminal"],
            numerical_contract_sha256=str(
                bridge.get("numerical_acceptance_contract_sha256")
            ),
        )
        if _canonical_bytes(validated) != _canonical_bytes(index):
            raise ValueError("banked result bundle-index drift")
        return validated

    return storage.anchored_path_call(role_leaf, validate)


def _validate_banked_comparison(
    comparison: Mapping[str, object],
    primary: Mapping[str, object],
    secondary: Mapping[str, object],
    bridge: _ValidatedBridge,
    storage: _StorageBinding,
    comparison_terminal_sha256: str,
) -> str:
    summary_raw = storage.read("comparison-summary.json")
    summary = _parse_artifact_bytes(summary_raw)
    summary_sha = _sha(summary_raw)
    receipt_raw = storage.read("comparison-receipt.json")
    terminal_raw = storage.read("comparison-terminal.json")
    receipt = _parse_artifact_bytes(receipt_raw)
    terminal = _parse_artifact_bytes(terminal_raw)
    if any(type(item) is not dict for item in (summary, receipt, terminal)):
        raise ValueError("comparison control-document type")
    if (
        _canonical_bytes(summary) != _canonical_bytes(dict(comparison))
        or receipt.get("comparison_summary_sha256") != summary_sha
        or receipt.get("package_attempt_id")
        != bridge.get("package_attempt_id")
        or receipt.get("result") != "PASS"
        or terminal.get("comparison_receipt_sha256") != _sha(receipt_raw)
        or terminal.get("state") != "COMPLETE"
        or terminal.get("result") != "PASS"
        or _sha(terminal_raw) != comparison_terminal_sha256
    ):
        raise ValueError("banked comparison closure")
    pa = primary["artifacts"]
    sa = secondary["artifacts"]

    def validate(primary_dir: Path, secondary_dir: Path) -> None:
        _validate_comparison(
            dict(summary),
            primary_dir,
            pa["manifest"]["payloads"][2],
            secondary_dir,
            sa["manifest"]["payloads"][2],
            pa["routing"],
            sa["routing"],
            pa["manifest"],
            sa["manifest"],
            pa["top32"],
            sa["top32"],
            pa["receipt"],
            sa["receipt"],
            str(bridge.get("authorization_id")),
        )

    storage.anchored_pair_call("primary", "secondary", validate)
    return _contract_sha256(
        {
            "summary_sha256": summary_sha,
            "receipt_sha256": _sha(receipt_raw),
            "terminal_sha256": _sha(terminal_raw),
        }
    )


def _derive_v11_result_closure(
    primary: Mapping[str, object],
    secondary: Mapping[str, object],
    comparison: Mapping[str, object],
    comparison_terminal_sha256: str,
    identity: _IdentityOutcome,
    bridge: _ValidatedBridge,
    storage: _StorageBinding,
) -> dict[str, object]:
    validated_indexes: dict[str, dict[str, object]] = {}
    for role, bundle in (("PRIMARY", primary), ("SECONDARY", secondary)):
        artifacts = bundle["artifacts"]
        index = bundle["index"]
        checks = (
            _document_sha(artifacts["manifest"]) == index["manifest_sha256"],
            _document_sha(artifacts["receipt"]) == index["result_receipt_sha256"],
            _document_sha(artifacts["result_terminal"]) == index["result_terminal_sha256"],
            _document_sha(artifacts["consumer_terminal"]) == index["consumer_terminal_sha256"],
        )
        if not all(checks):
            raise ValueError("immutable result closure")
        validated_indexes[role] = _validate_banked_bundle(
            bundle, role, bridge, storage
        )
    identity_closure = _validate_identity_evidence_closure(identity, storage)
    comparison_closure_sha256 = _validate_banked_comparison(
        comparison,
        primary,
        secondary,
        bridge,
        storage,
        comparison_terminal_sha256,
    )
    return {
        "schema": "pulsarmlx.f017.event06-minimum-gate-v11-result-closure/1.0.0",
        "authorization_id": bridge.get("authorization_id"),
        "package_attempt_id": bridge.get("package_attempt_id"),
        "primary_bundle": validated_indexes["PRIMARY"],
        "secondary_bundle": validated_indexes["SECONDARY"],
        "identity_evidence_closure": identity_closure,
        "comparison_closure_sha256": comparison_closure_sha256,
        "comparison_terminal_sha256": comparison_terminal_sha256,
        "result": "PASS",
    }


def _gate_m016_immutable_result_closure(
    primary: Mapping[str, object],
    secondary: Mapping[str, object],
    comparison: Mapping[str, object],
    comparison_terminal_sha256: str,
    identity: _IdentityOutcome,
    bridge: _ValidatedBridge,
    storage: _StorageBinding,
) -> dict[str, object]:
    """Validate the immutable V11 result leaves at the retained M016 gate."""
    return _derive_v11_result_closure(
        primary,
        secondary,
        comparison,
        comparison_terminal_sha256,
        identity,
        bridge,
        storage,
    )


def _require_exact_banked_document(
    storage: _StorageBinding,
    leaf: str,
    expected: Mapping[str, object],
    expected_sha256: str,
) -> None:
    raw = storage.read(leaf)
    if raw != _canonical_bytes(dict(expected)) or _sha(raw) != expected_sha256:
        raise ValueError(f"banked package closure: {leaf}")


def _validate_package_control_closure(
    *,
    storage: _StorageBinding,
    consumed_gate: object,
    bridge: _ValidatedBridge,
    package_start_sha256: str,
    primary_start_sha256: str,
    secondary_start_sha256: str,
    comparison_receipt_sha256: str,
    comparison_terminal_sha256: str,
    release_start_sha256: str,
    release: Mapping[str, object],
    release_report_sha256: str,
    release_receipt_sha256: str,
    release_terminal_sha256: str,
    accounting: object,
    accounting_sha256: str,
    v11_closure: Mapping[str, object],
    v11_closure_sha256: str,
    package_receipt_value: Mapping[str, object],
    package_receipt_sha256: str,
) -> None:
    """Re-derive every root control leaf before the package terminal wins."""
    start_receipt = consumed_gate.get("package_start_receipt")
    if type(start_receipt) is not dict:
        raise TypeError("package-start receipt closure")
    _require_exact_banked_document(
        storage, "package-start.json", start_receipt, package_start_sha256
    )
    for stage, expected_sha256 in (
        ("PRIMARY", primary_start_sha256),
        ("SECONDARY", secondary_start_sha256),
        ("RELEASE", release_start_sha256),
    ):
        value = {
            "schema": "pulsarmlx.f017.event06-minimum-gate-stage-receipt/1.0.0",
            "stage": stage,
            "subject_sha256": _contract_sha256(bridge.as_dict()),
            "result": "PASS",
        }
        _require_exact_banked_document(
            storage, f"{stage.lower()}-start-receipt.json", value, expected_sha256
        )

    _require_exact_banked_document(
        storage, "release-report.json", release, release_report_sha256
    )
    release_receipt = {
        "schema": "pulsarmlx.f017.event06-minimum-gate-release-receipt/1.0.0",
        "release_report_sha256": release_report_sha256,
        "result": "PASS",
    }
    _require_exact_banked_document(
        storage, "release-receipt.json", release_receipt, release_receipt_sha256
    )
    release_terminal = {
        "schema": "pulsarmlx.f017.event06-minimum-gate-release-terminal/1.0.0",
        "release_receipt_sha256": release_receipt_sha256,
        "live_leases": 0,
        "state": "COMPLETE",
        "result": "PASS",
    }
    _require_exact_banked_document(
        storage, "release-terminal.json", release_terminal, release_terminal_sha256
    )

    validated_accounting = _validate_accounting_closure(accounting)
    if validated_accounting is not accounting:
        raise TypeError("exact receipt-derived accounting closure")
    _require_exact_banked_document(
        storage,
        "receipt-derived-accounting.json",
        accounting.as_dict(),
        accounting_sha256,
    )
    _require_exact_banked_document(
        storage,
        "v11-result-closure.json",
        v11_closure,
        v11_closure_sha256,
    )
    _require_exact_banked_document(
        storage,
        "package-receipt.json",
        package_receipt_value,
        package_receipt_sha256,
    )

    bindings = accounting.get("receipt_bindings")
    if type(bindings) is not dict or (
        bindings.get("comparison_receipt_sha256") != comparison_receipt_sha256
        or bindings.get("comparison_terminal_sha256")
        != comparison_terminal_sha256
        or bindings.get("release_report_sha256") != release_report_sha256
        or bindings.get("release_receipt_sha256") != release_receipt_sha256
        or bindings.get("release_terminal_sha256") != release_terminal_sha256
    ):
        raise ValueError("package control receipt continuity")


def _finalize_package_terminal(
    *,
    primary: Mapping[str, object],
    secondary: Mapping[str, object],
    comparison: Mapping[str, object],
    comparison_receipt_sha256: str,
    comparison_terminal_sha256: str,
    identity: _IdentityOutcome,
    bridge: _ValidatedBridge,
    storage: _StorageBinding,
    consumed_gate: object,
    package_start_sha256: str,
    primary_start_sha256: str,
    secondary_start_sha256: str,
    release_start_sha256: str,
    release: Mapping[str, object],
    release_report_sha256: str,
    release_receipt_sha256: str,
    release_terminal_sha256: str,
    accounting: object,
    accounting_sha256: str,
    v11_closure: Mapping[str, object],
    v11_closure_sha256: str,
    package_receipt_value: Mapping[str, object],
    package_receipt_sha256: str,
    stop: _StopBoundary,
    runtime: _Runtime,
) -> Mapping[str, object]:
    """Validate raw package leaves and bank the sole terminal in one call."""
    def validate_raw_closure() -> None:
        observed = _derive_v11_result_closure(
            primary,
            secondary,
            comparison,
            comparison_terminal_sha256,
            identity,
            bridge,
            storage,
        )
        if observed != dict(v11_closure):
            raise ValueError("pre-terminal V11 closure drift")
        _validate_package_control_closure(
            storage=storage,
            consumed_gate=consumed_gate,
            bridge=bridge,
            package_start_sha256=package_start_sha256,
            primary_start_sha256=primary_start_sha256,
            secondary_start_sha256=secondary_start_sha256,
            comparison_receipt_sha256=comparison_receipt_sha256,
            comparison_terminal_sha256=comparison_terminal_sha256,
            release_start_sha256=release_start_sha256,
            release=release,
            release_report_sha256=release_report_sha256,
            release_receipt_sha256=release_receipt_sha256,
            release_terminal_sha256=release_terminal_sha256,
            accounting=accounting,
            accounting_sha256=accounting_sha256,
            v11_closure=v11_closure,
            v11_closure_sha256=v11_closure_sha256,
            package_receipt_value=package_receipt_value,
            package_receipt_sha256=package_receipt_sha256,
        )

    terminal_descriptor = storage._terminal_fd
    if terminal_descriptor is None:
        raise RuntimeError("package-start terminal reservation required")
    committed = False
    try:
        # The empty immutable terminal has been held since package start.  Seal
        # the namespace and every predecessor before accepting the exact,
        # scope-specific recursive inventory.  A racing extra entry can no
        # longer disappear or be legitimized by a mutually changed manifest.
        _set_user_immutable(storage._package_fd, True)
        storage._verify_package_path_identity()
        storage._verify_exact_success_inventory(terminal_descriptor)
        validate_raw_closure()
        terminal = _build_package_terminal(
            accounting,
            package_receipt_sha256=package_receipt_sha256,
            v11_closure_root_sha256=v11_closure_sha256,
        )
        terminal = _validate_package_terminal(terminal, accounting)
        terminal_value = terminal.as_dict()
        terminal_sha256 = _sha(_canonical_bytes(terminal_value))
        success_result = MappingProxyType({
            "result": "PASS",
            "package_terminal_sha256": terminal_sha256,
            "package_receipt_sha256": package_receipt_sha256,
            "accounting_closure_sha256": accounting_sha256,
            "comparison": _deep_immutable(dict(comparison)),
            "required_gates": tuple(_REQUIRED_MECHANISM_IDS),
            "original_checkpoint_root_resolutions": runtime.observed_effects[
                "checkpoint_root_resolutions"
            ],
            "original_checkpoint_opens": runtime.observed_effects[
                "checkpoint_opens"
            ],
            "real_numerical_executions": runtime.observed_effects[
                "numerical_executions"
            ],
        })
        # Every transitive leaf and the reserved terminal identity have been
        # rederived immediately before this write.  The terminal is sealed
        # before either durability sync, and nothing fallible remains after
        # the stop boundary becomes terminal.
        try:
            storage._commit_reserved_success_terminal(
                terminal_descriptor, terminal_value, stop, terminal_sha256
            )
        except BaseException:
            if not storage._terminal_writer_retired:
                raise
            stop.terminal_banked = True
        committed = True
        return success_result
    finally:
        if not committed and not stop.terminal_banked:
            storage._abort_success_commit(terminal_descriptor)


def _gate_m017_release_before_package_terminal(release: Mapping[str, object]) -> None:
    if (
        release.get("result") != "PASS"
        or release.get("attempted_closures") != 5
        or release.get("successful_closures") != 5
        or release.get("duplicate_closures") != 0
        or release.get("unknown_leases") != 0
        or release.get("live_leases_after_release") != 0
    ):
        raise ValueError("resource release before package terminal")


def _execute_minimum_gate_path(raw: bytes, runtime: _Runtime,
                               *, now_unix_ns: int | None = None,
                               validated_go: _ValidatedCollapsedGo | None = None,
                               ) -> dict[str, object]:
    stop = _StopBoundary(runtime.storage)
    identity: _IdentityOutcome | None = None
    completed_release: Mapping[str, object] | None = None
    try:
        _gate_m004_stop_boundary(stop, "PREPARED", runtime)
        go = validated_go
        if go is None:
            go = _gate_m003_fail_closed_preflight(
                raw, runtime.profile, now_unix_ns=now_unix_ns
            )
        elif type(go) is not _ValidatedCollapsedGo or go.sha256 != _sha(raw):
            raise TypeError("exact prevalidated collapsed GO required")
        if runtime.package_claim_sha256 != go.get("human_decision_sha256"):
            raise ValueError("one-shot package claim/human decision binding")
        _validate_fresh_integration_state(runtime.integration_state, runtime.scope)
        installed = _build_installed_authority(go, runtime)
        _gate_m004_stop_boundary(stop, "INSTALLED", runtime)
        gate = _package_gate(go, installed, runtime)
        _gate_m006_no_retry_or_resume(gate)
        _gate_m012_fresh_human_package_authority(go, gate, runtime.profile)
        _gate_m009_stage_vocabulary()
        _gate_m004_stop_boundary(stop, "PACKAGE_START_ELIGIBLE_DRY_STOP", runtime)

        _gate_m004_stop_boundary(stop, "PACKAGE_START", runtime)
        consumed_gate, package_start_sha = _gate_m001_one_shot_claim(
            gate, runtime.storage, runtime.integration_state, stop
        )

        _gate_m004_stop_boundary(stop, "IDENTITY_TERMINAL", runtime)
        if runtime.scope == "PRODUCTION":
            runtime.observed_effects["checkpoint_root_resolutions"] = 1
        identity = runtime.checkpoint_effect.run(consumed_gate, installed, runtime.storage)
        if runtime.scope == "PRODUCTION":
            runtime.observed_effects["checkpoint_opens"] = int(
                identity.report["checkpoint_shard_opens"]
            )
        _gate_m002_per_read_receipts(identity)
        _gate_m013_checkpoint_identity_stability(
            identity, runtime.profile, runtime.storage
        )
        stop.record("IDENTITY_RECEIPT", identity.identity_receipt_sha256)
        bridge = _bridge_from_gate(consumed_gate, identity, runtime)

        _gate_m004_stop_boundary(stop, "PRIMARY_RESULT_TERMINAL", runtime)
        primary_start = _bank_stage_receipt(runtime.storage, "PRIMARY", bridge.as_dict())
        stop.record("PRIMARY_START", primary_start)
        if runtime.scope == "PRODUCTION":
            runtime.observed_effects["numerical_executions"] += 1
        primary = runtime.numerical_effect.primary(
            bridge, identity, runtime.storage, primary_start
        )
        _gate_m007_numeric_acceptance(primary, "PRIMARY")
        stop.record("PRIMARY_RESULT_RECEIPT", _document_sha(primary["artifacts"]["receipt"]))

        _gate_m014_causal_prerequisite_order(primary)
        _gate_m004_stop_boundary(stop, "SECONDARY_RESULT_TERMINAL", runtime)
        secondary_start = _bank_stage_receipt(runtime.storage, "SECONDARY", bridge.as_dict())
        stop.record("SECONDARY_START", secondary_start)
        if runtime.scope == "PRODUCTION":
            runtime.observed_effects["numerical_executions"] += 1
        secondary = runtime.numerical_effect.secondary(
            bridge, identity, primary, runtime.storage, secondary_start
        )
        _gate_m007_numeric_acceptance(secondary, "SECONDARY")
        _gate_m014_causal_prerequisite_order(primary, secondary)
        _gate_m015_independent_primary_secondary(primary, secondary)
        stop.record("SECONDARY_RESULT_RECEIPT", _document_sha(secondary["artifacts"]["receipt"]))

        _gate_m004_stop_boundary(stop, "COMPARISON_TERMINAL", runtime)
        comparison, comparison_receipt, comparison_terminal = _comparison(
            primary, secondary, bridge, runtime.storage
        )
        _gate_m008_comparison_rules(comparison)
        v11_closure = _gate_m016_immutable_result_closure(
            primary,
            secondary,
            comparison,
            comparison_terminal,
            identity,
            bridge,
            runtime.storage,
        )
        v11_closure_root = runtime.storage.bank(
            "v11-result-closure.json", v11_closure
        )
        stop.record("COMPARISON_RECEIPT", comparison_receipt)

        _gate_m004_stop_boundary(stop, "RELEASE_TERMINAL", runtime)
        release_start = _bank_stage_receipt(runtime.storage, "RELEASE", bridge.as_dict())
        stop.record("RELEASE_START", release_start)
        close_function: Callable[[int, str], None] | None = None
        if runtime.scope == "SYNTHETIC":
            close_function = lambda _descriptor, _lease: None
        release = identity.leases.release(close_function=close_function)
        completed_release = release
        _gate_m017_release_before_package_terminal(release)
        release_report_sha = runtime.storage.bank("release-report.json", release)
        release_receipt = runtime.storage.bank("release-receipt.json", {
            "schema": "pulsarmlx.f017.event06-minimum-gate-release-receipt/1.0.0",
            "release_report_sha256": release_report_sha,
            "result": "PASS",
        })
        release_terminal = runtime.storage.bank("release-terminal.json", {
            "schema": "pulsarmlx.f017.event06-minimum-gate-release-terminal/1.0.0",
            "release_receipt_sha256": release_receipt,
            "live_leases": 0,
            "state": "COMPLETE",
            "result": "PASS",
        })
        stop.record("RELEASE_RECEIPT", release_receipt)

        _gate_m004_stop_boundary(stop, "ACCOUNTING_CLOSURE", runtime)
        accounting = _gate_m005_receipt_derived_ledger(
            consumed_gate, identity, primary_start, primary,
            secondary_start, secondary, comparison_receipt,
            comparison_terminal, release_start, release, release_report_sha,
            release_receipt, release_terminal,
        )
        _gate_m010_accounting_units(accounting)
        _gate_m011_historical_master_ledger(accounting)
        accounting_sha = runtime.storage.bank("receipt-derived-accounting.json", accounting.as_dict())
        package_receipt_value = {
            "schema": "pulsarmlx.f017.event06-minimum-gate-package-receipt/1.0.0",
            "package_start_sha256": package_start_sha,
            "accounting_closure_sha256": accounting_sha,
            "v11_closure_leaf": "v11-result-closure.json",
            "v11_closure_root_sha256": v11_closure_root,
            "result": "PASS",
        }
        package_receipt = runtime.storage.bank(
            "package-receipt.json", package_receipt_value
        )

        _gate_m004_stop_boundary(stop, "PACKAGE_TERMINAL", runtime)
        return _finalize_package_terminal(
            primary=primary,
            secondary=secondary,
            comparison=comparison,
            comparison_receipt_sha256=comparison_receipt,
            comparison_terminal_sha256=comparison_terminal,
            identity=identity,
            bridge=bridge,
            storage=runtime.storage,
            consumed_gate=consumed_gate,
            package_start_sha256=package_start_sha,
            primary_start_sha256=primary_start,
            secondary_start_sha256=secondary_start,
            release_start_sha256=release_start,
            release=release,
            release_report_sha256=release_report_sha,
            release_receipt_sha256=release_receipt,
            release_terminal_sha256=release_terminal,
            accounting=accounting,
            accounting_sha256=accounting_sha,
            v11_closure=v11_closure,
            v11_closure_sha256=v11_closure_root,
            package_receipt_value=package_receipt_value,
            package_receipt_sha256=package_receipt,
            stop=stop,
            runtime=runtime,
        )
    except BaseException as exc:
        emergency_release_sha: str | None = None
        emergency_release_outcome: Mapping[str, object] | None = None
        if isinstance(exc, _IdentityHandoffFailure):
            emergency_release_sha = exc.release_sha256
            emergency_release_outcome = exc.release_outcome
        elif identity is not None and identity.leases.closed:
            source = (
                dict(completed_release)
                if completed_release is not None
                else {
                    "attempted_closures": sum(
                        record.close_attempt_count > 0
                        for record in identity.leases.records
                    ),
                    "successful_closures": sum(
                        record.state == "CLOSED"
                        for record in identity.leases.records
                    ),
                    "duplicate_closures": 0,
                    "unknown_leases": sum(
                        record.state == "UNKNOWN"
                        for record in identity.leases.records
                    ),
                    "live_leases_after_release": 0,
                    "result": "PASS",
                }
            )
            source["release_disposition"] = "ALREADY_RELEASED"
            emergency_release_outcome = source
            try:
                emergency_release_sha = runtime.storage.bank_failure(
                    "emergency-release-report.json",
                    _emergency_release_value(stop.current_stage, source),
                )
            except BaseException:
                pass
        elif identity is not None and not identity.leases.closed:
            try:
                close_function = None
                if runtime.scope == "SYNTHETIC":
                    close_function = lambda _descriptor, _lease: None
                emergency_release = identity.leases.release(
                    close_function=close_function
                )
                emergency_release_outcome = emergency_release
                emergency_release_sha = runtime.storage.bank_failure(
                    "emergency-release-report.json",
                    _emergency_release_value(
                        stop.current_stage, emergency_release
                    ),
                )
            except BaseException:
                if emergency_release_outcome is None:
                    emergency_release_outcome = {
                        "attempted_closures": sum(
                            record.close_attempt_count > 0
                            for record in identity.leases.records
                        ),
                        "successful_closures": sum(
                            record.state == "CLOSED"
                            for record in identity.leases.records
                        ),
                        "duplicate_closures": 0,
                        "unknown_leases": sum(
                            record.state == "UNKNOWN"
                            for record in identity.leases.records
                        ),
                        "live_leases_after_release": sum(
                            record.state != "CLOSED"
                            for record in identity.leases.records
                        ),
                        "result": "RELEASE_OR_EVIDENCE_EXCEPTION",
                    }
        elif stop.package_started:
            emergency_release_outcome = {
                "attempted_closures": 0,
                "successful_closures": 0,
                "duplicate_closures": 0,
                "unknown_leases": 0,
                "live_leases_after_release": 0,
                "result": "NO_LEASES_ACQUIRED",
            }
            try:
                emergency_release_sha = runtime.storage.bank_failure(
                    "emergency-release-report.json",
                    _emergency_release_value(
                        stop.current_stage, emergency_release_outcome
                    ),
                )
            except Exception:
                pass
        stop.fail(
            exc,
            runtime,
            emergency_release_sha,
            emergency_release_outcome,
        )
        raise


def _close_storage_after_outcome(storage: _StorageBinding) -> None:
    """Attempt directory-descriptor cleanup without changing a terminal outcome."""
    try:
        storage.close()
    except BaseException:
        pass


def execute_event06_minimum_gate_path(collapsed_go_bytes: bytes) -> Mapping[str, object]:
    """Execute one package; no caller-selectable authority or effect surface exists."""
    if type(collapsed_go_bytes) is not bytes:
        raise TypeError("exact collapsed GO bytes required")
    go_sha256 = _sha(collapsed_go_bytes)
    qualification = _QUALIFICATION_INVOCATION.get()
    if qualification is None:
        profile = _authority_profile(synthetic=False)
        now_unix_ns = None
        validated_go = _gate_m003_fail_closed_preflight(
            collapsed_go_bytes, profile, now_unix_ns=now_unix_ns
        )
        # No live root, reservation, or state exists before the complete M003
        # fail-closed validation above succeeds.
        runtime = _production_runtime(
            str(validated_go.get("human_decision_sha256")), profile
        )
    else:
        if (
            type(qualification) is not _QualificationInvocation
            or qualification.seal is not _QUALIFICATION_INVOCATION_SEAL
            or qualification.collapsed_go_sha256 != go_sha256
            or qualification.runtime.scope != "SYNTHETIC"
        ):
            raise TypeError("invalid qualification invocation")
        runtime = qualification.runtime
        now_unix_ns = qualification.now_unix_ns
        validated_go = _gate_m003_fail_closed_preflight(
            collapsed_go_bytes, runtime.profile, now_unix_ns=now_unix_ns
        )
    try:
        return _execute_minimum_gate_path(
            collapsed_go_bytes,
            runtime,
            now_unix_ns=now_unix_ns,
            validated_go=validated_go,
        )
    finally:
        # Cleanup is not an additional outcome transition: it cannot mask a
        # classified failure or retroactively reclassify a durable terminal.
        _close_storage_after_outcome(runtime.storage)


def _qualification_go(profile: _AuthorityProfile, human_seed: bytes,
                      *, now_unix_ns: int) -> bytes:
    human = _sha(human_seed)
    nonce = _sha(
        b"F017-EVENT06-COLLAPSED-ONE-SHOT\x00"
        + human.encode("ascii")
        + profile.release_authority_sha256.encode("ascii")
    )
    return _canonical_bytes({
        "schema": _COLLAPSED_GO_SCHEMA,
        "decision": _COLLAPSED_GO_DECISION,
        "human_decision_sha256": human,
        "release_authority_sha256": profile.release_authority_sha256,
        "one_shot_nonce_sha256": nonce,
        "issued_at_unix_ns": now_unix_ns - 1,
        "expires_at_unix_ns": now_unix_ns + 10_000_000_000,
        "scope": _COLLAPSED_GO_SCOPE,
    })


def _qualification_collapsed_go_bytes() -> bytes:
    """Return a current, synthetic-only collapsed GO for private qualification."""
    return _qualification_go(
        _authority_profile(synthetic=True),
        b"F017-S39-PRIVATE-QUALIFICATION",
        now_unix_ns=time.time_ns(),
    )


def _qualification_root(value: Path) -> Path:
    if not isinstance(value, Path) or not value.is_absolute():
        raise TypeError("qualification root is graph-owned")
    root = value.resolve(strict=True)
    if value.is_symlink() or not root.is_dir():
        raise ValueError("qualification root must be a real directory")
    if root == _LIVE_PACKAGE_PARENT or root.is_relative_to(_LIVE_PACKAGE_PARENT):
        raise ValueError("qualification root cannot be live package storage")
    return root


def _invoke_public_qualification(
    collapsed_go_bytes: bytes,
    runtime: _Runtime,
    *,
    now_unix_ns: int,
) -> dict[str, object]:
    """Invoke the sole public entry under one context-local sealed test runtime."""
    invocation = _QualificationInvocation(
        _QUALIFICATION_INVOCATION_SEAL,
        runtime,
        now_unix_ns,
        _sha(collapsed_go_bytes),
    )
    token = _QUALIFICATION_INVOCATION.set(invocation)
    try:
        result = execute_event06_minimum_gate_path(collapsed_go_bytes)
        return dict(result)
    finally:
        _QUALIFICATION_INVOCATION.reset(token)


def _run_preopen_intercept(root: Path) -> dict[str, object]:
    """Prove interception at the real physical-identity call boundary."""
    qualification_root = _qualification_root(root)
    now = time.time_ns()
    profile = _authority_profile(synthetic=True)
    collapsed_go = _qualification_go(
        profile, b"F017-S39-PREOPEN", now_unix_ns=now
    )
    runtime = _qualification_runtime(
        qualification_root,
        str(_validate_go_bytes(collapsed_go, profile, now_unix_ns=now).get(
            "human_decision_sha256"
        )),
        intercept=True,
    )
    intercepted = False
    try:
        _invoke_public_qualification(
            collapsed_go,
            runtime,
            now_unix_ns=now,
        )
    except RuntimeError as exc:
        if str(exc) != "PREOPEN_INTERCEPTED":
            raise
        intercepted = True
    if not intercepted:
        raise AssertionError("physical checkpoint call was not intercepted")
    checkpoint_effect = runtime.checkpoint_effect
    provider = checkpoint_effect._qualification_interceptor
    if (
        type(checkpoint_effect) is not _ProductionCheckpointEffect
        or type(provider) is not _SyntheticCheckpointProvider
        or provider.preopen_intercepted is not True
    ):
        raise AssertionError("real physical-call boundary was not reached")
    terminal_path = runtime.storage.package_directory / "package-terminal.json"
    accounting_path = runtime.storage.package_directory / "failure-accounting.json"
    if not terminal_path.is_file() or not accounting_path.is_file():
        raise AssertionError("pre-open stop was not terminally accounted")
    return {
        "result": "PASS",
        "preopen_interception": "PASS",
        "physical_call_boundary": "f017_checkpoint_identity_producer_v12.produce",
        "package_started": True,
        "terminal_failure_banked": True,
        "failure_accounting_banked": True,
        "original_checkpoint_root_resolutions": 0,
        "original_checkpoint_opens": 0,
        "original_checkpoint_reads": 0,
        "original_checkpoint_mmaps": 0,
        "real_numerical_operations": 0,
        "synthetic_identities_instantiated": runtime.observed_effects[
            "synthetic_identities_instantiated"
        ],
        "synthetic_identities_consumed": runtime.integration_state.snapshot().get(
            "package_starts"
        ),
    }


def _run_no_access_qualification(
    root: Path,
    *,
    fail_stage: str | None = None,
    omit_optional: tuple[str, ...] = (),
) -> dict[str, object]:
    """Exercise the public entry through exactly three sealed synthetic seams."""
    from f017_event06_minimum_gate_contract_v1 import (
        OPTIONAL_NON_GATING_MECHANISM_IDS,
    )

    qualification_root = _qualification_root(root)
    if type(omit_optional) is not tuple or any(
        type(item) is not str for item in omit_optional
    ):
        raise TypeError("optional-mechanism omission tuple")
    if len(set(omit_optional)) != len(omit_optional) or not set(
        omit_optional
    ).issubset(set(OPTIONAL_NON_GATING_MECHANISM_IDS)):
        raise ValueError("only optional non-gating mechanisms may be omitted")
    if fail_stage is not None and fail_stage not in _STAGES:
        raise ValueError("fault stage vocabulary")

    intercept_root = qualification_root / "preopen"
    intercept_root.mkdir(exist_ok=False)
    preopen = _run_preopen_intercept(intercept_root)

    case_name = "success" if fail_stage is None else f"fault-{fail_stage.lower()}"
    case_root = qualification_root / case_name
    case_root.mkdir(exist_ok=False)
    now = time.time_ns()
    profile = _authority_profile(synthetic=True)
    seed = f"F017-S39-{case_name}".encode("ascii")
    collapsed_go = _qualification_go(profile, seed, now_unix_ns=now)
    runtime = _qualification_runtime(
        case_root,
        str(_validate_go_bytes(collapsed_go, profile, now_unix_ns=now).get(
            "human_decision_sha256"
        )),
        intercept=False,
        fault_stage=fail_stage,
    )
    result: dict[str, object] | None = None
    stopped = False
    try:
        result = _invoke_public_qualification(
            collapsed_go, runtime, now_unix_ns=now
        )
    except RuntimeError as exc:
        if fail_stage is None or str(exc) != f"INJECTED_STOP_AT_{fail_stage}":
            raise
        stopped = True
    if fail_stage is None and (result is None or result.get("result") != "PASS"):
        raise AssertionError("synthetic full-path qualification did not pass")
    if fail_stage is not None and not stopped:
        raise AssertionError("requested stage did not stop")

    terminal_path = runtime.storage.package_directory / "package-terminal.json"
    package_started = (runtime.storage.package_directory / "package-start.json").is_file()
    if fail_stage is not None:
        if package_started != (fail_stage not in {
            "PREPARED", "INSTALLED", "PACKAGE_START_ELIGIBLE_DRY_STOP", "PACKAGE_START"
        }):
            raise AssertionError("fault/package-start ordering")
        if package_started and not terminal_path.is_file():
            raise AssertionError("post-start failure lacks sole terminal")
        if not package_started and terminal_path.exists():
            raise AssertionError("pre-start failure fabricated a package terminal")

    return {
        "full_call_path_dry_run_with_synthetic_authority": "PASS",
        "public_entry_exercised": "execute_event06_minimum_gate_path",
        "preopen_interception": preopen["preopen_interception"],
        "production_path_components_exercised": "17/17",
        "required_gates_enforced": "17/17",
        "extra_required_gates": 0,
        "uncovered_required_gates": 0,
        "optional_non_gating_omitted": list(omit_optional),
        "optional_omission_changed_required_path": False,
        "fault_stage": fail_stage,
        "fault_stop_observed": stopped,
        "package_started": package_started,
        "package_terminal_banked": terminal_path.is_file(),
        "original_checkpoint_root_resolutions": 0,
        "original_checkpoint_opens_hashes_payload_reads_mmaps": "0/0/0/0",
        "primary_secondary_real_executions": "0/0",
        "full_model_inference": "NONE",
        "real_registry_ledger_or_terminal_writes": 0,
        "synthetic_identities_instantiated": (
            preopen["synthetic_identities_instantiated"]
            + runtime.observed_effects["synthetic_identities_instantiated"]
        ),
        "synthetic_identities_consumed": (
            preopen["synthetic_identities_consumed"]
            + runtime.integration_state.snapshot().get("package_starts")
        ),
        "success_package_terminal_sha256": (
            result["package_terminal_sha256"] if result is not None else None
        ),
        "result": "PASS",
    }
