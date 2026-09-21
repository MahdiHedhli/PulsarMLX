"""PulsarSlotStore + PulsarSwitchGLU: the paged-expert path without the per-expert loop (graph 24, ladder rung 2).

Upstream's OffloadedSwitchGLU host-syncs the routing, then per selected expert issues three quantized_matmul launches
and a full-array scatter (~40 launches and 8 output copies per layer per token: 4-5 ms/layer even when every expert
is resident, against ~1 ms for the resident SwitchGLU's three gather_qmm launches); misses are lazy one-at-a-time
mmap loads; prefill bulk-loads every layer's whole expert file per chunk. Here every MoE layer owns C SLOTS - stacked
gate/up/down (weight, scales, biases) tensors of shape (C, ...) - an int32 expert_to_slot map (-1 = absent), and the
graph-21 LFU-with-decay policy over the slots (per-layer capacity C = budget / layers / bytes per expert):

  * a call touches the sorted unique experts of its tokens (the one host read per layer); all of them must be
    resident at once for the gather, so a call is processed in WAVES of at most C experts, the wave's experts pinned
    against eviction; the slot indices are gathered on the host from the layer's expert -> slot map after the fill
    (graph 31: there is no device mirror of the map to refresh, and a -1 - an absent expert - is rejected before it
    can reach gather_qmm, where it would be an out-of-bounds read);
  * within a wave each expert is counted once; a hit keeps its slot; a miss takes a free slot, else the slot of the
    resident with the smallest (count, touch) outside the wave; the read is a materialized mmap slice written into
    the slot in place (`W[slot] = w`, the KV-cache pattern; batched into one scatter per projection per wave);
  * the forward is three mx.gather_qmm launches over the slot tensors with SwitchGLU's own sort/unsort and the
    caller's activation(x_up, x_gate); output [..., K, D] exactly like SwitchGLU; a wave's contribution is masked
    and accumulated when a call needs several waves;
  * prefill takes the same path (no bulk bypass): a chunk pays reads for its misses only;
  * warm state (<offload>/pulsar-slot-warm-state.json: counts, resident set, accesses) re-admits most-frequent
    first per layer into slots 0.., materialized at construction;
  * the allocator cache is not cleared per eviction (graph 22): a slot write reuses the slot's own buffer, but it IS
    cleared when MLX's cache memory exceeds `cache_clear_threshold_bytes` (default 2 GiB) after a fill: a long prefill
    through the store stacks tens of GB of freed temporaries otherwise (measured: a 331-token teacher-forced pass
    reached 117 GB wired on the Studio and wedged the host - graph 27 first contact);
  * reads do not go through mx.load per miss: parsing a layer file's 2,592-tensor header costs 4-5 ms (measured on the
    Studio: ~190 ms per token across 42 layers), so each layer's header is parsed once and misses are read by byte
    range. Measured on the Studio's internal SSD per 14.2 MB expert: a page-cache-resident range copies from a memmap
    at ~40 GB/s but faults in from disk at <1 GB/s (synchronous 16 KB faults, 2.3 GB/s with 16 threads), while
    preadv into a buffer reaches 6.3 GB/s cold with 8 threads (7 GB/s hot), and for a large cold batch mx.load's own
    lazy loads evaluated together are fastest (93 cold experts: 233 ms = 5.7 GB/s, vs 676 ms through the pool) but
    cost a 4-5 ms header parse per call. So each miss's range is checked with mincore: resident -> memmap copy on
    the calling thread; otherwise, fewer than `bulk_min` cold experts -> preadv (F_NOCACHE: the reads bypass the
    page cache, which on slow storage otherwise grows at the expense of the store's own slot tensors) in a small thread pool (decode:
    ~1 miss per layer), else -> one mx.load whose entries are popped as they are consumed (nothing retained). The
    arrays are stacked and scattered into the slots in one go per (projection, part).
  * graph 31: residency is COMMITTED only after materialization. touch_wave evicts the victim from the published map
    (its bytes are about to be overwritten) and records the new expert -> slot as a RESERVATION (L.pending); fill reads
    every part of every reserved expert, scatters, evals, and only then publishes the reservations into slot_of /
    expert_to_slot. A failure before the first write drops the reservations, puts the slots back
    at the front of the free list (a retry takes the same slots and misses again) and raises; a failure after the
    first write leaves the slot tensors in an unknown state, so the store is POISONED: every later call raises
    STORE_POISONED. A failed fill can never produce a false hit (the pre-graph-31 code published in touch_wave).
  * graph 29: with an expert-contiguous layout (repack_v2.py; offload_index.json layout='expert-contiguous/1', every
    expert one byte range in numeric order) a cold batch is read as MERGED RANGES: cold experts sorted, runs whose gap
    is at most `coalesce_gap_experts` experts merged into one preadv each (the gap is read and discarded at streaming
    rate), the merged ranges read through the thread pool, and each tensor sliced out of its buffer. The hash-ordered
    layout keeps the per-tensor paths.

  * graph 33: stats separate logical_admitted_bytes (misses x expert bytes; `read_bytes` is the same number and is NOT a
    physical I/O counter), requested_read_bytes (what the cold paths asked of the file, gaps included), overread_bytes
    (the gaps inside merged ranges) and hot_copy_bytes (page-cache copies), and count waves, sorted_gathers, pool_reads,
    bulk_reads, coalesced_ranges and chunks_read so a qualification can assert that a branch ran, not only that the
    values matched; read_chunk_bytes is a constructor argument (default 64 MiB).

  * item 1 (streaming prefill): with prefill_mode='stream' a call carrying more than one token does not go through the
    slots at all. Per wave the experts are read as merged ranges (the same F_NOCACHE page-aligned pool reads) into
    TRANSIENT stacked (len(wave), ...) tensors, the same three gather_qmm launches run over them with each (token, k)'s
    position INSIDE THE WAVE as rhs_indices (the plain gather kernel below SORTED_GATHER_MIN_EXPERTS - see that
    constant), the wave is evaluated and its transients dropped, and the allocator cache
    is cleared once per layer call. The slot map, the free list, the reservations and the hit/miss accounting are
    untouched; only the LFU counts advance (count_only), so decode's victim choice stays informed. Decode (1-token
    calls) is unchanged and takes the slots as before, and a stream prefill is bit-identical to a store prefill (the
    same bytes through the same kernels, same masking and accumulation across waves) - what changes is that prefill no
    longer evicts the store's residents and no longer pays the fill transient. Contiguous layouts only; stream_waves,
    stream_experts, stream_requested_bytes and stream_overread_bytes account for it separately in stats().

Quantized experts only (weight/scales/biases per projection, as repack writes them for a quantized build).
"""
from __future__ import annotations

