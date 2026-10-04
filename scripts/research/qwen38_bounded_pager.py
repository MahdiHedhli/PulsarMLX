"""Synthetic-only bounded page scheduler for Qwen expert and PLE spans.

No file I/O, checkpoint code, MLX allocation, or inference occurs here. The
budgets model desired accounting; a future adapter must enforce actual buffers
and provide independent OS/process observations before full-model execution.
"""

from __future__ import annotations

from collections import OrderedDict, deque
from dataclasses import dataclass
from typing import Callable

from qwen38_page_catalog import PageKey, PageSpec


class PagerStop(RuntimeError):
    """A demand or observed memory condition prevents safe progress."""


class PagerProtocolError(ValueError):
    """Caller violated page/lease lifecycle."""


@dataclass(frozen=True)
class Limits:
    weight_bytes: int
    staging_bytes: int
    inflight_requests: int
    queued_hints: int
    active_demands: int
    process_bytes: int
    system_headroom_bytes: int
    fixed_model_bytes: int = 0

    def __post_init__(self) -> None:
        if any(type(value) is not int or value <= 0 for name, value in vars(self).items()
               if name != "fixed_model_bytes"):
            raise ValueError("limits must be positive integer bytes/counts")
        if (type(self.fixed_model_bytes) is not int or self.fixed_model_bytes < 0 or
                self.fixed_model_bytes >= self.weight_bytes or
                self.staging_bytes > self.weight_bytes - self.fixed_model_bytes or
                self.weight_bytes > self.process_bytes):
            raise ValueError("inconsistent allocation limits")


@dataclass(frozen=True)
class Observation:
    process_bytes: int
    system_headroom_bytes: int
    swap_delta_bytes: int
    memory_pressure: bool


@dataclass(frozen=True)
class IoTicket:
    ticket: int
    spec: PageSpec
    purpose: str  # demand or hint at admission time


@dataclass
class Lease:
    key: PageKey
    gpu_done: bool = False


