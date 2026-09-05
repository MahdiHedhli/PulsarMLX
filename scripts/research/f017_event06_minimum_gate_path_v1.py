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
import fcntl
import hashlib
import importlib.util
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import time
from types import MappingProxyType
from typing import Callable, Final, Mapping, Never, TypeVar, cast

import f017_checkpoint_identity_producer_v12 as _identity_producer_module
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
from f017_checkpoint_identity_lifecycle_v12 import (
    IdentityAuthorityError as _IdentityAuthorityError,
)
from f017_checkpoint_identity_producer_v12 import (
    IdentityAccessPrefixValidationError as _IdentityAccessPrefixValidationError,
    _QUALIFICATION_ROOT_DESCRIPTOR_SEAL,
    _bind_qualification_root_descriptor,
    identity_success_evidence_leaves as _identity_success_evidence_leaves,
    missing_identity_access_prefix_census as _missing_identity_access_prefix_census,
    _minimum_gate_produce as _run_identity_stage,
    _reset_qualification_root_descriptor,
    validate_banked_identity_access_prefix as _validate_banked_identity_access_prefix,
    validate_banked_identity_evidence as _validate_banked_identity_evidence,
)
from f017_corrected_oracle_primary_wrapper_v11 import (
    _minimum_gate_execute_target_and_bank as _execute_primary_target,
)
from f017_corrected_oracle_secondary_wrapper_v11 import (
    _minimum_gate_execute_target_and_bank as _execute_secondary_target,
)
from f017_descriptor_lease_manager_v10 import (
    LeaseSet as _LeaseSet,
    validate_descriptors as _validate_descriptors,
)
from f017_event06_minimum_gate_contract_v1 import (
    ACCOUNTING_CLOSURE_SCHEMA as _SUCCESS_ACCOUNTING_SCHEMA,
    HISTORICAL_MASTER_LEDGER as _HISTORICAL_MASTER_LEDGER,
    PACKAGE_TERMINAL_SCHEMA as _SUCCESS_PACKAGE_TERMINAL_SCHEMA,
    REQUIRED_MECHANISM_IDS as _REQUIRED_MECHANISM_IDS,
    STAGE_VOCABULARY as _STAGE_VOCABULARY,
    _build_accounting_closure,
    _build_package_start_gate,
    _build_package_terminal,
    canonical_sha256 as _contract_sha256,
    _ACCOUNTING_KEYS as _SUCCESS_ACCOUNTING_KEYS,
    _IDENTITY_READ_KEYS as _SUCCESS_IDENTITY_READ_KEYS,
    _RECEIPT_BINDING_KEYS as _SUCCESS_RECEIPT_BINDING_KEYS,
    _TERMINAL_KEYS as _SUCCESS_PACKAGE_TERMINAL_KEYS,
    _consume_package_start_gate,
    _package_start_receipt,
    minimum_gate_contract as _minimum_gate_contract,
    _validate_accounting_closure,
    _validate_accounting_document as _validate_success_accounting_document,
    _validate_identity_read_receipts as _validate_success_identity_read_receipts,
    validate_minimum_gate_contract as _validate_minimum_gate_contract,
    _validate_package_start_gate,
    _validate_consumed_package_start_gate,
    _validate_package_terminal,
    _validate_package_terminal_document as _validate_success_package_terminal_document,
)
from f017_result_bundle_builder_v11 import (
    _minimum_gate_bank_output_bundle as _bank_output_bundle,
)
from f017_result_bundle_authority_v11 import validate_bundle as _validate_bundle
from f017_write_once_artifact_v1 import _set_user_immutable

__all__ = (
    "execute_event06_minimum_gate_path",
    "closeout_interrupted_event06_minimum_gate_path",
)


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
_SUCCESS_PHYSICAL_IDENTITY_FILES: Final = frozenset(
    _identity_success_evidence_leaves()
)
_SYNTHETIC_CHECKPOINT_BENIGN_EXTRA_LEAVES: Final = (
    "qualification-benign-extra-leaf.txt",
)
_EMPTY_SHA256: Final = hashlib.sha256(b"").hexdigest()
_STAGE_RECEIPT_SCHEMA: Final = (
    "pulsarmlx.f017.event06-minimum-gate-stage-receipt/1.1.0"
)
_FAILURE_ACCOUNTING_SCHEMA: Final = (
    "pulsarmlx.f017.event06-minimum-gate-failure-accounting/1.1.0"
)
_FAILURE_TERMINAL_SCHEMA: Final = (
    "pulsarmlx.f017.event06-minimum-gate-package-terminal/1.1.0"
)
_FAILURE_ACCOUNTING_FIELDS: Final = frozenset({
    "schema",
    "terminal_origin",
    "failed_stage",
    "authorization_delta",
    "package_delta",
    "primary_delta",
    "secondary_delta",
    "historical_master_ledger_before",
    "historical_master_ledger_after",
    "durable_receipts",
    "invalid_durable_receipts",
    "emergency_release_report_sha256",
    "emergency_release_outcome",
    "checkpoint_access_census",
    "original_checkpoint_opens_lower_bound",
    "original_checkpoint_opens_upper_bound",
    "original_checkpoint_identity_hash_reads_lower_bound",
    "original_checkpoint_identity_hash_reads_upper_bound",
    "real_numerical_executions_observed_in_process",
    "fabricated_successor_receipts",
    "result",
})
_FAILURE_TERMINAL_FIELDS: Final = frozenset({
    "schema",
    "state",
    "terminal_origin",
    "failed_stage",
    "failure_type",
    "failure_wrapper_type",
    "package_attempt_id",
    "failure_accounting",
    "failure_accounting_sha256",
    "failure_accounting_leaf_sha256",
    "emergency_release_report_sha256",
    "emergency_release_result",
    "emergency_release_disposition",
    "fabricated_successor_receipts",
    "result",
})
_ACCESS_CENSUS_FIELDS: Final = frozenset({
    "schema",
    "genesis_sha256",
    "head_sha256",
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
    "receipt_validation",
})
_RESTART_CLOSEOUT_ORIGIN: Final = "RESTART_CLOSEOUT"
_IN_PROCESS_TERMINAL_ORIGIN: Final = "IN_PROCESS_STOP_BOUNDARY"
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


def _canonical_absolute_path(path: Path) -> Path:
    """Reject alternate POSIX anchors and every noncanonical path spelling."""
    if not isinstance(path, Path) or not path.is_absolute() or path.anchor != os.sep:
        raise ValueError("fixed canonical absolute path")
    lexical = Path(os.path.normpath(str(path)))
    if lexical != path or str(path).startswith("//"):
        raise ValueError("fixed canonical absolute path")
    return lexical


