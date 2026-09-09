# SPDX-License-Identifier: MIT
# Exact Blaizzy/mlx-vlm classes, with a PipeNetwork caller-expression seam.
# See provenance.json and accompanying MIT/Apache-2.0 notices.

class _BaseCache:
    @property
    def state(self):
        return []

    @state.setter
    def state(self, v):
        if v is not None and v:
            raise ValueError("This cache has no state but a state was set.")

    @property
    def meta_state(self):
        return ""

    @meta_state.setter
    def meta_state(self, v):
        if v is not None and v:
            raise ValueError("This cache has no meta_state but a meta_state was set.")

    def is_trimmable(self):
        return False

    def size(self):
        """
        Return the size (i.e. sequence length) of the cache.

        Not every cache is required to implement this, in which case the size
        will always be 0 (though the cache may not be empty).
        """
        return 0

    @property
    def nbytes(self):
        """Return the size of this cache in bytes"""
        raise NotImplementedError("Cache sub-class must implement nbytes")

    def empty(self):
        """
        Return if the cache is empty or not.
        """
        raise NotImplementedError("Cache sub-class must implement this.")

    @classmethod
    def from_state(cls, state, meta_state):
        # Create an instance of cls without calling __init__
        obj = cls.__new__(cls)
        obj.state = state
        obj.meta_state = meta_state
        return obj

    def prefix_cache_snapshot(self):
        """Return an opaque, restorable snapshot of this cache's state.

        The returned object must round-trip through ``prefix_cache_restore``
        into a fresh cache from ``model.make_cache()``. References are returned
        as-is; the caller (adapter) is responsible for any detaching copy.
        """
        return {"state": self.state, "meta_state": self.meta_state}

    def prefix_cache_restore(self, snapshot):
        """Restore a snapshot from :meth:`prefix_cache_snapshot` into ``self``."""
        self.state = snapshot["state"]
        self.meta_state = snapshot["meta_state"]

    def prefix_cache_reserve(self, min_capacity_tokens):
        """Reserve optional post-restore capacity and return arrays to evaluate."""
        del min_capacity_tokens
        return ()

    def prefix_cache_merge(self, rows, prefix_lens):
        """Merge single-row snapshots into a batched cache, or ``None``.

        Default: not batch-mergeable. Pageable/windowed caches override to
        return a batched cache built from ``rows``.
        """
        return None


class ArraysCache(_BaseCache):
    def __new__(cls, *args, **kwargs):
        instance = super().__new__(cls)
        instance._left_padding = None
        instance._left_padding_advance = 0
        instance._lengths = None
        instance._lengths_advance = 0
        return instance

    def __init__(self, size, left_padding: Optional[List[int]] = None):
        self.cache = [None] * size
        if left_padding:
            self.left_padding = mx.array(left_padding)

    @property
    def left_padding(self):
        if self._left_padding is None:
            return None
        if self._left_padding_advance == 0:
            return self._left_padding
        return self._left_padding - self._left_padding_advance

    @left_padding.setter
    def left_padding(self, value):
        self._left_padding = value
        self._left_padding_advance = 0

    @property
    def lengths(self):
        if self._lengths is None:
            return None
        if self._lengths_advance == 0:
            return self._lengths
        return self._lengths - self._lengths_advance

    @lengths.setter
    def lengths(self, value):
        self._lengths = value
        self._lengths_advance = 0

    @property
    def batch_size(self):
        for c in self.cache:
            if c is not None:
                return c.shape[0]
        if self._left_padding is not None:
            return self._left_padding.size
        elif self._lengths is not None:
            return self._lengths.size
        else:
            return 1

    def __setitem__(self, idx, value):
        self.cache[idx] = value

    def __getitem__(self, idx):
        return self.cache[idx]

    @property
    def state(self):
        return self.cache

    @state.setter
    def state(self, v):
        self.cache = v

    def filter(self, batch_indices):
        """
        In-place filter to keep just the given indices in the cache.
        """
        self.cache = [c[batch_indices] if c is not None else None for c in self.cache]
        if self.left_padding is not None:
            self.left_padding = self.left_padding[batch_indices]
        if self.lengths is not None:
            self.lengths = self.lengths[batch_indices]

    def extend(self, other):
        """
        In-place extend this cache with the other cache.
        """

        a_batch = self.batch_size
        b_batch = other.batch_size

        def cat(a, b):
            shape = dtype = None
            if a is not None:
                shape = a.shape
                dtype = a.dtype
            if b is not None:
                shape = b.shape
                dtype = b.dtype

            if shape is None:
                return None

            if a is None:
                a = mx.zeros((a_batch,) + shape[1:], dtype=dtype)
            if b is None:
                b = mx.zeros((b_batch,) + shape[1:], dtype=dtype)

            return mx.concatenate([a, b])

        self.cache = [cat(c, o) for c, o in zip(self.cache, other.cache)]
        self.left_padding = cat(self.left_padding, other.left_padding)
        self.lengths = cat(self.lengths, other.lengths)

    def extract(self, idx):
        cache = ArraysCache(len(self.cache))
        cache.cache = [c[idx : idx + 1] for c in self.cache]
        return cache

    def prepare(self, lengths=None, **kwargs):
        self.lengths = mx.array(lengths)

    def finalize(self):
        self.lengths = None
        self.left_padding = None

    def advance(self, N):
        if self._lengths is not None:
            self._lengths_advance += N
        if self._left_padding is not None:
            self._left_padding_advance += N

    def make_mask(self, N: int):
        if self.left_padding is not None:
            pos = mx.arange(N)
            return pos >= self.left_padding[:, None]
        elif self.lengths is not None:
            pos = mx.arange(N)
            return pos < self.lengths[:, None]
        else:
            return None

    @classmethod
    def merge(cls, caches):
        n_state = len(caches[0].cache)
        B = len(caches)
        cache = cls(n_state)

        # All caches are empty so return early
        if all(c.empty() for c in caches):
            cache.left_padding = mx.array([0] * B)
            return cache

        for e in range(n_state):
            c_init = next(iter(c[e] for c in caches if c[e] is not None))
            shape = list(c_init.shape)
            shape[0] = B
            cache[e] = mx.zeros(shape, c_init.dtype)
            for i in range(B):
                if caches[i][e] is None:
                    continue
                cache[e][i : i + 1] = caches[i][e]
        return cache

    def empty(self):
        return self.cache[0] is None

    @property
    def nbytes(self):
        return sum(c.nbytes for c in self.cache if c is not None)


def source_make_cache():
    return ArraysCache(size=2)
