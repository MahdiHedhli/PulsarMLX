"""Tiny synthetic file identity and digest tests; no checkpoint payload."""

import hashlib
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from admit_qwen38_static import write_admission_result  # noqa: E402
from qwen38_page_catalog import (  # noqa: E402
    BoundCheckpoint, CatalogError, _BOUND_TOKEN, _admit_checkpoint_bound_from_manifest,
    admit_checkpoint, admit_checkpoint_bound,
    _verified_shard,
)
from qwen38_verified_files import VerifiedFiles, VerificationError  # noqa: E402
from test_qwen38_bounded_pager import E0, synthetic_catalog  # noqa: E402


def entry(name, content, *, blob=False):
    result = {"path": name, "size_bytes": len(content)}
    if blob:
        result["git_blob_sha1"] = hashlib.sha1(
            f"blob {len(content)}\0".encode() + content).hexdigest()
    else:
        result["sha256"] = hashlib.sha256(content).hexdigest()
    return result


class VerifiedFileTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="qwen38-verified-synthetic-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.content = bytes(range(96))
        (self.root / "tiny.bin").write_bytes(self.content)
        self.entries = [entry("tiny.bin", self.content)]

    def test_sha256_and_git_blob_files_bind_exact_bytes(self):
        import qwen38_verified_files as module
        other = b"manifest metadata"
        (self.root / "metadata.txt").write_bytes(other)
        with mock.patch.object(module, "CHUNK_BYTES", 16):
            with VerifiedFiles(self.root, self.entries + [entry("metadata.txt", other, blob=True)]) as files:
                target = bytearray(27)
                files.readinto("tiny.bin", memoryview(target), 11)
                self.assertEqual(target, self.content[11:38])
                self.assertEqual(files.read_metadata("metadata.txt"), other)
            # Restore a live set after the module default changes again.
            live = VerifiedFiles(self.root, self.entries)
        try:
            target = bytearray(27)
            live.readinto("tiny.bin", memoryview(target), 11)
            self.assertEqual(target, self.content[11:38])
        finally:
            live.close()
        with self.assertRaisesRegex(VerificationError, "closed"):
            files.readinto("tiny.bin", memoryview(bytearray(1)), 0)

    def test_changed_content_same_size_fails_closed(self):
        with VerifiedFiles(self.root, self.entries) as files:
            (self.root / "tiny.bin").write_bytes(bytes(reversed(self.content)))
            with self.assertRaisesRegex(VerificationError, "identity changed"):
                files.readinto("tiny.bin", memoryview(bytearray(8)), 0)
            self.assertTrue(files.poisoned)
            with self.assertRaisesRegex(VerificationError, "closed or failed"):
                files.read_metadata("tiny.bin")

    def test_replacement_and_symlink_are_rejected(self):
        with VerifiedFiles(self.root, self.entries) as files:
            replacement = self.root / "replacement.bin"
            replacement.write_bytes(self.content)
            replacement.replace(self.root / "tiny.bin")
            with self.assertRaisesRegex(VerificationError, "identity changed"):
                files.readinto("tiny.bin", memoryview(bytearray(1)), 0)
        (self.root / "tiny.bin").unlink()
        (self.root / "target.bin").write_bytes(self.content)
        (self.root / "tiny.bin").symlink_to(self.root / "target.bin")
        with self.assertRaises(OSError):
            VerifiedFiles(self.root, self.entries)
        linked_root = self.root.parent / (self.root.name + "-link")
        linked_root.symlink_to(self.root)
        self.addCleanup(linked_root.unlink)
        with self.assertRaisesRegex(VerificationError, "symlinked root"):
            VerifiedFiles(linked_root, self.entries)

    def test_identity_change_after_admission_rejects_even_same_content(self):
        with VerifiedFiles(self.root, self.entries) as files:
            path = self.root / "tiny.bin"
            before = stat.S_IMODE(path.stat().st_mode)
            path.chmod(before ^ stat.S_IXUSR)
            with self.assertRaisesRegex(VerificationError, "identity changed"):
                files.check("tiny.bin")

    def test_chunk_digest_detects_content_when_metadata_check_is_stubbed(self):
        import qwen38_verified_files as module
        with VerifiedFiles(self.root, self.entries) as files:
            (self.root / "tiny.bin").write_bytes(bytes(reversed(self.content)))
            original_root = files.root_identity
            original_file = files.files["tiny.bin"].identity
            def old_identity(info):
                return original_root if os.path.isdir(self.root) and info.st_ino == os.stat(self.root).st_ino else original_file
            with mock.patch.object(module, "_identity", side_effect=old_identity):
                with self.assertRaisesRegex(VerificationError, "verified chunk changed"):
                    files.readinto("tiny.bin", memoryview(bytearray(8)), 0)

    def test_digest_failure_closes_all_open_descriptors(self):
        second = b"wrong"
        (self.root / "second.bin").write_bytes(second)
        entries = self.entries + [entry("second.bin", b"right")]
        real_open, real_close = os.open, os.close
        opened, closed = [], []
        def track_open(*args, **kwargs):
            fd = real_open(*args, **kwargs)
            opened.append(fd)
            return fd
        def track_close(fd):
            closed.append(fd)
            return real_close(fd)
        with mock.patch("qwen38_verified_files.os.open", side_effect=track_open), \
             mock.patch("qwen38_verified_files.os.close", side_effect=track_close):
            with self.assertRaisesRegex(VerificationError, "pinned digest mismatch"):
                VerifiedFiles(self.root, entries)
        self.assertEqual(set(opened), set(closed))
        for fd in opened:
            with self.assertRaises(OSError):
                os.fstat(fd)

    def test_unsafe_manifest_entries_fail_before_open(self):
        for entries in ([entry("../escape", b"x")],
                        [entry("tiny.bin", self.content)] * 2,
                        [{"path": "tiny.bin", "size_bytes": len(self.content),
                          "sha256": "0" * 64, "git_blob_sha1": "0" * 40}],
                        [{"path": "tiny.bin", "size_bytes": len(self.content),
                          "sha256": None, "git_blob_sha1": "0" * 40}]):
            with self.subTest(entries=entries), \
                 self.assertRaises(VerificationError):
                VerifiedFiles(self.root, entries)

    def test_manifest_entry_is_copied_and_revision_checked(self):
        entries = [entry("tiny.bin", self.content)]
        with VerifiedFiles(self.root, entries) as files:
            original = files.entries["tiny.bin"]["sha256"]
            entries[0]["sha256"] = "0" * 64
            self.assertEqual(files.entries["tiny.bin"]["sha256"], original)
            with self.assertRaises(TypeError):
                files.entries["tiny.bin"]["sha256"] = "0" * 64
            manifest_path = self.root.parent / (self.root.name + "-manifest.json")
            self.addCleanup(manifest_path.unlink)
            manifest_path.write_text(json.dumps({
                "schema": "pulsarmlx.qwen38.pinned-checkpoint/1",
                "repo": "pipenetwork/Qwen3.8-Flash-Next-MLX-mixed-4_8bit",
                "revision": "wrong", "files": [entry("tiny.bin", self.content)]}))
            with self.assertRaisesRegex(CatalogError, "verified files do not match"):
                admit_checkpoint(self.root, manifest_path=manifest_path, verified_files=files)

    def test_close_attempts_all_descriptors_after_one_close_error(self):
        other = b"other"
        (self.root / "other.bin").write_bytes(other)
        files = VerifiedFiles(self.root, self.entries + [entry("other.bin", other)])
        descriptors = [file.fd for file in files.files.values()] + [files.root_fd]
        real_close = os.close
        first = True
        def close_and_fail_once(fd):
            nonlocal first
            real_close(fd)
            if first:
                first = False
                raise OSError("simulated close error")
        with mock.patch("qwen38_verified_files.os.close", side_effect=close_and_fail_once):
            with self.assertRaisesRegex(OSError, "simulated close error"):
                files.close()
        self.assertTrue(files.closed)
        for fd in descriptors:
            with self.assertRaises(OSError):
                os.fstat(fd)

    def test_static_report_does_not_follow_preexisting_temp_symlink(self):
        victim = self.root / "victim.txt"
        victim.write_text("keep me")
        (self.root / "static-admission.json.tmp").symlink_to(victim)
        output = self.root / "static-admission.json"
        write_admission_result(output, {"synthetic": True})
        self.assertEqual(victim.read_text(), "keep me")
        self.assertEqual(json.loads(output.read_text()), {"synthetic": True})
        output.unlink()
        output.symlink_to(victim)
        write_admission_result(output, {"synthetic": False})
        self.assertEqual(victim.read_text(), "keep me")
        self.assertFalse(output.is_symlink())

    def test_bound_page_uses_only_verified_spans(self):
        catalog = synthetic_catalog()
        spec = catalog.page(E0)
        size = max(span.offset + span.length for span in spec.spans)
        content = bytes((index % 251 for index in range(size)))
        (self.root / "synthetic.safetensors").write_bytes(content)
        with VerifiedFiles(self.root, self.entries + [entry("synthetic.safetensors", content)]) as files:
            with self.assertRaisesRegex(CatalogError, "not parsed"):
                BoundCheckpoint(catalog, files)
            # White-box synthetic binding exercises the read path without
            # constructing the pinned 48-layer checkpoint catalog.
            catalog._verified_files = files
            bound = BoundCheckpoint(catalog, files, _BOUND_TOKEN)
            target = bytearray(spec.size_bytes)
            bound.read_page_into(E0, memoryview(target))
            expected = b"".join(content[s.offset:s.offset + s.length] for s in spec.spans)
            self.assertEqual(target, expected)

    def test_bound_admission_failure_closes_verified_handles(self):
        files = VerifiedFiles(self.root, self.entries)
        with mock.patch("qwen38_page_catalog.open_pinned_files", return_value=files), \
             mock.patch("qwen38_page_catalog.admit_checkpoint", side_effect=CatalogError("bad header")):
            with self.assertRaisesRegex(CatalogError, "bad header"):
                admit_checkpoint_bound(self.root)
        self.assertTrue(files.closed)

    def test_complete_bound_admission_on_tiny_synthetic_checkpoint(self):
        tensors = {}
        names = {}
        cursor = 0
        def affine(prefix, rows):
            nonlocal cursor
            for suffix, dtype, row_bytes in (("weight", "U32", 4),
                                             ("scales", "BF16", 2),
                                             ("biases", "BF16", 2)):
                name = f"{prefix}.{suffix}"
                length = rows * row_bytes
                tensors[name] = {"dtype": dtype, "shape": [rows, 1],
                                 "data_offsets": [cursor, cursor + length]}
                names[name] = "model-00001.safetensors"
                cursor += length
        for layer in range(48):
            for projection in ("gate_proj", "up_proj", "down_proj"):
                affine(f"language_model.model.layers.{layer}.mlp.switch_mlp.{projection}", 512)
        for shard in range(128):
            affine(f"language_model.model.layers.1.ple.ple_embedding.ngram_embedding.shard_{shard}", 1)
        header = json.dumps(tensors).encode()
        shard_bytes = len(header).to_bytes(8, "little") + header + bytes(cursor)
        config = {"model_type": "qwen4_exp", "model_file": "qwen4_exp.py",
                  "text_config": {"num_hidden_layers": 48, "num_experts": 512,
                                  "num_experts_per_tok": 10, "split_ngram_parts": 128},
                  "quantization": {"bits": 4, "group_size": 64}}
        config["quantization"].update({f"eight_{i}": {"bits": 8, "group_size": 64}
                                       for i in range(498)})
        config["quantization"].update({f"four_{i}": {"bits": 4, "group_size": 32}
                                       for i in range(128)})
        contents = {"model-00001.safetensors": shard_bytes,
                    "config.json": json.dumps(config).encode(),
                    "model.safetensors.index.json": json.dumps({"weight_map": names}).encode()}
        for name, data in contents.items():
            (self.root / name).write_bytes(data)
        entries = [entry(name, data) for name, data in contents.items()]
        manifest = {"schema": "pulsarmlx.qwen38.pinned-checkpoint/1",
                    "repo": "pipenetwork/Qwen3.8-Flash-Next-MLX-mixed-4_8bit",
                    "revision": "b2c422f3c643e36f04227a64d61796b44a4b1029",
                    "total_size_bytes": sum(len(data) for data in contents.values()),
                    "files": entries}
        manifest_path = self.root.parent / (self.root.name + "-manifest.json")
        self.addCleanup(manifest_path.unlink)
        manifest_path.write_text(json.dumps(manifest))
        with _admit_checkpoint_bound_from_manifest(self.root, manifest_path=manifest_path) as bound:
            spec = bound.catalog.page(E0)
            self.assertEqual(spec.size_bytes, 24)
            target = bytearray(spec.size_bytes)
            bound.read_page_into(E0, memoryview(target))
            self.assertEqual(target, bytes(24))
            self.assertIs(bound.catalog._verified_files, bound.files)
        self.assertTrue(bound.files.closed)

    def test_verified_header_parser_rejects_replacement(self):
        header = {"x": {"dtype": "U8", "shape": [4], "data_offsets": [0, 4]}}
        body = json.dumps(header).encode()
        content = len(body).to_bytes(8, "little") + body + b"abcd"
        (self.root / "a.safetensors").write_bytes(content)
        with VerifiedFiles(self.root, self.entries + [entry("a.safetensors", content)]) as files:
            parsed, start = _verified_shard(files, "a.safetensors", {"x"})
            self.assertEqual((parsed["x"]["dtype"], start), ("U8", 8 + len(body)))
            (self.root / "a.safetensors").write_bytes(content[:-4] + b"wxyz")
            with self.assertRaises(VerificationError):
                _verified_shard(files, "a.safetensors", {"x"})


if __name__ == "__main__":
    unittest.main()