def _open_directory_chain(path: Path, *, create: bool) -> int:
    """Open an absolute directory one component at a time without symlinks."""
    path = _canonical_absolute_path(path)
    if path == Path("/"):
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
        "_terminal_claim_fd",
        "_terminal_claim_held",
        "_terminal_writer_retired",
        "_owned_package_start_identity",
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
        self._terminal_claim_fd: int | None = None
        self._terminal_claim_held = False
        self._terminal_writer_retired = False
        self._owned_package_start_identity: tuple[int, int] | None = None

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

    def prepare_existing(self) -> None:
        """Bind an already-created package without creating any filesystem state."""
        if self._package_fd is not None:
            raise RuntimeError("package storage is already prepared")
        parent_fd = _open_directory_chain(
            self.package_directory.parent, create=False
        )
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        package_fd = -1
        try:
            package_fd = os.open(
                self.package_directory.name, flags, dir_fd=parent_fd
            )
            observed = os.fstat(package_fd)
            if (
                not stat.S_ISDIR(observed.st_mode)
                or observed.st_uid != os.getuid()
            ):
                raise ValueError("existing package directory authority")
            self._package_fd = package_fd
            self._package_identity = (observed.st_dev, observed.st_ino)
            package_fd = -1
        finally:
            if package_fd >= 0:
                os.close(package_fd)
            os.close(parent_fd)
        self._verify_package_path_identity()

    def close(self) -> None:
        """Release the package-directory descriptor exactly once."""
        terminal_descriptor = self._terminal_fd
        terminal_claim_descriptor = self._terminal_claim_fd
        descriptor = self._package_fd
        self._terminal_fd = None
        self._terminal_identity = None
        self._terminal_claim_fd = None
        self._terminal_claim_held = False
        self._terminal_writer_retired = False
        self._owned_package_start_identity = None
        self._package_fd = None
        self._package_identity = None
        terminal_error: BaseException | None = None
        if terminal_descriptor is not None:
            try:
                os.close(terminal_descriptor)
            except BaseException as exc:
                terminal_error = exc
        if (
            terminal_claim_descriptor is not None
            and terminal_claim_descriptor != terminal_descriptor
        ):
            try:
                os.close(terminal_claim_descriptor)
            except BaseException as exc:
                if terminal_error is None:
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

    def _verify_held_package_parent_identity(self, parent_fd: int) -> None:
        """Bind a held package to its original parent without trusting its leaf.

        Failure terminalization must remain possible after a canonical package
        leaf is retargeted: the held package descriptor is still the durable
        package authority.  The private staging inode lives in the original
        parent, so prove that parent through ``..`` from the held package rather
        than reopening the now-hostile canonical package leaf.
        """
        if (
            self._package_fd is None
            or self._package_identity is None
            or type(parent_fd) is not int
        ):
            raise RuntimeError("package storage is not prepared")
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        rebound_parent = os.open("..", flags, dir_fd=self._package_fd)
        try:
            held = os.fstat(self._package_fd)
            expected_parent = os.fstat(parent_fd)
            observed_parent = os.fstat(rebound_parent)
            if (
                not stat.S_ISDIR(held.st_mode)
                or held.st_uid != os.getuid()
                or (held.st_dev, held.st_ino) != self._package_identity
                or not stat.S_ISDIR(expected_parent.st_mode)
                or expected_parent.st_uid != os.getuid()
                or (expected_parent.st_dev, expected_parent.st_ino)
                != (observed_parent.st_dev, observed_parent.st_ino)
            ):
                raise RuntimeError("held package parent identity changed")
        finally:
            os.close(rebound_parent)

    def _open_held_package_parent(self) -> int:
        """Open the package's current parent through the held package inode."""
        if self._package_fd is None or self._package_identity is None:
            raise RuntimeError("package storage is not prepared")
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        parent_fd = os.open("..", flags, dir_fd=self._package_fd)
        try:
            self._verify_held_package_parent_identity(parent_fd)
        except BaseException:
            os.close(parent_fd)
            raise
        return parent_fd

    def _require_absent_leaf(self, leaf: str) -> None:
        """Require descriptor-relative no-follow absence of one exact leaf."""
        if self._package_fd is None:
            raise RuntimeError("package storage is not prepared")
        try:
            os.stat(leaf, dir_fd=self._package_fd, follow_symlinks=False)
        except FileNotFoundError:
            return
        raise FileExistsError(f"package leaf already exists: {leaf}")

    def _read_held_leaf(
        self,
        leaf: str,
        *,
        maximum_bytes: int,
        required_mode: int | None = None,
        require_immutable: bool = False,
    ) -> bytes:
        """Read one exact leaf from the held package, without a path reopen."""
        if (
            self._package_fd is None
            or type(maximum_bytes) is not int
            or maximum_bytes < 0
            or (
                required_mode is not None
                and (type(required_mode) is not int or required_mode < 0)
            )
            or type(require_immutable) is not bool
        ):
            raise RuntimeError("package storage is not prepared")
        flags = os.O_RDONLY | os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        descriptor = os.open(leaf, flags, dir_fd=self._package_fd)
        try:
            before = os.fstat(descriptor)
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_nlink != 1
                or before.st_uid != os.getuid()
                or before.st_size > maximum_bytes
                or (
                    required_mode is not None
                    and stat.S_IMODE(before.st_mode) != required_mode
                )
                or (
                    require_immutable
                    and not bool(before.st_flags & stat.UF_IMMUTABLE)
                )
            ):
                raise ValueError("held package leaf identity")
            chunks: list[bytes] = []
            remaining = before.st_size
            while remaining:
                chunk = os.read(descriptor, min(65_536, remaining))
                if not chunk:
                    raise OSError("short held package leaf read")
                chunks.append(chunk)
                remaining -= len(chunk)
            if os.read(descriptor, 1):
                raise ValueError("held package leaf excess bytes")
            after = os.fstat(descriptor)
            canonical = os.stat(
                leaf, dir_fd=self._package_fd, follow_symlinks=False
            )
            stable_fields = (
                "st_dev", "st_ino", "st_mode", "st_uid", "st_nlink",
                "st_size", "st_mtime_ns", "st_ctime_ns", "st_flags",
            )
            if (
                any(
                    getattr(before, field, 0) != getattr(after, field, 0)
                    for field in stable_fields
                )
                or (canonical.st_dev, canonical.st_ino)
                != (after.st_dev, after.st_ino)
            ):
                raise RuntimeError("held package leaf identity changed")
            return b"".join(chunks)
        finally:
            os.close(descriptor)

    def _classify_package_start(self, expected_raw: bytes) -> str:
        """Classify durable start truth solely from a fresh descriptor reopen."""
        try:
            raw = self._read_held_leaf("package-start.json", maximum_bytes=65_536)
        except FileNotFoundError:
            return "ABSENT"
        except BaseException:
            return "INVALID_START_WITH_RESERVATION"
        try:
            value = _parse_artifact_bytes(raw)
        except BaseException:
            return "INVALID_START_WITH_RESERVATION"
        try:
            marker = os.stat(
                "package-start.json",
                dir_fd=self._package_fd,
                follow_symlinks=False,
            )
        except OSError:
            return "INVALID_START_WITH_RESERVATION"
        if (
            raw == expected_raw
            and type(value) is dict
            and _canonical_bytes(value) == raw
            and stat.S_ISREG(marker.st_mode)
            and marker.st_uid == os.getuid()
            and marker.st_nlink == 1
            and stat.S_IMODE(marker.st_mode) == 0o600
        ):
            return "VALID_DURABLE_START"
        return "INVALID_START_WITH_RESERVATION"

    def _remove_owned_invalid_package_start(self) -> bool:
        """Durably remove only this reservation owner's invalid start leaf."""
        owned_identity = self._owned_package_start_identity
        if (
            self._package_fd is None
            or not self._terminal_claim_held
            or owned_identity is None
        ):
            return False
        flags = os.O_RDWR | os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        try:
            descriptor = os.open(
                "package-start.json", flags, dir_fd=self._package_fd
            )
        except OSError:
            return False
        removed = False
        try:
            observed = os.fstat(descriptor)
            canonical = os.stat(
                "package-start.json",
                dir_fd=self._package_fd,
                follow_symlinks=False,
            )
            if (
                not stat.S_ISREG(observed.st_mode)
                or observed.st_uid != os.getuid()
                or observed.st_nlink != 1
                or (observed.st_dev, observed.st_ino) != owned_identity
                or (observed.st_dev, observed.st_ino)
                != (canonical.st_dev, canonical.st_ino)
            ):
                return False
            if bool(observed.st_flags & stat.UF_IMMUTABLE):
                _set_user_immutable(descriptor, False)
            os.unlink("package-start.json", dir_fd=self._package_fd)
            os.fsync(self._package_fd)
            self._require_absent_leaf("package-start.json")
            self._owned_package_start_identity = None
            removed = True
        finally:
            os.close(descriptor)
        return removed

    def observe_package_start(self, expected_raw: bytes) -> str:
        """Classify one durable start marker from exact held-package bytes."""
        if type(expected_raw) is not bytes or not expected_raw:
            raise TypeError("expected package-start bytes")
        return self._classify_package_start(expected_raw)

    def _owns_valid_package_start(self, expected_raw: bytes) -> bool:
        """Return true only for the exact start inode created by this instance."""
        owned = self._owned_package_start_identity
        if owned is None or self._package_fd is None:
            return False
        if self._classify_package_start(expected_raw) != "VALID_DURABLE_START":
            return False
        try:
            observed = os.stat(
                "package-start.json",
                dir_fd=self._package_fd,
                follow_symlinks=False,
            )
        except OSError:
            return False
        return (
            stat.S_ISREG(observed.st_mode)
            and observed.st_uid == os.getuid()
            and observed.st_nlink == 1
            and (observed.st_dev, observed.st_ino) == owned
        )

    def acquire_interrupted_terminal(
        self,
        expected_start_raw: bytes,
        *,
        runtime: _Runtime | None = None,
    ) -> str:
        """Acquire only an existing empty reservation after its owner exited.

        This method never creates, replaces, truncates, or cleans up a package
        artifact.  The returned state is derived while holding the package
        descriptor and, for the winner, a nonblocking kernel claim on the
        already-existing terminal inode.
        """
        if self._package_fd is None or self._package_identity is None:
            raise RuntimeError("package storage is not prepared")
        start_state = self.observe_package_start(expected_start_raw)
        expected_start = _parse_artifact_bytes(expected_start_raw)
        if type(expected_start) is not dict:
            raise ValueError("expected package-start document")
        expected_package_id = expected_start.get("package_attempt_id")
        flags = os.O_RDWR | os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        opened_read_only = False
        try:
            descriptor = os.open(
                "package-terminal.json", flags, dir_fd=self._package_fd
            )
        except PermissionError:
            readonly_flags = os.O_RDONLY | os.O_NOFOLLOW
            if hasattr(os, "O_CLOEXEC"):
                readonly_flags |= os.O_CLOEXEC
            descriptor = os.open(
                "package-terminal.json", readonly_flags, dir_fd=self._package_fd
            )
            opened_read_only = True
        except FileNotFoundError:
            return (
                "VALID_START_WITHOUT_VALID_RESERVED_TERMINAL"
                if start_state == "VALID_DURABLE_START"
                else start_state
            )
        except OSError:
            return (
                "VALID_START_WITHOUT_VALID_RESERVED_TERMINAL"
                if start_state == "VALID_DURABLE_START"
                else "INVALID_START_WITH_RESERVATION"
            )
        retain = False
        writer_descriptor: int | None = None
        try:
            observed = os.fstat(descriptor)
            canonical = os.stat(
                "package-terminal.json",
                dir_fd=self._package_fd,
                follow_symlinks=False,
            )
            terminal_identity = (observed.st_dev, observed.st_ino)
            valid_identity = (
                stat.S_ISREG(observed.st_mode)
                and observed.st_uid == os.getuid()
                and observed.st_nlink == 1
                and terminal_identity == (canonical.st_dev, canonical.st_ino)
                and stat.S_IMODE(observed.st_mode) in {0o400, 0o600}
            )
            if not valid_identity:
                return (
                    "VALID_START_WITHOUT_VALID_RESERVED_TERMINAL"
                    if start_state == "VALID_DURABLE_START"
                    else "INVALID_START_WITH_RESERVATION"
                )
            if observed.st_size:
                if start_state != "VALID_DURABLE_START":
                    return "INVALID_START_WITH_RESERVATION"
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except (BlockingIOError, OSError) as exc:
                    if isinstance(exc, BlockingIOError) or getattr(
                        exc, "errno", None
                    ) in {errno.EACCES, errno.EAGAIN}:
                        return "EXECUTING_OWNER_ACTIVE"
                    raise
                try:
                    os.lseek(descriptor, 0, os.SEEK_SET)
                    raw = os.read(descriptor, min(observed.st_size + 1, 1_048_577))
                    value = _parse_artifact_bytes(raw)
                except BaseException:
                    return "VALID_START_WITHOUT_VALID_RESERVED_TERMINAL"
                common_invalid = (
                    len(raw) != observed.st_size
                    or observed.st_size > 1_048_576
                    or type(value) is not dict
                    or _canonical_bytes(value) != raw
                    or value.get("package_attempt_id") != expected_package_id
                    or stat.S_IMODE(observed.st_mode) != 0o400
                )
                if common_invalid:
                    return "VALID_START_WITHOUT_VALID_RESERVED_TERMINAL"
                try:
                    _validate_existing_package_terminal(
                        self,
                        value,
                        raw,
                        expected_start_raw,
                        runtime=runtime,
                    )
                except BaseException:
                    return "VALID_START_WITHOUT_VALID_RESERVED_TERMINAL"
                # A process can exit at any instruction after the atomic
                # rename, including after sealing the terminal but before
                # sealing or syncing its package directory.  Hold the exact
                # published inode while revalidating the bytes and completing
                # every missing durability step.  This path is used even when
                # the terminal is already immutable so a terminal-sealed /
                # package-unsealed crash cannot be accepted as complete.
                current = os.fstat(descriptor)
                rebound = os.stat(
                    "package-terminal.json",
                    dir_fd=self._package_fd,
                    follow_symlinks=False,
                )
                os.lseek(descriptor, 0, os.SEEK_SET)
                repeated = os.read(descriptor, len(raw) + 1)
                if (
                    (current.st_dev, current.st_ino) != terminal_identity
                    or (rebound.st_dev, rebound.st_ino) != terminal_identity
                    or current.st_uid != os.getuid()
                    or current.st_nlink != 1
                    or current.st_size != len(raw)
                    or stat.S_IMODE(current.st_mode) != 0o400
                    or repeated != raw
                ):
                    return "VALID_START_WITHOUT_VALID_RESERVED_TERMINAL"
                _set_user_immutable(descriptor, True)
                _set_user_immutable(self._package_fd, True)
                os.fsync(descriptor)
                os.fsync(self._package_fd)
                parent_fd = _open_directory_chain(
                    self.package_directory.parent, create=False
                )
                try:
                    os.fsync(parent_fd)
                finally:
                    self._close_descriptor_confirmed(parent_fd)
                sealed = os.fstat(descriptor)
                sealed_package = os.fstat(self._package_fd)
                rebound = os.stat(
                    "package-terminal.json",
                    dir_fd=self._package_fd,
                    follow_symlinks=False,
                )
                self._verify_package_path_identity()
                if (
                    (sealed.st_dev, sealed.st_ino) != terminal_identity
                    or (rebound.st_dev, rebound.st_ino) != terminal_identity
                    or stat.S_IMODE(sealed.st_mode) != 0o400
                    or not bool(sealed.st_flags & stat.UF_IMMUTABLE)
                    or not bool(sealed_package.st_flags & stat.UF_IMMUTABLE)
                ):
                    raise RuntimeError("recovered package terminal seal")
                return "ALREADY_TERMINAL"
            if start_state == "ABSENT":
                return "EMPTY_RESERVATION_WITHOUT_START"
            if start_state != "VALID_DURABLE_START":
                return "INVALID_START_WITH_RESERVATION"
            if stat.S_IMODE(observed.st_mode) != 0o600:
                return "VALID_START_WITHOUT_VALID_RESERVED_TERMINAL"
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return "EXECUTING_OWNER_ACTIVE"
            except OSError as exc:
                if exc.errno in {errno.EACCES, errno.EAGAIN}:
                    return "EXECUTING_OWNER_ACTIVE"
                raise
            # Revalidate both leaves after winning.  The lock applies to this
            # exact existing terminal inode, not a pathname or package claim.
            if self.observe_package_start(expected_start_raw) != "VALID_DURABLE_START":
                return "INVALID_START_WITH_RESERVATION"
            current = os.fstat(descriptor)
            rebound = os.stat(
                "package-terminal.json",
                dir_fd=self._package_fd,
                follow_symlinks=False,
            )
            if (
                (current.st_dev, current.st_ino) != terminal_identity
                or (rebound.st_dev, rebound.st_ino) != terminal_identity
                or current.st_size != 0
                or current.st_uid != os.getuid()
                or current.st_nlink != 1
                or stat.S_IMODE(current.st_mode) != 0o600
            ):
                return "VALID_START_WITHOUT_VALID_RESERVED_TERMINAL"
            if not bool(current.st_flags & stat.UF_IMMUTABLE):
                _set_user_immutable(descriptor, True)
                os.fsync(descriptor)
                os.fsync(self._package_fd)
            if opened_read_only:
                # The read-only descriptor holds the uninterrupted kernel
                # claim.  Temporarily clear the immutable flag through that
                # exact inode, open a distinct writer while the claim remains
                # held, revalidate identity, and reseal before exposing the
                # writer to the terminal routine.
                _set_user_immutable(descriptor, False)
                writer_descriptor = os.open(
                    "package-terminal.json",
                    flags,
                    dir_fd=self._package_fd,
                )
                writer = os.fstat(writer_descriptor)
                rebound = os.stat(
                    "package-terminal.json",
                    dir_fd=self._package_fd,
                    follow_symlinks=False,
                )
                if (
                    (writer.st_dev, writer.st_ino) != terminal_identity
                    or (rebound.st_dev, rebound.st_ino) != terminal_identity
                    or writer.st_size != 0
                    or writer.st_uid != os.getuid()
                    or writer.st_nlink != 1
                    or stat.S_IMODE(writer.st_mode) != 0o600
                ):
                    raise ValueError("restart terminal writer identity")
                _set_user_immutable(writer_descriptor, True)
                os.fsync(writer_descriptor)
                os.fsync(self._package_fd)
                self._terminal_fd = writer_descriptor
                self._terminal_claim_fd = descriptor
                writer_descriptor = None
            else:
                self._terminal_fd = descriptor
                self._terminal_claim_fd = None
            self._terminal_identity = terminal_identity
            self._terminal_claim_held = True
            self._terminal_writer_retired = False
            retain = True
            return "ACQUIRED_FOR_RESTART_CLOSEOUT"
        finally:
            if writer_descriptor is not None:
                try:
                    _set_user_immutable(writer_descriptor, True)
                except BaseException:
                    pass
                os.close(writer_descriptor)
            if not retain:
                if opened_read_only:
                    try:
                        _set_user_immutable(descriptor, True)
                    except BaseException:
                        pass
                os.close(descriptor)

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
        if leaf == "package-start.json" and durable_start is not None:
            created = os.fstat(descriptor)
            self._owned_package_start_identity = (created.st_dev, created.st_ino)
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
            durable_start.mark_package_started(digest, expected_raw=raw)
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
        expected_raw = _canonical_bytes(dict(value))
        expected_digest = _sha(expected_raw)
        self._reserve_package_terminal(stop)
        try:
            return self._bank_leaf(
                "package-start.json",
                value,
                require_canonical_path=True,
                durable_start=stop,
            )
        except BaseException:
            classification = self._classify_package_start(expected_raw)
            if (
                classification == "VALID_DURABLE_START"
                and self._owns_valid_package_start(expected_raw)
            ):
                stop.mark_package_started(expected_digest, expected_raw=expected_raw)
            elif classification in {"ABSENT", "VALID_DURABLE_START"}:
                try:
                    self._discard_prestart_terminal_reservation()
                except BaseException:
                    pass
            elif self._remove_owned_invalid_package_start():
                try:
                    self._discard_prestart_terminal_reservation()
                except BaseException:
                    pass
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
            or self._terminal_claim_fd is not None
            or self._terminal_claim_held
            or self._terminal_writer_retired
        ):
            raise TypeError("uncommitted package stop boundary required")
        self._verify_package_path_identity()
        # The terminal claim is never introduced into a package that already
        # has a start marker.  Any later EEXIST is therefore an owner race,
        # not adoption of foreign or historical package state.
        self._require_absent_leaf("package-terminal.json")
        # This is deliberately the last namespace observation before O_EXCL:
        # an already-started package never acquires a new terminal reservation.
        self._require_absent_leaf("package-start.json")
        flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        descriptor = os.open(
            "package-terminal.json", flags, 0o600, dir_fd=self._package_fd
        )
        created_identity: tuple[int, int] | None = None
        terminal_immutable = False
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            observed = os.fstat(descriptor)
            created_identity = (observed.st_dev, observed.st_ino)
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
            self._terminal_claim_fd = None
            self._terminal_claim_held = True
            self._terminal_writer_retired = False
            return None
        except BaseException:
            removable = False
            try:
                # If a start appeared after the pre-open check, the reservation
                # is now part of a potentially durable package prefix.  Retain
                # it; cleanup must never strand that start without a terminal.
                self._require_absent_leaf("package-start.json")
                removable = True
            except BaseException:
                try:
                    if not terminal_immutable:
                        _set_user_immutable(descriptor, True)
                        os.fsync(descriptor)
                        os.fsync(self._package_fd)
                except BaseException:
                    pass
            if removable and terminal_immutable:
                try:
                    _set_user_immutable(descriptor, False)
                except BaseException:
                    removable = False
            try:
                if removable:
                    canonical = os.stat(
                        "package-terminal.json",
                        dir_fd=self._package_fd,
                        follow_symlinks=False,
                    )
                    if (
                        stat.S_ISREG(canonical.st_mode)
                        and canonical.st_uid == os.getuid()
                        and canonical.st_nlink == 1
                        and created_identity is not None
                        and (canonical.st_dev, canonical.st_ino)
                        == created_identity
                        and canonical.st_size == 0
                    ):
                        # No path operation is performed between this final
                        # nofollow start-absence proof and the owned unlink.
                        self._require_absent_leaf("package-start.json")
                        os.unlink(
                            "package-terminal.json", dir_fd=self._package_fd
                        )
                        os.fsync(self._package_fd)
            except BaseException:
                pass
            try:
                self._close_descriptor_confirmed(descriptor)
            except BaseException:
                # Reservation cleanup is best effort and must never replace
                # the original pre-start exception.
                pass
            raise

    def _discard_prestart_terminal_reservation(self) -> None:
        """Remove only this instance's empty terminal before durable start."""
        descriptor = self._terminal_fd
        identity = self._terminal_identity
        if descriptor is None or identity is None:
            return
        removed = False
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
            self._require_absent_leaf("package-start.json")
            _set_user_immutable(descriptor, False)
            # Recheck immediately before the only namespace mutation.  A
            # concurrent start retains the reservation and forces fail-closed.
            self._require_absent_leaf("package-start.json")
            os.unlink("package-terminal.json", dir_fd=self._package_fd)
            os.fsync(self._package_fd)
            removed = True
        except BaseException:
            try:
                _set_user_immutable(descriptor, True)
                os.fsync(descriptor)
            except BaseException:
                pass
            raise
        finally:
            if removed:
                os.close(descriptor)
                self._terminal_fd = None
                self._terminal_identity = None
                self._terminal_claim_fd = None
                self._terminal_claim_held = False
                self._terminal_writer_retired = False

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
        root_directories = {"primary", "secondary", "identity"}
        if self.scope not in {"SYNTHETIC", "PRODUCTION"}:
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
                _SUCCESS_PHYSICAL_IDENTITY_FILES
            ):
                raise ValueError("package identity directory entry census")
            for leaf in sorted(_SUCCESS_PHYSICAL_IDENTITY_FILES):
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
                or not self._terminal_claim_held
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
            os.fchmod(current, 0o600)
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

    @staticmethod
    def _close_descriptor_confirmed(descriptor: int) -> None:
        """Retire one descriptor even when a wrapper reports ambiguous close."""
        try:
            os.close(descriptor)
            return
        except BaseException as close_error:
            try:
                os.fstat(descriptor)
            except OSError as state_error:
                if state_error.errno == errno.EBADF:
                    return
                raise close_error
            libc = ctypes.CDLL(None, use_errno=True)
            kernel_close = libc.close
            kernel_close.argtypes = [ctypes.c_int]
            kernel_close.restype = ctypes.c_int
            if kernel_close(descriptor) == 0:
                return
            kernel_error = ctypes.get_errno()
            try:
                os.fstat(descriptor)
            except OSError as state_error:
                if state_error.errno == errno.EBADF:
                    return
            raise OSError(kernel_error, os.strerror(kernel_error)) from close_error

    def _publish_reserved_terminal_atomically(
        self,
        descriptor: int,
        raw: bytes,
        stop: _StopBoundary | None,
    ) -> None:
        """Publish complete terminal bytes by one same-filesystem rename.

        The continuously locked empty terminal remains the sole namespace
        reservation while a private sibling inode is written, read back,
        fsynced, mode-restricted, and sealed.  A crash before the rename leaves
        the empty reservation recoverable; a crash after it exposes only the
        complete immutable terminal.
        """
        if (
            self._package_fd is None
            or self._package_identity is None
            or descriptor != self._terminal_fd
            or self._terminal_identity is None
            or not self._terminal_claim_held
            or self._terminal_writer_retired
            or type(raw) is not bytes
            or not raw
            or (stop is not None and type(stop) is not _StopBoundary)
        ):
            raise ValueError("reserved atomic terminal authority")
        reserved_identity = self._terminal_identity
        observed = os.fstat(descriptor)
        canonical = os.stat(
            "package-terminal.json",
            dir_fd=self._package_fd,
            follow_symlinks=False,
        )
        if (
            (observed.st_dev, observed.st_ino) != reserved_identity
            or (canonical.st_dev, canonical.st_ino) != reserved_identity
            or not stat.S_ISREG(observed.st_mode)
            or observed.st_uid != os.getuid()
            or observed.st_nlink != 1
            or observed.st_size != 0
            or not bool(observed.st_flags & stat.UF_IMMUTABLE)
        ):
            raise ValueError("reserved atomic terminal identity")

        # Derive the staging parent from the held package inode.  A canonical
        # path-recheck failure may mean the original package leaf was renamed;
        # failure closure must not follow the replacement pathname.
        parent_fd = self._open_held_package_parent()
        stage_leaf = (
            f".{self.package_directory.name}.terminal-stage-"
            f"{_sha(raw)[:16]}-{os.getpid()}-{time.monotonic_ns()}"
        )
        stage_fd = -1
        stage_identity: tuple[int, int] | None = None
        renamed = False
        final_reader = -1
        try:
            self._verify_held_package_parent_identity(parent_fd)
            if stop is not None:
                # Success may only publish into the still-canonical package.
                # Failure publication deliberately remains bound to the held
                # package so a path-recheck failure can itself terminalize.
                self._verify_package_path_identity()
            flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
            if hasattr(os, "O_CLOEXEC"):
                flags |= os.O_CLOEXEC
            stage_fd = os.open(stage_leaf, flags, 0o600, dir_fd=parent_fd)
            # The staging inode becomes the published terminal inode at the
            # rename.  Claim it before the first write and retain that claim
            # through publication and writer retirement; the old reservation
            # remains independently claimed until the rename has completed.
            fcntl.flock(stage_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            created = os.fstat(stage_fd)
            stage_identity = (created.st_dev, created.st_ino)
            if (
                not stat.S_ISREG(created.st_mode)
                or created.st_uid != os.getuid()
                or created.st_nlink != 1
                or created.st_size != 0
            ):
                raise ValueError("atomic terminal staging identity")
            view = memoryview(raw)
            written = 0
            while written < len(view):
                count = os.write(stage_fd, view[written:])
                if count <= 0:
                    raise OSError("short staged terminal write")
                written += count
            os.fsync(stage_fd)
            staged = os.fstat(stage_fd)
            if staged.st_size != len(raw):
                raise ValueError("staged terminal byte count")
            os.lseek(stage_fd, 0, os.SEEK_SET)
            chunks: list[bytes] = []
            remaining = len(raw)
            while remaining:
                chunk = os.read(stage_fd, min(65_536, remaining))
                if not chunk:
                    raise OSError("short staged terminal readback")
                chunks.append(chunk)
                remaining -= len(chunk)
            if os.read(stage_fd, 1) or b"".join(chunks) != raw:
                raise ValueError("staged terminal readback")
            os.fchmod(stage_fd, 0o400)
            _set_user_immutable(stage_fd, True)
            os.fsync(stage_fd)
            staged = os.fstat(stage_fd)
            rebound_stage = os.stat(
                stage_leaf, dir_fd=parent_fd, follow_symlinks=False
            )
            if (
                (staged.st_dev, staged.st_ino) != stage_identity
                or (rebound_stage.st_dev, rebound_stage.st_ino) != stage_identity
                or staged.st_size != len(raw)
                or stat.S_IMODE(staged.st_mode) != 0o400
                or not bool(staged.st_flags & stat.UF_IMMUTABLE)
            ):
                raise ValueError("sealed staged terminal identity")

            # The old locked inode remains the exact target until the single
            # atomic replacement.  Darwin forbids renaming either an immutable
            # source or over an immutable target, so clear exactly those two
            # leaf flags and the parent flag immediately around rename.
            self._verify_held_package_parent_identity(parent_fd)
            if stop is not None:
                self._verify_package_path_identity()
            _set_user_immutable(stage_fd, False)
            _set_user_immutable(descriptor, False)
            _set_user_immutable(self._package_fd, False)
            current = os.fstat(descriptor)
            rebound = os.stat(
                "package-terminal.json",
                dir_fd=self._package_fd,
                follow_symlinks=False,
            )
            if (
                (current.st_dev, current.st_ino) != reserved_identity
                or (rebound.st_dev, rebound.st_ino) != reserved_identity
                or current.st_size != 0
            ):
                raise ValueError("atomic terminal reservation changed")
            os.rename(
                stage_leaf,
                "package-terminal.json",
                src_dir_fd=parent_fd,
                dst_dir_fd=self._package_fd,
            )
            renamed = True
            _set_user_immutable(stage_fd, True)
            _set_user_immutable(self._package_fd, True)
            os.fsync(stage_fd)
            os.fsync(self._package_fd)
            os.fsync(parent_fd)
            self._verify_held_package_parent_identity(parent_fd)
            if stop is not None:
                self._verify_package_path_identity()

            read_flags = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW
            if hasattr(os, "O_CLOEXEC"):
                read_flags |= os.O_CLOEXEC
            final_reader = os.open(
                "package-terminal.json", read_flags, dir_fd=self._package_fd
            )
            final = os.fstat(final_reader)
            rebound = os.stat(
                "package-terminal.json",
                dir_fd=self._package_fd,
                follow_symlinks=False,
            )
            if (
                (final.st_dev, final.st_ino) != stage_identity
                or (rebound.st_dev, rebound.st_ino) != stage_identity
                or final.st_size != len(raw)
                or final.st_uid != os.getuid()
                or final.st_nlink != 1
                or stat.S_IMODE(final.st_mode) != 0o400
                or not bool(final.st_flags & stat.UF_IMMUTABLE)
                or not bool(os.fstat(self._package_fd).st_flags & stat.UF_IMMUTABLE)
            ):
                raise ValueError("published terminal identity")
            readback = os.read(final_reader, len(raw) + 1)
            if readback != raw:
                raise ValueError("published terminal bytes")
            self._close_descriptor_confirmed(descriptor)
            claim_descriptor = self._terminal_claim_fd
            if claim_descriptor is not None and claim_descriptor != descriptor:
                self._close_descriptor_confirmed(claim_descriptor)
            self._terminal_fd = final_reader
            final_reader = -1
            self._terminal_identity = stage_identity
            # The staging descriptor still owns an exclusive flock on the
            # inode that became the canonical terminal.  Retain it until
            # storage retirement instead of introducing a post-publication
            # lock gap between closing the writer and recording retirement.
            self._terminal_claim_fd = stage_fd
            stage_fd = -1
            self._terminal_claim_held = True
            self._terminal_writer_retired = True
            if stop is not None:
                stop.terminal_banked = True
        except BaseException:
            if renamed and stage_identity is not None:
                # A post-rename fault can only expose the already complete
                # staged inode.  Reopen and prove it before declaring the
                # writer retired; never roll a complete terminal backward.
                try:
                    if stage_fd >= 0:
                        _set_user_immutable(stage_fd, True)
                    _set_user_immutable(self._package_fd, True)
                    if stage_fd >= 0:
                        os.fsync(stage_fd)
                    os.fsync(self._package_fd)
                    os.fsync(parent_fd)
                    self._verify_held_package_parent_identity(parent_fd)
                    if stop is not None:
                        self._verify_package_path_identity()
                    flags = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW
                    if hasattr(os, "O_CLOEXEC"):
                        flags |= os.O_CLOEXEC
                    proven = os.open(
                        "package-terminal.json", flags, dir_fd=self._package_fd
                    )
                    final = os.fstat(proven)
                    if (
                        (final.st_dev, final.st_ino) == stage_identity
                        and final.st_size == len(raw)
                        and stat.S_IMODE(final.st_mode) == 0o400
                        and bool(final.st_flags & stat.UF_IMMUTABLE)
                        and bool(
                            os.fstat(self._package_fd).st_flags
                            & stat.UF_IMMUTABLE
                        )
                        and os.read(proven, len(raw) + 1) == raw
                    ):
                        self._close_descriptor_confirmed(descriptor)
                        claim_descriptor = self._terminal_claim_fd
                        if claim_descriptor is not None and claim_descriptor != descriptor:
                            self._close_descriptor_confirmed(claim_descriptor)
                        self._terminal_fd = proven
                        self._terminal_identity = stage_identity
                        # Keep the published inode's staging flock through
                        # recovery retirement for the same continuous-claim
                        # guarantee as the non-faulting publication path.
                        self._terminal_claim_fd = stage_fd
                        stage_fd = -1
                        self._terminal_claim_held = True
                        self._terminal_writer_retired = True
                        if stop is not None:
                            stop.terminal_banked = True
                        proven = -1
                    if proven >= 0:
                        os.close(proven)
                except BaseException:
                    pass
            else:
                try:
                    _set_user_immutable(descriptor, True)
                    _set_user_immutable(self._package_fd, True)
                    os.fsync(descriptor)
                    os.fsync(self._package_fd)
                except BaseException:
                    pass
            raise
        finally:
            if final_reader >= 0:
                self._close_descriptor_confirmed(final_reader)
            if stage_fd >= 0:
                self._close_descriptor_confirmed(stage_fd)
            if not renamed and stage_identity is not None:
                try:
                    candidate = os.stat(
                        stage_leaf, dir_fd=parent_fd, follow_symlinks=False
                    )
                    if (candidate.st_dev, candidate.st_ino) == stage_identity:
                        cleanup = os.open(
                            stage_leaf,
                            os.O_RDONLY | os.O_NOFOLLOW,
                            dir_fd=parent_fd,
                        )
                        try:
                            _set_user_immutable(cleanup, False)
                        finally:
                            os.close(cleanup)
                        os.unlink(stage_leaf, dir_fd=parent_fd)
                        os.fsync(parent_fd)
                except BaseException:
                    pass
            self._close_descriptor_confirmed(parent_fd)

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
            or not self._terminal_claim_held
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
        self._publish_reserved_terminal_atomically(descriptor, raw, stop)

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
        claim_descriptor = self._terminal_claim_fd
        if (
            claim_descriptor is not None
            and claim_descriptor != writer_descriptor
        ):
            try:
                os.close(claim_descriptor)
            except BaseException as close_error:
                try:
                    os.fstat(claim_descriptor)
                except OSError as state_error:
                    if state_error.errno != errno.EBADF:
                        raise close_error
                else:
                    libc = ctypes.CDLL(None, use_errno=True)
                    kernel_close = libc.close
                    kernel_close.argtypes = [ctypes.c_int]
                    kernel_close.restype = ctypes.c_int
                    if kernel_close(claim_descriptor) != 0:
                        raise close_error
        self._terminal_fd = reader
        self._terminal_claim_fd = None
        self._terminal_claim_held = False
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
            or not self._terminal_claim_held
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
        self._publish_reserved_terminal_atomically(descriptor, raw, None)

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

    def anchored_existing_path_call(
        self, child: str, operation: Callable[[Path], _AnchoredResult]
    ) -> _AnchoredResult:
        """Run a read-only path API below an existing held child directory."""
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
                raise ValueError("anchored existing child directory identity")
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
                raise RuntimeError("anchored existing child identity changed")
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

    __slots__ = ("_qualification_root", "_preserve_terminal_on_close")

    def __new__(cls, seal: object = None, *args: object):
        del args
        if seal is not _SYNTHETIC_STORAGE_SEAL:
            raise TypeError("synthetic storage is qualification-created")
        return super().__new__(cls)

    def __init__(self, seal: object, qualification_root: Path, package_key: str) -> None:
        del seal
        graph_root = _qualification_root(qualification_root)
        package = graph_root / f"minimum-gate-{package_key}"
        self._qualification_root = graph_root
        self._preserve_terminal_on_close = False
        super().__init__(package, "SYNTHETIC")

    def preserve_terminal_for_closeout(self, seal: object) -> None:
        """Keep closeout bytes sealed until the test harness explicitly cleans up."""
        if seal is not _SYNTHETIC_STORAGE_SEAL:
            raise TypeError("synthetic closeout preservation seal")
        self._preserve_terminal_on_close = True

    def prepare(self) -> None:
        if self.scope != "SYNTHETIC":
            raise TypeError("synthetic storage authority")
        super().prepare()
        if self.package_directory.parent != self._qualification_root:
            raise ValueError("synthetic storage escape")
        self._verify_package_path_identity()

    def close(self) -> None:
        """Unseal graph-owned test leaves only after the public path returns."""
        try:
            if (
                not self._preserve_terminal_on_close
                and self._package_fd is not None
                and self._terminal_fd is not None
            ):
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
    producer_failure = (
        release.get("release_disposition")
        == "IDENTITY_PRODUCER_FAILURE_DESCRIPTOR_DISPOSITION"
        and type(release.get("identity_failure")) is dict
        and release.get("result") == "PASS"
        and release.get("attempted_closures")
        == release.get("successful_closures")
        and release.get("live_leases_after_release") == 0
    )
    value = {
        "schema": "pulsarmlx.f017.event06-minimum-gate-emergency-release/1.0.0",
        "failed_stage": failed_stage,
        "attempted_closures": release.get("attempted_closures"),
        "successful_closures": release.get("successful_closures"),
        "duplicate_closes": release.get("duplicate_closures"),
        "unknown_leases": release.get("unknown_leases"),
        "live_leases": release.get("live_leases_after_release"),
        "release_result": release.get("result"),
        "release_disposition": release.get("release_disposition"),
        "result": (
            "PASS"
            if no_leases or complete_release or producer_failure
            else "FAIL"
        ),
    }
    if type(release.get("identity_failure")) is dict:
        value["identity_failure"] = dict(release["identity_failure"])
    return value


def _identity_failure_release_outcome(
    exc: _IdentityAuthorityError,
) -> dict[str, object] | None:
    """Project producer-retired descriptor truth into outer release evidence."""
    disposition = exc.descriptor_disposition
    if disposition is None:
        return None
    descriptor = disposition.evidence
    opened = int(descriptor["opened"])
    retained = int(descriptor["retained_leases"])
    return {
        "attempted_closures": opened,
        "successful_closures": opened - retained,
        "duplicate_closures": 0,
        "unknown_leases": 0,
        "live_leases_after_release": retained,
        "release_disposition": (
            "IDENTITY_PRODUCER_FAILURE_DESCRIPTOR_DISPOSITION"
        ),
        "identity_failure": {
            "outcome_id": exc.outcome_id,
            "detail": exc.detail,
            "evidence_failure_type": exc.evidence_failure_type,
            "operation_observation": (
                exc.operation_observation.evidence
                if exc.operation_observation is not None
                else None
            ),
            "access_census": (
                exc.access_census.evidence
                if exc.access_census is not None
                else None
            ),
            "descriptor_disposition": descriptor,
        },
        "result": "PASS" if retained == 0 else "FAIL",
    }


def _raise_identity_handoff_failure(
    storage: _StorageBinding,
    leases: _LeaseSet,
    cause: BaseException,
) -> Never:
    """Retire acquired leases and carry their exact census to terminalization."""
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
                    record.close_attempt_count > 0 for record in leases.records
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
        cause,
        release_evidence_error,
    ) from cause


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
            _raise_identity_handoff_failure(storage, leases, exc)


