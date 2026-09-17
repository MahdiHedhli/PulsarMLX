"""PulsarSlotStore + PulsarSwitchGLU: the paged-expert path without the per-expert loop (graph 24, ladder rung 2).

Upstream's OffloadedSwitchGLU host-syncs the routing, then per selected expert issues three quantized_matmul launches
and a full-array scatter (~40 launches and 8 output copies per layer per token: 4-5 ms/layer even when every expert
is resident, against ~1 ms for the resident SwitchGLU's three gather_qmm launches); misses are lazy one-at-a-time
mmap loads; prefill bulk-loads every layer's whole expert file per chunk. Here every MoE layer owns C SLOTS - stacked
gate/up/down (weight, scales, biases) tensors of shape (C, ...) - an int32 expert_to_slot map (-1 = absent), and the
graph-21 LFU-with-decay policy over the slots (per-layer capacity C = budget / layers / bytes per expert):

  * a call touches the sorted unique experts of its tokens; all of them must be resident at once for the gather,
    so a call is processed in WAVES of at most C experts, the wave's experts pinned against eviction;
  * within a wave each expert is counted once; a hit keeps its slot; a miss takes a free slot, else the slot of the
    resident with the smallest (count, touch) outside the wave; the read is a materialized mmap slice written into
    the slot in place (`W[slot] = w`, the KV-cache pattern; batched into one scatter per projection per wave);
  * the forward is three mx.gather_qmm launches over the slot tensors with SwitchGLU's own sort/unsort and the
    caller's activation(x_up, x_gate); output [..., K, D] exactly like SwitchGLU; a wave's contribution is masked
    and accumulated when a call needs several waves;
  * prefill takes the same path (no bulk bypass): a chunk pays reads for its misses only;
  * warm state (<offload>/pulsar-slot-warm-state.json: counts, resident set, accesses) re-admits most-frequent
    first per layer into slots 0.., materialized at construction;
  * the allocator cache is not cleared per eviction (graph 22): a slot write reuses the slot's own buffer;
  * reads do not go through mx.load per miss: parsing a layer file's 2,592-tensor header costs 4-5 ms (measured on the
    Studio: ~190 ms per token across 42 layers), so each layer's header is parsed once and misses are read by byte
    range. Measured on the Studio's internal SSD per 14.2 MB expert: a page-cache-resident range copies from a memmap
    at ~40 GB/s but faults in from disk at <1 GB/s (synchronous 16 KB faults, 2.3 GB/s with 16 threads), while
    preadv into a buffer reaches 6.3 GB/s cold with 8 threads (7 GB/s hot), and for a large cold batch mx.load's own
    lazy loads evaluated together are fastest (93 cold experts: 233 ms = 5.7 GB/s, vs 676 ms through the pool) but
    cost a 4-5 ms header parse per call. So each miss's range is checked with mincore: resident -> memmap copy on
    the calling thread; otherwise, fewer than `bulk_min` cold experts -> preadv in a small thread pool (decode:
    ~1 miss per layer), else -> one mx.load whose entries are popped as they are consumed (nothing retained). The
    arrays are stacked and scattered into the slots in one go per (projection, part).

Quantized experts only (weight/scales/biases per projection, as repack writes them for a quantized build).
"""
from __future__ import annotations

import glob
import json
import os
from typing import Optional

import numpy as np

_PROJS = ("gate_proj", "up_proj", "down_proj")
_PARTS = ("weight", "scales", "biases")
WARM_STATE = "pulsar-slot-warm-state.json"


_SAFETENSORS_DTYPES = {"U32": ("uint32", "uint32"), "U8": ("uint8", "uint8"), "F32": ("float32", "float32"), "F16": ("float16", "float16"),
                       "BF16": ("uint16", "bfloat16")}   # safetensors dtype -> (numpy read dtype, mlx dtype; bf16 is read as u16 and viewed)


_PAGE = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 16384
_libc = None


