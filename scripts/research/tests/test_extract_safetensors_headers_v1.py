"""The header extractor reads the prefix and the header, and provably nothing else.

The synthetic checkpoint built here is also the source of the committed
header-only census fixture, `crates/mlx-affine/tests/census_header_only_fixture/`:
the first test regenerates it through the extractor and requires the committed
bytes to be exactly what the extractor writes. To rewrite the fixture after a
deliberate change::

    python3 -I -B scripts/research/tests/test_extract_safetensors_headers_v1.py --write-fixture
"""

from __future__ import annotations

import ast
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import sys
import tempfile
import unittest
from unittest import mock

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = REPOSITORY_ROOT / "scripts" / "research" / "extract_safetensors_headers_v1.py"
FIXTURE = REPOSITORY_ROOT / "crates" / "mlx-affine" / "tests" / "census_header_only_fixture"
SENTINEL = b"PAYLOAD-SENTINEL"
PYC_SENTINEL = b"NEVER-READ-BYTECODE"


def _load():
    spec = importlib.util.spec_from_file_location("extract_safetensors_headers_v1", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("the extractor could not be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


extractor = _load()

# Neutral synthetic tensors. Shapes follow the MLX affine layout: a U32 packed
# weight [.., out, in * bits / 32] with scales and biases [.., out, in / group].
SHARDS = {
    "model-00001-of-00002.safetensors": [
        ("blocks.0.proj.weight", "U32", [8, 8]),
        ("blocks.0.proj.scales", "BF16", [8, 1]),
        ("blocks.0.proj.biases", "BF16", [8, 1]),
        ("blocks.0.wide.weight", "U32", [4, 16]),
        ("blocks.0.wide.scales", "F16", [4, 1]),
        ("blocks.0.wide.biases", "F16", [4, 1]),
        ("blocks.0.norm.weight", "BF16", [64]),
    ],
    "model-00002-of-00002.safetensors": [
        ("blocks.1.stack.weight", "U32", [3, 4, 8]),
        ("blocks.1.stack.scales", "F32", [3, 4, 1]),
        ("blocks.1.stack.biases", "F32", [3, 4, 1]),
        ("blocks.1.gate.correction", "F32", [3]),
        ("embed.weight", "BF16", [4, 64]),
    ],
}
SIZES = {"U32": 4, "F32": 4, "BF16": 2, "F16": 2}
QUANTIZATION = {"group_size": 64, "bits": 4, "blocks.0.wide": {"group_size": 64, "bits": 8}}


def _payload(length: int) -> bytes:
    return (SENTINEL * (length // len(SENTINEL) + 1))[:length]


def build_synthetic_checkpoint(root: Path) -> None:
    """A two-shard checkpoint whose every payload byte is the sentinel."""
    root.mkdir(parents=True)
    weight_map = {}
    total = 0
    for shard, tensors in SHARDS.items():
        header = {"__metadata__": {"format": "mlx"}}
        offset = 0
        for name, dtype, shape in tensors:
            count = 1
            for extent in shape:
                count *= extent
            length = count * SIZES[dtype]
            header[name] = {"dtype": dtype, "shape": shape, "data_offsets": [offset, offset + length]}
            offset += length
            weight_map[name] = shard
        total += offset
        text = json.dumps(header, separators=(",", ":")).encode()
        (root / shard).write_bytes(struct.pack("<Q", len(text)) + text + _payload(offset))
    config = {"model_type": "synthetic-census", "quantization": QUANTIZATION,
              "quantization_config": QUANTIZATION}
    (root / "config.json").write_text(json.dumps(config, indent=2, sort_keys=True) + "\n")
    index = {"metadata": {"total_size": total}, "weight_map": weight_map}
    (root / "model.safetensors.index.json").write_text(json.dumps(index, indent=2, sort_keys=True) + "\n")
    (root / "__pycache__").mkdir()
    (root / "__pycache__" / "stray.cpython-314.pyc").write_bytes(PYC_SENTINEL)


def _files(root: Path) -> dict:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*")) if path.is_file()
    }


class _Trace:
    """Record every pread and the name each descriptor was opened under."""

    def __init__(self):
        self.names = {}
        self.reads = []
        self._open = os.open
        self._pread = os.pread

    def open(self, path, flags, *args, **kwargs):
        fd = self._open(path, flags, *args, **kwargs)
        self.names[fd] = os.path.basename(path)
        return fd

    def pread(self, fd, length, offset):
        self.reads.append((self.names.get(fd, "?"), offset, length))
        return self._pread(fd, length, offset)

    def __enter__(self):
        self._patches = [mock.patch.object(os, "open", self.open),
                         mock.patch.object(os, "pread", self.pread)]
        for patch in self._patches:
            patch.start()
        return self

    def __exit__(self, *exc):
        for patch in self._patches:
            patch.stop()
        return False


class ExtractorTests(unittest.TestCase):
    def setUp(self):
        self._temporary = tempfile.TemporaryDirectory()
        self.base = Path(self._temporary.name)
        self.checkpoint = self.base / "checkpoint"
        self.output = self.base / "out"

    def tearDown(self):
        self._temporary.cleanup()

    def _extract(self):
        build_synthetic_checkpoint(self.checkpoint)
        return extractor.extract(str(self.checkpoint), str(self.output))

    def test_committed_fixture_is_exactly_the_extractor_output(self):
        self._extract()
        produced = _files(self.output)
        committed = _files(FIXTURE)
        self.assertEqual(sorted(produced), sorted(committed))
        for name in produced:
            self.assertEqual(produced[name], committed[name], name)

    def test_no_payload_or_bytecode_byte_reaches_the_output(self):
        self._extract()
        for name, data in _files(self.output).items():
            self.assertNotIn(SENTINEL[:8], data, name)
            self.assertNotIn(PYC_SENTINEL, data, name)
            self.assertNotIn(str(self.base).encode(), data, name)

    def test_each_shard_is_read_as_prefix_then_header_and_nothing_more(self):
        build_synthetic_checkpoint(self.checkpoint)
        with _Trace() as trace:
            summary = extractor.extract(str(self.checkpoint), str(self.output))
        for record in summary["shards"]:
            limit = 8 + record["header_len"]
            reads = [(o, n) for name, o, n in trace.reads if name == record["file"]]
            # Short reads would be retried, so the traced calls are exactly these.
            self.assertEqual(reads, [(0, 8), (8, record["header_len"])])
            self.assertEqual(max(o + n for o, n in reads), limit)
            self.assertEqual(record["max_read_offset_exclusive"], limit)
            self.assertEqual(record["bytes_read"], limit)
            self.assertEqual(record["payload_bytes_read"], 0)
            self.assertEqual(record["file_position_after"], 0)
            self.assertLess(limit, record["file_len"])
        self.assertNotIn("stray.cpython-314.pyc", {name for name, _, _ in trace.reads})
        self.assertEqual(summary["totals"]["payload_bytes_read"], 0)
        self.assertEqual(summary["totals"]["shards_within_bound"], 2)

    def test_an_oversized_header_is_refused_after_reading_eight_bytes(self):
        self.checkpoint.mkdir()
        shard = self.checkpoint / "model.safetensors"
        shard.write_bytes(struct.pack("<Q", extractor.MAX_HEADER_BYTES + 1) + b"{}" + SENTINEL)
        with _Trace() as trace, self.assertRaises(extractor.ExtractionError):
            extractor.extract_shard_header(str(shard))
        self.assertEqual(trace.reads, [("model.safetensors", 0, 8)])

    def test_a_header_longer_than_the_file_is_refused_after_eight_bytes(self):
        self.checkpoint.mkdir()
        shard = self.checkpoint / "model.safetensors"
        shard.write_bytes(struct.pack("<Q", 64) + b"{}")
        with _Trace() as trace, self.assertRaises(extractor.ExtractionError):
            extractor.extract_shard_header(str(shard))
        self.assertEqual(trace.reads, [("model.safetensors", 0, 8)])

    def test_the_reader_refuses_past_its_ceiling_without_reading(self):
        self.checkpoint.mkdir()
        path = self.checkpoint / "f"
        path.write_bytes(b"x" * 64)
        fd = os.open(str(path), os.O_RDONLY)
        try:
            with _Trace() as trace:
                reader = extractor.BoundedReader(fd, 8)
                with self.assertRaises(extractor.BoundViolation):
                    reader.pread_exact(1, 8)
                with self.assertRaises(extractor.BoundViolation):
                    reader.pread_exact(9, 0)
                with self.assertRaises(extractor.BoundViolation):
                    reader.raise_ceiling(7)
                with self.assertRaises(extractor.BoundViolation):
                    reader.raise_ceiling(8 + extractor.MAX_HEADER_BYTES + 1)
            self.assertEqual(trace.reads, [])
            self.assertEqual(reader.max_end, 0)
        finally:
            os.close(fd)

    def test_a_symlinked_shard_is_refused(self):
        build_synthetic_checkpoint(self.checkpoint)
        target = self.checkpoint / "model-00001-of-00002.safetensors"
        os.symlink(target, self.checkpoint / "model-00003-of-00003.safetensors")
        with self.assertRaises(extractor.ExtractionError):
            extractor.extract(str(self.checkpoint), str(self.output))
        with self.assertRaises(extractor.ExtractionError):
            extractor.extract_shard_header(str(self.checkpoint / "model-00003-of-00003.safetensors"))

    def test_an_existing_output_directory_is_refused(self):
        build_synthetic_checkpoint(self.checkpoint)
        self.output.mkdir()
        with self.assertRaises(extractor.ExtractionError):
            extractor.extract(str(self.checkpoint), str(self.output))

    def test_subdirectories_are_named_not_read(self):
        summary = self._extract()
        listing = json.loads((self.output / "listing.json").read_text())
        cache = [e for e in listing["entries"] if e["name"] == "__pycache__"][0]
        self.assertEqual(cache["children"], [
            {"name": "stray.cpython-314.pyc", "size": len(PYC_SENTINEL), "type": "file"}])
        self.assertEqual(summary["small_json"]["download-record.json"], {"present": False})

    def test_the_extractor_imports_only_the_standard_library(self):
        tree = ast.parse(MODULE_PATH.read_text())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add((node.module or "").split(".")[0])
        self.assertEqual(imported, {"__future__", "argparse", "hashlib", "json", "os", "stat", "sys"})
        # Reads go through os.pread only: no open() of a shard in text or
        # binary mode, no mmap, no seek other than the final position check.
        source = MODULE_PATH.read_text()
        self.assertNotIn("mmap", source)
        self.assertNotIn("os.read(", source)
        self.assertEqual(source.count("os.lseek("), 1)
        self.assertIn("os.lseek(fd, 0, os.SEEK_CUR)", source)


def write_fixture() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        checkpoint = Path(temporary) / "checkpoint"
        output = Path(temporary) / "out"
        build_synthetic_checkpoint(checkpoint)
        extractor.extract(str(checkpoint), str(output))
        if FIXTURE.exists():
            shutil.rmtree(FIXTURE)
        shutil.copytree(output, FIXTURE)
    print(f"wrote {FIXTURE.relative_to(REPOSITORY_ROOT)}")


if __name__ == "__main__":
    if sys.argv[1:] == ["--write-fixture"]:
        write_fixture()
    else:
        unittest.main()