def _close_synthetic_checkpoint_root_descriptor(descriptor: int) -> None:
    """One injectable close boundary for the qualification-owned root handle."""
    os.close(descriptor)


class _SyntheticCheckpointProvider:
    """The sole checkpoint seam; no production authority can reach it."""

    __slots__ = (
        "_intercept",
        "_fixture_identity",
        "_fixture_leaf_identities",
        "preopen_intercepted",
        "physical_identity_producer_calls",
        "producer_checkpoint_binding_checks",
        "producer_checkpoint_shard_opens",
        "producer_checkpoint_hash_attempts",
        "producer_checkpoint_identity_hash_reads",
    )

    def __new__(cls, seal: object = None, *args: object, **kwargs: object):
        del args, kwargs
        if seal is not _SYNTHETIC_CHECKPOINT_SEAL:
            raise TypeError("synthetic checkpoint provider is qualification-created")
        return super().__new__(cls)

    def __init__(self, seal: object, *, intercept: bool) -> None:
        del seal
        self._intercept = intercept
        self._fixture_identity: tuple[int, int] | None = None
        self._fixture_leaf_identities: tuple[tuple[str, int, int], ...] | None = None
        self.preopen_intercepted = False
        self.physical_identity_producer_calls = 0
        self.producer_checkpoint_binding_checks = 0
        self.producer_checkpoint_shard_opens = 0
        self.producer_checkpoint_hash_attempts = 0
        self.producer_checkpoint_identity_hash_reads = 0

    def _bind_graph_owned_checkpoint_fixture(
        self,
        observed: os.stat_result,
        leaf_identities: Mapping[str, tuple[int, int]],
    ) -> None:
        if (
            self._fixture_identity is not None
            or self._fixture_leaf_identities is not None
            or not stat.S_ISDIR(observed.st_mode)
            or observed.st_uid != os.getuid()
            or type(leaf_identities) is not dict
            or len(leaf_identities) not in {5, 6}
            or any(
                type(name) is not str
                or type(identity) is not tuple
                or len(identity) != 2
                or any(type(item) is not int for item in identity)
                for name, identity in leaf_identities.items()
            )
        ):
            raise ValueError("graph-owned synthetic checkpoint fixture identity")
        self._fixture_identity = (observed.st_dev, observed.st_ino)
        self._fixture_leaf_identities = tuple(
            sorted(
                (name, identity[0], identity[1])
                for name, identity in leaf_identities.items()
            )
        )

    def _require_graph_owned_checkpoint_binding(
        self,
        authority: _ValidatedIdentityAuthority,
        storage: _StorageBinding,
    ) -> int:
        """Open the exact graph-created checkpoint leaf without following it."""
        root = Path(str(authority.get("checkpoint_root")))
        try:
            lexical = _canonical_absolute_path(root)
            graph_root = _qualification_root(lexical.parent)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "graph-owned synthetic checkpoint root authority"
            ) from exc
        if (
            graph_root != storage.package_directory.parent
            or lexical == _LIVE_CHECKPOINT_ROOT
            or lexical.is_relative_to(_LIVE_CHECKPOINT_ROOT)
            or _LIVE_CHECKPOINT_ROOT.is_relative_to(lexical)
            or lexical == _LIVE_PACKAGE_PARENT
            or lexical.is_relative_to(_LIVE_PACKAGE_PARENT)
            or _LIVE_PACKAGE_PARENT.is_relative_to(lexical)
        ):
            raise ValueError("graph-owned synthetic checkpoint root authority")
        if self._fixture_identity is None:
            raise ValueError("graph-owned synthetic checkpoint fixture identity")
        parent_fd = _open_directory_chain(graph_root, create=False)
        checkpoint_fd = -1
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        if hasattr(os, "O_CLOEXEC"):
            flags |= os.O_CLOEXEC
        try:
            checkpoint_fd = os.open(lexical.name, flags, dir_fd=parent_fd)
            observed = os.fstat(checkpoint_fd)
            if (
                not stat.S_ISDIR(observed.st_mode)
                or observed.st_uid != os.getuid()
                or (observed.st_dev, observed.st_ino) != self._fixture_identity
            ):
                raise ValueError("graph-owned synthetic checkpoint fixture changed")
        except BaseException:
            if checkpoint_fd >= 0:
                os.close(checkpoint_fd)
                checkpoint_fd = -1
            raise
        finally:
            try:
                os.close(parent_fd)
            except BaseException:
                if checkpoint_fd >= 0:
                    os.close(checkpoint_fd)
                    checkpoint_fd = -1
                raise
        return checkpoint_fd

    def run(self, consumed_gate: object, authority: _ValidatedIdentityAuthority,
            storage: _StorageBinding) -> _IdentityOutcome:
        _require_consumed_gate(consumed_gate, authority)
        if authority.get("authority_scope") != "SYNTHETIC" or storage.scope != "SYNTHETIC":
            raise TypeError("synthetic checkpoint provider rejects production authority")
        # This is the immediate call boundary for the unchanged physical
        # identity producer.  The interception case proves the exact input and
        # deliberately does not invoke _run_identity_stage.
        if self._intercept:
            raise AssertionError("interception must traverse production call boundary")
        # Fixture construction completed before package start.  This call
        # traverses only the measured V12 producer and its ordinary seven-leaf
        # evidence closure; no alternate public provider is introduced.
        checkpoint_root_descriptor = self._require_graph_owned_checkpoint_binding(
            authority, storage
        )
        self.producer_checkpoint_binding_checks += 1
        self.physical_identity_producer_calls += 1
        try:
            binding_token = _bind_qualification_root_descriptor(
                _QUALIFICATION_ROOT_DESCRIPTOR_SEAL, checkpoint_root_descriptor
            )
        except BaseException:
            try:
                _close_synthetic_checkpoint_root_descriptor(
                    checkpoint_root_descriptor
                )
            except OSError:
                pass
            raise

        outcome: _IdentityOutcome | None = None
        execution_error: BaseException | None = None
        reset_error: BaseException | None = None
        close_error: BaseException | None = None
        expected_shards = {
            name: (device, inode)
            for name, device, inode in cast(
                tuple[tuple[str, int, int], ...], self._fixture_leaf_identities
            )
        }
        observed_shard_descriptors: set[int] = set()
        original_open = _identity_producer_module.os.open
        original_hash_descriptor = _identity_producer_module._hash_descriptor

        def observed_open(
            candidate: object,
            flags: int,
            mode: int = 0o777,
            *,
            dir_fd: int | None = None,
        ) -> int:
            descriptor = original_open(
                candidate, flags, mode, dir_fd=dir_fd
            )
            if type(candidate) is str and candidate in expected_shards:
                self.producer_checkpoint_shard_opens += 1
                observed_shard_descriptors.add(descriptor)
            return descriptor

        def observed_hash_descriptor(
            descriptor: int,
            expected_size: int,
            *,
            require_single_link: bool,
        ) -> tuple[str, os.stat_result]:
            tracked = descriptor in observed_shard_descriptors
            if tracked:
                self.producer_checkpoint_hash_attempts += 1
            try:
                result = original_hash_descriptor(
                    descriptor,
                    expected_size,
                    require_single_link=require_single_link,
                )
            except BaseException as hash_error:
                observation = getattr(hash_error, "operation_observation", None)
                if tracked and getattr(observation, "effect_count", None) == 1:
                    self.producer_checkpoint_identity_hash_reads += 1
                raise
            if tracked:
                self.producer_checkpoint_identity_hash_reads += 1
            return result

        _identity_producer_module.os.open = observed_open
        _identity_producer_module._hash_descriptor = observed_hash_descriptor
        try:
            try:
                outcome = _ProductionCheckpointEffect().run(
                    consumed_gate, authority, storage
                )
            except BaseException as exc:
                execution_error = exc
        finally:
            _identity_producer_module._hash_descriptor = original_hash_descriptor
            _identity_producer_module.os.open = original_open
        try:
            _reset_qualification_root_descriptor(
                _QUALIFICATION_ROOT_DESCRIPTOR_SEAL, binding_token
            )
        except BaseException as exc:
            reset_error = exc
        try:
            _close_synthetic_checkpoint_root_descriptor(
                checkpoint_root_descriptor
            )
        except BaseException as exc:
            close_error = exc

        if outcome is not None and (reset_error is not None or close_error is not None):
            _raise_identity_handoff_failure(
                storage,
                outcome.leases,
                reset_error if reset_error is not None else cast(BaseException, close_error),
            )
        if execution_error is not None:
            raise execution_error
        if reset_error is not None:
            raise reset_error
        if close_error is not None:
            raise close_error
        if outcome is None:
            raise AssertionError("physical identity producer returned no outcome")
        try:
            checkpoint_root_identity = outcome.report[
                "checkpoint_root_descriptor_identity"
            ]
            shard_descriptor_identities = outcome.report[
                "all_shard_descriptor_identities"
            ]
            shard_opens = outcome.report["checkpoint_shard_opens"]
            identity_hash_reads = outcome.report["checkpoint_identity_hash_reads"]
            if type(shard_opens) is not int or type(identity_hash_reads) is not int:
                raise TypeError("physical identity producer access counters")
            if (
                shard_opens != self.producer_checkpoint_shard_opens
                or identity_hash_reads
                != self.producer_checkpoint_identity_hash_reads
                or self.producer_checkpoint_hash_attempts != 6
            ):
                raise TypeError("physical identity producer counter divergence")
            observed_shards = tuple(
                sorted(
                    (
                        item["filename"],
                        item["device"],
                        item["inode"],
                    )
                    for item in shard_descriptor_identities
                )
            ) if type(shard_descriptor_identities) is list and all(
                type(item) is dict
                and set(item) == {"filename", "device", "inode"}
                and type(item["filename"]) is str
                and type(item["device"]) is int
                and type(item["inode"]) is int
                for item in shard_descriptor_identities
            ) else ()
            if (
                type(checkpoint_root_identity) is not dict
                or set(checkpoint_root_identity) != {"device", "inode"}
                or type(checkpoint_root_identity["device"]) is not int
                or type(checkpoint_root_identity["inode"]) is not int
                or (
                    checkpoint_root_identity["device"],
                    checkpoint_root_identity["inode"],
                )
                != self._fixture_identity
                or observed_shards != self._fixture_leaf_identities
            ):
                raise TypeError("physical identity producer provenance")
        except BaseException as exc:
            _raise_identity_handoff_failure(storage, outcome.leases, exc)
        return outcome

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
        checkpoint_root_descriptor = self._require_graph_owned_checkpoint_binding(
            authority, storage
        )
        try:
            self.preopen_intercepted = True
            raise RuntimeError("PREOPEN_INTERCEPTED")
        finally:
            _close_synthetic_checkpoint_root_descriptor(
                checkpoint_root_descriptor
            )


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
    synthetic_missing_required_ordinal: int | None = None
    synthetic_checkpoint_leaf: str = "synthetic-checkpoint"
    observed_effects: dict[str, int] = field(default_factory=lambda: {
        "checkpoint_root_resolutions": 0,
        "checkpoint_opens": 0,
        "numerical_executions": 0,
        "synthetic_identities_instantiated": 0,
        "synthetic_fixture_required_leaves": 0,
        "synthetic_fixture_benign_extra_leaves": 0,
        "synthetic_fixture_leaf_creation_opens": 0,
        "synthetic_fixture_benign_extra_creation_opens": 0,
        "synthetic_fixture_payload_bytes": 0,
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
            or (
                runtime.synthetic_missing_required_ordinal is not None
                and (
                    type(runtime.synthetic_missing_required_ordinal) is not int
                    or runtime.synthetic_missing_required_ordinal not in range(1, 7)
                )
            )
            or type(runtime.synthetic_checkpoint_leaf) is not str
            or not runtime.synthetic_checkpoint_leaf
            or runtime.synthetic_checkpoint_leaf in {".", ".."}
            or Path(runtime.synthetic_checkpoint_leaf).name
            != runtime.synthetic_checkpoint_leaf
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
        package = runtime.storage.package_directory
        if (
            package.parent != _qualification_root(package.parent)
            or package == _LIVE_PACKAGE_PARENT
            or package.is_relative_to(_LIVE_PACKAGE_PARENT)
            or _LIVE_PACKAGE_PARENT.is_relative_to(package)
            or package == _LIVE_CHECKPOINT_ROOT
            or package.is_relative_to(_LIVE_CHECKPOINT_ROOT)
            or _LIVE_CHECKPOINT_ROOT.is_relative_to(package)
        ):
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
    expected_package_start_raw: bytes | None = None

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

    def mark_package_started(
        self, digest: str, *, expected_raw: bytes | None = None
    ) -> None:
        """Project the durable marker into memory without making it authority."""
        if _HEX64.fullmatch(digest) is None:
            raise ValueError("package-start digest")
        existing = [value for kind, value in self.receipts if kind == "PACKAGE_START"]
        if existing and existing != [digest]:
            raise ValueError("package-start receipt conflict")
        if not existing:
            self.record("PACKAGE_START", digest)
        if expected_raw is not None:
            if type(expected_raw) is not bytes or _sha(expected_raw) != digest:
                raise ValueError("package-start bytes")
            if (
                self.expected_package_start_raw is not None
                and self.expected_package_start_raw != expected_raw
            ):
                raise ValueError("package-start bytes conflict")
            self.expected_package_start_raw = expected_raw
        self.package_started = True

    def fail(
        self,
        exc: BaseException,
        runtime: _Runtime,
        emergency_release_sha256: str | None,
        emergency_release_outcome: Mapping[str, object] | None = None,
        access_progress: Mapping[str, object] | None = None,
    ) -> None:
        if not self.package_started or self.terminal_banked:
            return
        if emergency_release_sha256 is not None:
            self.record("EMERGENCY_RELEASE_REPORT", emergency_release_sha256)
        expected_raw = self.expected_package_start_raw
        if expected_raw is None:
            raise RuntimeError("durable package-start bytes unavailable")
        if access_progress is None:
            access_progress = _derive_access_progress_for_failure(
                self.storage, runtime, exc
            )
        try:
            _bank_failure_terminal_from_durable_progress(
                storage=self.storage,
                expected_package_start_raw=expected_raw,
                exc=exc,
                access_progress=access_progress,
                terminal_origin=_IN_PROCESS_TERMINAL_ORIGIN,
                emergency_release_sha256=emergency_release_sha256,
                emergency_release_outcome=emergency_release_outcome,
                runtime=runtime,
            )
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
                           fault_stage: str | None = None,
                           missing_required_ordinal: int | None = None,
                           checkpoint_leaf: str = "synthetic-checkpoint") -> _Runtime:
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
        synthetic_missing_required_ordinal=missing_required_ordinal,
        synthetic_checkpoint_leaf=checkpoint_leaf,
    )