class BoundedPager:
    """Demand-first scheduler with explicit in-flight, resident, and GPU leases."""

    def __init__(self, catalog: Callable[[PageKey], PageSpec], limits: Limits):
        self.catalog = catalog
        self.limits = limits
        self.demand_queue: deque[PageKey] = deque()
        self.hint_queue: deque[PageKey] = deque()
        self.actual_demands: set[PageKey] = set()
        self.pending: dict[PageKey, IoTicket] = {}
        self.resident: OrderedDict[PageKey, PageSpec] = OrderedDict()
        self.hint_resident: set[PageKey] = set()
        self.leases: dict[int, Lease] = {}
        self.next_ticket = 1
        self.next_lease = 1
        self.resident_bytes = 0
        self.staging_bytes = 0
        self.hint_waste_bytes = 0
        self.closed = False
        self.cancelled: set[PageKey] = set()

    def _open(self) -> None:
        if self.closed:
            raise PagerStop("pager stopped")

    def _stop(self, reason: str) -> None:
        self.cancel_request()
        self.closed = True
        self._drain_unpinned()
        raise PagerStop(reason)

    def stop(self, reason: str) -> None:
        self._stop(reason)

    def _drain_unpinned(self) -> None:
        for key in list(self.resident):
            if not self._pinned(key):
                self.resident_bytes -= self.resident.pop(key).size_bytes
                self.hint_resident.discard(key)

    def _spec(self, key: PageKey) -> PageSpec:
        spec = self.catalog(key)
        if spec.key != key or not spec.spans or any(span.length <= 0 for span in spec.spans):
            raise PagerProtocolError("catalog returned an invalid page")
        return spec

    def observe(self, sample: Observation) -> None:
        """Stop on sampled pressure; this is not an allocation hard limit."""
        self._open()
        if (any(type(v) is not int or v < 0 for v in
                (sample.process_bytes, sample.system_headroom_bytes, sample.swap_delta_bytes))
                or type(sample.memory_pressure) is not bool):
            self._stop("invalid memory observation")
        if (sample.process_bytes > self.limits.process_bytes or
                sample.system_headroom_bytes < self.limits.system_headroom_bytes or
                sample.swap_delta_bytes > 0 or sample.memory_pressure):
            self._stop("observed process, headroom, swap, or pressure limit")

    def demand(self, key: PageKey) -> None:
        """Only the actual router or PLE lookup may call this method."""
        self._open()
        self._spec(key)
        if key not in self.actual_demands and len(self.actual_demands) >= self.limits.active_demands:
            self._stop("active demand limit exceeded")
        self.actual_demands.add(key)
        self.hint_resident.discard(key)
        self.cancelled.discard(key)
        if key in self.resident or key in self.pending or key in self.demand_queue:
            return
        try:
            self.hint_queue.remove(key)
        except ValueError:
            pass
        self.demand_queue.append(key)

    def hint(self, key: PageKey) -> bool:
        self._open()
        spec = self._spec(key)
        if spec.size_bytes > self.limits.staging_bytes or spec.size_bytes > self.limits.weight_bytes - self.limits.fixed_model_bytes:
            return False
        if (key in self.actual_demands or key in self.resident or key in self.pending or
                key in self.hint_queue or key in self.demand_queue):
            return False
        if len(self.hint_queue) >= self.limits.queued_hints:
            return False
        self.hint_queue.append(key)
        return True

    def invalidate_hint(self, key: PageKey) -> None:
        self._open()
        try:
            self.hint_queue.remove(key)
        except ValueError:
            pass
        if key in self.pending and key not in self.actual_demands:
            self.cancelled.add(key)
        if key in self.hint_resident:
            spec = self.resident.pop(key)
            self.resident_bytes -= spec.size_bytes
            self.hint_waste_bytes += spec.size_bytes
            self.hint_resident.remove(key)

    def _pinned(self, key: PageKey) -> bool:
        return any(lease.key == key for lease in self.leases.values())

    def _evict_for(self, size: int) -> bool:
        if size > self.limits.weight_bytes:
            return False
        reserved = self.limits.fixed_model_bytes + self.resident_bytes + self.staging_bytes
        victims = []
        for key, spec in self.resident.items():
            if reserved + size <= self.limits.weight_bytes:
                break
            if not self._pinned(key) and key not in self.actual_demands:
                victims.append(key)
                reserved -= spec.size_bytes
        if reserved + size > self.limits.weight_bytes:
            return False
        for key in victims:
            self.resident_bytes -= self.resident.pop(key).size_bytes
            self.hint_resident.discard(key)
        return True

    def next_io(self) -> IoTicket | None:
        """Reserve bytes before I/O; never admit a hint ahead of a queued demand."""
        self._open()
        # A demand promoted from an in-flight hint is still waiting. New hints
        # must not take I/O slots until that actual demand has completed.
        waiting_on_io = any(key in self.actual_demands and key not in self.resident
                            for key in self.pending)
        if not self.demand_queue and waiting_on_io:
            return None
        source = self.demand_queue if self.demand_queue else self.hint_queue
        if not source or len(self.pending) >= self.limits.inflight_requests:
            return None
        key = source[0]
        spec = self._spec(key)
        purpose = "demand" if source is self.demand_queue else "hint"
        if (spec.size_bytes > self.limits.staging_bytes or
                self.staging_bytes + spec.size_bytes > self.limits.staging_bytes):
            if purpose == "demand" and spec.size_bytes > self.limits.staging_bytes:
                self._stop("demand page exceeds staging budget")
            return None
        if not self._evict_for(spec.size_bytes):
            if purpose == "demand":
                self._stop("demand page exceeds available weight/staging budget")
            return None
        source.popleft()
        ticket = IoTicket(self.next_ticket, spec, purpose)
        self.next_ticket += 1
        self.pending[key] = ticket
        self.staging_bytes += spec.size_bytes
        return ticket

    def complete_io(self, ticket: IoTicket) -> None:
        """An adapter must call this only after the read and copy have completed."""
        current = self.pending.get(ticket.spec.key)
        if current != ticket:
            raise PagerProtocolError("unmatched I/O completion")
        del self.pending[ticket.spec.key]
        self.staging_bytes -= ticket.spec.size_bytes
        if ticket.spec.key in self.cancelled and ticket.spec.key not in self.actual_demands:
            self.cancelled.remove(ticket.spec.key)
            if ticket.purpose == "hint":
                self.hint_waste_bytes += ticket.spec.size_bytes
            return
        self.resident[ticket.spec.key] = ticket.spec
        self.resident_bytes += ticket.spec.size_bytes
        self.resident.move_to_end(ticket.spec.key)
        if ticket.purpose == "hint" and ticket.spec.key not in self.actual_demands:
            self.hint_resident.add(ticket.spec.key)

    def fail_io(self, ticket: IoTicket) -> None:
        """A synchronous failed read ended; release its reservation and stop."""
        current = self.pending.get(ticket.spec.key)
        if current != ticket:
            raise PagerProtocolError("unmatched I/O failure")
        del self.pending[ticket.spec.key]
        self.staging_bytes -= ticket.spec.size_bytes
        self._stop("page I/O failed")

    def acquire(self, key: PageKey) -> int:
        """Return a lease only for a page demanded by actual model computation."""
        self._open()
        if key not in self.actual_demands or key not in self.resident:
            raise PagerProtocolError("page is not demanded and resident")
        self.resident.move_to_end(key)
        lease_id = self.next_lease
        self.next_lease += 1
        self.leases[lease_id] = Lease(key)
        return lease_id

    def mark_gpu_done(self, lease_id: int) -> None:
        lease = self.leases.get(lease_id)
        if lease is None or lease.gpu_done:
            raise PagerProtocolError("unknown or completed GPU lease")
        lease.gpu_done = True

    def release(self, lease_id: int) -> None:
        lease = self.leases.get(lease_id)
        if lease is None or not lease.gpu_done:
            raise PagerProtocolError("release before GPU completion")
        del self.leases[lease_id]
        if self.closed:
            self._drain_unpinned()

    def finish_demand(self, key: PageKey) -> None:
        if key not in self.actual_demands or self._pinned(key) or key in self.pending or key in self.demand_queue:
            raise PagerProtocolError("demand has unfinished work")
        self.actual_demands.remove(key)

    def cancel_request(self) -> None:
        """Drop queued hints/demands; in-flight buffers still await I/O completion."""
        self.demand_queue.clear()
        self.hint_queue.clear()
        self.cancelled.update(self.pending)
        for key in tuple(self.hint_resident):
            self.invalidate_hint(key)
        self.actual_demands.clear()

    def accounting(self) -> dict[str, int]:
        return {"resident_bytes": self.resident_bytes,
                "fixed_model_bytes": self.limits.fixed_model_bytes,
                "staging_bytes": self.staging_bytes,
                "reserved_weight_bytes": (self.limits.fixed_model_bytes +
                                          self.resident_bytes + self.staging_bytes),
                "inflight_requests": len(self.pending),
                "queued_demands": len(self.demand_queue),
                "queued_hints": len(self.hint_queue),
                "gpu_leases": len(self.leases),
                "invalidated_hint_bytes": self.hint_waste_bytes}
