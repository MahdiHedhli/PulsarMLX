"""Synthetic owning-allocation and injected-observation contract; no backend.

Logical owners are distinct from observed process memory. Providers must be
independent of this ledger; injection exercises that interface, not macOS/MLX
measurement. No real sampler or production physical ceiling is qualified here.
"""
from __future__ import annotations

from dataclasses import dataclass

GIB = 1024**3
MAX_ALLOCATION = 16 * 1024**2
WEIGHTS = frozenset(("fixed", "page", "device"))
KINDS = WEIGHTS | {"staging", "runtime"}


class MemoryStop(RuntimeError):
    pass


@dataclass(frozen=True)
class Budget:
    process_bytes: int = 48 * GIB
    weight_bytes: int = 40 * GIB
    other_bytes: int = 8 * GIB
    headroom_bytes: int = 16 * GIB
    max_age_ns: int = 10_000_000

    def __post_init__(self):
        caps = (48 * GIB, 40 * GIB, 8 * GIB, 64 * GIB, 1_000_000_000)
        values = tuple(vars(self).values())
        if (any(type(v) is not int or not 0 < v <= cap for v, cap in zip(values, caps)) or
                self.headroom_bytes < 16 * GIB or
                self.weight_bytes + self.other_bytes > self.process_bytes or
                self.process_bytes + self.headroom_bytes > 64 * GIB):
            raise ValueError("memory planning gates cannot be relaxed")


@dataclass(frozen=True)
class FreshObservation:
    sequence: int
    sampled_at_ns: int
    process_bytes: int
    mlx_live_bytes: int
    mlx_cache_bytes: int
    runtime_bytes: int
    headroom_bytes: int
    swap_bytes: int
    pressure: bool
    units: str
    process_source: str
    mlx_source: str
    system_source: str


@dataclass(frozen=True)
class Allocation:
    number: int
    kind: str
    size: int


@dataclass
class _Owner:
    token: Allocation
    buffer: bytearray | None = None
    retired: bool = False