def _validate_go_non_temporal(
    raw: bytes, profile: _AuthorityProfile
) -> _ValidatedCollapsedGo:
    """Validate every collapsed-GO binding except its wall-clock window."""
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
    return _ValidatedCollapsedGo(_GO_SEAL, value)


def _validate_go_bytes(raw: bytes, profile: _AuthorityProfile,
                       *, now_unix_ns: int | None = None) -> _ValidatedCollapsedGo:
    validated = _validate_go_non_temporal(raw, profile)
    now = time.time_ns() if now_unix_ns is None else now_unix_ns
    if (
        type(now) is not int
        or now < validated.get("issued_at_unix_ns")
        or now >= validated.get("expires_at_unix_ns")
    ):
        raise ValueError("collapsed GO validity")
    return validated


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
    """Build retained identity authority only from the already-pinned profile."""
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
    producer_path = runtime.profile.release_authority.get(
        "checkpoint_identity_producer_path"
    )
    producer_sha256 = runtime.profile.release_authority.get(
        "checkpoint_identity_producer_sha256"
    )
    validator_path = runtime.profile.release_authority.get(
        "checkpoint_identity_validator_path"
    )
    validator_sha256 = runtime.profile.release_authority.get(
        "checkpoint_identity_validator_sha256"
    )
    if (
        producer_path != _IDENTITY_PRODUCER
        or validator_path != _IDENTITY_VALIDATOR
        or type(producer_sha256) is not str
        or _HEX64.fullmatch(producer_sha256) is None
        or type(validator_sha256) is not str
        or _HEX64.fullmatch(validator_sha256) is None
    ):
        raise ValueError("pinned checkpoint implementation authority")
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
        "measured_producer_path": producer_path,
        "measured_producer_sha256": producer_sha256,
        "measured_validator_path": validator_path,
        "measured_validator_sha256": validator_sha256,
        "expected_shard_count": len(shards),
        "expected_identity_only_shard_count": identity_only,
        "expected_graph_payload_shard_count": graph_payload,
        "expected_total_bytes": sum(int(item["size_bytes"]) for item in shards),
        "attempts": 1,
        "retries": 0,
        "resume": False,
    }


