"""Additive bound-session contract, executable only on tiny marked fixtures.

No admission of real checkpoints, model code, MLX, backend or inference occurs.
Completion objects model an original-object synthetic protocol, not GPU fences.
"""
from __future__ import annotations

import hashlib
from contextlib import contextmanager
from dataclasses import dataclass

from qwen38_adapter_memory import Budget, MemoryLedger
from qwen38_adapter_trace import (FrozenCatalog, SyntheticOperations, Tape, catalog_identity,
                                 file_identity, key_name, spans, weight_digest)
from qwen38_fixture_io import MARKER, MARKER_CONTENT, MAX_FIXTURE_BYTES
from qwen38_page_catalog import BoundCheckpoint, ByteSpan, PageKey
from qwen38_verified_files import VerifiedFiles


class SessionError(ValueError):
    pass


class BindingError(SessionError):
    pass


def _segment(parent, start, end):
    return parent[start:end]


@dataclass(frozen=True)
class Demand:
    number: int
    key: PageKey
    at: int


@dataclass(frozen=True)
class ReadTicket:
    number: int
    key: PageKey
    size_bytes: int
    purpose: str


@dataclass
class _Read:
    ticket: ReadTicket
    owner: object
    status: str = "pending"
    classification: str | None = None
    retired: bool = False
    done_at: int | None = None
    digest: str | None = None


@dataclass(frozen=True)
class Completion:
    number: int


@dataclass(frozen=True)
class Borrow:
    number: int
    segments: dict
    completion: Completion


@dataclass
class _Borrow:
    borrow: Borrow
    demand: Demand
    read: _Read
    device: object
    parents: tuple
    done: bool = False
    release_recorded: bool = False


