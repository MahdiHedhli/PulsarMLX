#!/usr/bin/env python3
"""S2 executor v2 with exact producer-specific retained-manifest parsing.

Arithmetic remains delegated byte-for-byte to the accepted v1 scalar
implementation.  Only the immutable retained operand admission surface is
repaired: S1 uses its singular producer manifest and FFN keeps its distinct
plural producer manifest.
"""

from __future__ import annotations

import json
import math
import os
import struct
from pathlib import Path
from typing import Any

import f017_representative_s2_executor_v1 as arithmetic_v1


S2Error = arithmetic_v1.S2Error
require = arithmetic_v1.require
sha256 = arithmetic_v1.sha256
sha256_path = arithmetic_v1.sha256_path
unique = arithmetic_v1.unique
open_directory = arithmetic_v1.open_directory
open_leaf = arithmetic_v1.open_leaf
read_exact = arithmetic_v1.read_exact
validate_arithmetic = arithmetic_v1.validate_arithmetic
require_environment = arithmetic_v1.require_environment
compose_bytes = arithmetic_v1.compose_bytes
compose_from_open_operands = arithmetic_v1.compose_from_open_operands
S1_SHA = arithmetic_v1.S1_SHA
FFN_SHA = arithmetic_v1.FFN_SHA


def _load_manifest(raw: bytes) -> dict[str, Any]:
    try:
        value = json.loads(raw, object_pairs_hook=unique)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise S2Error("MANIFEST_JSON") from error
    require(isinstance(value, dict), "MANIFEST_OBJECT")
    return value


def _validate_s1_manifest(doc: dict[str, Any], artifact: dict[str, Any]) -> None:
    """Validate the exact accepted S1 producer vocabulary before aliasing."""
    require(set(artifact) == {
        "relative_path", "sha256", "semantic_role", "producer_semantic_role",
        "dtype", "shape", "byte_length",
    }, "S1_SPEC_CENSUS")
    producer_role = artifact["producer_semantic_role"]
    require(producer_role == "LAYER3_POST_ATTENTION_RESIDUAL", "S1_PRODUCER_ROLE")
    expected = {
        "schema": "pulsarmlx.f017.representative-s1-private-manifest",
        "schema_version": "1.0.0",
        "artifact": {
            "byte_length": artifact["byte_length"],
            "dtype": artifact["dtype"],
            "finite": True,
            "path": artifact["relative_path"],
            "semantic_role": producer_role,
            "sha256": artifact["sha256"],
            "shape": artifact["shape"],
        },
        "expected_equals_produced_equals_readback": True,
        "matching_complete_terminal_required": True,
    }
    require(doc == expected, "S1_MANIFEST_BINDING")


def _validate_ffn_manifest(doc: dict[str, Any], artifact: dict[str, Any]) -> None:
    """Validate the distinct accepted FFN producer vocabulary exactly."""
    require(set(artifact) == {
        "relative_path", "sha256", "semantic_role", "semantic_surface",
        "dtype", "shape", "byte_length",
    }, "FFN_SPEC_CENSUS")
    expected = {
        "schema": "pulsarmlx.f017.representative-ffn-output-private-manifest",
        "schema_version": "1.0.0",
        "semantic_surface": artifact["semantic_surface"],
        "artifacts": [{
            "byte_length": artifact["byte_length"],
            "dtype": artifact["dtype"],
            "finite": True,
            "semantic_role": artifact["semantic_role"],
            "sha256": artifact["sha256"],
            "shape": artifact["shape"],
            "symbolic_path": artifact["relative_path"],
        }],
        "authority_requires_matching_complete_terminal": True,
        "execution_receipt_relative_path": "../attempt-state/ffn-execution-receipt.json",
    }
    require(doc == expected, "FFN_MANIFEST_BINDING")


class OpenOperand:
    """Validate one producer-specific manifest and hold one immutable operand."""

    def __init__(self, root: Path, specification: dict[str, Any]) -> None:
        self.root_fd, _ = open_directory(root)
        self.descriptor: int | None = None
        try:
            manifest = specification["manifest"]
            manifest_fd, _, manifest_raw = open_leaf(
                self.root_fd, manifest["relative_path"], manifest["byte_length"]
            )
            try:
                require(sha256(manifest_raw) == manifest["sha256"], "MANIFEST_SHA")
                manifest_doc = _load_manifest(manifest_raw)
                artifact = specification["artifact"]
                kind = specification["manifest_kind"]
                if kind == "S1_SINGULAR_PRODUCER_V1":
                    _validate_s1_manifest(manifest_doc, artifact)
                elif kind == "FFN_PLURAL_PRODUCER_V1":
                    _validate_ffn_manifest(manifest_doc, artifact)
                else:
                    raise S2Error("MANIFEST_KIND")
            finally:
                os.close(manifest_fd)

            artifact = specification["artifact"]
            self.descriptor, self.before_metadata, self.raw = open_leaf(
                self.root_fd, artifact["relative_path"], artifact["byte_length"]
            )
            self.expected_sha = artifact["sha256"]
            self.before_sha = sha256(self.raw)
            require(self.expected_sha == self.before_sha, "EXPECTED_BEFORE")
            fmt = "<6144f" if artifact["dtype"] == "little-endian-f32" else "<6144d"
            require(all(math.isfinite(value) for value in struct.unpack(fmt, self.raw)), "INPUT_NONFINITE")
            # The consumer alias exists only after exact producer authority passes.
            self.consumer_semantic_role = artifact["semantic_role"]
        except BaseException:
            if self.descriptor is not None:
                os.close(self.descriptor)
            os.close(self.root_fd)
            raise

    def _stable_readback(self) -> str:
        require(self.descriptor is not None, "OPERAND_CLOSED")
        after_raw = read_exact(self.descriptor, len(self.raw))
        after_metadata = os.fstat(self.descriptor)
        after = sha256(after_raw)
        before = self.before_metadata
        require(
            (before.st_dev, before.st_ino, before.st_size)
            == (after_metadata.st_dev, after_metadata.st_ino, after_metadata.st_size),
            "INPUT_OBJECT_CHANGED",
        )
        require(self.expected_sha == self.before_sha == after, "EXPECTED_BEFORE_READBACK")
        return after

    def verify_preflight(self) -> dict[str, str]:
        """Read-only descriptor stability check; this is not execution consumption."""
        readback = self._stable_readback()
        return {
            "expected_sha256": self.expected_sha,
            "before_sha256": self.before_sha,
            "readback_sha256": readback,
        }

    def verify_after(self) -> dict[str, str]:
        consumed = sha256(self.raw)
        after = self._stable_readback()
        require(self.expected_sha == self.before_sha == consumed == after, "EXPECTED_BEFORE_CONSUMED_AFTER")
        return {
            "expected_sha256": self.expected_sha,
            "before_sha256": self.before_sha,
            "consumed_sha256": consumed,
            "after_sha256": after,
        }

    def close(self) -> None:
        if self.descriptor is not None:
            os.close(self.descriptor)
            self.descriptor = None
        os.close(self.root_fd)


def main() -> int:
    return arithmetic_v1.main()


if __name__ == "__main__":
    raise SystemExit(main())
