"""PulsarExpertStore: a drop-in for mlx-vlm's ExpertStore with a different residency policy.

Same on-disk format (repack output) and the same interface OffloadedSwitchGLU/patch_model use
(num_experts, experts_present, get, get_all, stats, _maps, swapped), same byte budget semantics
(a resident expert is one whose arrays are kept in the per-layer dict; eviction drops them so MLX
can reclaim; refetch is a lazy mx.load from the same file). Differences:

  * policy: least-frequently-used with periodic multiplicative decay. Every get() increments the
    expert's counter; every `decay_every` gets, all counters are multiplied by `decay`. A miss evicts
    the resident expert with the smallest (counter, last_touch) until the incoming expert fits. Routing
    is skewed toward hot experts, so frequency beats recency; the decay keeps the set adaptive.
  * warm state: `save_warm_state()` writes the counters and the resident set to
    <offload_dir>/pulsar-warm-state.json; a new store re-admits those experts (most frequent first,
    within the budget) at construction, so a second request starts warm instead of cold.
  * get_all keeps upstream's semantics (bulk load for a call touching most of a layer; no accounting).
"""
from __future__ import annotations

import glob
import json
import os
from typing import Optional, Tuple

_PROJ_KEYS = tuple(f"{p}.{k}" for p in ("gate_proj", "up_proj", "down_proj") for k in ("weight", "scales", "biases"))
WARM_STATE = "pulsar-warm-state.json"


class PulsarExpertStore:
    policy = "lfu-decay"

    def __init__(self, offload_dir: str, expert_cache_bytes: int, kv_reserve_bytes: int = 0,
                 decay: float = 0.5, decay_every: int = 4096, warm_start: bool = True):
        import mlx.core as mx

        idx = json.load(open(os.path.join(offload_dir, "offload_index.json")))
        self.offload_dir = offload_dir
        self.num_experts = idx["num_experts"]
        self._paths = {}
        self._maps = {}
        for path in glob.glob(os.path.join(offload_dir, "experts", "layer_*.safetensors")):
            lid = int(os.path.basename(path).split("_")[1].split(".")[0])
            self._paths[lid] = path
            self._maps[lid] = mx.load(path)  # mmap, lazy
        self._budget = int(expert_cache_bytes)
        self.decay, self.decay_every = float(decay), int(decay_every)
        self._counts: dict = {}          # (layer, expert) -> frequency (decayed)
        self._resident: dict = {}        # (layer, expert) -> nbytes
        self._touch: dict = {}           # (layer, expert) -> last access ordinal
        self._resident_bytes = 0
        self._accesses = 0
        self._hits = self._misses = self._evictions = 0
        self._warm_admitted = 0
        if warm_start:
            self._warm_admitted = self._admit_warm_state()

    # --- interface used by OffloadedSwitchGLU / patch_model -------------------------------------
    def experts_present(self, layer_id: int) -> bool:
        return layer_id in self._maps

    def _ensure_loaded(self, layer_id: int, j: int, m: dict) -> None:
        import mlx.core as mx

        if f"e{j}.gate_proj.weight" in m:
            return
        fresh = mx.load(self._paths[layer_id])
        for k in _PROJ_KEYS:
            name = f"e{j}.{k}"
            if name in fresh:
                m[name] = fresh[name]

    def _nbytes(self, m: dict, j: int) -> int:
        return sum(m[f"e{j}.{k}"].nbytes for k in _PROJ_KEYS if f"e{j}.{k}" in m)

    def _evict_until_fits(self, incoming_bytes: int) -> None:
        import mlx.core as mx

        if self._budget <= 0:
            return
        evicted = False
        while self._resident and self._resident_bytes + incoming_bytes > self._budget:
            victim = min(self._resident, key=lambda key: (self._counts.get(key, 0.0), self._touch.get(key, 0)))
            nbytes = self._resident.pop(victim)
            lid, j = victim
            m = self._maps[lid]
            for k in _PROJ_KEYS:
                m.pop(f"e{j}.{k}", None)
            self._resident_bytes -= nbytes
            self._evictions += 1
            evicted = True
        if evicted:
            try:
                mx.clear_cache()
            except Exception:
                pass

    def _count(self, key) -> None:
        self._accesses += 1
        self._counts[key] = self._counts.get(key, 0.0) + 1.0
        self._touch[key] = self._accesses
        if self._accesses % self.decay_every == 0:
            for k in list(self._counts):
                self._counts[k] *= self.decay

    def get(self, layer_id: int, j: int):
        m = self._maps[layer_id]
        self._ensure_loaded(layer_id, j, m)
        key = (layer_id, j)
        self._count(key)
        if key in self._resident:
            self._hits += 1
        else:
            self._misses += 1
            nbytes = self._nbytes(m, j)
            self._evict_until_fits(nbytes)
            self._resident[key] = nbytes
            self._resident_bytes += nbytes
        trip = lambda p: (m[f"e{j}.{p}.weight"], m.get(f"e{j}.{p}.scales"), m.get(f"e{j}.{p}.biases"))
        return (trip("gate_proj"), trip("up_proj"), trip("down_proj"))

    def get_all(self, layer_id: int, needed) -> dict:
        import mlx.core as mx

        fresh = mx.load(self._paths[layer_id])
        out = {}
        for j in needed:
            j = int(j)
            trip = lambda p: (fresh[f"e{j}.{p}.weight"], fresh.get(f"e{j}.{p}.scales"), fresh.get(f"e{j}.{p}.biases"))
            out[j] = (trip("gate_proj"), trip("up_proj"), trip("down_proj"))
        return out

    def stats(self) -> dict:
        total = self._hits + self._misses
        return {"policy": self.policy, "budget_bytes": self._budget, "resident_bytes": self._resident_bytes,
                "resident_experts": len(self._resident), "num_experts": self.num_experts, "num_layers": len(self._maps),
                "hits": self._hits, "misses": self._misses, "evictions": self._evictions,
                "hit_rate": (self._hits / total) if total else None, "warm_admitted": self._warm_admitted,
                "decay": self.decay, "decay_every": self.decay_every, "accesses": self._accesses}

    # --- warm state ------------------------------------------------------------------------------
    def save_warm_state(self) -> str:
        path = os.path.join(self.offload_dir, WARM_STATE)
        json.dump({"policy": self.policy, "counts": [[l, j, c] for (l, j), c in self._counts.items()],
                   "resident": [[l, j] for (l, j) in self._resident], "accesses": self._accesses}, open(path, "w"))
        return path

    def _admit_warm_state(self) -> int:
        path = os.path.join(self.offload_dir, WARM_STATE)
        if not os.path.exists(path):
            return 0
        state = json.load(open(path))
        self._counts = {(int(l), int(j)): float(c) for l, j, c in state["counts"]}
        self._accesses = int(state.get("accesses", 0))
        admitted = 0
        for l, j in sorted(state["resident"], key=lambda lj: -self._counts.get((int(lj[0]), int(lj[1])), 0.0)):
            l, j = int(l), int(j)
            if l not in self._maps:
                continue
            m = self._maps[l]
            self._ensure_loaded(l, j, m)
            nbytes = self._nbytes(m, j)
            if self._resident_bytes + nbytes > self._budget:
                break
            self._resident[(l, j)] = nbytes
            self._resident_bytes += nbytes
            admitted += 1
        return admitted
