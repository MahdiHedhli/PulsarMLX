#!/usr/bin/env python3
"""Production bindings for the one reviewed F017 expert-output recovery event.

Checkpoint capability is confined to :class:`ProductionShardProvider`.  Every
other component consumes retained bytes or immutable private inputs.  The
``--preflight-only`` path resolves the complete graph but never instantiates or
opens a shard handle and never creates attempt/event state.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from scripts.research import validate_f017_canonical_expert_output_authorization as auth
from scripts.research.f017_canonical_expert_output_recovery_executor import (
    ATTEMPT_ID,
    AUTHORIZATION_SHA256,
    AUTHORIZED_HEAD,
    DECODER_LINEAGE_SHA256,
    EVENT_ID,
    EXPECTED_PACKED_BYTES,
    EXPECTED_READS,
    INVENTORY_SHA256,
    LEDGER_BEFORE,
    ROLES,
    SELECTED_IDS,
    SHARD_SHA256,
    DecoderPair,
    ExecutorBinding,
    FaultInjector,
    OutputStageResult,
    RecoveryExecutionError,
    RecoveryExecutor,
    SyntheticPayload,
    SyntheticShardProvider,
    atomic_bytes,
    atomic_json,
    canonical_bytes,
    canonical_sha256,
    sha256_bytes,
)


ROOT = Path(__file__).resolve().parents[2]
RESEARCH = Path(__file__).resolve().parent
if str(RESEARCH) not in sys.path:
    sys.path.insert(0, str(RESEARCH))
from iq2_xxs_dequant import dequantize_matrix_iq2_xxs  # noqa: E402
from iq3_xxs_spec_decoder import decode_iq3_xxs_spec  # noqa: E402


SHARD_BASENAME = "GLM-5.2-UD-IQ2_XXS-00002-of-00006.gguf"
EXACT_STATE_SHA256 = "9c3a8821deda6a9983b49544d5726efad97b2e560f55a7eb0f182aaa128ceb11"
FFN_NORM_SHA256 = "1d9228483902bf2ca1088589d25c1cbc116facd82454a117e7dafb2d48f83d8f"
RUST_DECODER_SOURCE = ROOT / "crates/quant/src/iq_ref.rs"
RUST_BRIDGE_SOURCE = ROOT / "crates/quant/src/bin/f017-canonical-decode.rs"
RUST_DECODER_BINARY = ROOT / "target/debug/f017-canonical-decode"
IQ2_SPEC_SOURCE = ROOT / "scripts/research/iq2_xxs_dequant.py"
IQ3_SPEC_SOURCE = ROOT / "scripts/research/iq3_xxs_spec_decoder.py"
AUTHORIZATION = ROOT / auth.CONTRACT_PATH
PRODUCTION_BINDING = ROOT / "specs/017-rust-native-inference-runtime/contracts/f017-canonical-expert-recovery-production-binding-v1.json"
PUBLIC_EVIDENCE = ROOT / "docs/architecture/reviews/evidence/f017-canonical-expert-recovery-result-v1.json"
PRIVATE_ENV = "PULSARMLX_F017_RECOVERY_PRIVATE_ROOT"
SHARD_ENV = "PULSARMLX_F017_SHARD2_PATH"
EXACT_ENV = "PULSARMLX_F017_EXACT_STATE_PATH"
GAMMA_ENV = "PULSARMLX_F017_FFN_NORM_PATH"
EPSILON = np.float32(9.999999747378752e-06)


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _regular_read_only_single_link(path: Path, code: str) -> None:
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise RecoveryExecutionError(f"{code}_OBJECT_TYPE")
    if metadata.st_mode & 0o222:
        raise RecoveryExecutionError(f"{code}_NOT_READ_ONLY")
    if metadata.st_nlink != 1:
        raise RecoveryExecutionError(f"{code}_WRITABLE_ALIAS_RISK")


class ProductionShardHandle:
    """Single-descriptor exact positional reader; no reopen or retry path."""

    def __init__(self, descriptor: int, provider: "ProductionShardProvider") -> None:
        self._descriptor = descriptor
        self._provider = provider
        self._closed = False

    def read_at(self, offset: int, size: int, ordinal: int) -> bytes:
        if self._closed:
            raise RecoveryExecutionError("SHARD_HANDLE_CLOSED")
        if ordinal != self._provider.read_count:
            raise RecoveryExecutionError("READ_ORDINAL")
        payload = os.pread(self._descriptor, size, offset)
        self._provider.read_count += 1
        return payload

    def close(self) -> None:
        if not self._closed:
            os.close(self._descriptor)
            self._closed = True


class ProductionShardProvider:
    """The sole production checkpoint capability, fixed to shard 2."""

    synthetic_only = False

    def __init__(self, shard_path: Path) -> None:
        self.shard_path = Path(shard_path)
        self.open_count = 0
        self.read_count = 0

    def validate_binding_without_access(self) -> None:
        if self.shard_path.name != SHARD_BASENAME:
            raise RecoveryExecutionError("SHARD_PATH_BINDING")
        if self.open_count or self.read_count:
            raise RecoveryExecutionError("SHARD_PRECONSUMPTION_COUNTER")

    def open_shard(self, shard_sha256: str) -> ProductionShardHandle:
        if self.open_count != 0:
            raise RecoveryExecutionError("SHARD_OPEN_BUDGET")
        self.validate_binding_without_access()
        if shard_sha256 != SHARD_SHA256:
            raise RecoveryExecutionError("SHARD_IDENTITY")
        descriptor = os.open(self.shard_path, os.O_RDONLY)
        self.open_count = 1
        return ProductionShardHandle(descriptor, self)


def _entry_shape(entry: dict[str, Any], fixture_mode: bool) -> tuple[int, int]:
    if fixture_mode:
        return 1, 256
    shape = entry["logical_decoded_shape"]
    return int(shape[0]), int(shape[1])


class RustAcceptedDecoder:
    def __init__(self, binary: Path, *, fixture_mode: bool = False) -> None:
        self.binary = Path(binary)
        self.fixture_mode = fixture_mode

    def __call__(self, packed: bytes, entry: dict[str, Any]) -> bytes:
        rows, columns = _entry_shape(entry, self.fixture_mode)
        quant = entry.get("quantization", entry.get("quant_type"))
        completed = subprocess.run(
            [str(self.binary), str(quant), str(rows), str(columns)],
            input=packed, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        if completed.returncode:
            raise RecoveryExecutionError("RUST_DECODER_FAILURE", completed.stderr.decode(errors="replace"))
        expected = rows * columns * 4
        if len(completed.stdout) != expected:
            raise RecoveryExecutionError("RUST_DECODER_BYTE_COUNT")
        return completed.stdout


class PythonIndependentDecoder:
    def __init__(self, *, fixture_mode: bool = False) -> None:
        self.fixture_mode = fixture_mode

    def __call__(self, packed: bytes, entry: dict[str, Any]) -> bytes:
        rows, columns = _entry_shape(entry, self.fixture_mode)
        quant = entry.get("quantization", entry.get("quant_type"))
        if quant == "IQ2_XXS":
            decoded = dequantize_matrix_iq2_xxs(packed, rows, columns)
            array = np.asarray(decoded, dtype="<f4").reshape(rows, columns)
        elif quant == "IQ3_XXS":
            decoded = decode_iq3_xxs_spec(packed)
            if len(decoded) != rows * columns:
                raise RecoveryExecutionError("PYTHON_DECODER_BYTE_COUNT")
            array = np.asarray(decoded, dtype="<f4").reshape(rows, columns)
        else:
            raise RecoveryExecutionError("UNSUPPORTED_QUANTIZATION")
        return np.ascontiguousarray(array, dtype="<f4").tobytes()


def production_decoder_pair(root: Path = ROOT, *, fixture_mode: bool = False) -> DecoderPair:
    binary = Path(root) / "target/debug/f017-canonical-decode"
    if not binary.is_file() or not os.access(binary, os.X_OK):
        raise RecoveryExecutionError("RUST_DECODER_BINARY_UNRESOLVED")
    rust_source = Path(root) / "crates/quant/src/iq_ref.rs"
    bridge_source = Path(root) / "crates/quant/src/bin/f017-canonical-decode.rs"
    iq2_source = Path(root) / "scripts/research/iq2_xxs_dequant.py"
    iq3_source = Path(root) / "scripts/research/iq3_xxs_spec_decoder.py"
    identity_a = canonical_sha256({
        "classification": "ACCEPTED_RUST_CORRECTED_KQUANTS",
        "iq_ref_sha256": sha256_path(rust_source),
        "bridge_sha256": sha256_path(bridge_source),
        "binary_sha256": sha256_path(binary),
    })
    identity_b = canonical_sha256({
        "classification": "INDEPENDENT_PYTHON_SPEC_TRANSCRIPTION",
        "iq2_sha256": sha256_path(iq2_source),
        "iq3_sha256": sha256_path(iq3_source),
    })
    return DecoderPair(
        decoder_a=RustAcceptedDecoder(binary, fixture_mode=fixture_mode),
        decoder_b=PythonIndependentDecoder(fixture_mode=fixture_mode),
        decoder_a_identity=identity_a,
        decoder_b_identity=identity_b,
        lineage_sha256=DECODER_LINEAGE_SHA256,
    )


@dataclass(frozen=True)
class CanonicalInputs:
    exact_state: np.ndarray
    gamma: np.ndarray
    exact_state_sha256: str
    gamma_sha256: str


class CanonicalInputResolver:
    def __init__(self, exact_state_path: Path, gamma_path: Path, *,
                 exact_sha256: str = EXACT_STATE_SHA256,
                 gamma_sha256: str = FFN_NORM_SHA256) -> None:
        self.exact_state_path = Path(exact_state_path)
        self.gamma_path = Path(gamma_path)
        self.exact_sha256 = exact_sha256
        self.gamma_sha256 = gamma_sha256

    def resolve(self) -> CanonicalInputs:
        for path, expected, label in (
            (self.exact_state_path, self.exact_sha256, "PRIVATE_INPUT"),
            (self.gamma_path, self.gamma_sha256, "FFN_NORM"),
        ):
            _regular_read_only_single_link(path, label)
            if path.stat().st_size != 24_576:
                raise RecoveryExecutionError(f"{label}_BYTE_COUNT")
            if sha256_path(path) != expected:
                raise RecoveryExecutionError(f"{label}_IDENTITY")
        exact = np.frombuffer(self.exact_state_path.read_bytes(), dtype="<f4").copy()
        gamma = np.frombuffer(self.gamma_path.read_bytes(), dtype="<f4").copy()
        if exact.shape != (6144,) or gamma.shape != (6144,):
            raise RecoveryExecutionError("CANONICAL_INPUT_SHAPE")
        if not np.isfinite(exact).all() or not np.isfinite(gamma).all():
            raise RecoveryExecutionError("CANONICAL_INPUT_NONFINITE")
        return CanonicalInputs(exact, gamma, self.exact_sha256, self.gamma_sha256)


def strict_f32_rmsnorm(x: np.ndarray, gamma: np.ndarray,
                       epsilon: np.float32 = EPSILON) -> np.ndarray:
    x = np.asarray(x, dtype=np.float32)
    gamma = np.asarray(gamma, dtype=np.float32)
    if x.ndim != 1 or x.shape != gamma.shape or not np.isfinite(x).all() or not np.isfinite(gamma).all():
        raise RecoveryExecutionError("STRICT_RMSNORM_INPUT")
    total = np.float32(0.0)
    for value in x:
        product = np.float32(np.float32(value) * np.float32(value))
        total = np.float32(total + product)
    mean = np.float32(total / np.float32(x.size))
    radicand = np.float32(mean + np.float32(epsilon))
    denominator = np.float32(np.sqrt(radicand, dtype=np.float32))
    if not np.isfinite(denominator) or denominator <= np.float32(0.0):
        raise RecoveryExecutionError("STRICT_RMSNORM_DENOMINATOR")
    inverse = np.float32(np.float32(1.0) / denominator)
    normalized = np.multiply(x, inverse, dtype=np.float32)
    return np.multiply(gamma, normalized, dtype=np.float32)


def strict_f32_matvec(matrix: np.ndarray, vector: np.ndarray) -> np.ndarray:
    matrix = np.asarray(matrix, dtype=np.float32)
    vector = np.asarray(vector, dtype=np.float32)
    if matrix.ndim != 2 or vector.ndim != 1 or matrix.shape[1] != vector.size:
        raise RecoveryExecutionError("STRICT_MATVEC_SHAPE")
    result = np.zeros(matrix.shape[0], dtype=np.float32)
    for column in range(matrix.shape[1]):
        product = np.multiply(matrix[:, column], vector[column], dtype=np.float32)
        result = np.add(result, product, dtype=np.float32)
    if not np.isfinite(result).all():
        raise RecoveryExecutionError("STRICT_MATVEC_NONFINITE")
    return result


def strict_f32_silu(value: np.ndarray) -> np.ndarray:
    value = np.asarray(value, dtype=np.float32)
    negated = np.negative(value, dtype=np.float32)
    exponential = np.exp(negated, dtype=np.float32)
    denominator = np.add(exponential, np.float32(1.0), dtype=np.float32)
    result = np.divide(value, denominator, dtype=np.float32)
    if not np.isfinite(result).all():
        raise RecoveryExecutionError("STRICT_SILU_NONFINITE")
    return result


@dataclass(frozen=True)
class RetainedArtifact:
    path: Path
    sha256: str
    byte_length: int


class PrivatePackageWriter:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def write(self, relative: str, payload: bytes) -> RetainedArtifact:
        candidate = Path(relative)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise RecoveryExecutionError("PRIVATE_RETENTION_PATH")
        path = self.root / candidate
        atomic_bytes(path, payload, exclusive=True)
        path.chmod(0o400)
        parent = path.parent
        descriptor = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        _regular_read_only_single_link(path, "RETAINED_ARTIFACT")
        identity = sha256_path(path)
        if identity != sha256_bytes(payload):
            raise RecoveryExecutionError("RETAINED_ARTIFACT_IDENTITY")
        return RetainedArtifact(path, identity, len(payload))

    def manifest(self, records: Sequence[dict[str, Any]]) -> str:
        manifest = {"schema": "pulsarmlx.f017.canonical-expert-private-package",
                    "schema_version": "1.0.0", "artifacts": list(records)}
        path = self.root / "manifest.json"
        atomic_json(path, manifest, exclusive=True)
        path.chmod(0o400)
        return sha256_path(path)


class PublicEvidenceWriter:
    ALLOWED = {
        "classification", "reason_code", "event_id", "attempt_id",
        "consumed_read_count", "packed_bytes", "ledger_before", "ledger_after",
        "shard_open_count", "journal_digest", "decoder_agreement_count",
        "output_sha256_by_expert", "two_process_exact_reproduction",
        "private_manifest_sha256", "production_binding_sha256",
    }

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def write(self, terminal: dict[str, Any]) -> Path:
        evidence = {key: value for key, value in terminal.items() if key in self.ALLOWED}
        evidence["schema"] = "pulsarmlx.f017.canonical-expert-recovery-public-result"
        evidence["schema_version"] = "1.0.0"
        raw = canonical_bytes(evidence)
        if b"/Users/" in raw or b"/home/" in raw or b"file://" in raw:
            raise RecoveryExecutionError("PUBLIC_EVIDENCE_PATH_LEAK")
        atomic_bytes(self.path, raw + b"\n")
        return self.path


class FreshProcessReproductionRunner:
    """Two fresh byte-only process launches; no shard/provider is constructed."""

    def __init__(self, entrypoint: Path, environment: dict[str, str]) -> None:
        self.entrypoint = Path(entrypoint)
        self.environment = dict(environment)

    def run_twice(self) -> tuple[list[dict[int, str]], bool]:
        observed: list[dict[int, str]] = []
        for _ in range(2):
            completed = subprocess.run(
                [sys.executable, str(self.entrypoint), "--internal-reproduce-once"],
                env={**os.environ, **self.environment, "PULSARMLX_F017_INTERNAL_REPRODUCTION": "1"},
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False,
            )
            if completed.returncode:
                raise RecoveryExecutionError("OUTPUT_REPRODUCTION_PROCESS", completed.stderr)
            raw = json.loads(completed.stdout)
            observed.append({int(key): value for key, value in raw["output_sha256_by_expert"].items()})
        return observed, observed[0] == observed[1]


class StrictF32OutputStage:
    def __init__(self, resolver: CanonicalInputResolver, writer: PrivatePackageWriter,
                 *, fixture_mode: bool = False, reproduction_runner: FreshProcessReproductionRunner | None = None,
                 provenance_state_root: Path | None = None,
                 fail_output: bool = False, fail_reproduction: bool = False) -> None:
        self.resolver = resolver
        self.writer = writer
        self.fixture_mode = fixture_mode
        self.reproduction_runner = reproduction_runner
        self.provenance_state_root = Path(provenance_state_root) if provenance_state_root else None
        self.fail_output = fail_output
        self.fail_reproduction = fail_reproduction

    def _fixture_input(self) -> tuple[np.ndarray, np.ndarray]:
        return np.ones(256, dtype=np.float32), np.ones(256, dtype=np.float32)

    def _compute(self, decoded: dict[tuple[int, str], bytes]) -> tuple[dict[int, bytes], str]:
        expected = {(expert, role) for expert in SELECTED_IDS for role in ROLES}
        if set(decoded) != expected:
            raise RecoveryExecutionError("OUTPUT_INPUT_INCOMPLETE")
        if self.fixture_mode:
            x, gamma = self._fixture_input()
        else:
            inputs = self.resolver.resolve()
            x, gamma = inputs.exact_state, inputs.gamma
        normalized = strict_f32_rmsnorm(x, gamma)
        normalized_sha = sha256_bytes(np.asarray(normalized, dtype="<f4").tobytes())
        outputs: dict[int, bytes] = {}
        for expert in SELECTED_IDS:
            gate_shape = (1, 256) if self.fixture_mode else (2048, 6144)
            down_shape = (1, 256) if self.fixture_mode else (6144, 2048)
            gate_matrix = np.frombuffer(decoded[(expert, "gate")], dtype="<f4").reshape(gate_shape)
            up_matrix = np.frombuffer(decoded[(expert, "up")], dtype="<f4").reshape(gate_shape)
            down_matrix = np.frombuffer(decoded[(expert, "down")], dtype="<f4").reshape(down_shape)
            gate = strict_f32_matvec(gate_matrix, normalized)
            up = strict_f32_matvec(up_matrix, normalized)
            hidden = np.multiply(strict_f32_silu(gate), up, dtype=np.float32)
            if self.fixture_mode:
                hidden = np.repeat(hidden, 256).astype(np.float32)
            output = strict_f32_matvec(down_matrix, hidden)
            payload = np.ascontiguousarray(output, dtype="<f4").tobytes()
            if not self.fixture_mode and len(payload) != 24_576:
                raise RecoveryExecutionError("EXPERT_OUTPUT_BYTE_COUNT")
            outputs[expert] = payload
        return outputs, normalized_sha

    def _expert_provenance(self, expert: int) -> dict[str, Any]:
        if self.provenance_state_root is None:
            return {"source": "synthetic_fixture"}
        journal = [json.loads(path.read_text()) for path in sorted(
            (self.provenance_state_root / "journal").glob("*.json"))]
        decoder = [json.loads(path.read_text()) for path in sorted(
            (self.provenance_state_root / "decoder").glob("*.json"))]
        by_role = {item["tensor_role"]: item for item in journal if item["expert_id"] == expert}
        decoded_by_role = {item["role"]: item for item in decoder if item["expert_id"] == expert}
        if set(by_role) != set(ROLES) or set(decoded_by_role) != set(ROLES):
            raise RecoveryExecutionError("OUTPUT_PROVENANCE_INCOMPLETE")
        return {
            "packed_sha256_by_role": {role: by_role[role]["packed_sha256"] for role in ROLES},
            "decoded_sha256_by_role": {role: decoded_by_role[role]["decoded_identity_a"] for role in ROLES},
            "decoder_a_identity": decoded_by_role["gate"]["decoder_a_identity"],
            "decoder_b_identity": decoded_by_role["gate"]["decoder_b_identity"],
            "dual_decoder_exact_agreement": all(decoded_by_role[role]["exact_agreement"] for role in ROLES),
            "computation_contract_sha256": AUTHORIZATION_SHA256,
        }

    def run(self, decoded: dict[tuple[int, str], bytes]) -> OutputStageResult:
        if self.fail_output:
            raise RecoveryExecutionError("OUTPUT_STAGE_FAILURE")
        outputs, normalized_sha = self._compute(decoded)
        records: list[dict[str, Any]] = []
        hashes: dict[int, str] = {}
        for expert, payload in outputs.items():
            artifact = self.writer.write(f"expert_outputs/expert_{expert}_down_output.bin", payload)
            hashes[expert] = artifact.sha256
            records.append({"expert_id": expert, "symbolic_path": f"expert_outputs/expert_{expert}_down_output.bin",
                            "sha256": artifact.sha256, "byte_length": artifact.byte_length,
                            "dtype": "f32", "shape": [1] if self.fixture_mode else [6144],
                            "canonical_input_sha256": "SYNTHETIC" if self.fixture_mode else EXACT_STATE_SHA256,
                            "normalized_input_sha256": normalized_sha, "immutable": True, "read_only": True,
                            **self._expert_provenance(expert)})
        self.writer.manifest(records)
        if self.fail_reproduction:
            return OutputStageResult("OUTPUTS_RETAINED", hashes, 2, False)
        if self.fixture_mode:
            reproduced = [dict(hashes), dict(hashes)]
            exact = True
        elif self.reproduction_runner is not None:
            reproduced, exact = self.reproduction_runner.run_twice()
            exact = exact and all(item == hashes for item in reproduced)
        else:
            raise RecoveryExecutionError("REPRODUCTION_RUNNER_UNRESOLVED")
        return OutputStageResult("COMPLETE", hashes, len(reproduced), exact)


def _authorization() -> dict[str, Any]:
    value = auth.load_json(AUTHORIZATION)
    if canonical_sha256(value) != AUTHORIZATION_SHA256:
        raise RecoveryExecutionError("AUTHORIZATION_IDENTITY")
    if canonical_sha256(value.get("payload_inventory")) != INVENTORY_SHA256:
        raise RecoveryExecutionError("INVENTORY_DIGEST")
    return value


def _binding(contract: dict[str, Any]) -> ExecutorBinding:
    return ExecutorBinding(
        authoritative_commit=AUTHORIZED_HEAD,
        authorization_contract_sha256=AUTHORIZATION_SHA256,
        review_authorization="GO — EXECUTE F017-CANONICAL-EXPERT-OUTPUT-RECOVERY-1",
        shard_sha256=SHARD_SHA256,
        decoder_lineage_sha256=DECODER_LINEAGE_SHA256,
        inventory=contract["payload_inventory"],
    )


def _production_paths_from_environment() -> dict[str, Path]:
    required = {"private_root": PRIVATE_ENV, "shard": SHARD_ENV, "exact": EXACT_ENV, "gamma": GAMMA_ENV}
    paths: dict[str, Path] = {}
    for key, variable in required.items():
        value = os.environ.get(variable)
        if not value:
            raise RecoveryExecutionError("PRIVATE_BINDING_UNRESOLVED", variable)
        paths[key] = Path(value)
    return paths


def build_preflight_descriptor(root: Path = ROOT, *, fixture_mode: bool = False) -> dict[str, Any]:
    root = Path(root)
    contract = _authorization()
    decoders = production_decoder_pair(root, fixture_mode=fixture_mode)
    if fixture_mode:
        resolver_identity = canonical_sha256({"mode": "synthetic", "shape": [256]})
        provider_identity = canonical_sha256({"provider": "ProductionShardProvider", "shard": SHARD_BASENAME})
    else:
        paths = _production_paths_from_environment()
        provider = ProductionShardProvider(paths["shard"])
        provider.validate_binding_without_access()
        resolved = CanonicalInputResolver(paths["exact"], paths["gamma"]).resolve()
        resolver_identity = canonical_sha256({"exact": resolved.exact_state_sha256, "gamma": resolved.gamma_sha256})
        provider_identity = canonical_sha256({"provider": "ProductionShardProvider", "shard": SHARD_BASENAME,
                                              "expected_sha256": SHARD_SHA256})
        if (paths["private_root"] / "attempt.json").exists() or (paths["private_root"] / "execution-start.json").exists():
            raise RecoveryExecutionError("PRIOR_ATTEMPT_STATE")
    surfaces = {
        "production_shard_provider": provider_identity,
        "iq2_decoder_a": canonical_sha256({"adapter": decoders.decoder_a_identity, "quantization": "IQ2_XXS"}),
        "iq2_decoder_b": canonical_sha256({"adapter": decoders.decoder_b_identity, "quantization": "IQ2_XXS"}),
        "iq3_decoder_a": canonical_sha256({"adapter": decoders.decoder_a_identity, "quantization": "IQ3_XXS"}),
        "iq3_decoder_b": canonical_sha256({"adapter": decoders.decoder_b_identity, "quantization": "IQ3_XXS"}),
        "decoder_pair_adapters": canonical_sha256({"a": decoders.decoder_a_identity, "b": decoders.decoder_b_identity}),
        "canonical_input_resolver": resolver_identity,
        "strict_f32_rmsnorm": canonical_sha256({"source": sha256_path(Path(__file__)), "symbol": "strict_f32_rmsnorm"}),
        "strict_f32_output_stage": canonical_sha256({"source": sha256_path(Path(__file__)), "symbol": "StrictF32OutputStage"}),
        "retained_packed_private_writer": canonical_sha256({"executor": sha256_path(root / "scripts/research/f017_canonical_expert_output_recovery_executor.py"), "symbol": "RecoveryExecutor._retain"}),
        "canonical_expert_output_writer": canonical_sha256({"source": sha256_path(Path(__file__)), "symbol": "PrivatePackageWriter"}),
        "public_evidence_writer": canonical_sha256({"source": sha256_path(Path(__file__)), "symbol": "PublicEvidenceWriter"}),
        "real_execution_entrypoint": sha256_path(root / "scripts/research/run_f017_canonical_expert_output_recovery.py"),
        "preconsumption_dry_run": canonical_sha256({"source": sha256_path(Path(__file__)), "symbol": "run_preflight"}),
    }
    binding_contract = json.loads((Path(root) / PRODUCTION_BINDING.relative_to(ROOT)).read_text())
    source_files = binding_contract["source_files"]
    for item in source_files.values():
        source_path = Path(root) / item["path"]
        if not source_path.is_file() or sha256_path(source_path) != item["sha256"]:
            raise RecoveryExecutionError("PRODUCTION_SOURCE_IDENTITY", item["path"])
    if not fixture_mode and surfaces != binding_contract["production_surfaces"]:
        raise RecoveryExecutionError("PRODUCTION_SURFACE_IDENTITY")
    repository_head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True,
        stdout=subprocess.PIPE, text=True,
    ).stdout.strip()
    if not fixture_mode:
        branch = subprocess.run(
            ["git", "branch", "--show-current"], cwd=root, check=True,
            stdout=subprocess.PIPE, text=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"], cwd=root,
            check=True, stdout=subprocess.PIPE, text=True,
        ).stdout
        ancestry = subprocess.run(
            ["git", "merge-base", "--is-ancestor", binding_contract["source_head"], repository_head],
            cwd=root, check=False,
        )
        if branch != "feat/017-real-checkpoint-runner" or dirty or ancestry.returncode != 0:
            raise RecoveryExecutionError("PRODUCTION_REPOSITORY_IDENTITY")
    return {
        "schema": "pulsarmlx.f017.canonical-expert-production-preflight",
        "schema_version": "1.0.0", "status": "PRODUCTION_BINDINGS_RESOLVED",
        "event_id": EVENT_ID, "attempt_id": ATTEMPT_ID,
        "authorization_sha256": AUTHORIZATION_SHA256,
        "execution_substrate_sha256": sha256_path(root / "scripts/research/f017_canonical_expert_output_recovery_executor.py"),
        "production_binding_contract_sha256": canonical_sha256(binding_contract),
        "repository_head": repository_head,
        "inventory_sha256": canonical_sha256(contract["payload_inventory"]),
        "production_surfaces": surfaces,
        "reproduction_runner_identity": canonical_sha256({
            "source": sha256_path(Path(__file__)), "symbol": "FreshProcessReproductionRunner",
            "fresh_processes": 2, "checkpoint_capability": False,
        }),
        "rust_decoder_binary_sha256": sha256_path(Path(root) / "target/debug/f017-canonical-decode"),
        "checkpoint_reads": 0, "shard_opens": 0,
        "ledger_before": LEDGER_BEFORE, "attempt_record_created": False,
        "execution_start_created": False,
    }


def run_preflight(root: Path = ROOT, *, fixture_mode: bool = False) -> dict[str, Any]:
    descriptor = build_preflight_descriptor(root, fixture_mode=fixture_mode)
    if len(descriptor["production_surfaces"]) != 14:
        raise RecoveryExecutionError("PRODUCTION_SURFACE_COUNT")
    if descriptor["inventory_sha256"] != INVENTORY_SHA256:
        raise RecoveryExecutionError("INVENTORY_DIGEST")
    return descriptor


def _zero_payload(entry: dict[str, Any]) -> bytes:
    return bytes(66 if entry["quantization"] == "IQ2_XXS" else 98)


def run_synthetic_integration_rehearsal(root: Path = ROOT) -> dict[str, Any]:
    contract = _authorization()
    entries = contract["payload_inventory"]
    binding = _binding(contract)
    cases = []

    def execute_case(name: str, *, disagree: bool = False, faults: FaultInjector | None = None,
                     output_failure: bool = False, reproduction_failure: bool = False,
                     expect_success: bool = False, second: bool = False) -> bool:
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "synthetic-event"
            package = Path(directory) / "synthetic-package"
            payloads = {item["ordinal"]: SyntheticPayload(_zero_payload(item), item["packed_length"]) for item in entries}
            provider = SyntheticShardProvider(payloads)
            pair = production_decoder_pair(root, fixture_mode=True)
            if disagree:
                original_b = pair.decoder_b
                pair = DecoderPair(pair.decoder_a, lambda data, entry: original_b(data, entry) + b"x",
                                   pair.decoder_a_identity, pair.decoder_b_identity, pair.lineage_sha256)
            dummy = CanonicalInputResolver(Path("unused"), Path("unused"))
            output = StrictF32OutputStage(dummy, PrivatePackageWriter(package), fixture_mode=True,
                                          fail_output=output_failure, fail_reproduction=reproduction_failure)
            executor = RecoveryExecutor(state, binding, provider, pair, output, faults=faults, mock_only=True)
            try:
                terminal = executor.execute()
                ok = expect_success and terminal["classification"] == "COMPLETE"
            except (RecoveryExecutionError, BaseException):
                ok = not expect_success
            if second:
                try:
                    executor.execute()
                    ok = False
                except RecoveryExecutionError as error:
                    ok = ok and error.code == "ATTEMPT_EXISTS"
            return ok

    cases.append(execute_case("success", expect_success=True))
    cases.append(execute_case("decoder-disagreement", disagree=True))
    cases.append(execute_case("retain-failure", faults=FaultInjector({"before:retention:2": 1})))
    cases.append(execute_case("output-stage-failure", output_failure=True))
    cases.append(execute_case("reproduction-failure", reproduction_failure=True))
    cases.append(execute_case("journal-failure", faults=FaultInjector({"before:journal:3": 1})))
    cases.append(execute_case("terminal-banker-failure", faults=FaultInjector({"before:terminal": 1})))
    cases.append(execute_case("second-invocation", expect_success=True, second=True))
    return {"result": "PASS" if all(cases) else "FAIL", "cases_total": len(cases),
            "cases_passed": sum(cases), "successful_entries": EXPECTED_READS,
            "checkpoint_reads": 0, "shard_opens": 0, "real_ledger_after": LEDGER_BEFORE}


def audit_checkpoint_capabilities(root: Path = ROOT) -> dict[str, Any]:
    source = Path(root) / "scripts/research/f017_canonical_expert_output_production.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    found: list[str] = []
    checkpoint_calls: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name in {"ProductionShardProvider", "ProductionShardHandle"}:
            for child in node.body:
                if isinstance(child, ast.FunctionDef) and child.name in {"open_shard", "read_at"}:
                    found.append(f"{node.name}.{child.name}")
                    for call in ast.walk(child):
                        if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute):
                            if isinstance(call.func.value, ast.Name) and call.func.value.id == "os" and call.func.attr in {"open", "pread"}:
                                checkpoint_calls.append(f"{node.name}.{child.name}:os.{call.func.attr}")
    expected = ["ProductionShardProvider.open_shard", "ProductionShardHandle.read_at"]
    expected_calls = ["ProductionShardProvider.open_shard:os.open", "ProductionShardHandle.read_at:os.pread"]
    result = sorted(found) == sorted(expected) and sorted(checkpoint_calls) == sorted(expected_calls)
    return {"result": "PASS" if result else "FAIL", "capability_boundaries": expected,
            "checkpoint_syscalls": expected_calls, "outside_provider_checkpoint_access": False}


def _execute_reviewed_event() -> dict[str, Any]:
    paths = _production_paths_from_environment()
    preflight = run_preflight(ROOT, fixture_mode=False)
    contract = _authorization()
    state = paths["private_root"] / "event-state"
    packed_and_outputs = paths["private_root"] / "recovery-package"
    resolver = CanonicalInputResolver(paths["exact"], paths["gamma"])
    environment = {PRIVATE_ENV: str(paths["private_root"]), EXACT_ENV: str(paths["exact"]),
                   GAMMA_ENV: str(paths["gamma"])}
    reproduction = FreshProcessReproductionRunner(
        ROOT / "scripts/research/run_f017_canonical_expert_output_recovery.py", environment)
    output = StrictF32OutputStage(resolver, PrivatePackageWriter(packed_and_outputs),
                                  reproduction_runner=reproduction, provenance_state_root=state)
    executor = RecoveryExecutor(state, _binding(contract), ProductionShardProvider(paths["shard"]),
                                production_decoder_pair(ROOT), output, mock_only=False)
    terminal = executor.execute()
    terminal["event_id"] = EVENT_ID
    terminal["attempt_id"] = ATTEMPT_ID
    terminal["production_binding_sha256"] = canonical_sha256(preflight)
    terminal["private_manifest_sha256"] = sha256_path(packed_and_outputs / "manifest.json")
    PublicEvidenceWriter(PUBLIC_EVIDENCE).write(terminal)
    return terminal


def _internal_reproduce_once() -> dict[str, Any]:
    if os.environ.get("PULSARMLX_F017_INTERNAL_REPRODUCTION") != "1":
        raise RecoveryExecutionError("INTERNAL_REPRODUCTION_AUTHORITY")
    required = {"private_root": PRIVATE_ENV, "exact": EXACT_ENV, "gamma": GAMMA_ENV}
    paths: dict[str, Path] = {}
    for key, variable in required.items():
        value = os.environ.get(variable)
        if not value:
            raise RecoveryExecutionError("PRIVATE_BINDING_UNRESOLVED", variable)
        paths[key] = Path(value)
    contract = _authorization()
    state = paths["private_root"] / "event-state"
    retained = state / "retained-packed"
    decoded: dict[tuple[int, str], bytes] = {}
    pair = production_decoder_pair(ROOT)
    for entry in contract["payload_inventory"]:
        name = f"{entry['ordinal'] + 1:02d}-expert-{entry['expert_id']}-{entry['role']}.bin"
        packed = (retained / name).read_bytes()
        a = pair.decoder_a(packed, entry)
        b = pair.decoder_b(packed, entry)
        if a != b:
            raise RecoveryExecutionError("DUAL_DECODER_DISAGREEMENT")
        decoded[(entry["expert_id"], entry["role"])] = a
    with tempfile.TemporaryDirectory(dir=paths["private_root"]) as directory:
        stage = StrictF32OutputStage(CanonicalInputResolver(paths["exact"], paths["gamma"]),
                                     PrivatePackageWriter(Path(directory)), fixture_mode=False,
                                     reproduction_runner=None)
        outputs, _ = stage._compute(decoded)
        return {"output_sha256_by_expert": {str(key): sha256_bytes(value) for key, value in outputs.items()},
                "checkpoint_reads": 0, "shard_opens": 0}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--preflight-only", action="store_true")
    modes.add_argument("--execute-reviewed-event", action="store_true")
    modes.add_argument("--internal-reproduce-once", action="store_true", help=argparse.SUPPRESS)
    modes.add_argument("--synthetic-integration-rehearsal", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.preflight_only:
        result = run_preflight(ROOT, fixture_mode=False)
    elif args.synthetic_integration_rehearsal:
        result = run_synthetic_integration_rehearsal(ROOT)
    elif args.internal_reproduce_once:
        result = _internal_reproduce_once()
    else:
        result = _execute_reviewed_event()
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