class MemoryLedger:
    """Single-threaded reservation/owner ledger with fail-closed observations.

    Reserved but unmaterialized bytes reduce prospective process/headroom.
    Already materialized bytes are in the provider's process observation, so
    they are not added to it twice. All owners still count in logical budgets.
    Only <=16 MiB bytearrays may materialize in this synthetic implementation.
    """
    def __init__(self, budget, observe, clock, *, sources=("fixture-process", "fixture-mlx", "fixture-system")):
        if type(budget) is not Budget or not callable(observe) or not callable(clock):
            raise ValueError("budget, independent provider and monotonic clock required")
        if type(sources) is not tuple or len(sources) != 3 or any(type(s) is not str or not s for s in sources):
            raise ValueError("explicit observation provenance required")
        self.budget, self.observe, self.clock, self.sources = budget, observe, clock, sources
        self._owners = {}
        self._next = 1
        self.stopped = False
        self._sequence = 0
        self._sample_time = -1
        self._clock_time = -1
        self._swap = None
        self.last_observation = None

    def counts(self):
        weight = sum(o.token.size for o in self._owners.values() if o.token.kind in WEIGHTS)
        other = sum(o.token.size for o in self._owners.values() if o.token.kind not in WEIGHTS)
        return {"weight_bytes": weight, "other_bytes": other, "total_bytes": weight + other,
                "pending_bytes": sum(o.token.size for o in self._owners.values() if o.buffer is None),
                "retired_bytes": sum(o.token.size for o in self._owners.values() if o.retired)}

    def _stop(self, message):
        self.stopped = True
        raise MemoryStop(message)

    def check(self, prospective=0):
        if self.stopped:
            raise MemoryStop("allocation ledger stopped")
        if type(prospective) is not int or prospective < 0:
            self._stop("invalid prospective allocation")
        try:
            s = self.observe()
            now = self.clock()
        except Exception as exc:
            self.stopped = True
            raise MemoryStop("independent observation unavailable") from exc
        fields = ("sequence", "sampled_at_ns", "process_bytes", "mlx_live_bytes", "mlx_cache_bytes",
                  "runtime_bytes", "headroom_bytes", "swap_bytes")
        if (type(s) is not FreshObservation or
                any(type(getattr(s, f)) is not int or getattr(s, f) < 0 for f in fields) or
                type(s.pressure) is not bool or type(s.units) is not str or s.units != "bytes" or
                any(type(v) is not str for v in (s.process_source, s.mlx_source, s.system_source)) or
                (s.process_source, s.mlx_source, s.system_source) != self.sources or
                s.headroom_bytes > 64 * GIB or
                type(now) is not int or now < self._clock_time or
                s.sequence <= self._sequence or s.sampled_at_ns < self._sample_time or
                s.sampled_at_ns > now or now - s.sampled_at_ns > self.budget.max_age_ns):
            self._stop("invalid, stale, replayed or untrusted observation")
        if self._swap is None:
            self._swap = s.swap_bytes
        pending = self.counts()["pending_bytes"] + prospective
        if (s.pressure or s.swap_bytes > self._swap or
                s.process_bytes + pending > self.budget.process_bytes or
                s.mlx_live_bytes + s.mlx_cache_bytes > self.budget.process_bytes or
                s.runtime_bytes > self.budget.other_bytes or
                s.headroom_bytes - pending < self.budget.headroom_bytes):
            self._stop("process, runtime, MLX, headroom, pressure or swap gate")
        self._sequence, self._sample_time, self._clock_time = s.sequence, s.sampled_at_ns, now
        self._swap = max(self._swap, s.swap_bytes)
        self.last_observation = s
        return s

    def reserve(self, kind, size):
        if kind not in KINDS or type(size) is not int or size <= 0:
            raise ValueError("positive owning allocation required")
        self.check(size)
        c = self.counts()
        if ((c["weight_bytes"] + (size if kind in WEIGHTS else 0) > self.budget.weight_bytes) or
                (c["other_bytes"] + (0 if kind in WEIGHTS else size) > self.budget.other_bytes) or
                c["total_bytes"] + size > self.budget.process_bytes):
            self._stop("owning allocation budget exceeded before allocation")
        token = Allocation(self._next, kind, size)
        self._next += 1
        self._owners[token.number] = _Owner(token)
        return token

    def _owner(self, token):
        if type(token) is not Allocation or token.number not in self._owners or self._owners[token.number].token is not token:
            raise ValueError("allocation requires original owning token")
        return self._owners[token.number]

    def owns(self, token):
        return (type(token) is Allocation and token.number in self._owners and
                self._owners[token.number].token is token)

    def allocate(self, token):
        owner = self._owner(token)
        if owner.buffer is not None or owner.retired or token.size > MAX_ALLOCATION:
            raise ValueError("invalid or non-tiny materialization")
        self.check()
        try:
            owner.buffer = bytearray(token.size)
            self.check()
        except BaseException:
            self.retire(token)
            raise

    def view(self, token):
        owner = self._owner(token)
        if owner.buffer is None or owner.retired:
            raise ValueError("allocation not live")
        return memoryview(owner.buffer).toreadonly()

    def writable(self, token):
        """Adapter-only initialization view, released before exposing data."""
        owner = self._owner(token)
        if owner.buffer is None or owner.retired:
            raise ValueError("allocation not live")
        return memoryview(owner.buffer)

    def retire(self, token):
        owner = self._owner(token)
        owner.retired = True
        if owner.buffer is not None:
            try:
                owner.buffer.clear()
            except BufferError:
                return False
        del self._owners[token.number]
        return True

    def collect(self):
        for owner in tuple(self._owners.values()):
            if owner.retired:
                self.retire(owner.token)

    def retire_all(self):
        errors = []
        for owner in tuple(self._owners.values()):
            try:
                if not self.retire(owner.token):
                    errors.append(BufferError(f"allocation {owner.token.number} retains exported views"))
            except Exception as exc:
                errors.append(exc)
        if errors:
            for extra in errors[1:]: errors[0].add_note(str(extra))
            raise errors[0]