def _mincore_resident(mm, offset: int, length: int) -> bool:
    """True when every page of mm[offset:offset+length] is in the page cache (macOS/BSD mincore); False on any doubt."""
    global _libc
    try:
        import ctypes
        if _libc is None:
            _libc = ctypes.CDLL(None)
            _libc.mincore.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_char_p]
            _libc.mincore.restype = ctypes.c_int
        base = mm.ctypes.data
        start = (base + offset) // _PAGE * _PAGE
        end = base + offset + length
        n = (end - start + _PAGE - 1) // _PAGE
        vec = ctypes.create_string_buffer(n)
        if _libc.mincore(ctypes.c_void_p(start), ctypes.c_size_t(end - start), vec) != 0:
            return False
        return all(b & 1 for b in vec.raw)
    except Exception:
        return False


class _LayerFile:
    """One repack layer file: header parsed once (name -> dtype, shape, byte range); data read by byte range, from the
    memmap when the range is page-cache resident, else with preadv into a buffer (thread-pool friendly)."""
    __slots__ = ("path", "entries", "data_start", "mmap", "fd")

    def __init__(self, path):
        import struct
        self.path = path
        with open(path, "rb") as fh:
            n = struct.unpack("<Q", fh.read(8))[0]
            header = json.loads(fh.read(n))
        self.data_start = 8 + n
        self.entries = {k: v for k, v in header.items() if k != "__metadata__"}
        self.mmap = None
        self.fd = None

    def _open(self):
        if self.mmap is None:
            self.mmap = np.memmap(self.path, dtype=np.uint8, mode="r")
            self.fd = os.open(self.path, os.O_RDONLY)

    def resident(self, name) -> bool:
        self._open()
        a, b = self.entries[name]["data_offsets"]
        return _mincore_resident(self.mmap, self.data_start + a, b - a)

    def read_hot(self, name):
        """memmap copy (call only when resident): one copy page cache -> MLX buffer."""
        import mlx.core as mx

        e = self.entries[name]; np_dtype, mx_dtype = _SAFETENSORS_DTYPES[e["dtype"]]
        a, b = e["data_offsets"]
        view = np.frombuffer(self.mmap[self.data_start + a:self.data_start + b], dtype=np_dtype).reshape(e["shape"])
        arr = mx.array(view)
        return arr.view(getattr(mx, mx_dtype)) if mx_dtype != np_dtype else arr

    def read_cold_np(self, name):
        """preadv into a numpy buffer (releases the GIL; safe from a thread); the caller converts."""
        e = self.entries[name]; np_dtype, _ = _SAFETENSORS_DTYPES[e["dtype"]]
        a, b = e["data_offsets"]
        buf = np.empty(b - a, dtype=np.uint8)
        got = os.preadv(self.fd, [memoryview(buf)], self.data_start + a)
        if got != b - a:
            raise IOError(f"SHORT_READ {name}: {got} of {b - a}")
        return np.frombuffer(buf, dtype=np_dtype).reshape(e["shape"])

    def to_mx(self, name, np_arr):
        import mlx.core as mx

        _, mx_dtype = _SAFETENSORS_DTYPES[self.entries[name]["dtype"]]
        arr = mx.array(np_arr)
        return arr.view(getattr(mx, mx_dtype)) if str(np_arr.dtype) != mx_dtype else arr


class _LayerSlots:
    __slots__ = ("tensors", "expert_to_slot", "slot_of", "free", "map_array", "file")

    def __init__(self, capacity, num_experts):
        self.tensors = None                 # {proj: [W, S, B]} stacked (C, ...)
        self.expert_to_slot = np.full((num_experts,), -1, dtype=np.int32)
        self.slot_of = {}                   # expert -> slot
        self.free = list(range(capacity))
        self.map_array = None               # mx.array mirror of expert_to_slot (rebuilt when it changes)
        self.file = None                    # _LayerFile, opened on first use