def _materialize_graph_owned_checkpoint_fixture(
    checkpoint_root: Path, runtime: _Runtime
) -> None:
    """Create the complete synthetic input fixture before package start."""
    if runtime.scope != "SYNTHETIC" or runtime.profile.authority_scope != "SYNTHETIC":
        raise TypeError("synthetic checkpoint fixture authority")
    shards = [dict(item) for item in runtime.profile.shards]
    if (
        len(shards) != 6
        or any(
            type(item.get("ordinal")) is not int
            or item["ordinal"] not in range(1, 7)
            or type(item.get("filename")) is not str
            or not str(item["filename"])
            or str(item["filename"]) in {".", ".."}
            or Path(str(item["filename"])).name != str(item["filename"])
            or item.get("size_bytes") != 0
            or item.get("sha256") != _EMPTY_SHA256
            for item in shards
        )
    ):
        raise ValueError("bounded empty synthetic checkpoint contract")
    shards.sort(key=lambda item: int(item["ordinal"]))
    if [item["ordinal"] for item in shards] != list(range(1, 7)):
        raise ValueError("synthetic checkpoint ordinal authority")
    required_names = tuple(str(item["filename"]) for item in shards)
    if (
        len(set(required_names)) != len(required_names)
        or set(required_names) & set(_SYNTHETIC_CHECKPOINT_BENIGN_EXTRA_LEAVES)
    ):
        raise ValueError("synthetic checkpoint leaf authority")
    missing = runtime.synthetic_missing_required_ordinal
    if missing is not None and (type(missing) is not int or missing not in range(1, 7)):
        raise TypeError("synthetic missing-required ordinal")

    directory_flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    create_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        directory_flags |= os.O_CLOEXEC
        create_flags |= os.O_CLOEXEC
    parent_fd = _open_directory_chain(checkpoint_root.parent, create=False)
    checkpoint_fd = -1
    created_required = 0
    created_extra = 0
    created_required_identities: dict[str, tuple[int, int]] = {}
    try:
        os.mkdir(checkpoint_root.name, mode=0o700, dir_fd=parent_fd)
        checkpoint_fd = os.open(
            checkpoint_root.name, directory_flags, dir_fd=parent_fd
        )
        observed = os.fstat(checkpoint_fd)
        if (
            not stat.S_ISDIR(observed.st_mode)
            or observed.st_uid != os.getuid()
            or os.listdir(checkpoint_fd)
        ):
            raise ValueError("fresh graph-owned synthetic checkpoint root")
        for shard in shards:
            if shard["ordinal"] == missing:
                continue
            descriptor = os.open(
                str(shard["filename"]),
                create_flags,
                0o600,
                dir_fd=checkpoint_fd,
            )
            try:
                created = os.fstat(descriptor)
                if (
                    not stat.S_ISREG(created.st_mode)
                    or created.st_nlink != 1
                    or created.st_uid != os.getuid()
                    or created.st_size != 0
                ):
                    raise ValueError("graph-owned synthetic checkpoint leaf")
                created_required_identities[str(shard["filename"])] = (
                    created.st_dev,
                    created.st_ino,
                )
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            created_required += 1
        for leaf in _SYNTHETIC_CHECKPOINT_BENIGN_EXTRA_LEAVES:
            descriptor = os.open(leaf, create_flags, 0o600, dir_fd=checkpoint_fd)
            try:
                created = os.fstat(descriptor)
                if (
                    not stat.S_ISREG(created.st_mode)
                    or created.st_nlink != 1
                    or created.st_uid != os.getuid()
                    or created.st_size != 0
                ):
                    raise ValueError("graph-owned benign extra leaf")
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
            created_extra += 1
        expected = {
            str(item["filename"])
            for item in shards
            if item["ordinal"] != missing
        } | set(_SYNTHETIC_CHECKPOINT_BENIGN_EXTRA_LEAVES)
        if set(os.listdir(checkpoint_fd)) != expected:
            raise ValueError("graph-owned synthetic checkpoint fixture census")
        checkpoint_provider = runtime.checkpoint_effect
        if type(checkpoint_provider) is _ProductionCheckpointEffect:
            checkpoint_provider = checkpoint_provider._qualification_interceptor
        if type(checkpoint_provider) is not _SyntheticCheckpointProvider:
            raise TypeError("sealed synthetic checkpoint provider")
        checkpoint_provider._bind_graph_owned_checkpoint_fixture(
            observed, created_required_identities
        )
        os.fsync(checkpoint_fd)
        os.fsync(parent_fd)
    finally:
        if checkpoint_fd >= 0:
            os.close(checkpoint_fd)
        os.close(parent_fd)

    runtime.observed_effects["synthetic_fixture_required_leaves"] = created_required
    runtime.observed_effects["synthetic_fixture_benign_extra_leaves"] = created_extra
    runtime.observed_effects["synthetic_fixture_leaf_creation_opens"] = (
        created_required + created_extra
    )
    runtime.observed_effects["synthetic_fixture_benign_extra_creation_opens"] = (
        created_extra
    )
    runtime.observed_effects["synthetic_fixture_payload_bytes"] = sum(
        int(item["size_bytes"])
        for item in shards
        if item["ordinal"] != missing
    )


def _build_installed_authority(
    go: _ValidatedCollapsedGo, runtime: _Runtime
) -> _ValidatedIdentityAuthority:
    checkpoint_root = (
        runtime.storage.package_directory.parent / runtime.synthetic_checkpoint_leaf
        if runtime.scope == "SYNTHETIC" else _LIVE_CHECKPOINT_ROOT
    )
    if runtime.scope == "SYNTHETIC":
        _materialize_graph_owned_checkpoint_fixture(checkpoint_root, runtime)
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