class SyntheticSession:
    """Own one bound fixture session, payload ledger and operation-bound tape.

    Single-threaded; no new request can reuse a canceled session. A new session
    needs its own live binding. Private Python internals are not a sandbox.
    """
    def __init__(self, bound, operations, observe, clock, *, budget=Budget()):
        self.closed = False
        self.cancelled = False
        self._bound = bound
        self._reads, self._cache, self._demands, self._borrows = {}, {}, {}, {}
        self._hints = []
        self._op_seen = set()
        self._next_op = self._next_demand = self._next_read = self._next_borrow = 1
        self.ledger = MemoryLedger(budget, observe, clock)
        self.tape = Tape(clock)
        self._fixed = None
        self._scratch = self._control = None
        try:
            if (type(bound) is not BoundCheckpoint or type(bound.files) is not VerifiedFiles or
                    type(operations) is not SyntheticOperations or
                    bound.files.closed or bound.files.poisoned or
                    bound.catalog._verified_files is not bound.files or
                    sum(bound.files.file_sizes.values()) > MAX_FIXTURE_BYTES or
                    len(bound.catalog.tensors) > 4096 or
                    any(len(name) > 1024 for name in bound.catalog.tensors)):
                raise BindingError("live tiny synthetic bound session required")
            marker = bound.files.entries.get(MARKER, {})
            marker_file = bound.files.files.get(MARKER)
            if (marker.get("size_bytes") != len(MARKER_CONTENT.encode()) or
                    marker.get("sha256") != hashlib.sha256(MARKER_CONTENT.encode()).hexdigest() or
                    marker_file is None or marker_file.algorithm != "sha256" or
                    marker_file.expected_digest != marker["sha256"] or marker_file.size != marker["size_bytes"]):
                raise BindingError("authenticated synthetic fixture marker required")
            self.catalog = FrozenCatalog.capture(bound.catalog, bound.files)
            self._original_catalog = bound.catalog
            self._files = bound.files
            self.operations = operations
            self._check_binding()
            self._scratch = self.ledger.reserve("runtime", 2 * max(f.chunk_bytes for f in self._files.files.values()))
            # Bounded control metadata allowance, not an exact Python footprint.
            # It remains prospective; independent observations cover real heap.
            self._control = self.ledger.reserve("runtime", 512 * 1024)
            self._fixed_spans = {}
            cursor = 0
            for name, ref in sorted(self.catalog.tensors.items()):
                if (".mlp.switch_mlp." in name or ".ple.ple_embedding.ngram_embedding.shard_" in name or
                        name.startswith(("vision_tower.", "model.visual."))):
                    continue
                length = ref.end - ref.start
                if length:
                    self._fixed_spans[name] = (cursor, ByteSpan(ref.filename, ref.data_start + ref.start, length, name))
                    cursor += length
            if cursor:
                self._fixed = self.ledger.reserve("fixed", cursor)
                self.ledger.allocate(self._fixed)
                target = self.ledger.writable(self._fixed)
                try:
                    for offset, span in self._fixed_spans.values():
                        segment = target[offset:offset + span.length]
                        try: self._files.readinto(span.filename, segment, span.offset)
                        finally: segment.release()
                    self._fixed_digest = hashlib.sha256(target).hexdigest()
                finally: target.release()
                self.ledger.check()
                self._check_binding()
        except BaseException as exc:
            self._abort(exc)
            raise

    def _check_binding(self):
        if (self._bound.catalog is not self._original_catalog or self._bound.files is not self._files or
                self._original_catalog._verified_files is not self._files or
                self._files.closed or self._files.poisoned or
                catalog_identity(self._original_catalog) != self.catalog.signature or
                file_identity(self._files) != self.catalog.file_signature):
            raise BindingError("catalog/verified-handle session binding changed")
        for name in self._files.files:
            self._files.check(name)

    @contextmanager
    def _operation(self):
        try:
            if self.closed or self.cancelled:
                raise SessionError("session no longer accepts operations")
            self._check_binding()
            self.ledger.check()
            yield
        except SessionError as exc:
            if isinstance(exc, BindingError): self._abort(exc)
            raise
        except BaseException as exc:
            self._abort(exc)
            raise

    def _demand(self, operation, key):
        self.catalog.page(key)
        if len(self._demands) >= 64:
            raise BindingError("bounded demand table full")
        number = self._next_demand; self._next_demand += 1
        at = self.tape.emit("demand", id=number, key=key_name(key), operation=operation)
        demand = Demand(number, key, at)
        self._demands[number] = [demand, False]
        return demand

    def route(self, step, layer):
        with self._operation():
            if any(type(n) is not int or n < 0 for n in (step, layer)) or ("route", step, layer) in self._op_seen:
                raise SessionError("invalid/duplicate route operation")
            try: selected, weights = self.operations.route(step, layer)
            except KeyError as exc: raise SessionError("unknown synthetic route operation") from exc
            keys = tuple(PageKey("expert", layer, n) for n in selected)
            for key in keys: self.catalog.page(key)
            number = self._next_op; self._next_op += 1
            self.tape.emit("route", id=number, step=step, layer=layer, selected=list(selected), executed=list(selected),
                           weights=list(weights), weights_digest=weight_digest(weights))
            self._op_seen.add(("route", step, layer))
            return tuple(self._demand(number, key) for key in keys)

    def ple(self, step, lookup):
        with self._operation():
            if any(type(n) is not int or n < 0 for n in (step, lookup)) or ("ple", step, lookup) in self._op_seen:
                raise SessionError("invalid/duplicate PLE operation")
            try: row = self.operations.ple(step, lookup)
            except KeyError as exc: raise SessionError("unknown synthetic PLE operation") from exc
            key = self.catalog.ple_key_for_global_row(row)
            number = self._next_op; self._next_op += 1
            self.tape.emit("ple", id=number, step=step, lookup=lookup, global_row=row, key=key_name(key))
            self._op_seen.add(("ple", step, lookup))
            return self._demand(number, key)

    def hint(self, key):
        with self._operation():
            self.catalog.page(key)
            if (key in self._hints or key in self._cache or
                    any(r.ticket.key == key and r.status == "pending" for r in self._reads.values()) or
                    any(d.key == key and not used for d, used in self._demands.values())):
                raise SessionError("duplicate or already demanded hint")
            if len(self._hints) >= 64: raise BindingError("bounded hint queue full")
            self.tape.emit("hint", key=key_name(key)); self._hints.append(key)

    def begin_read(self):
        with self._operation():
            pending = {r.ticket.key for r in self._reads.values() if r.status == "pending"}
            if len(pending) >= 2: return None
            waiting = [d.key for d, used in self._demands.values() if not used and d.key not in self._cache]
            candidates = [key for key in waiting if key not in pending]
            if candidates:
                key, purpose = candidates[0], "demand"
            elif waiting:
                return None  # Includes actual demands promoted from pending hints.
            else:
                candidates = [key for key in self._hints if key not in pending and key not in self._cache]
                if not candidates: return None
                key, purpose = candidates[0], "hint"
            if len(self._reads) >= 64: raise BindingError("bounded read table full")
            spec = self.catalog.page(key)
            owner = self.ledger.reserve("page", spec.size_bytes)
            number = self._next_read; self._next_read += 1
            ticket = ReadTicket(number, key, spec.size_bytes, purpose)
            self.tape.emit("read_start", id=number, key=key_name(key), bytes=spec.size_bytes,
                           purpose=purpose, spans=spans(spec))
            self._reads[number] = _Read(ticket, owner)
            if key in self._hints: self._hints.remove(key)
            return ticket

    def _read(self, ticket):
        r = self._reads.get(getattr(ticket, "number", None))
        if r is None or r.ticket is not ticket or r.status != "pending":
            raise SessionError("read requires original pending ticket")
        return r

    def finish_read(self, ticket):
        r = self._read(ticket)
        if self.cancelled or self.closed:
            r.status = "cancelled"
            self.tape.emit("read_cancelled", cleanup=True, id=ticket.number)
            self._retire(r)
            return
        try:
            with self._operation():
                self.ledger.allocate(r.owner)
                target = self.ledger.writable(r.owner)
                try:
                    self._bound.read_page_into(ticket.key, target)
                    r.digest = hashlib.sha256(target).hexdigest()
                finally: target.release()
                self.ledger.check(); self._check_binding()
                r.done_at = self.tape.emit("read_done", id=ticket.number, payload_sha256=r.digest)
                r.status = "done"; self._cache[ticket.key] = r
        except BaseException:
            # _operation has already aborted/closed the session, including this
            # pending owner. The original error remains the caller's result.
            raise

    def pump_one(self):
        ticket = self.begin_read()
        if ticket is not None: self.finish_read(ticket)
        return ticket

    def is_resident(self, demand):
        self._demand_identity(demand)
        return demand.key in self._cache

    def _demand_identity(self, demand):
        state = self._demands.get(getattr(demand, "number", None))
        if state is None or state[0] is not demand or state[1]:
            raise SessionError("original unserved operation demand required")

    def borrow(self, demand):
        self._demand_identity(demand)
        with self._operation():
            if demand.key not in self._cache: raise SessionError("actual demand has no verified resident page")
            if len(self._borrows) >= 8: raise BindingError("bounded completion table full")
            r = self._cache[demand.key]
            device = self.ledger.reserve("device", r.ticket.size_bytes)
            self.ledger.allocate(device)
            original = duplicate = None
            try:
                original = self.ledger.view(r.owner)
                if hashlib.sha256(original).hexdigest() != r.digest:
                    raise BindingError("verified cached payload changed")
                duplicate = self.ledger.writable(device)
                duplicate[:] = original
                if hashlib.sha256(duplicate).hexdigest() != r.digest:
                    raise BindingError("owning duplicate differs from verified payload")
            finally:
                if duplicate is not None: duplicate.release()
                if original is not None: original.release()
            self.ledger.check()
            segments = {}; parent = self.ledger.view(r.owner); cursor = 0
            try:
                for span in self.catalog.page(demand.key).spans:
                    segments[span.tensor] = _segment(parent, cursor, cursor+span.length)
                    cursor += span.length
            except BaseException:
                for view in segments.values(): view.release()
                raise
            finally: parent.release()
            number = self._next_borrow; self._next_borrow += 1
            completion = Completion(number)
            borrow = Borrow(number, segments, completion)
            try:
                self.tape.emit("borrow", lease=number, demand=demand.number, read=r.ticket.number,
                               completion=number, device_bytes=device.size, payload_sha256=r.digest)
            except BaseException:
                # No completion work has been issued to a caller. Do not leave
                # an unpublished borrow protected forever on trace failure.
                for view in segments.values(): view.release()
                self.ledger.retire(device)
                raise
            self._borrows[number] = _Borrow(borrow, demand, r, device, tuple(segments.values()))
            self._demands[demand.number][1] = True
            if r.ticket.purpose == "hint" and r.classification is None:
                r.classification = "useful" if r.done_at <= demand.at else "late"
            return borrow

    def _borrow_identity(self, borrow):
        state = self._borrows.get(getattr(borrow, "number", None))
        if state is None or state.borrow is not borrow:
            raise SessionError("original owning borrow required")
        return state

    def complete(self, borrow, completion):
        state = self._borrow_identity(borrow)
        if state.done or completion is not state.borrow.completion:
            raise SessionError("original synthetic completion required")
        self.tape.emit("completion", cleanup=True, lease=borrow.number, completion=completion.number)
        state.done = True

    def release(self, borrow):
        state = self._borrow_identity(borrow)
        if not state.done: raise SessionError("release before synthetic completion")
        for view in state.parents: view.release()
        if not state.release_recorded:
            self.tape.emit("release", cleanup=True, lease=borrow.number)
            state.release_recorded = True
        try:
            if self.ledger.owns(state.device): self.ledger.retire(state.device)
        except BaseException as exc:
            self._abort(exc)
            raise
        del self._borrows[borrow.number]
        borrow.segments.clear()
        if self.cancelled or self.closed:
            if not any(b.read is state.read for b in self._borrows.values()): self._retire(state.read)
        self.collect()

    def fixed_view(self, tensor):
        with self._operation():
            if tensor not in self._fixed_spans: raise SessionError("unknown fixed tensor")
            offset, span = self._fixed_spans[tensor]
            parent = self.ledger.view(self._fixed)
            try:
                if hashlib.sha256(parent).hexdigest() != self._fixed_digest:
                    raise BindingError("verified fixed payload changed")
                return parent[offset:offset+span.length]
            finally: parent.release()

    def _retire(self, r):
        if r.retired: return
        if r.status == "pending" or any(b.read is r for b in self._borrows.values()):
            raise SessionError("owner cannot retire before operation drain")
        self.ledger.retire(r.owner)
        self._cache.pop(r.ticket.key, None)
        r.retired = True
        self.tape.emit("retire", cleanup=True, id=r.ticket.number)
        if r.ticket.purpose == "hint":
            self.tape.emit("hint_terminal", cleanup=True, id=r.ticket.number, bytes=r.ticket.size_bytes,
                           classification=r.classification or "wasted")

    def evict(self, key):
        with self._operation():
            r = self._cache.get(key)
            if r is None: raise SessionError("page not resident")
            if any(b.read is r for b in self._borrows.values()): raise SessionError("cannot evict active owning lease")
            if any(d.key == key and not used for d, used in self._demands.values()): raise SessionError("cannot evict actual demand")
            self._retire(r)

    def cancel(self):
        if not self.cancelled:
            self.tape.emit("cancel", cleanup=True)
            self.cancelled = True
            self._hints.clear()

    def collect(self):
        self.ledger.collect()

    def close(self):
        if self.closed:
            self.collect()
            return
        self.closed = True
        errors = []
        def attempt(call):
            try: call()
            except BaseException as exc: errors.append(exc)
        attempt(self.cancel)
        for r in self._reads.values():
            if r.status == "pending":
                r.status = "cancelled"
                attempt(lambda r=r: self.tape.emit("read_cancelled", cleanup=True, id=r.ticket.number))
            if not r.retired and not any(b.read is r for b in self._borrows.values()):
                attempt(lambda r=r: self._retire(r))
        protected = {b.device.number for b in self._borrows.values()} | {b.read.owner.number for b in self._borrows.values()}
        for owner in tuple(self.ledger._owners.values()):
            if owner.token.number not in protected:
                attempt(lambda owner=owner: self.ledger.retire(owner.token))
        attempt(self._bound.close)
        if errors:
            for error in errors[1:]: errors[0].add_note(str(error))
            raise errors[0]

    def _abort(self, primary):
        # Mark the failed read distinctly before canceling other pending work.
        if hasattr(self, "catalog"):
            for r in self._reads.values():
                if r.status == "pending":
                    r.status = "failed"
                    try: self.tape.emit("read_failed", cleanup=True, id=r.ticket.number)
                    except BaseException as extra: primary.add_note(str(extra))
        try: self.close()
        except BaseException as cleanup: primary.add_note("session cleanup also failed: " + str(cleanup))

    def report(self):
        return self.tape.report(self.catalog, self.ledger.counts()["total_bytes"])

    def __enter__(self):
        return self

    def __exit__(self, kind, error, traceback):
        if error is None: self.close()
        else: self._abort(error)