import glob
import json
import os
from typing import Optional

import numpy as np

# MLX 0.32.2 hazard (measured, item 1): mx.gather_qmm(..., sorted_indices=True) disagrees with the plain kernel -
# grossly, not by rounding - as soon as the gathered stack has FEWER THAN 64 experts; at 64 and above the two agree
# bit for bit. The slot path never meets it (its stack is `capacity` rows, 100 in the accepted configuration), but a
# streaming wave can be short, so the stream path takes the plain kernel below this floor.
SORTED_GATHER_MIN_EXPERTS = 64
_PROJS = ("gate_proj", "up_proj", "down_proj")
_PARTS = ("weight", "scales", "biases")
WARM_STATE = "pulsar-slot-warm-state.json"


_SAFETENSORS_DTYPES = {"U32": ("uint32", "uint32"), "U8": ("uint8", "uint8"), "F32": ("float32", "float32"), "F16": ("float16", "float16"),
                       "BF16": ("uint16", "bfloat16")}   # safetensors dtype -> (numpy read dtype, mlx dtype; bf16 is read as u16 and viewed)


_PAGE = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 16384
_libc = None


def _mincore_resident(base: int, offset: int, length: int) -> bool:
    """True when every page of the mapping range [base+offset, +length) is in the page cache (macOS/BSD mincore); False on any doubt."""
    global _libc
    try:
        import ctypes
        if _libc is None:
            _libc = ctypes.CDLL(None)
            _libc.mincore.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_char_p]
            _libc.mincore.restype = ctypes.c_int
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
    mapping when the range is page-cache resident (copied, then madvise(MADV_DONTNEED) so the pages are not pinned in
    this process: pinned file pages rank above the store's own inactive tensors and the kernel compresses the tensors
    instead of dropping the cache - measured on the Studio), else with preadv into a buffer (thread-pool friendly)."""
    __slots__ = ("path", "entries", "data_start", "mmap", "base", "fd", "contiguous", "_ranges", "_lock", "alignment_extra")

    def __init__(self, path):
        import struct
        self.path = path
        with open(path, "rb") as fh:
            n = struct.unpack("<Q", fh.read(8))[0]
            header = json.loads(fh.read(n))
        self.data_start = 8 + n
        self.entries = {k: v for k, v in header.items() if k != "__metadata__"}
        self.mmap = None
        self.base = 0
        self.fd = None
        self.contiguous = (header.get("__metadata__") or {}).get("layout") == "expert-contiguous/1"
        self._ranges = {}
        self.alignment_extra = 0      # bytes read beyond the requested ranges to keep F_NOCACHE reads page-aligned
        import threading
        self._lock = threading.Lock()

    def expert_range(self, j: int):
        """[start, end) of expert j's nine tensors (contiguous layouts only; cached)."""
        if j not in self._ranges:
            parts = [self.entries[f"e{j}.{p}.{k}"]["data_offsets"] for p in _PROJS for k in _PARTS if f"e{j}.{p}.{k}" in self.entries]
            lo, hi = min(a for a, _ in parts), max(b for _, b in parts)
            if hi - lo != sum(b - a for a, b in parts):
                raise ValueError(f"NOT_CONTIGUOUS e{j}")
            self._ranges[j] = (lo, hi)
        return self._ranges[j]

    def merged_ranges(self, experts, gap_experts: int):
        """Sorted experts -> list of (lo, hi, [experts]) with runs merged when the gap is <= gap_experts expert sizes."""
        runs = []
        for j in sorted(experts):
            lo, hi = self.expert_range(j)
            if runs and lo - runs[-1][1] <= gap_experts * (hi - lo):
                runs[-1][1] = hi; runs[-1][2].append(j)
            else:
                runs.append([lo, hi, [j]])
        return [(lo, hi, js) for lo, hi, js in runs]

    def read_ranges_np(self, ranges, pool=None, chunk: int = 64 << 20, alignment: Optional[list] = None):
        """Merged ranges [(lo, hi), ...] -> one buffer each; every `chunk`-sized piece of every range is dispatched to the
        pool at once, so both a single huge range (a 1.3 GB preadv on one thread measured 3.0 vs 4.6 GB/s for eight
        threads on the MacBook's NVMe) and many small disjoint runs (sparse decode misses) read in parallel.
        Every piece is read on PAGE boundaries (unpruned-fidelity G38 first contact: F_NOCACHE only bypasses the page cache
        for page-aligned I/O, and the expert ranges start after an unaligned header, so the cold reads had been filling
        the file cache - 3.6 GB per 4 GB file - until the OS compressed the store's own tensors); the exact bytes are
        copied out of the aligned window, and the extra bytes are counted in `alignment` ([0] += bytes) when given."""
        self._open()
        bufs = [np.empty(hi - lo, dtype=np.uint8) for lo, hi in ranges]
        pieces = [(i, off, min(off + chunk, hi - lo)) for i, (lo, hi) in enumerate(ranges) for off in range(0, hi - lo, chunk)]

        def piece(item):
            i, a, b = item; lo = ranges[i][0]
            a0 = self.data_start + lo + a; b0 = self.data_start + lo + b
            pa = a0 // _PAGE * _PAGE; pb = -(-b0 // _PAGE) * _PAGE
            tmp = np.empty(pb - pa, dtype=np.uint8)
            got = os.preadv(self.fd, [memoryview(tmp)], pa)
            if got < b0 - pa:
                raise IOError(f"SHORT_READ range {lo + a}-{lo + b}: {got} of {b0 - pa} from page {pa}")
            bufs[i][a:b] = tmp[a0 - pa:b0 - pa]
            return (pb - pa) - (b - a)
        if pool is not None and len(pieces) > 1:
            extra = sum(pool.map(piece, pieces))
        else:
            extra = sum(piece(pc) for pc in pieces)
        if alignment is not None:
            alignment[0] += extra
        return bufs, len(pieces)

    def slice_np(self, buf, lo: int, name: str):
        e = self.entries[name]; np_dtype, _ = _SAFETENSORS_DTYPES[e["dtype"]]
        a, b = e["data_offsets"]
        return np.frombuffer(buf[a - lo:b - lo], dtype=np_dtype).reshape(e["shape"])

    def _open(self):
        if self.fd is not None:
            return
        with self._lock:   # readers run on a thread pool: open exactly once, descriptor before the map
            if self.fd is not None:
                return
            fd = os.open(self.path, os.O_RDONLY)
            try:   # cold reads must not populate the page cache: on a slow array the kernel compresses the store's own
                import fcntl   # (inactive) slot tensors in favour of the active file pages - measured on the Studio
                fcntl.fcntl(fd, fcntl.F_NOCACHE, 1)
            except (ImportError, AttributeError, OSError):
                pass
            import mmap as _mmap
            self.mmap = _mmap.mmap(fd, 0, access=_mmap.ACCESS_READ)
            self.base = np.frombuffer(self.mmap, dtype=np.uint8, count=1).ctypes.data
            self.fd = fd

    def resident(self, name) -> bool:
        self._open()
        a, b = self.entries[name]["data_offsets"]
        return _mincore_resident(self.base, self.data_start + a, b - a)

    def read_hot(self, name):
        """memmap copy (call only when resident): one copy page cache -> MLX buffer."""
        import mlx.core as mx

        self._open()
        e = self.entries[name]; np_dtype, mx_dtype = _SAFETENSORS_DTYPES[e["dtype"]]
        a, b = e["data_offsets"]
        off = self.data_start + a
        view = np.frombuffer(self.mmap, dtype=np_dtype, count=(b - a) // np.dtype(np_dtype).itemsize, offset=off).reshape(e["shape"])
        arr = mx.array(view)   # copy
        mx.eval(arr)
        try:   # unpin the pages from this mapping (they stay in the page cache for the kernel to keep or drop)
            import mmap as _mmap
            start = off // _PAGE * _PAGE
            self.mmap.madvise(_mmap.MADV_DONTNEED, start, (off + (b - a)) - start)
        except (AttributeError, OSError, ValueError):
            pass
        return arr.view(getattr(mx, mx_dtype)) if mx_dtype != np_dtype else arr

    def read_cold_np(self, name):
        """Page-aligned preadv into a numpy buffer (releases the GIL; safe from a thread); the caller converts. Returns the
        exact tensor bytes; the alignment over-read is reported through `self.alignment_extra` when the store reads it."""
        self._open()
        e = self.entries[name]; np_dtype, _ = _SAFETENSORS_DTYPES[e["dtype"]]
        a, b = e["data_offsets"]
        a0 = self.data_start + a; b0 = self.data_start + b
        pa = a0 // _PAGE * _PAGE; pb = -(-b0 // _PAGE) * _PAGE
        tmp = np.empty(pb - pa, dtype=np.uint8)
        got = os.preadv(self.fd, [memoryview(tmp)], pa)
        if got < b0 - pa:
            raise IOError(f"SHORT_READ {name}: {got} of {b0 - pa} from page {pa}")
        buf = np.array(tmp[a0 - pa:b0 - pa])          # exact bytes, own buffer
        self.alignment_extra += (pb - pa) - (b - a)
        return np.frombuffer(buf, dtype=np_dtype).reshape(e["shape"])

    def to_mx(self, name, np_arr):
        import mlx.core as mx

        _, mx_dtype = _SAFETENSORS_DTYPES[self.entries[name]["dtype"]]
        arr = mx.array(np_arr)
        return arr.view(getattr(mx, mx_dtype)) if str(np_arr.dtype) != mx_dtype else arr


class _LayerSlots:
    __slots__ = ("tensors", "expert_to_slot", "slot_of", "pending", "free", "file")

    def __init__(self, capacity, num_experts):
        self.tensors = None                 # {proj: [W, S, B]} stacked (C, ...)
        self.expert_to_slot = np.full((num_experts,), -1, dtype=np.int32)
        self.slot_of = {}                   # expert -> slot: PUBLISHED residency (bytes materialized)
        self.pending = {}                   # expert -> slot: reserved by touch_wave, not yet materialized
        self.free = list(range(capacity))
        self.file = None                    # _LayerFile, opened on first use


class PulsarSlotStore:
    policy = "lfu-decay-slots"

    def __init__(self, offload_dir: str, expert_cache_bytes: int, kv_reserve_bytes: int = 0, decay: float = 0.5,
                 decay_every: int = 4096, warm_start: bool = True, capacity_per_layer: Optional[int] = None, read_workers: int = 8,
                 bulk_min: int = 4, cache_clear_threshold_bytes: Optional[int] = 2 << 30, coalesce_gap_experts: int = 2, read_chunk_bytes: int = 64 << 20,
                 write_mode: str = "stack", prefill_mode: str = "store"):
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
        # PULSAR_SLOT_BULK_MIN overrides the bulk threshold (e.g. a huge value keeps every read on the preadv pool: better
        # for storage whose random page-fault reads are slow, such as a SAS array; measured 100 MB/s via faults there)
        self.bulk_min = int(os.environ.get("PULSAR_SLOT_BULK_MIN", bulk_min))
        self.cache_clear_threshold_bytes = None if cache_clear_threshold_bytes is None else int(cache_clear_threshold_bytes)
        self._cache_clears = 0
        self.coalesce_gap_experts = int(coalesce_gap_experts)
        self.read_chunk_bytes = int(read_chunk_bytes)   # merged ranges are read in pieces of this size (graph 33: the qualification uses 4096)
        # write_mode (freetoken-followon H1): 'stack' = mx.stack the wave's arrays and issue one in-place scatter per
        # (projection, part) - the baseline; 'per-expert' = one in-place scatter per expert per part, no stacked temporary
        # (one fewer pass over every cold byte and no 1.4 GB wave temporaries in prefill). Same reads, same policy, same
        # slot contents, same kernels: a byte-movement-only change that must stay bit-identical.
        if write_mode not in ("stack", "per-expert"):
            raise ValueError(f"WRITE_MODE {write_mode!r}")
        self.write_mode = write_mode
        self.layout = idx.get("layout", "hash-ordered")
        # prefill_mode (item 1): 'store' = every call fills slots (the baseline); 'stream' = a multi-token call reads its
        # experts into transient stacked tensors instead, leaving the slots to decode. Merged ranges need the contiguous
        # layout, so the mode is refused up front rather than at the first prefill.
        if prefill_mode not in ("store", "stream"):
            raise ValueError(f"PREFILL_MODE {prefill_mode!r}")
        if prefill_mode == "stream" and self.layout != "expert-contiguous/1":
            raise ValueError(f"STREAM_PREFILL_REQUIRES_CONTIGUOUS_LAYOUT: layout {self.layout!r}")
        self.prefill_mode = prefill_mode
        self._stream_waves = self._stream_experts = 0
        self._stream_requested_bytes = self._stream_overread_bytes = 0
        self._observed_accesses = 0   # experts counted by count_only (observation); NOT hits, misses or admissions
        self._coalesced_ranges = self._chunks_read = self._pool_reads = 0
        # byte accounting (graph 33): logical = misses x expert bytes (what the model admitted; `read_bytes` is its alias and
        # NOT a physical I/O counter); requested = bytes asked of the file by the cold paths (merged ranges incl. their
        # gaps, per-tensor preadv, bulk mx.load); overread = the gap bytes inside merged ranges; hot_copy = page-cache copies
        self._requested_read_bytes = self._overread_bytes = self._hot_copy_bytes = 0
        self._alignment_overread_bytes = 0   # page-alignment padding of cold reads (not part of requested/overread: those stay logical)
        self._waves = self._sorted_gathers = 0
        # trace capture (unpruned-fidelity G37): when `trace` is a list, every wave is appended as (phase, layer, wave)
        # so a replay can reproduce the exact request sequence and policy without the model; `phase` is set by the runner
        self.trace = None
        self.phase = None
        # force_cold: treat every read as not resident (skip mincore): the qualification runs the cold paths on files that
        # are page-cache resident, and storage whose residency reporting is unreliable can use it too
        self.force_cold = os.environ.get("PULSAR_SLOT_FORCE_COLD", "") == "1"
        self._pool = ThreadPoolExecutor(max_workers=max(1, int(read_workers)))
        self.poisoned = None        # str: why the store must not be used any more (a write-phase fill failure)
        self._fill_failures = 0
        self.fault_hook = None      # tests: callable(stage) invoked at 'read-done', 'projection-written', 'before-eval'
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

    def _usable(self) -> None:
        if self.poisoned is not None:
            raise RuntimeError(f"STORE_POISONED: {self.poisoned}")

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
        self._usable()
        self._waves += 1
        if self.trace is not None:
            self.trace.append((self.phase, lid, list(wave)))
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
                s = L.slot_of.pop(victim); L.expert_to_slot[victim] = -1   # evicted now: its bytes are about to go
                self._evictions += 1
            L.pending[j] = s                                                  # reserved, published by fill on success
            reads.append((j, s))
        return reads

    def count_only(self, lid: int, wave) -> None:
        """OBSERVATION, not admission (correction 1): the policy half of touch_wave and nothing else. Every expert of
        the wave is counted once, in wave order, through the same `_count` - so the global `_accesses` ordinal advances
        by one per expert and the decay fires on exactly the same `_accesses % decay_every == 0` boundaries with the
        same factor as it would have under touch_wave. An LFU victim chosen later during decode therefore still sees
        what prefill asked for.

        Nothing else is read or written: no slot_of / pending / free / expert_to_slot / slot tensor mutation, no hit,
        miss, eviction, reservation or read admission. The observation is recorded ONLY in the counters that are
        distinct from the admission counters: `observed_accesses` here, `stream_waves` / `stream_experts` and the
        stream byte counters in stream_wave. `_waves` and `trace` belong to the slot path and stay untouched."""
        self._usable()
        for j in wave:
            self._count((lid, j))
        self._observed_accesses += len(wave)

    def stream_wave(self, lid: int, wave) -> dict:
        """One wave of a streaming prefill: read the wave's experts as merged ranges and return TRANSIENT stacked
        tensors {proj: [W, S, B]} of shape (len(wave), ...) - the same shape the slot tensors have, so the caller's
        gather_qmm launches are unchanged apart from the index space (position in the wave, not slot). The store keeps
        no reference: the caller drops them. `wave` must be sorted (the stack is in wave order)."""
        import mlx.core as mx

        self._usable()
        f = self._file(lid); f._open()
        if not f.contiguous:
            raise ValueError(f"STREAM_PREFILL_REQUIRES_CONTIGUOUS_LAYOUT: layer {lid}")
        self.count_only(lid, wave)
        self._stream_waves += 1; self._stream_experts += len(wave)
        runs = f.merged_ranges(wave, self.coalesce_gap_experts)
        align = [0]
        bufs, _pieces = f.read_ranges_np([(lo, hi) for lo, hi, _ in runs], pool=self._pool, chunk=self.read_chunk_bytes, alignment=align)
        self._alignment_overread_bytes += align[0]
        arrays = {}
        for (lo, hi, js), buf in zip(runs, bufs):
            for j in js:
                for p in _PROJS:
                    for k in _PARTS:
                        n = f"e{j}.{p}.{k}"
                        if n in f.entries:
                            arrays[n] = f.to_mx(n, f.slice_np(buf, lo, n))
            self._stream_requested_bytes += hi - lo
            exact = sum(f.expert_range(j)[1] - f.expert_range(j)[0] for j in js)
            self._stream_overread_bytes += (hi - lo) - exact
        # mx.stack over the wave's arrays, not a numpy stack + one mx.array: measured on the MacBook (uint32, the
        # weight shape that dominates), 100 experts 32 ms vs 56 ms and 288 experts 43 ms vs 141 ms.
        tensors = {p: [mx.stack([arrays[f"e{j}.{p}.{k}"] for j in wave]) if len(wave) > 1 else arrays[f"e{wave[0]}.{p}.{k}"][None]
                       for k in _PARTS] for p in _PROJS}
        mx.eval([t for parts in tensors.values() for t in parts])
        return tensors

    def fill(self, lid: int, reads) -> None:
        """Materialize the reserved experts, write them into their slots (one scatter per (projection, part)), then
        commit the reservations. Read-phase failure: reservations released, raise. Write-phase failure: poison, raise."""
        import mlx.core as mx

        self._usable()
        if not reads:
            return
        self._ensure_tensors(lid)
        L = self._layers[lid]; f = self._file(lid)
        try:
            arrays = self._read_arrays(lid, f, reads)
            if self.fault_hook is not None:
                self.fault_hook("read-done")
        except BaseException:
            self._fill_failures += 1
            for j, _ in reads:
                L.pending.pop(j, None)
            L.free[0:0] = [s for _, s in reads]                               # a retry takes the same slots back
            raise
        try:
            self._write_slots(L, reads, arrays)
        except BaseException as exc:
            self._fill_failures += 1
            self.poisoned = f"write-phase fill failure on layer {lid}: {type(exc).__name__}: {exc}"
            raise
        for j, _ in reads:                                                    # commit: residency is published here only
            s = L.pending.pop(j); L.slot_of[j] = s; L.expert_to_slot[j] = s
        self._read_bytes += len(reads) * self.expert_bytes
        if self.cache_clear_threshold_bytes is not None and mx.get_cache_memory() >= self.cache_clear_threshold_bytes:
            mx.clear_cache()
            self._cache_clears += 1

    def _read_arrays(self, lid: int, f: _LayerFile, reads) -> dict:
        """Every part of every reserved expert as an mx.array (nothing written yet)."""
        import mlx.core as mx

        f._open()
        names = [(j, f"e{j}.{p}.{k}") for j, _ in reads for p in _PROJS for k in _PARTS]
        # the weight range decides hot/cold per expert (scales/biases are small and sit next to it in the file)
        hot = {j: (False if self.force_cold else f.resident(f"e{j}.gate_proj.weight")) for j, _ in reads}
        cold_names = [n for j, n in names if not hot[j]]
        n_cold = sum(1 for v in hot.values() if not v)
        arrays = {}
        if cold_names and f.contiguous:
            cold_experts = [j for j, _ in reads if not hot[j]]
            runs = f.merged_ranges(cold_experts, self.coalesce_gap_experts)
            align = [0]
            bufs, pieces = f.read_ranges_np([(lo, hi) for lo, hi, _ in runs], pool=self._pool, chunk=self.read_chunk_bytes, alignment=align)   # all runs' chunks in flight at once
            self._alignment_overread_bytes += align[0]
            for (lo, hi, js), buf in zip(runs, bufs):
                for j in js:
                    for p in _PROJS:
                        for k in _PARTS:
                            n = f"e{j}.{p}.{k}"
                            if n in f.entries:
                                arrays[n] = f.to_mx(n, f.slice_np(buf, lo, n))
                self._requested_read_bytes += hi - lo
                self._overread_bytes += (hi - lo) - sum(f.expert_range(j)[1] - f.expert_range(j)[0] for j in js)
            self._coalesced_ranges += len(runs); self._chunks_read += pieces
        elif n_cold >= self.bulk_min:
            lazy = mx.load(self._paths[lid])          # one header parse; MLX evaluates the loads together (parallel I/O)
            for n in cold_names:
                arrays[n] = lazy.pop(n)
            del lazy
            self._bulk_reads += n_cold; self._requested_read_bytes += n_cold * self.expert_bytes
        elif cold_names:
            before = f.alignment_extra
            cold = dict(zip(cold_names, self._pool.map(f.read_cold_np, cold_names)))
            for n in cold_names:
                arrays[n] = f.to_mx(n, cold[n])
            self._pool_reads += n_cold; self._requested_read_bytes += n_cold * self.expert_bytes; self._alignment_overread_bytes += f.alignment_extra - before
        for j, n in names:
            if n not in arrays:
                arrays[n] = f.read_hot(n)
        n_hot = sum(1 for v in hot.values() if v)
        self._hot_reads += n_hot; self._cold_reads += n_cold; self._hot_copy_bytes += n_hot * self.expert_bytes
        return arrays

    def _write_slots(self, L: _LayerSlots, reads, arrays: dict) -> None:
        """Scatter every (projection, part) into the reserved slots in place and evaluate."""
        import mlx.core as mx

        slots = mx.array([s for _, s in reads], dtype=mx.int32) if self.write_mode == "stack" else None
        for p in _PROJS:
            for ki, k in enumerate(_PARTS):
                if self.write_mode == "stack":
                    group = [arrays[f"e{j}.{p}.{k}"] for j, _ in reads]
                    stacked = mx.stack(group) if len(reads) > 1 else group[0][None]
                    L.tensors[p][ki][slots] = stacked             # in place (scatter into the uniquely referenced slot tensor)
                else:
                    for j, s in reads:
                        L.tensors[p][ki][s] = arrays[f"e{j}.{p}.{k}"]   # in place, one expert at a time (no stacked temporary)
            if self.fault_hook is not None:
                self.fault_hook("projection-written")
        if self.fault_hook is not None:
            self.fault_hook("before-eval")
        mx.eval([t for parts in L.tensors.values() for t in parts])

    def reset_logical_state(self) -> dict:
        """Test seam (unpruned-persistent G55/G57): forget every resident expert and every policy count, keeping the slot
        tensors ALLOCATED (no reallocation, no free) and the lifetime counters untouched - a same-process logical-cold
        control that isolates process warmth from expert warmth. Never exposed on a public serving API; must be called
        at idle by the model's single owner. A poisoned store stays poisoned."""
        self._usable()
        forgotten = 0
        for L in self._layers.values():
            forgotten += len(L.slot_of) + len(L.pending)
            L.slot_of.clear(); L.pending.clear(); L.expert_to_slot[:] = -1; L.free = list(range(self.capacity))
        self._counts.clear(); self._touch.clear(); self._accesses = 0
        self._logical_resets = getattr(self, "_logical_resets", 0) + 1
        return {"forgotten_experts": forgotten, "reallocated_slot_buffers": False, "logical_resets": self._logical_resets}

    def slots_for(self, lid: int, idx_host, mask=None):
        """Slot index per (token, k) from the layer's published map, gathered on the host; `mask` (same shape) zeroes
        the entries outside the current wave. An absent expert (-1) is rejected: it must never reach gather_qmm."""
        import mlx.core as mx

        self._usable()
        slots = self._layers[lid].expert_to_slot[idx_host]
        if mask is not None:
            slots = np.where(mask, slots, 0)
        if (slots < 0).any():
            raise RuntimeError("SLOT_MAP_INCOMPLETE: an expert of this call is not resident after fill")
        return mx.array(slots)

    def tensors(self, lid: int):
        self._usable()
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
                "hit_rate": (self._hits / total) if total else None, "fill_failures": self._fill_failures, "poisoned": self.poisoned,
                "read_bytes": self._read_bytes, "logical_admitted_bytes": self._read_bytes, "requested_read_bytes": self._requested_read_bytes, "overread_bytes": self._overread_bytes, "hot_copy_bytes": self._hot_copy_bytes, "alignment_overread_bytes": self._alignment_overread_bytes,
                "hot_reads": self._hot_reads, "cold_reads": self._cold_reads, "bulk_reads": self._bulk_reads, "pool_reads": self._pool_reads, "coalesced_ranges": self._coalesced_ranges, "chunks_read": self._chunks_read, "read_chunk_bytes": self.read_chunk_bytes,
                "waves": self._waves, "sorted_gathers": self._sorted_gathers, "write_mode": self.write_mode, "prefill_mode": self.prefill_mode,
                "stream_waves": self._stream_waves, "stream_experts": self._stream_experts, "stream_requested_bytes": self._stream_requested_bytes, "stream_overread_bytes": self._stream_overread_bytes, "observed_accesses": self._observed_accesses, "logical_resets": getattr(self, "_logical_resets", 0), "layout": self.layout, "cache_clears": self._cache_clears, "warm_admitted": self._warm_admitted,
                "decay": self.decay, "decay_every": self.decay_every, "accesses": self._accesses}

    # --- warm state -----------------------------------------------------------------------------
    def save_warm_state(self) -> str:
        self._usable()
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
                s = L.free.pop(0); L.pending[j] = s; reads.append((j, s))
            self.fill(lid, reads)                       # reserve -> fill -> commit, as for a miss
            admitted += len(reads)
        return admitted