class PulsarSlotStore:
    policy = "lfu-decay-slots"

    def __init__(self, offload_dir: str, expert_cache_bytes: int, kv_reserve_bytes: int = 0, decay: float = 0.5,
                 decay_every: int = 4096, warm_start: bool = True, capacity_per_layer: Optional[int] = None, read_workers: int = 8,
                 bulk_min: int = 4):
        import mlx.core as mx
        from concurrent.futures import ThreadPoolExecutor

        idx = json.load(open(os.path.join(offload_dir, "offload_index.json")))
        self.offload_dir = offload_dir
        self.num_experts = int(idx["num_experts"])
        self._paths = {}
        for path in glob.glob(os.path.join(offload_dir, "experts", "layer_*.safetensors")):
            self._paths[int(os.path.basename(path).split("_")[1].split(".")[0])] = path
        if not self._paths:
            raise ValueError("NO_EXPERT_FILES")
        self._budget = int(expert_cache_bytes)
        self.decay, self.decay_every = float(decay), int(decay_every)
        first = _LayerFile(self._paths[min(self._paths)]).entries
        if "e0.gate_proj.scales" not in first:
            raise ValueError("UNQUANTIZED_EXPERTS_UNSUPPORTED")
        self.expert_bytes = sum(first[f"e0.{p}.{k}"]["data_offsets"][1] - first[f"e0.{p}.{k}"]["data_offsets"][0] for p in _PROJS for k in _PARTS if f"e0.{p}.{k}" in first)
        self.capacity = int(capacity_per_layer) if capacity_per_layer else max(1, self._budget // (len(self._paths) * self.expert_bytes))
        self._layers = {lid: _LayerSlots(self.capacity, self.num_experts) for lid in self._paths}
        self._counts: dict = {}     # (layer, expert) -> decayed frequency
        self._touch: dict = {}      # (layer, expert) -> last access ordinal
        self._accesses = 0
        self._hits = self._misses = self._evictions = 0
        self._read_bytes = 0
        self._hot_reads = self._cold_reads = self._bulk_reads = 0
        self.bulk_min = int(bulk_min)
        self._pool = ThreadPoolExecutor(max_workers=max(1, int(read_workers)))
        self._warm_admitted = 0
        if warm_start:
            self._warm_admitted = self._admit_warm_state()

    # --- interface ------------------------------------------------------------------------------
    def experts_present(self, layer_id: int) -> bool:
        return layer_id in self._paths

    def _file(self, lid: int) -> _LayerFile:
        L = self._layers[lid]
        if L.file is None:
            L.file = _LayerFile(self._paths[lid])
        return L.file

    def _ensure_tensors(self, lid: int) -> None:
        import mlx.core as mx

        L = self._layers[lid]
        if L.tensors is not None:
            return
        f = self._file(lid)
        L.tensors = {}
        for p in _PROJS:
            parts = []
            for k in _PARTS:
                e = f.entries[f"e0.{p}.{k}"]
                parts.append(mx.zeros((self.capacity,) + tuple(e["shape"]), dtype=getattr(mx, _SAFETENSORS_DTYPES[e["dtype"]][1])))
            L.tensors[p] = parts
        mx.eval([t for parts in L.tensors.values() for t in parts])

    def _count(self, key) -> None:
        self._accesses += 1
        self._counts[key] = self._counts.get(key, 0.0) + 1.0
        self._touch[key] = self._accesses
        if self._accesses % self.decay_every == 0:
            for k in list(self._counts):
                self._counts[k] *= self.decay

    def _priority(self, key):
        return (self._counts.get(key, 0.0), self._touch.get(key, 0))

    def touch_wave(self, lid: int, wave) -> list:
        """Policy for one wave (sorted unique experts, len <= capacity): counts, hits/misses, slot assignment with the
        wave pinned. Returns the reads to perform as [(expert, slot)] in wave order; the caller materializes them."""
        L = self._layers[lid]
        pinned = set(wave)
        reads = []
        for j in wave:
            self._count((lid, j))
            if j in L.slot_of:
                self._hits += 1
                continue
            self._misses += 1
            if L.free:
                s = L.free.pop(0)
            else:
                candidates = [k for k in L.slot_of if k not in pinned]
                victim = min(candidates, key=lambda k: self._priority((lid, k)))
                s = L.slot_of.pop(victim); L.expert_to_slot[victim] = -1
                self._evictions += 1
            L.slot_of[j] = s; L.expert_to_slot[j] = s
            reads.append((j, s))
        if reads:
            L.map_array = None
        return reads

    def fill(self, lid: int, reads) -> None:
        """Materialize the missed experts and write them into their slots: one scatter per (projection, part)."""
        import mlx.core as mx

        if not reads:
            return
        self._ensure_tensors(lid)
        L = self._layers[lid]; f = self._file(lid)
        slots = mx.array([s for _, s in reads], dtype=mx.int32)
        names = [(j, f"e{j}.{p}.{k}") for j, _ in reads for p in _PROJS for k in _PARTS]
        # the weight range decides hot/cold per expert (scales/biases are small and sit next to it in the file)
        hot = {j: f.resident(f"e{j}.gate_proj.weight") for j, _ in reads}
        cold_names = [n for j, n in names if not hot[j]]
        n_cold = sum(1 for v in hot.values() if not v)
        arrays = {}
        if n_cold >= self.bulk_min:
            lazy = mx.load(self._paths[lid])          # one header parse; MLX evaluates the loads together (parallel I/O)
            for n in cold_names:
                arrays[n] = lazy.pop(n)
            del lazy
            self._bulk_reads += n_cold
        elif cold_names:
            cold = dict(zip(cold_names, self._pool.map(f.read_cold_np, cold_names)))
            for n in cold_names:
                arrays[n] = f.to_mx(n, cold[n])
        for j, n in names:
            if n not in arrays:
                arrays[n] = f.read_hot(n)
        for p in _PROJS:
            for ki, k in enumerate(_PARTS):
                group = [arrays[f"e{j}.{p}.{k}"] for j, _ in reads]
                stacked = mx.stack(group) if len(reads) > 1 else group[0][None]
                L.tensors[p][ki][slots] = stacked                 # in place (scatter into the uniquely referenced slot tensor)
        mx.eval([t for parts in L.tensors.values() for t in parts])
        self._read_bytes += len(reads) * self.expert_bytes
        self._hot_reads += sum(1 for v in hot.values() if v); self._cold_reads += sum(1 for v in hot.values() if not v)

    def map_array(self, lid: int):
        import mlx.core as mx

        L = self._layers[lid]
        if L.map_array is None:
            L.map_array = mx.array(L.expert_to_slot)
        return L.map_array

    def tensors(self, lid: int):
        self._ensure_tensors(lid)
        return self._layers[lid].tensors

    def slot_of(self, lid: int) -> dict:
        return dict(self._layers[lid].slot_of)

    def stats(self) -> dict:
        total = self._hits + self._misses
        resident = sum(len(L.slot_of) for L in self._layers.values())
        return {"policy": self.policy, "budget_bytes": self._budget, "capacity_per_layer": self.capacity, "expert_bytes": self.expert_bytes,
                "resident_experts": resident, "resident_bytes": resident * self.expert_bytes, "num_experts": self.num_experts,
                "num_layers": len(self._paths), "hits": self._hits, "misses": self._misses, "evictions": self._evictions,
                "hit_rate": (self._hits / total) if total else None, "read_bytes": self._read_bytes, "hot_reads": self._hot_reads, "cold_reads": self._cold_reads, "bulk_reads": self._bulk_reads, "warm_admitted": self._warm_admitted,
                "decay": self.decay, "decay_every": self.decay_every, "accesses": self._accesses}

    # --- warm state -----------------------------------------------------------------------------
    def save_warm_state(self) -> str:
        path = os.path.join(self.offload_dir, WARM_STATE)
        json.dump({"policy": self.policy, "counts": [[l, j, c] for (l, j), c in self._counts.items()],
                   "resident": [[l, j] for l, L in self._layers.items() for j in L.slot_of], "accesses": self._accesses}, open(path, "w"))
        return path

    def _admit_warm_state(self) -> int:
        path = os.path.join(self.offload_dir, WARM_STATE)
        if not os.path.exists(path):
            return 0
        state = json.load(open(path))
        self._counts = {(int(l), int(j)): float(c) for l, j, c in state["counts"]}
        self._accesses = int(state.get("accesses", 0))
        per_layer: dict = {}
        for l, j in state["resident"]:
            per_layer.setdefault(int(l), []).append(int(j))
        admitted = 0
        for lid, experts in per_layer.items():
            if lid not in self._layers:
                continue
            L = self._layers[lid]
            order = sorted(experts, key=lambda j: -self._counts.get((lid, j), 0.0))[:self.capacity]
            reads = []
            for j in order:
                s = L.free.pop(0); L.slot_of[j] = s; L.expert_to_slot[j] = s; reads.append((j, s))
            L.map_array = None
            self.fill(lid, reads)
            admitted += len(reads)
        return admitted


class PulsarSwitchGLU:
    """Drop-in for SwitchGLU / OffloadedSwitchGLU: (x [..., D], indices [..., K]) -> [..., K, D]."""

    def __init__(self, store: PulsarSlotStore, layer_id: int, gate_quant, up_quant, down_quant, activation=None):
        self.store, self.layer_id = store, int(layer_id)
        self.gate_quant, self.up_quant, self.down_quant = tuple(gate_quant), tuple(up_quant), tuple(down_quant)
        self.activation = activation
        self.training = False

    def _gather(self, x, proj, quant, slots, sorted_indices):
        import mlx.core as mx

        W, S, B = self.store.tensors(self.layer_id)[proj]
        group_size, bits, mode = quant
        return mx.gather_qmm(x, W, S, B, rhs_indices=slots, transpose=True, group_size=group_size, bits=bits, mode=mode, sorted_indices=sorted_indices)

    def _experts(self, x, slots):
        """SwitchGLU's forward over slot indices, with its sort/unsort (mlx_vlm.models.switch_layers._gather_sort /
        _scatter_unsort, inlined so the module has no mlx-vlm import: sort the flattened (token, k) pairs by slot,
        gather the matching rows, run the three grouped matmuls with sorted_indices, and undo the permutation)."""
        import mlx.core as mx

        x = mx.expand_dims(x, (-2, -3))
        do_sort = slots.size >= 64
        idx, inv_order = slots, None
        if do_sort:
            M = slots.shape[-1]
            flat = slots.flatten()
            order = mx.argsort(flat)
            inv_order = mx.argsort(order)
            x, idx = x.flatten(0, -3)[order // M], flat[order]
        x_up = self._gather(x, "up_proj", self.up_quant, idx, do_sort)
        x_gate = self._gather(x, "gate_proj", self.gate_quant, idx, do_sort)
        h = self.activation(x_up, x_gate) if self.activation is not None else (mx.sigmoid(x_gate) * x_gate * x_up)
        y = self._gather(h, "down_proj", self.down_quant, idx, do_sort)
        if do_sort:
            y = mx.unflatten(y[inv_order], 0, slots.shape)
        return y.squeeze(-2)

    def __call__(self, x, indices):
        import mlx.core as mx

        lid, store = self.layer_id, self.store
        idx_host = np.asarray(indices)                      # the one host read per layer (small)
        uniq = sorted(int(j) for j in np.unique(idx_host))
        C = store.capacity
        waves = [uniq[i:i + C] for i in range(0, len(uniq), C)]
        if len(waves) == 1:
            store.fill(lid, store.touch_wave(lid, waves[0]))
            slots = store.map_array(lid)[indices]
            return self._experts(x, slots)
        out = None
        for wave in waves:
            store.fill(lid, store.touch_wave(lid, wave))
            in_wave = mx.array(np.isin(idx_host, np.array(wave, dtype=idx_host.dtype)))
            slots = mx.where(in_wave, store.map_array(lid)[indices], mx.zeros_like(indices))
            y = self._experts(x, slots) * in_wave[..., None].astype(x.dtype)
            out = y if out is None else out + y
        return out


def patch_model_slots(model, offload_dir: str, expert_cache_gb=None, warm_start: bool = True, decay: float = 0.5, decay_every: int = 4096, read_workers: int = 8):
    """After mlx_vlm.moe_offload.patch_model has swapped every MoE layer's switch_mlp for an OffloadedSwitchGLU (which
    drops the resident expert parameters and computes the byte budget), replace each with a PulsarSwitchGLU over one
    shared PulsarSlotStore, reusing the upstream module's quant triples and activation."""
    from mlx_vlm.moe_offload import patch_model

    upstream = patch_model(model, offload_dir, expert_cache_gb=expert_cache_gb)
    store = PulsarSlotStore(offload_dir, upstream._budget, 0, decay=decay, decay_every=decay_every, warm_start=warm_start, read_workers=read_workers)
    patched = 0
    for layer in model.language_model.model.layers:
        switch = getattr(getattr(layer, "mlp", None), "switch_mlp", None)
        if switch is not None and type(switch).__name__ == "OffloadedSwitchGLU":
            layer.mlp.switch_mlp = PulsarSwitchGLU(store, switch.layer_id, switch.gate_quant, switch.up_quant, switch.down_quant, activation=switch.activation)
            patched += 1
    return store, patched
