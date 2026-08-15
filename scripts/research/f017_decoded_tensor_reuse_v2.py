#!/usr/bin/env python3
"""Checkpoint-free decoded-tensor reuse planning and synthetic enforcement.

The real 12-payload package is never opened here.  The module derives its
immutable identity surface from accepted public evidence and exercises the
same package rules with tiny synthetic payloads.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterator, Sequence


AUTHORITY_PATH = Path(
    "docs/architecture/reviews/evidence/f017-v2-antecedent-recovery-execution-config-v1.json"
)
AUTHORITY_SHA256 = "649a53630be246af11270f1cad19bdb8a7ccabf06e928febfe6cbc282dd4c7e2"
LEDGER_PATH = Path("docs/architecture/reviews/evidence/f017-real-payload-access-ledger-v1.json")
LEDGER_SHA256 = "1dc884c4a9c328bef518a3989e671ff33467f38b48d61405fdc25c160b7a6401"
CHECKPOINT = "d7d1e6a8f8ab11726a7f1e43e4d8f02ed73f04ee27ffb876915147a568b9afee"
CATALOG = "0f0425106a240c5062acab9fc41b1b2651680c6ad06fe476214f88a8d2a177f0"
TENSOR_MAP = "ea0786f0e890af01dc111d355ef64aec1ca4898de5432197258bacccfaecc223"
TENSOR_COUNT = 12
COMPRESSED_BYTES = 139_217_920
DECODED_BYTES = 666_430_464


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_json_no_duplicates(path: Path) -> dict:
    def pairs(items: list[tuple[str, object]]) -> dict:
        result: dict[str, object] = {}
        for key, value in items:
            if key in result:
                raise ValueError(f"duplicate key {key!r} in {path}")
            result[key] = value
        return result

    value = json.loads(path.read_text(), object_pairs_hook=pairs)
    if not isinstance(value, dict):
        raise ValueError(f"expected object in {path}")
    return value


def contract_value(root: Path) -> dict[str, object]:
    authority_path = root / AUTHORITY_PATH
    ledger_path = root / LEDGER_PATH
    if sha256_path(authority_path) != AUTHORITY_SHA256:
        raise ValueError("accepted M1-F0 identity authority mismatch")
    if sha256_path(ledger_path) != LEDGER_SHA256:
        raise ValueError("real-payload ledger identity mismatch")
    authority = parse_json_no_duplicates(authority_path)
    checkpoint = authority["checkpoint_bindings"]
    if checkpoint != {
        "catalog_sha256": CATALOG,
        "checkpoint_set_sha256": CHECKPOINT,
        "tensor_map_sha256": TENSOR_MAP,
    }:
        raise ValueError("checkpoint/catalog/map binding mismatch")
    tensors = []
    for ordinal, tensor in enumerate(authority["tensor_allowlist"]):
        tensors.append({
            "ordinal": ordinal,
            "name": tensor["name"],
            "shard_ordinal": tensor["shard_ordinal"],
            "offset": tensor["offset"],
            "packed_length": tensor["packed_length"],
            "decoded_length": tensor["decoded_length"],
            "packed_sha256": tensor["packed_sha256"],
            "decoded_sha256": tensor["decoded_sha256"],
            "quantization": tensor["quantization"],
            "logical_shape": tensor["logical_shape"],
            "decoder_contract": tensor["decoder_contract"],
            "allowed_initial_payload_reads": 1,
            "allowed_reuse_reads": 0,
        })
    if len(tensors) != TENSOR_COUNT:
        raise ValueError("exactly 12 accepted tensors required")
    decoder_contracts = sorted({str(item["decoder_contract"]) for item in tensors})
    naive_payloads = TENSOR_COUNT * 8
    return {
        "schema": "pulsarmlx.f017.m1f0-decoded-tensor-reuse",
        "schema_version": "2.0.0",
        "contract_id": "f017-m1f0-decoded-tensor-reuse-v2",
        "status": "PLANNING_ONLY_NOT_AUTHORIZED",
        "predecessor_v1_sha256": "e061bb16af5bda05c39fd439c76c17447e2af0093369bb00fb14062425cead16",
        "checkpoint_access": 0,
        "real_payload_ledger": 57,
        "identity_authority": {"path": str(AUTHORITY_PATH), "sha256": AUTHORITY_SHA256},
        "ledger_authority": {"path": str(LEDGER_PATH), "sha256": LEDGER_SHA256},
        "checkpoint_bindings": {
            "checkpoint_set_sha256": CHECKPOINT,
            "catalog_sha256": CATALOG,
            "tensor_map_sha256": TENSOR_MAP,
        },
        "tensor_allowlist": tensors,
        "decoder_contract_set": decoder_contracts,
        "reuse_boundary": {
            "one_initial_shard_open": 1,
            "one_initial_positional_read_per_tensor": 12,
            "initial_payloads": 12,
            "compressed_bytes": COMPRESSED_BYTES,
            "decoded_bytes": DECODED_BYTES,
            "subsequent_checkpoint_reads": 0,
            "scope": "one authorization event, one exact checkpoint/config identity, one precommitted fixture family",
            "cross_event_reuse": "REQUIRES_NEW_REVIEW_AND_AUTHORIZATION",
            "automatic_reread_fallback": "FORBIDDEN",
        },
        "immutability": {
            "canonical_package_identity": "sha256(canonical manifest containing checkpoint/catalog/map, execution identity, ordered tensor descriptors, and decoded content hashes)",
            "machine_local_path_in_identity": False,
            "absolute_paths_in_public_evidence": False,
            "symlink_components": "REJECT",
            "path_escape": "REJECT",
            "non_regular_payload": "REJECT",
            "read_only_in_memory_bytes": True,
            "manifest_and_payload_hash_before_execution": True,
            "backing_root_and_all_payload_hashes_before_and_after_each_fixture": True,
            "package_identity_before_and_after_each_fixture_equal": True,
            "relocation_before_execution": "ALLOWED_ONLY_AFTER_COMPLETE_REVALIDATION; content identity is path-independent",
            "relocation_after_execution_start": "REJECT",
            "mutation": "FAIL_CLOSED",
        },
        "fixture_isolation": {
            "fixture_allowlist_precommitted": True,
            "fixture_input_not_part_of_decoded_package": True,
            "each_fixture_gets_read_only_views": True,
            "repeat_outputs_and_full_analytics_banked_per_fixture": True,
            "package_rehashed_around_each_fixture": True,
        },
        "candidate_oracle_separation": {
            "review_enum_A4": "MIXED_POLICY",
            "m1f0_ladder": "ORACLE_ONLY_REUSE_ALLOWED_BY_DESIGN_AFTER_SEPARATE_AUTHORIZATION",
            "production_candidate_consumer": "REJECT_FROM_SHARED_PACKAGE",
            "future_m1f_candidate": "REQUIRES_SEPARATE_COPY_OR_INDEPENDENT_IMPORT_WITH_OWN_HASH_AND_LIFECYCLE",
            "dense_prefix_future_consumer": "MAY_COPY_OR_IMPORT_SOURCE_CANONICAL_BYTES_ONLY_WITH_A_SEPARATE_HASH_AND_LIFECYCLE; SHARED_WRITABLE_ALIAS_FORBIDDEN",
            "oracle_and_candidate_mutable_alias": "FORBIDDEN",
            "candidate_result_may_not_mutate_or_replace_oracle_package": True,
        },
        "economics": {
            "fixture_count": 8,
            "naive_payload_reads": naive_payloads,
            "reuse_payload_reads": TENSOR_COUNT,
            "payload_reads_avoided": naive_payloads - TENSOR_COUNT,
            "naive_compressed_bytes": COMPRESSED_BYTES * 8,
            "reuse_compressed_bytes": COMPRESSED_BYTES,
            "compressed_bytes_avoided": COMPRESSED_BYTES * 7,
            "naive_decoded_bytes": DECODED_BYTES * 8,
            "reuse_decoded_bytes": DECODED_BYTES,
            "decode_bytes_avoided": DECODED_BYTES * 7,
            "fraction_avoided": 0.875,
            "official_repeats_per_fixture": 10,
            "repeats_do_not_add_checkpoint_reads": True,
        },
        "conditional_dense_prefix_ledger_planning": {
            "status": "HYPOTHETICAL_NOT_AUTHORIZED",
            "ledger_before": 57,
            "baseline_without_retained_qualification_components": {
                "new_payload_reads": 42,
                "ledger_after": 99,
            },
            "reuse_option": {
                "precondition": "Track2 Q4_K and Q6_K qualification outputs are retained as immutable canonical components with accepted hashes and compatible checkpoint/catalog/map/decoder identities",
                "new_payload_reads": 40,
                "ledger_after": 97,
                "source_byte_transfer": "separate copy/import with a new consumer hash and lifecycle",
                "shared_writable_alias": "FORBIDDEN",
            },
            "scientific_disposition": "57_TO_97_IS_CONDITIONALLY_SOUND_ONLY_IF_THE_PRECONDITION_IS_INDEPENDENTLY_ACCEPTED; OTHERWISE_57_TO_99",
            "authorization_issued": False,
        },
        "use_case_matrix": [
            {"use_case": "single M1-F0 fixture", "reuse": "NO_ECONOMIC_GAIN", "disposition": "one 12-payload package"},
            {"use_case": "precommitted M1-F0 fixture family", "reuse": "ELIGIBLE", "disposition": "oracle-only, full family banking, one execution event"},
            {"use_case": "M1-F0 retry or later authorization", "reuse": "NOT_IMPLICIT", "disposition": "new review/config identity required"},
            {"use_case": "decoder qualification", "reuse": "INELIGIBLE", "disposition": "independent exact packed-byte A/B/C gate"},
            {"use_case": "M1-F candidate versus oracle", "reuse": "ORACLE_SIDE_ONLY", "disposition": "candidate must use separate copy/import identity"},
            {"use_case": "M1-G/P1", "reuse": "INELIGIBLE", "disposition": "different tensor and execution boundary"},
            {"use_case": "checkpoint-free synthetic validation", "reuse": "ELIGIBLE", "disposition": "tiny synthetic package only"},
            {"use_case": "future dense-prefix boundary", "reuse": "CONDITIONAL_SOURCE_BYTES_ONLY", "disposition": "57->97 only with retained immutable Q4_K/Q6_K qualification components; otherwise 57->99; consumer receives separately hashed copy/import, never shared writable alias"},
        ],
        "threat_model": [
            {"threat": "payload or manifest mutation", "control": "pre/post SHA-256 and immutable bytes", "failure": "REJECT"},
            {"threat": "checkpoint/catalog/map substitution", "control": "direct cryptographic binding", "failure": "REJECT"},
            {"threat": "tensor reorder, omission, duplicate, or decoder drift", "control": "ordered exact 12-entry manifest and decoder set", "failure": "REJECT"},
            {"threat": "symlink or path escape", "control": "relative safe paths and no symlink components", "failure": "REJECT"},
            {"threat": "candidate mutates oracle bytes", "control": "candidate consumer rejected; separate copy/import required", "failure": "REJECT"},
            {"threat": "cross-authorization stale reuse", "control": "execution and family identity in manifest", "failure": "REJECT"},
            {"threat": "silent reread after validation failure", "control": "no fallback budget", "failure": "STOP"},
        ],
        "review_disposition_A7": "DECODED_REUSE_READY_FOR_FUTURE_AUTHORIZATION",
        "real_execution_authorized": False,
    }


def _safe_relative(value: str) -> Path:
    pure = PurePosixPath(value)
    if pure.is_absolute() or not pure.parts or any(part in ("", ".", "..") for part in pure.parts):
        raise ValueError("unsafe payload path")
    return Path(*pure.parts)


def _reject_symlink_chain(root: Path, relative: Path | None = None) -> None:
    current = root
    if current.is_symlink():
        raise ValueError("symlink package root")
    if relative is None:
        return
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("symlink package component")


@dataclass(frozen=True, slots=True)
class TensorPayload:
    name: str
    filename: str
    sha256: str
    byte_length: int
    content: bytes


class DecodedTensorPackage:
    def __init__(self, root: Path, manifest: dict, payloads: Sequence[TensorPayload]):
        self._root = root.resolve(strict=True)
        self._root_stat = (self._root.stat().st_dev, self._root.stat().st_ino)
        self.manifest = manifest
        self.payloads = tuple(payloads)
        self.package_sha256 = sha256_bytes(canonical_json_bytes(manifest))
        self._started = False

    @classmethod
    def load(cls, root: Path) -> "DecodedTensorPackage":
        _reject_symlink_chain(root)
        resolved = root.resolve(strict=True)
        manifest_path = resolved / "manifest.json"
        _reject_symlink_chain(resolved, Path("manifest.json"))
        manifest = parse_json_no_duplicates(manifest_path)
        if manifest.get("schema") != "pulsarmlx.f017.synthetic-decoded-tensor-package":
            raise ValueError("package schema")
        records = manifest.get("tensors")
        if not isinstance(records, list) or len(records) != TENSOR_COUNT:
            raise ValueError("exactly 12 package tensors required")
        payloads = []
        seen_names: set[str] = set()
        seen_files: set[str] = set()
        for ordinal, record in enumerate(records):
            if record.get("ordinal") != ordinal:
                raise ValueError("tensor order mismatch")
            name = str(record["name"])
            filename = str(record["filename"])
            if name in seen_names or filename in seen_files:
                raise ValueError("duplicate tensor identity")
            seen_names.add(name)
            seen_files.add(filename)
            relative = _safe_relative(filename)
            _reject_symlink_chain(resolved, relative)
            path = resolved / relative
            mode = path.stat().st_mode
            if not stat.S_ISREG(mode):
                raise ValueError("payload is not a regular file")
            content = path.read_bytes()
            if len(content) != int(record["byte_length"]) or sha256_bytes(content) != record["sha256"]:
                raise ValueError("payload identity mismatch")
            payloads.append(TensorPayload(name, filename, record["sha256"], len(content), content))
        return cls(resolved, manifest, payloads)

    def validate_backing(self) -> None:
        if not self._root.exists() or self._root.is_symlink():
            raise ValueError("package root unavailable or substituted")
        root_stat = (self._root.stat().st_dev, self._root.stat().st_ino)
        if root_stat != self._root_stat:
            raise ValueError("package root relocated after load")
        if sha256_bytes(canonical_json_bytes(parse_json_no_duplicates(self._root / "manifest.json"))) != self.package_sha256:
            raise ValueError("package manifest mutated")
        for payload in self.payloads:
            relative = _safe_relative(payload.filename)
            _reject_symlink_chain(self._root, relative)
            path = self._root / relative
            if not path.is_file() or sha256_path(path) != payload.sha256 or path.stat().st_size != payload.byte_length:
                raise ValueError("package payload mutated")

    @contextlib.contextmanager
    def oracle_lease(self, fixture_id: str) -> Iterator[tuple[memoryview, ...]]:
        allowed = self.manifest.get("fixture_ids")
        if not isinstance(allowed, list) or fixture_id not in allowed:
            raise ValueError("fixture is not precommitted")
        self._started = True
        self.validate_backing()
        before = self.package_sha256
        views = tuple(memoryview(payload.content) for payload in self.payloads)
        if not all(view.readonly for view in views):
            raise AssertionError("decoded payload view is mutable")
        try:
            yield views
        finally:
            self.validate_backing()
            if self.package_sha256 != before:
                raise ValueError("package identity changed during fixture")

    def candidate_lease(self, fixture_id: str) -> None:
        del fixture_id
        raise ValueError("production candidate cannot alias the oracle reuse package")


def synthetic_manifest(fixture_ids: Sequence[str]) -> tuple[dict, list[bytes]]:
    if not fixture_ids or len(set(fixture_ids)) != len(fixture_ids):
        raise ValueError("fixture IDs must be unique and non-empty")
    contents = [f"synthetic-decoded-tensor-{index:02d}".encode() for index in range(TENSOR_COUNT)]
    tensors = [
        {
            "ordinal": index,
            "name": f"synthetic.tensor.{index}",
            "filename": f"payloads/tensor-{index:02d}.bin",
            "byte_length": len(content),
            "sha256": sha256_bytes(content),
        }
        for index, content in enumerate(contents)
    ]
    return ({
        "schema": "pulsarmlx.f017.synthetic-decoded-tensor-package",
        "schema_version": "1.0.0",
        "execution_identity": "synthetic-zero-read-v1",
        "checkpoint_set_sha256": "0" * 64,
        "catalog_sha256": "1" * 64,
        "tensor_map_sha256": "2" * 64,
        "fixture_ids": list(fixture_ids),
        "tensors": tensors,
    }, contents)


def write_synthetic_package(root: Path, fixture_ids: Sequence[str]) -> None:
    manifest, contents = synthetic_manifest(fixture_ids)
    payload_root = root / "payloads"
    payload_root.mkdir(parents=True, exist_ok=False)
    for record, content in zip(manifest["tensors"], contents, strict=True):
        (root / record["filename"]).write_bytes(content)
    (root / "manifest.json").write_bytes(canonical_json_bytes(manifest))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.repository_root.resolve()
    output = args.output if args.output.is_absolute() else root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(canonical_json_bytes(contract_value(root)))
    print(sha256_path(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