class PulsarSwitchGLU:
    """Drop-in for SwitchGLU / OffloadedSwitchGLU: (x [..., D], indices [..., K]) -> [..., K, D]."""

    def __init__(self, store: PulsarSlotStore, layer_id: int, gate_quant, up_quant, down_quant, activation=None):
        self.store, self.layer_id = store, int(layer_id)
        self.gate_quant, self.up_quant, self.down_quant = tuple(gate_quant), tuple(up_quant), tuple(down_quant)
        self.activation = activation
        self.training = False

    def _gather(self, x, proj, quant, slots, sorted_indices, tensors=None):
        import mlx.core as mx

        W, S, B = (self.store.tensors(self.layer_id) if tensors is None else tensors)[proj]
        group_size, bits, mode = quant
        return mx.gather_qmm(x, W, S, B, rhs_indices=slots, transpose=True, group_size=group_size, bits=bits, mode=mode, sorted_indices=sorted_indices)

    def _experts(self, x, slots, tensors=None, allow_sort: bool = True):
        """SwitchGLU's forward over slot indices (or, when `tensors` is given, over a streaming prefill's transient
        stack, where `slots` is the position inside the wave), with its sort/unsort (mlx_vlm.models.switch_layers._gather_sort /
        _scatter_unsort, inlined so the module has no mlx-vlm import: sort the flattened (token, k) pairs by slot,
        gather the matching rows, run the three grouped matmuls with sorted_indices, and undo the permutation)."""
        import mlx.core as mx

        x = mx.expand_dims(x, (-2, -3))
        do_sort = slots.size >= 64
        if not allow_sort:                                  # a stack under SORTED_GATHER_MIN_EXPERTS: the plain kernel
            do_sort = False
        idx, inv_order = slots, None
        if do_sort:
            self.store._sorted_gathers += 1
            M = slots.shape[-1]
            flat = slots.flatten()
            order = mx.argsort(flat)
            inv_order = mx.argsort(order)
            x, idx = x.flatten(0, -3)[order // M], flat[order]
        x_up = self._gather(x, "up_proj", self.up_quant, idx, do_sort, tensors=tensors)
        x_gate = self._gather(x, "gate_proj", self.gate_quant, idx, do_sort, tensors=tensors)
        h = self.activation(x_up, x_gate) if self.activation is not None else (mx.sigmoid(x_gate) * x_gate * x_up)
        y = self._gather(h, "down_proj", self.down_quant, idx, do_sort, tensors=tensors)
        if do_sort:
            y = mx.unflatten(y[inv_order], 0, slots.shape)
        return y.squeeze(-2)

    def _stream_prefill(self, x, idx_host, waves):
        """Prefill outside the store: per wave, transient stacked tensors from stream_wave, the same three gather_qmm
        launches over them with each (token, k)'s position in the wave as rhs_indices (np.searchsorted on the sorted
        wave; entries outside the wave are masked exactly as the multi-wave slot path masks them), the wave evaluated
        so its transients die before the next one is read, and one mx.clear_cache() per layer call so the allocator
        does not carry 42 layers' wave temporaries. Bit-identical to the slot path: same bytes, and the single-wave
        case skips the mask multiply just as the slot path does. A wave shorter than SORTED_GATHER_MIN_EXPERTS takes
        the plain gather kernel, because MLX's sorted-index kernel does not agree with it on a short stack (measured
        on the Studio: the trailing wave of every multi-wave layer differed on every one of its rows)."""
        import mlx.core as mx

        lid, store = self.layer_id, self.store
        single = len(waves) == 1
        out = None
        for wave in waves:
            w = np.array(wave, dtype=idx_host.dtype)
            pos = np.searchsorted(w, idx_host).astype(np.int32)   # the expert's row in this wave's stack (as slots_for returns int32)
            tensors = store.stream_wave(lid, wave)
            allow_sort = len(wave) >= SORTED_GATHER_MIN_EXPERTS
            if single:
                out = self._experts(x, mx.array(pos), tensors=tensors, allow_sort=allow_sort)
            else:
                in_wave = np.isin(idx_host, w)
                y = self._experts(x, mx.array(np.where(in_wave, pos, 0)), tensors=tensors, allow_sort=allow_sort) * mx.array(in_wave)[..., None].astype(x.dtype)
                out = y if out is None else out + y
            mx.eval(out)                                    # the gathers must run before the wave's transients are dropped
            del tensors
        mx.clear_cache()
        return out

    def __call__(self, x, indices):
        """DISPATCH RULE (correction 4), stated by token count of THIS call, not by "phase":

          n = int(np.prod(idx_host.shape[:-1]))   # the call's (batch x tokens) count; the last axis is k
          n > 1 and store.prefill_mode == 'stream'  ->  STREAM path: transient wave tensors, counts observed,
                                                        slots untouched (nothing is admitted or evicted)
          otherwise                                 ->  SLOT path: touch_wave + fill, exactly the baseline

        So it is NOT true that "every prefill is streamed". A prefill chunk of exactly ONE token takes the SLOT path
        and fills slots like any decode step - which is how a prompt of length k * prefill_step_size + 1 behaves: its
        k full chunks stream, and its one-token remainder fills. A one-token prompt never streams at all. This is also
        why a streamed prefill still leaves a few hundred experts resident in a real run: the remainder chunk admitted
        them. With prefill_mode == 'store' (the default) every call takes the slot path, byte-for-byte as before."""
        import mlx.core as mx

        lid, store = self.layer_id, self.store
        idx_host = np.asarray(indices)                      # the one host read per layer (small)
        uniq = sorted(int(j) for j in np.unique(idx_host))
        C = store.capacity
        waves = [uniq[i:i + C] for i in range(0, len(uniq), C)]
        if store.prefill_mode == "stream" and int(np.prod(idx_host.shape[:-1])) > 1:
            return self._stream_prefill(x, idx_host, waves)   # more than one token in the call: a prefill chunk
        if len(waves) == 1:
            store.fill(lid, store.touch_wave(lid, waves[0]))
            return self._experts(x, store.slots_for(lid, idx_host))
        out = None
        for wave in waves:
            store.fill(lid, store.touch_wave(lid, wave))
            in_wave = np.isin(idx_host, np.array(wave, dtype=idx_host.dtype))
            slots = store.slots_for(lid, idx_host, mask=in_wave)
            y = self._experts(x, slots) * mx.array(in_wave)[..., None].astype(x.dtype)
            out = y if out is None else out + y
        return out


def patch_model_slots(model, offload_dir: str, expert_cache_gb=None, warm_start: bool = True, decay: float = 0.5, decay_every: int = 4096, read_workers: int = 8,
                      coalesce_gap_experts: int = 2, read_chunk_bytes: int = 64 << 20, write_mode: str = "stack", prefill_mode: str = "store"):
    """After mlx_vlm.moe_offload.patch_model has swapped every MoE layer's switch_mlp for an OffloadedSwitchGLU (which
    drops the resident expert parameters and computes the byte budget), replace each with a PulsarSwitchGLU over one
    shared PulsarSlotStore, reusing the upstream module's quant triples and activation."""
    from mlx_vlm.moe_offload import patch_model

    upstream = patch_model(model, offload_dir, expert_cache_gb=expert_cache_gb)
    store = PulsarSlotStore(offload_dir, upstream._budget, 0, decay=decay, decay_every=decay_every, warm_start=warm_start, read_workers=read_workers,
                            coalesce_gap_experts=coalesce_gap_experts, read_chunk_bytes=read_chunk_bytes, write_mode=write_mode, prefill_mode=prefill_mode)
    patched = 0
    for layer in model.language_model.model.layers:
        switch = getattr(getattr(layer, "mlp", None), "switch_mlp", None)
        if switch is not None and type(switch).__name__ == "OffloadedSwitchGLU":
            layer.mlp.switch_mlp = PulsarSwitchGLU(store, switch.layer_id, switch.gate_quant, switch.up_quant, switch.down_quant, activation=switch.activation)
            patched += 1
    return store, patched