def _derive_expected_package_start_receipt(
    go: _ValidatedCollapsedGo, runtime: _Runtime
) -> dict[str, object]:
    """Purely rederive the write-once start marker for restart closeout."""
    checkpoint_root = (
        runtime.storage.package_directory.parent / runtime.synthetic_checkpoint_leaf
        if runtime.scope == "SYNTHETIC"
        else _LIVE_CHECKPOINT_ROOT
    )
    installed_value = _identity_installed_document(go, runtime, checkpoint_root)
    installed_sha256 = _sha(_canonical_bytes(installed_value))
    ids = _identities(go)
    gate = _build_package_start_gate(
        authorization_id=ids["authorization_id"],
        package_attempt_id=ids["package_attempt_id"],
        primary_event_id=ids["primary_event_id"],
        secondary_event_id=ids["secondary_event_id"],
        collapsed_go_sha256=go.sha256,
        installed_authority_sha256=installed_sha256,
        checkpoint_authority_sha256=runtime.profile.checkpoint_authority_sha256,
        numerical_acceptance_contract_sha256=(
            runtime.profile.numerical_acceptance_contract_sha256
        ),
        comparison_rules_sha256=runtime.profile.comparison_rules_sha256,
        result_authority_sha256=runtime.profile.result_authority_sha256,
        preflight_passed=True,
    )
    validated = _validate_package_start_gate(gate)
    receipt = _package_start_receipt(validated)
    if _contract_sha256(receipt) != _sha(_canonical_bytes(receipt)):
        raise ValueError("pure package-start receipt derivation")
    return receipt


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
            directory,
            dict(report),
            authority=authority,
        ),
    )
    if (
        validated_evidence.get("result") != "PASS"
        or validated_evidence.get("leaf_count")
        != len(_SUCCESS_PHYSICAL_IDENTITY_FILES)
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
    result = storage.anchored_path_call(
        "identity",
        lambda directory: _validate_banked_identity_evidence(
            directory,
            dict(identity.report),
            authority=identity.authority,
        ),
    )
    if (
        result.get("result") != "PASS"
        or result.get("leaf_count") != len(_SUCCESS_PHYSICAL_IDENTITY_FILES)
        or result.get("terminal_sha256") != identity.identity_terminal_sha256
        or result.get("deterministic_core_sha256")
        != evidence.get("deterministic_core_sha256")
    ):
        raise ValueError("physical identity evidence closure")
    return dict(result)


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


def _bank_stage_receipt(
    storage: _StorageBinding,
    stage: str,
    subject: Mapping[str, object],
    package_start_sha256: str,
) -> str:
    if stage not in {"PRIMARY", "SECONDARY", "RELEASE"}:
        raise ValueError("durable stage receipt vocabulary")
    if _HEX64.fullmatch(package_start_sha256) is None:
        raise ValueError("durable package-start binding")
    event_key = {
        "PRIMARY": "primary_event_id",
        "SECONDARY": "secondary_event_id",
        "RELEASE": "package_attempt_id",
    }[stage]
    stage_authority = {
        "stage": stage,
        "authorization_id": subject.get("authorization_id"),
        "package_attempt_id": subject.get("package_attempt_id"),
        "stage_event_id": subject.get(event_key),
        "package_start_sha256": package_start_sha256,
    }
    value = {
        "schema": _STAGE_RECEIPT_SCHEMA,
        **stage_authority,
        "stage_authority_sha256": _contract_sha256(stage_authority),
        "result": "PASS",
    }
    return storage.bank(f"{stage.lower()}-start-receipt.json", value)


def _read_optional_canonical_leaf(
    storage: _StorageBinding, leaf: str
) -> tuple[dict[str, object], str] | None:
    try:
        raw = storage._read_held_leaf(
            leaf,
            maximum_bytes=1_048_576,
            required_mode=0o600,
            require_immutable=True,
        )
    except FileNotFoundError:
        return None
    value = _parse_artifact_bytes(raw)
    if type(value) is not dict or _canonical_bytes(value) != raw:
        raise ValueError(f"durable receipt canonical bytes: {leaf}")
    return value, _sha(raw)


def _derive_durable_stage_progress(
    storage: _StorageBinding,
    expected_package_start_raw: bytes,
    *,
    access_progress: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Derive consumer deltas and the furthest stage from durable receipts."""
    if type(expected_package_start_raw) is not bytes:
        raise TypeError("expected durable package-start bytes")
    if storage.observe_package_start(expected_package_start_raw) != "VALID_DURABLE_START":
        raise ValueError("durable package-start authority")
    start_value = _parse_artifact_bytes(expected_package_start_raw)
    if type(start_value) is not dict:
        raise ValueError("durable package-start document")
    start_sha256 = _sha(expected_package_start_raw)
    durable: list[dict[str, str]] = [
        {"kind": "PACKAGE_START", "sha256": start_sha256}
    ]
    invalid: list[str] = []
    valid_stage: dict[str, str] = {}
    expected_keys = {
        "schema",
        "stage",
        "authorization_id",
        "package_attempt_id",
        "stage_event_id",
        "package_start_sha256",
        "stage_authority_sha256",
        "result",
    }
    stage_event_keys = {
        "PRIMARY": "primary_event_id",
        "SECONDARY": "secondary_event_id",
        "RELEASE": "package_attempt_id",
    }
    for stage in ("PRIMARY", "SECONDARY", "RELEASE"):
        leaf = f"{stage.lower()}-start-receipt.json"
        try:
            observed = _read_optional_canonical_leaf(storage, leaf)
        except BaseException:
            invalid.append(leaf)
            continue
        if observed is None:
            continue
        value, digest = observed
        event_key = stage_event_keys[stage]
        if (
            set(value) != expected_keys
            or value.get("schema") != _STAGE_RECEIPT_SCHEMA
            or value.get("stage") != stage
            or value.get("authorization_id") != start_value.get("authorization_id")
            or value.get("package_attempt_id") != start_value.get("package_attempt_id")
            or value.get("stage_event_id") != start_value.get(event_key)
            or value.get("package_start_sha256") != start_sha256
            or value.get("stage_authority_sha256")
            != _contract_sha256({
                "stage": stage,
                "authorization_id": start_value.get("authorization_id"),
                "package_attempt_id": start_value.get("package_attempt_id"),
                "stage_event_id": start_value.get(event_key),
                "package_start_sha256": start_sha256,
            })
            or value.get("result") != "PASS"
        ):
            invalid.append(leaf)
            continue
        # Frozen causal order: later durable starts cannot confer authority
        # when their required predecessor start is absent or invalid.
        if stage == "SECONDARY" and "PRIMARY" not in valid_stage:
            invalid.append(leaf)
            continue
        if stage == "RELEASE" and "SECONDARY" not in valid_stage:
            invalid.append(leaf)
            continue
        valid_stage[stage] = digest
        durable.append({"kind": f"{stage}_START", "sha256": digest})

    failed_stage = "PACKAGE_START"
    if access_progress is not None:
        if type(access_progress) is not dict:
            access_progress = dict(access_progress)
        if access_progress.get("receipt_count", 0) or access_progress.get(
            "checkpoint_shard_opens_lower_bound", 0
        ):
            failed_stage = "IDENTITY_TERMINAL"
    else:
        identity_receipt = None
        try:
            identity_receipt = storage.anchored_existing_path_call(
                "identity",
                lambda directory: _read_banked_document(
                    directory, "identity-receipt.json"
                ),
            )
        except BaseException:
            pass
        if identity_receipt is not None:
            failed_stage = "IDENTITY_TERMINAL"
    if "PRIMARY" in valid_stage:
        failed_stage = "PRIMARY_RESULT_TERMINAL"
    if "SECONDARY" in valid_stage:
        failed_stage = "SECONDARY_RESULT_TERMINAL"
    try:
        comparison_receipt = _read_optional_canonical_leaf(
            storage, "comparison-receipt.json"
        )
        comparison_terminal = _read_optional_canonical_leaf(
            storage, "comparison-terminal.json"
        )
        if (
            "SECONDARY" in valid_stage
            and comparison_receipt is not None
            and comparison_terminal is not None
            and comparison_terminal[0].get("comparison_receipt_sha256")
            == comparison_receipt[1]
            and comparison_terminal[0].get("state") == "COMPLETE"
        ):
            failed_stage = "COMPARISON_TERMINAL"
            durable.extend(
                (
                    {"kind": "COMPARISON_RECEIPT", "sha256": comparison_receipt[1]},
                    {"kind": "COMPARISON_TERMINAL", "sha256": comparison_terminal[1]},
                )
            )
    except BaseException:
        invalid.append("comparison-receipt-or-terminal.json")
    if "RELEASE" in valid_stage:
        failed_stage = "RELEASE_TERMINAL"

    return {
        "package_attempt_id": start_value.get("package_attempt_id"),
        "failed_stage": failed_stage,
        "package_delta": 1,
        "primary_delta": int("PRIMARY" in valid_stage),
        "secondary_delta": int("SECONDARY" in valid_stage),
        "durable_receipts": durable,
        "invalid_durable_receipts": sorted(set(invalid)),
        "access_progress": dict(access_progress) if access_progress is not None else None,
    }


def _empty_access_progress() -> dict[str, object]:
    return {
        "schema": "pulsarmlx.f017.checkpoint-identity-access-census/12.1.0",
        "genesis_sha256": _EMPTY_SHA256,
        "head_sha256": _EMPTY_SHA256,
        "receipt_count": 0,
        "checkpoint_shard_opens_lower_bound": 0,
        "checkpoint_shard_opens_upper_bound": 0,
        "checkpoint_shard_opens_unconfirmed": 0,
        "checkpoint_identity_hash_reads_lower_bound": 0,
        "checkpoint_identity_hash_reads_upper_bound": 0,
        "checkpoint_identity_hash_reads_unconfirmed": 0,
        "identity_hash_bytes_lower_bound": 0,
        "identity_hash_bytes_upper_bound": 0,
        "identity_hash_bytes_unconfirmed": 0,
        "exact": True,
        "unresolved_operation": None,
        "unresolved_ordinal": 0,
        "prefix_complete": False,
        "receipt_validation": "PASS",
        "result": "PASS",
    }


def _derive_access_progress_for_failure(
    storage: _StorageBinding,
    runtime: _Runtime | None,
    exc: BaseException | None,
) -> dict[str, object]:
    """Read receipt-derived access truth; never fall back to mutable counters."""
    if runtime is None:
        raise TypeError("runtime authority required for access-prefix validation")
    exception_census: dict[str, object] | None = None
    if isinstance(exc, _IdentityAuthorityError) and exc.access_census is not None:
        exception_census = dict(exc.access_census.evidence)
    try:
        start_raw = storage._read_held_leaf(
            "package-start.json", maximum_bytes=65_536
        )
        start = _parse_artifact_bytes(start_raw)
    except FileNotFoundError:
        return _empty_access_progress()
    if type(start) is not dict:
        raise ValueError("package-start access binding")
    contract = _parse_artifact_bytes(
        (_ROOT / runtime.profile.checkpoint_contract_path).read_bytes()
    )
    if type(contract) is not dict:
        raise ValueError("checkpoint access contract")
    authority_binding = {
        "authorization_id": start.get("authorization_id"),
        "package_attempt_id": start.get("package_attempt_id"),
        "checkpoint_identity_contract_sha256": (
            runtime.profile.checkpoint_authority_sha256
        ),
        "checkpoint_set_sha256": runtime.profile.checkpoint_set_sha256,
    }
    try:
        census = storage.anchored_existing_path_call(
            "identity",
            lambda directory: _validate_banked_identity_access_prefix(
                directory,
                authority_binding,
                contract,
                require_complete=False,
            ),
        )
        evidence = dict(census)
        evidence["receipt_validation"] = "PASS"
        # The durable receipt prefix is authoritative.  An exception-carried
        # census is accepted as corroboration only when it is exactly equal;
        # it can never increase a durable lower or upper bound.
        if exception_census is not None and exception_census != census:
            exception_census = None
        return evidence
    except FileNotFoundError as validation_error:
        # Missing durable receipts cannot be replaced by exception-carried
        # process memory.  Preserve only the conservative receipt-authority
        # bounds for an absent prefix.
        evidence = _missing_identity_access_prefix_census(
            authority_binding,
            contract,
        )
        evidence["result"] = "FAIL"
        evidence["receipt_validation"] = "FAIL"
        evidence["validation_failure_type"] = type(validation_error).__name__
        return evidence
    except _IdentityAccessPrefixValidationError as validation_error:
        evidence = dict(validation_error.access_census)
        if exception_census is not None and exception_census != evidence:
            exception_census = None
        evidence["receipt_validation"] = "FAIL"
        evidence["validation_failure_type"] = type(validation_error).__name__
        return evidence
    except BaseException as validation_error:
        # An unreadable durable prefix likewise cannot confer authority on a
        # mutable in-memory census, even if the producer attached one to the
        # exception.  Report conservative receipt-derived bounds only.
        evidence = _missing_identity_access_prefix_census(
            authority_binding,
            contract,
        )
        evidence["unresolved_operation"] = "RECEIPT_VALIDATION"
        evidence["unresolved_ordinal"] = 0
        evidence["result"] = "FAIL"
        evidence["receipt_validation"] = "FAIL"
        evidence["validation_failure_type"] = type(validation_error).__name__
        return evidence


def _failure_accounting_value(
    *,
    progress: Mapping[str, object],
    access_progress: Mapping[str, object],
    terminal_origin: str,
    emergency_release_sha256: str | None,
    emergency_release_outcome: Mapping[str, object] | None,
    runtime: _Runtime | None,
) -> dict[str, object]:
    if terminal_origin not in {_IN_PROCESS_TERMINAL_ORIGIN, _RESTART_CLOSEOUT_ORIGIN}:
        raise ValueError("failure terminal origin")
    opens_lower = access_progress.get("checkpoint_shard_opens_lower_bound", 0)
    opens_upper = access_progress.get("checkpoint_shard_opens_upper_bound", 0)
    hashes_lower = access_progress.get(
        "checkpoint_identity_hash_reads_lower_bound", 0
    )
    hashes_upper = access_progress.get(
        "checkpoint_identity_hash_reads_upper_bound", 0
    )
    for item in (opens_lower, opens_upper, hashes_lower, hashes_upper):
        if type(item) is not int or item < 0:
            raise ValueError("receipt-derived checkpoint access bounds")
    return {
        "schema": _FAILURE_ACCOUNTING_SCHEMA,
        "terminal_origin": terminal_origin,
        "failed_stage": progress["failed_stage"],
        "authorization_delta": 0,
        "package_delta": 1,
        "primary_delta": progress["primary_delta"],
        "secondary_delta": progress["secondary_delta"],
        "historical_master_ledger_before": _HISTORICAL_MASTER_LEDGER,
        "historical_master_ledger_after": _HISTORICAL_MASTER_LEDGER,
        "durable_receipts": list(progress["durable_receipts"]),
        "invalid_durable_receipts": list(progress["invalid_durable_receipts"]),
        "emergency_release_report_sha256": emergency_release_sha256,
        "emergency_release_outcome": (
            dict(emergency_release_outcome)
            if emergency_release_outcome is not None
            else None
        ),
        "checkpoint_access_census": dict(access_progress),
        "original_checkpoint_opens_lower_bound": opens_lower,
        "original_checkpoint_opens_upper_bound": opens_upper,
        "original_checkpoint_identity_hash_reads_lower_bound": hashes_lower,
        "original_checkpoint_identity_hash_reads_upper_bound": hashes_upper,
        "real_numerical_executions_observed_in_process": (
            runtime.observed_effects["numerical_executions"]
            if runtime is not None and terminal_origin == _IN_PROCESS_TERMINAL_ORIGIN
            else None
        ),
        "fabricated_successor_receipts": 0,
        "result": "FAIL",
    }


def _validate_failure_access_census(value: object) -> dict[str, object]:
    if type(value) is not dict:
        raise TypeError("failure checkpoint access census")
    fields = set(value)
    allowed = {
        _ACCESS_CENSUS_FIELDS,
        _ACCESS_CENSUS_FIELDS | {"validation_failure_type"},
    }
    if fields not in allowed:
        raise ValueError("failure checkpoint access census fields")
    if (
        value.get("schema")
        != "pulsarmlx.f017.checkpoint-identity-access-census/12.1.0"
        or value.get("result") not in {"PASS", "FAIL"}
        or value.get("receipt_validation") not in {"PASS", "FAIL"}
        or type(value.get("exact")) is not bool
        or type(value.get("prefix_complete")) is not bool
    ):
        raise ValueError("failure checkpoint access census semantics")
    for key in ("genesis_sha256", "head_sha256"):
        digest = value.get(key)
        if type(digest) is not str or _HEX64.fullmatch(digest) is None:
            raise ValueError(f"failure checkpoint access census {key}")
    integer_fields = (
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
        "unresolved_ordinal",
    )
    if any(
        type(value.get(key)) is not int or int(value[key]) < 0
        for key in integer_fields
    ):
        raise ValueError("failure checkpoint access census integers")
    opens_lower = int(value["checkpoint_shard_opens_lower_bound"])
    opens_upper = int(value["checkpoint_shard_opens_upper_bound"])
    hashes_lower = int(value["checkpoint_identity_hash_reads_lower_bound"])
    hashes_upper = int(value["checkpoint_identity_hash_reads_upper_bound"])
    bytes_lower = int(value["identity_hash_bytes_lower_bound"])
    bytes_upper = int(value["identity_hash_bytes_upper_bound"])
    if (
        opens_upper != opens_lower + value["checkpoint_shard_opens_unconfirmed"]
        or hashes_upper
        != hashes_lower + value["checkpoint_identity_hash_reads_unconfirmed"]
        or bytes_upper != bytes_lower + value["identity_hash_bytes_unconfirmed"]
        or opens_upper > 6
        or hashes_upper > 6
        or value["receipt_count"] > 24
        or value["exact"]
        is not (
            value["checkpoint_shard_opens_unconfirmed"] == 0
            and value["checkpoint_identity_hash_reads_unconfirmed"] == 0
            and value["identity_hash_bytes_unconfirmed"] == 0
        )
    ):
        raise ValueError("failure checkpoint access census bounds")
    unresolved = value.get("unresolved_operation")
    unresolved_ordinal = value["unresolved_ordinal"]
    if unresolved is None:
        if unresolved_ordinal != 0:
            raise ValueError("failure checkpoint access unresolved ordinal")
    elif (
        unresolved not in {"SHARD_OPEN", "IDENTITY_HASH_READ", "RECEIPT_VALIDATION"}
        or unresolved_ordinal not in range(0, 7)
        or value["exact"] is not False
    ):
        raise ValueError("failure checkpoint access unresolved operation")
    return dict(value)


def _validate_existing_failure_terminal(
    storage: _StorageBinding,
    terminal: dict[str, object],
    expected_start_raw: bytes,
    *,
    runtime: _Runtime | None,
) -> None:
    if set(terminal) != _FAILURE_TERMINAL_FIELDS:
        raise ValueError("failure terminal field census")
    accounting = terminal.get("failure_accounting")
    if type(accounting) is not dict or set(accounting) != _FAILURE_ACCOUNTING_FIELDS:
        raise ValueError("failure accounting field census")
    origin = terminal.get("terminal_origin")
    failed_stage = terminal.get("failed_stage")
    if (
        terminal.get("schema") != _FAILURE_TERMINAL_SCHEMA
        or terminal.get("state") != "TERMINAL_FAILURE"
        or origin not in {_IN_PROCESS_TERMINAL_ORIGIN, _RESTART_CLOSEOUT_ORIGIN}
        or failed_stage not in _STAGES
        or terminal.get("result") != "FAIL"
        or terminal.get("fabricated_successor_receipts") != 0
        or type(terminal.get("fabricated_successor_receipts")) is not int
        or accounting.get("schema") != _FAILURE_ACCOUNTING_SCHEMA
        or accounting.get("terminal_origin") != origin
        or accounting.get("failed_stage") != failed_stage
        or accounting.get("authorization_delta") != 0
        or type(accounting.get("authorization_delta")) is not int
        or accounting.get("package_delta") != 1
        or type(accounting.get("package_delta")) is not int
        or accounting.get("historical_master_ledger_before")
        != _HISTORICAL_MASTER_LEDGER
        or type(accounting.get("historical_master_ledger_before")) is not int
        or accounting.get("historical_master_ledger_after")
        != _HISTORICAL_MASTER_LEDGER
        or type(accounting.get("historical_master_ledger_after")) is not int
        or accounting.get("fabricated_successor_receipts") != 0
        or type(accounting.get("fabricated_successor_receipts")) is not int
        or accounting.get("result") != "FAIL"
    ):
        raise ValueError("failure terminal semantics")
    for key in ("primary_delta", "secondary_delta"):
        if type(accounting.get(key)) is not int or accounting[key] not in {0, 1}:
            raise ValueError("failure accounting consumer delta")
    if accounting["secondary_delta"] > accounting["primary_delta"]:
        raise ValueError("failure accounting causal delta")
    access = _validate_failure_access_census(accounting.get("checkpoint_access_census"))
    if runtime is None:
        raise TypeError("failure terminal runtime authority")
    derived_access = _validate_failure_access_census(
        _derive_access_progress_for_failure(storage, runtime, None)
    )
    if access != derived_access:
        raise ValueError("failure checkpoint access durable-prefix projection")
    for lower_key, upper_key, accounting_lower, accounting_upper in (
        (
            "checkpoint_shard_opens_lower_bound",
            "checkpoint_shard_opens_upper_bound",
            "original_checkpoint_opens_lower_bound",
            "original_checkpoint_opens_upper_bound",
        ),
        (
            "checkpoint_identity_hash_reads_lower_bound",
            "checkpoint_identity_hash_reads_upper_bound",
            "original_checkpoint_identity_hash_reads_lower_bound",
            "original_checkpoint_identity_hash_reads_upper_bound",
        ),
    ):
        if (
            accounting.get(accounting_lower) != access[lower_key]
            or type(accounting.get(accounting_lower)) is not int
            or accounting.get(accounting_upper) != access[upper_key]
            or type(accounting.get(accounting_upper)) is not int
        ):
            raise ValueError("failure accounting access projection")
    progress = _derive_durable_stage_progress(
        storage, expected_start_raw, access_progress=access
    )
    for key in (
        "failed_stage",
        "primary_delta",
        "secondary_delta",
        "durable_receipts",
        "invalid_durable_receipts",
    ):
        if accounting.get(key) != progress[key]:
            raise ValueError("failure accounting durable-stage projection")
    start = _parse_artifact_bytes(expected_start_raw)
    if (
        type(start) is not dict
        or terminal.get("package_attempt_id") != start.get("package_attempt_id")
        or type(terminal.get("failure_type")) is not str
        or not terminal["failure_type"]
        or (
            terminal.get("failure_wrapper_type") is not None
            and (
                type(terminal.get("failure_wrapper_type")) is not str
                or not terminal["failure_wrapper_type"]
            )
        )
    ):
        raise ValueError("failure terminal start binding")
    if origin == _RESTART_CLOSEOUT_ORIGIN:
        if (
            terminal.get("failure_type")
            != "PROCESS_INTERRUPTION_AFTER_PACKAGE_START"
            or terminal.get("failure_wrapper_type") is not None
            or accounting.get("real_numerical_executions_observed_in_process")
            is not None
        ):
            raise ValueError("restart failure terminal semantics")
    elif (
        type(accounting.get("real_numerical_executions_observed_in_process"))
        is not int
        or accounting["real_numerical_executions_observed_in_process"] < 0
    ):
        raise ValueError("in-process failure execution census")
    accounting_raw = _canonical_bytes(accounting)
    if terminal.get("failure_accounting_sha256") != _sha(accounting_raw):
        raise ValueError("failure terminal accounting digest")
    accounting_leaf_sha = terminal.get("failure_accounting_leaf_sha256")
    if accounting_leaf_sha is not None:
        observed = _read_optional_canonical_leaf(storage, "failure-accounting.json")
        if observed is None or observed[1] != accounting_leaf_sha or observed[0] != accounting:
            raise ValueError("failure accounting leaf binding")
    emergency_sha = terminal.get("emergency_release_report_sha256")
    if accounting.get("emergency_release_report_sha256") != emergency_sha:
        raise ValueError("failure emergency-release digest continuity")
    emergency = accounting.get("emergency_release_outcome")
    if emergency is not None and type(emergency) is not dict:
        raise TypeError("failure emergency-release outcome")
    if terminal.get("emergency_release_result") != (
        emergency.get("result") if type(emergency) is dict else None
    ) or terminal.get("emergency_release_disposition") != (
        emergency.get("release_disposition") if type(emergency) is dict else None
    ):
        raise ValueError("failure emergency-release terminal projection")
    if emergency_sha is not None:
        if type(emergency_sha) is not str or _HEX64.fullmatch(emergency_sha) is None:
            raise ValueError("failure emergency-release SHA-256")
        observed = _read_optional_canonical_leaf(storage, "emergency-release-report.json")
        expected_emergency = (
            _emergency_release_value(
                str(observed[0].get("failed_stage")),
                emergency,
            )
            if observed is not None
            and observed[0].get("failed_stage") in _STAGES
            and type(emergency) is dict
            else None
        )
        if (
            observed is None
            or observed[1] != emergency_sha
            or observed[0] != expected_emergency
        ):
            raise ValueError("failure emergency-release leaf binding")


def _validate_existing_success_terminal(
    storage: _StorageBinding,
    terminal: dict[str, object],
    expected_start_raw: bytes,
) -> None:
    accounting_observed = _read_optional_canonical_leaf(
        storage, "receipt-derived-accounting.json"
    )
    if accounting_observed is None:
        raise ValueError("success accounting leaf")
    accounting, accounting_sha = accounting_observed
    _validate_success_accounting_document(accounting)
    _validate_success_package_terminal_document(terminal, accounting)
    if terminal.get("accounting_closure_sha256") != accounting_sha:
        raise ValueError("success terminal accounting leaf digest")
    start = _parse_artifact_bytes(expected_start_raw)
    if type(start) is not dict:
        raise ValueError("success terminal start document")
    for key in (
        "authorization_id",
        "package_attempt_id",
        "primary_event_id",
        "secondary_event_id",
    ):
        if terminal.get(key) != start.get(key):
            raise ValueError("success terminal start continuity")
    bindings = accounting.get("receipt_bindings")
    if type(bindings) is not dict:
        raise TypeError("success terminal receipt bindings")

    def root_digest(leaf: str) -> str:
        observed = _read_optional_canonical_leaf(storage, leaf)
        if observed is None:
            raise ValueError(f"success terminal missing leaf: {leaf}")
        return observed[1]

    def child_digest(child: str, leaf: str) -> str:
        return storage.anchored_existing_path_call(
            child, lambda directory: _read_banked_document(directory, leaf)[1]
        )

    observed_bindings = {
        "package_start_receipt_sha256": _sha(expected_start_raw),
        "identity_receipt_sha256": child_digest("identity", "identity-receipt.json"),
        "identity_terminal_sha256": child_digest("identity", "identity-terminal.json"),
        "primary_start_receipt_sha256": root_digest("primary-start-receipt.json"),
        "primary_result_receipt_sha256": child_digest("primary", "primary-result-receipt.json"),
        "primary_result_terminal_sha256": child_digest("primary", "primary-result-terminal.json"),
        "primary_consumer_terminal_sha256": child_digest("primary", "primary-consumer-terminal.json"),
        "secondary_start_receipt_sha256": root_digest("secondary-start-receipt.json"),
        "secondary_result_receipt_sha256": child_digest("secondary", "secondary-result-receipt.json"),
        "secondary_result_terminal_sha256": child_digest("secondary", "secondary-result-terminal.json"),
        "secondary_consumer_terminal_sha256": child_digest("secondary", "secondary-consumer-terminal.json"),
        "comparison_receipt_sha256": root_digest("comparison-receipt.json"),
        "comparison_terminal_sha256": root_digest("comparison-terminal.json"),
        "release_start_receipt_sha256": root_digest("release-start-receipt.json"),
        "release_report_sha256": root_digest("release-report.json"),
        "release_receipt_sha256": root_digest("release-receipt.json"),
        "release_terminal_sha256": root_digest("release-terminal.json"),
    }
    if bindings != observed_bindings:
        raise ValueError("success terminal transitive receipt closure")
    if terminal.get("package_receipt_sha256") != root_digest("package-receipt.json"):
        raise ValueError("success package receipt closure")
    if terminal.get("v11_closure_root_sha256") != root_digest("v11-result-closure.json"):
        raise ValueError("success V11 closure")


def _validate_existing_package_terminal(
    storage: _StorageBinding,
    value: object,
    raw: bytes,
    expected_start_raw: bytes,
    *,
    runtime: _Runtime | None,
) -> None:
    if type(value) is not dict or _canonical_bytes(value) != raw:
        raise ValueError("existing package terminal bytes")
    if value.get("schema") == _FAILURE_TERMINAL_SCHEMA:
        _validate_existing_failure_terminal(
            storage,
            value,
            expected_start_raw,
            runtime=runtime,
        )
    elif value.get("schema") == _SUCCESS_PACKAGE_TERMINAL_SCHEMA:
        _validate_existing_success_terminal(storage, value, expected_start_raw)
    else:
        raise ValueError("existing package terminal schema")


def _bank_failure_terminal_from_durable_progress(
    *,
    storage: _StorageBinding,
    expected_package_start_raw: bytes,
    exc: BaseException,
    access_progress: Mapping[str, object],
    terminal_origin: str,
    emergency_release_sha256: str | None,
    emergency_release_outcome: Mapping[str, object] | None,
    runtime: _Runtime | None,
) -> tuple[dict[str, object], str]:
    progress = _derive_durable_stage_progress(
        storage,
        expected_package_start_raw,
        access_progress=access_progress,
    )
    accounting = _failure_accounting_value(
        progress=progress,
        access_progress=access_progress,
        terminal_origin=terminal_origin,
        emergency_release_sha256=emergency_release_sha256,
        emergency_release_outcome=emergency_release_outcome,
        runtime=runtime,
    )
    accounting_raw = _canonical_bytes(accounting)
    accounting_sha256 = _sha(accounting_raw)
    accounting_leaf_sha256: str | None = None
    try:
        accounting_leaf_sha256 = storage.bank_failure(
            "failure-accounting.json", accounting
        )
    except FileExistsError:
        try:
            existing = storage._read_held_leaf(
                "failure-accounting.json", maximum_bytes=1_048_576
            )
        except BaseException:
            existing = b""
        if existing == accounting_raw:
            accounting_leaf_sha256 = accounting_sha256
    except BaseException:
        # The terminal embeds the complete accounting value and digest, so a
        # failure to create this convenience leaf cannot strand a started
        # package without its sole authoritative terminal.
        accounting_leaf_sha256 = None
    if terminal_origin == _RESTART_CLOSEOUT_ORIGIN:
        failure_type = "PROCESS_INTERRUPTION_AFTER_PACKAGE_START"
        failure_wrapper_type = None
    elif isinstance(exc, _IdentityAuthorityError):
        failure_type = exc.outcome_id
        failure_wrapper_type = type(exc).__name__
    else:
        failure_type = (
            exc.cause_type
            if isinstance(exc, _IdentityHandoffFailure)
            else type(exc).__name__
        )
        failure_wrapper_type = (
            type(exc).__name__ if isinstance(exc, _IdentityHandoffFailure) else None
        )
    terminal = {
        "schema": _FAILURE_TERMINAL_SCHEMA,
        "state": "TERMINAL_FAILURE",
        "terminal_origin": terminal_origin,
        "failed_stage": progress["failed_stage"],
        "failure_type": failure_type,
        "failure_wrapper_type": failure_wrapper_type,
        "package_attempt_id": progress["package_attempt_id"],
        "failure_accounting": accounting,
        "failure_accounting_sha256": accounting_sha256,
        "failure_accounting_leaf_sha256": accounting_leaf_sha256,
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
    storage._bank_failure_terminal(terminal)
    return terminal, _sha(_canonical_bytes(terminal))


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
        or report.get("operation_class") != authority.get("operation_class")
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
        event_key = {
            "PRIMARY": "primary_event_id",
            "SECONDARY": "secondary_event_id",
            "RELEASE": "package_attempt_id",
        }[stage]
        stage_authority = {
            "stage": stage,
            "authorization_id": bridge.get("authorization_id"),
            "package_attempt_id": bridge.get("package_attempt_id"),
            "stage_event_id": bridge.get(event_key),
            "package_start_sha256": package_start_sha256,
        }
        value = {
            "schema": _STAGE_RECEIPT_SCHEMA,
            **stage_authority,
            "stage_authority_sha256": _contract_sha256(stage_authority),
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
        primary_start = _bank_stage_receipt(
            runtime.storage, "PRIMARY", bridge.as_dict(), package_start_sha
        )
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
        secondary_start = _bank_stage_receipt(
            runtime.storage, "SECONDARY", bridge.as_dict(), package_start_sha
        )
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
        release_start = _bank_stage_receipt(
            runtime.storage, "RELEASE", bridge.as_dict(), package_start_sha
        )
        stop.record("RELEASE_START", release_start)
        release = identity.leases.release()
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
        elif (
            isinstance(exc, _IdentityAuthorityError)
            and exc.descriptor_disposition is not None
        ):
            source = _identity_failure_release_outcome(exc)
            if source is None:
                raise RuntimeError("identity descriptor disposition projection")
            emergency_release_outcome = source
            try:
                emergency_release_sha = runtime.storage.bank_failure(
                    "emergency-release-report.json",
                    _emergency_release_value(stop.current_stage, source),
                )
            except BaseException:
                pass
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
                emergency_release = identity.leases.release()
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


def closeout_interrupted_event06_minimum_gate_path(
    collapsed_go_bytes: bytes,
) -> Mapping[str, object]:
    """Close an already-started package without reaching an execution stage."""
    if type(collapsed_go_bytes) is not bytes:
        raise TypeError("exact collapsed GO bytes required")
    go_sha256 = _sha(collapsed_go_bytes)
    qualification = _QUALIFICATION_INVOCATION.get()
    if qualification is None:
        profile = _authority_profile(synthetic=False)
        try:
            go = _validate_go_non_temporal(collapsed_go_bytes, profile)
        except ValueError as exc:
            if str(exc) == "collapsed GO release authority":
                return MappingProxyType({
                    "result": "SOURCE_RELEASE_AUTHORITY_MISMATCH_CLOSEOUT",
                    "terminal_written": False,
                    "checkpoint_effects": 0,
                    "numerical_effects": 0,
                })
            raise
        runtime = _production_runtime(
            str(go.get("human_decision_sha256")), profile
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
        try:
            go = _validate_go_non_temporal(collapsed_go_bytes, runtime.profile)
        except ValueError as exc:
            if str(exc) == "collapsed GO release authority":
                return MappingProxyType({
                    "result": "SOURCE_RELEASE_AUTHORITY_MISMATCH_CLOSEOUT",
                    "terminal_written": False,
                    "checkpoint_effects": 0,
                    "numerical_effects": 0,
                })
            raise
    if runtime.package_claim_sha256 != go.get("human_decision_sha256"):
        raise ValueError("one-shot package claim/human decision binding")
    expected_start = _derive_expected_package_start_receipt(go, runtime)
    expected_start_raw = _canonical_bytes(expected_start)
    try:
        try:
            runtime.storage.prepare_existing()
        except FileNotFoundError:
            return MappingProxyType({
                "result": "NO_DURABLE_PACKAGE_START",
                "terminal_written": False,
                "checkpoint_effects": 0,
                "numerical_effects": 0,
            })
        state = runtime.storage.acquire_interrupted_terminal(
            expected_start_raw,
            runtime=runtime,
        )
        if state != "ACQUIRED_FOR_RESTART_CLOSEOUT":
            terminal_sha256: str | None = None
            if state == "ALREADY_TERMINAL":
                terminal_sha256 = _sha(
                    runtime.storage._read_held_leaf(
                        "package-terminal.json", maximum_bytes=1_048_576
                    )
                )
            return MappingProxyType({
                "result": state,
                "terminal_written": False,
                "package_terminal_sha256": terminal_sha256,
                "checkpoint_effects": 0,
                "numerical_effects": 0,
            })
        access_progress = _derive_access_progress_for_failure(
            runtime.storage, runtime, None
        )
        terminal, terminal_sha256 = _bank_failure_terminal_from_durable_progress(
            storage=runtime.storage,
            expected_package_start_raw=expected_start_raw,
            exc=RuntimeError("PROCESS_INTERRUPTION_AFTER_PACKAGE_START"),
            access_progress=access_progress,
            terminal_origin=_RESTART_CLOSEOUT_ORIGIN,
            emergency_release_sha256=None,
            emergency_release_outcome={
                "attempted_closures": 0,
                "successful_closures": 0,
                "duplicate_closures": 0,
                "unknown_leases": 0,
                "live_leases_after_release": 0,
                "release_disposition": "KERNEL_RELEASED_PROCESS_DESCRIPTORS",
                "result": "PASS",
            },
            runtime=None,
        )
        if (
            terminal.get("terminal_origin") != _RESTART_CLOSEOUT_ORIGIN
            or terminal.get("failure_type")
            != "PROCESS_INTERRUPTION_AFTER_PACKAGE_START"
        ):
            raise RuntimeError("restart closeout terminal authority")
        return MappingProxyType({
            "result": "TERMINAL_FAILURE_BANKED",
            "terminal_written": True,
            "package_terminal_sha256": terminal_sha256,
            "failed_stage": terminal["failed_stage"],
            "primary_delta": terminal["failure_accounting"]["primary_delta"],
            "secondary_delta": terminal["failure_accounting"]["secondary_delta"],
            "checkpoint_effects": 0,
            "numerical_effects": 0,
        })
    finally:
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


def _graph_owned_qualification_seed(root: Path, label: str) -> bytes:
    """Bank and read back one deterministic, graph-owned decision seed."""
    root = _qualification_root(root)
    if type(label) is not str or not label or len(label) > 128:
        raise TypeError("bounded qualification decision label")
    label_bytes = label.encode("utf-8")
    raw = b"F017-SEQUENCE41-GRAPH-OWNED-DECISION\x00" + label_bytes
    leaf = f".f017-sequence41-decision-{_sha(label_bytes)[:24]}.bin"
    root_fd = _open_directory_chain(root, create=False)
    descriptor = -1
    flags = os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
    if hasattr(os, "O_CLOEXEC"):
        flags |= os.O_CLOEXEC
    try:
        descriptor = os.open(leaf, flags, 0o600, dir_fd=root_fd)
        written = 0
        while written < len(raw):
            count = os.write(descriptor, raw[written:])
            if count <= 0:
                raise OSError("short qualification decision write")
            written += count
        os.fsync(descriptor)
        observed = os.fstat(descriptor)
        if (
            not stat.S_ISREG(observed.st_mode)
            or observed.st_uid != os.getuid()
            or observed.st_nlink != 1
            or observed.st_size != len(raw)
        ):
            raise ValueError("graph-owned qualification decision identity")
        os.lseek(descriptor, 0, os.SEEK_SET)
        readback = bytearray()
        while len(readback) < len(raw):
            chunk = os.read(descriptor, len(raw) - len(readback))
            if not chunk:
                raise OSError("short qualification decision readback")
            readback.extend(chunk)
        if os.read(descriptor, 1) or bytes(readback) != raw:
            raise ValueError("graph-owned qualification decision readback")
        os.fsync(root_fd)
        return bytes(readback)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        os.close(root_fd)


def _qualification_collapsed_go_bytes() -> bytes:
    """Return a current, synthetic-only collapsed GO for private qualification."""
    return _qualification_go(
        _authority_profile(synthetic=True),
        b"F017-S39-PRIVATE-QUALIFICATION",
        now_unix_ns=time.time_ns(),
    )


def _qualification_root(value: Path) -> Path:
    if not isinstance(value, Path):
        raise TypeError("qualification root is graph-owned")
    try:
        lexical = _canonical_absolute_path(value)
        temporary_parent = _canonical_absolute_path(
            Path(os.path.realpath(tempfile.gettempdir()))
        )
    except ValueError as exc:
        raise ValueError("qualification root is noncanonical") from exc
    if (
        lexical == temporary_parent
        or not lexical.is_relative_to(temporary_parent)
        or lexical == _LIVE_PACKAGE_PARENT
        or lexical.is_relative_to(_LIVE_PACKAGE_PARENT)
        or _LIVE_PACKAGE_PARENT.is_relative_to(lexical)
        or lexical == _LIVE_CHECKPOINT_ROOT
        or lexical.is_relative_to(_LIVE_CHECKPOINT_ROOT)
        or _LIVE_CHECKPOINT_ROOT.is_relative_to(lexical)
    ):
        raise ValueError("qualification root cannot overlap a live root")
    descriptor = -1
    try:
        descriptor = _open_directory_chain(lexical, create=False)
        observed = os.fstat(descriptor)
        physical = Path(os.path.realpath(lexical))
        if (
            physical != lexical
            or not stat.S_ISDIR(observed.st_mode)
            or observed.st_uid != os.getuid()
        ):
            raise ValueError("qualification root must be a real directory")
    except (OSError, ValueError) as exc:
        raise ValueError("qualification root must be a nonsymlink directory") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return lexical


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


def _invoke_public_closeout_qualification(
    collapsed_go_bytes: bytes,
    runtime: _Runtime,
    *,
    now_unix_ns: int,
) -> dict[str, object]:
    """Reach the non-executing public closeout through the sealed test seam."""
    invocation = _QualificationInvocation(
        _QUALIFICATION_INVOCATION_SEAL,
        runtime,
        now_unix_ns,
        _sha(collapsed_go_bytes),
    )
    token = _QUALIFICATION_INVOCATION.set(invocation)
    try:
        runtime.storage.preserve_terminal_for_closeout(_SYNTHETIC_STORAGE_SEAL)
        return dict(closeout_interrupted_event06_minimum_gate_path(collapsed_go_bytes))
    finally:
        _QUALIFICATION_INVOCATION.reset(token)


def _run_preopen_intercept(root: Path) -> dict[str, object]:
    """Prove interception at the real physical-identity call boundary."""
    qualification_root = _qualification_root(root)
    now = time.time_ns()
    profile = _authority_profile(synthetic=True)
    human_seed = _graph_owned_qualification_seed(
        qualification_root, "PREOPEN"
    )
    collapsed_go = _qualification_go(profile, human_seed, now_unix_ns=now)
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
        "physical_call_boundary": (
            "f017_checkpoint_identity_producer_v12._minimum_gate_produce"
        ),
        "package_started": True,
        "terminal_failure_banked": True,
        "failure_accounting_banked": True,
        "synthetic_human_decision_sha256": _sha(human_seed),
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
    seed = _graph_owned_qualification_seed(case_root, case_name)
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

    checkpoint_provider = runtime.checkpoint_effect
    if type(checkpoint_provider) is not _SyntheticCheckpointProvider:
        raise AssertionError("synthetic checkpoint provider accounting")

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
        "synthetic_human_decision_sha256s": [
            preopen["synthetic_human_decision_sha256"],
            _sha(seed),
        ],
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
        "physical_v12_identity_producer_calls": (
            checkpoint_provider.physical_identity_producer_calls
        ),
        "synthetic_checkpoint_binding_checks": (
            checkpoint_provider.producer_checkpoint_binding_checks
        ),
        "synthetic_checkpoint_shard_opens": (
            checkpoint_provider.producer_checkpoint_shard_opens
        ),
        "synthetic_checkpoint_identity_hash_reads": (
            checkpoint_provider.producer_checkpoint_identity_hash_reads
        ),
        "synthetic_checkpoint_payload_bytes_read": (
            runtime.observed_effects["synthetic_fixture_payload_bytes"]
        ),
        "synthetic_checkpoint_mmaps": 0,
        "graph_owned_synthetic_checkpoint_required_leaves": (
            runtime.observed_effects["synthetic_fixture_required_leaves"]
        ),
        "graph_owned_synthetic_checkpoint_benign_extra_leaves": (
            runtime.observed_effects["synthetic_fixture_benign_extra_leaves"]
        ),
        "graph_owned_fixture_leaf_creation_opens": runtime.observed_effects[
            "synthetic_fixture_leaf_creation_opens"
        ],
        "graph_owned_fixture_benign_extra_creation_opens": (
            runtime.observed_effects[
                "synthetic_fixture_benign_extra_creation_opens"
            ]
        ),
        "identity_producer_extra_leaf_open_follow_stat_hash": "0/0/0/0",
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
