"""Generated two-layer fixture; no pinned manifest or model payload is read."""
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

from qwen38_page_catalog import BoundCheckpoint, PageCatalog, TensorRef, _BOUND_TOKEN, _verified_shard
from qwen38_verified_files import VerifiedFiles
from qwen38_fixture_io import MARKER, MARKER_CONTENT


class Clock:
    def __init__(self):
        self.value = 1000

    def __call__(self):
        self.value += 10
        return self.value


class Samples:
    """Exogenous observation values: never reads a ledger or scheduler counter."""
    def __init__(self, clock):
        self.clock = clock
        self.sequence = 0
        self.overrides = {}
        self.failure = None

    def __call__(self):
        from qwen38_adapter_memory import FreshObservation, GIB
        if self.failure:
            raise self.failure
        self.sequence += 1
        values = dict(sequence=self.sequence, sampled_at_ns=self.clock.value,
                      process_bytes=0, mlx_live_bytes=0, mlx_cache_bytes=0,
                      runtime_bytes=0, headroom_bytes=20 * GIB, swap_bytes=0,
                      pressure=False, units="bytes", process_source="fixture-process",
                      mlx_source="fixture-mlx", system_source="fixture-system")
        values.update(self.overrides)
        return FreshObservation(**values)


def make_bound(root: Path):
    """Parse authenticated tiny headers, then bind the actual retained handles.

    The private constructor token is used only here for a two-layer fixture;
    this does not exercise or replace the production pinned-revision admission.
    """
    headers = {"a.safetensors": {}, "b.safetensors": {}}
    payloads = {name: bytearray() for name in headers}

    def tensor(name, dtype, shape, length, filename):
        data = payloads[filename]
        start = len(data)
        data.extend((i + start + len(name)) % 251 for i in range(length))
        headers[filename][name] = dict(dtype=dtype, shape=shape, data_offsets=[start, len(data)])

    def triple(prefix, rows):
        for suffix, dtype, width in (("weight", "U32", 4), ("scales", "BF16", 2), ("biases", "BF16", 2)):
            tensor(prefix + "." + suffix, dtype, [rows, 1], rows * width,
                   "a.safetensors" if suffix == "weight" else "b.safetensors")

    for layer in range(2):
        for projection in ("gate_proj", "up_proj", "down_proj"):
            triple(f"language_model.model.layers.{layer}.mlp.switch_mlp.{projection}", 3)
    for shard in range(2):
        triple(f"language_model.model.layers.1.ple.ple_embedding.ngram_embedding.shard_{shard}", 5)
    tensor("language_model.model.norm.weight", "BF16", [2], 4, "b.safetensors")
    contents = {MARKER: MARKER_CONTENT.encode()}
    for filename, header in headers.items():
        raw = json.dumps(header).encode()
        contents[filename] = len(raw).to_bytes(8, "little") + raw + payloads[filename]
    entries = []
    for name, raw in contents.items():
        (root / name).write_bytes(raw)
        entries.append(dict(path=name, size_bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest()))
    with patch("qwen38_verified_files.CHUNK_BYTES", 64):
        files = VerifiedFiles(root, entries)
    try:
        tensors = {}
        for filename, names in headers.items():
            header, start = _verified_shard(files, filename, set(names))
            for name, item in header.items():
                tensors[name] = TensorRef(filename, start, item["dtype"], tuple(item["shape"]), *item["data_offsets"])
        catalog = PageCatalog(tensors, layers=2, experts=3, ple_layer=1, ple_shards=2, ple_rows_per_page=2)
        catalog._verified_files = files
        return BoundCheckpoint(catalog, files, _BOUND_TOKEN), contents
    except BaseException:
        files.close()
        raise
