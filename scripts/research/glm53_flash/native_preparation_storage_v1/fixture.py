"""Deterministic storage contract fixture. No filesystem payload or native runtime.

Capacity numbers are synthetic adapter obligations, NOT Python heap measurements.
Private internals are fault seams for tests, not a secure Python capability API.
"""
from dataclasses import dataclass

U64_MAX = (1 << 64) - 1
CATEGORIES = ('trunk', 'experts', 'state', 'scratch', 'io', 'overhead')
MAX_BYTES = 4096


class Refusal(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def require(condition, code):
    if not condition:
        raise Refusal(code)


def uint(value):
    require(type(value) is int and 0 <= value <= U64_MAX, 'Overflow')
    return value


def add(a, b):
    return uint(uint(a) + uint(b))


def label(value):
    require(isinstance(value, str) and 0 < len(value) <= 128, 'Identity')


@dataclass(frozen=True)
class Identity:
    checkpoint: str
    tensor: str
    role: str
    layer: str
    expert: str
    recipe: str
    graph: str


@dataclass(frozen=True)
class Selection:
    identity: Identity
    generation: int
    offset: int
    length: int
    logical_bytes: int


@dataclass(frozen=True)
class Step:
    request: str
    checkpoint: str
    graph: str
    recipe: str
    epoch: int
    position: int
    count: int
    context_limit: int


@dataclass(frozen=True)
class Boundary:
    request: str
    epoch: int
    position: int


@dataclass(frozen=True)
class Receipt:
    step: Step
    status: str
    state_advance_owned_by_storage: bool = False


class SyntheticSource:
    """Only authored tiny bytes; scripted single-read results and descriptor epochs."""
    def __init__(self, data, identity, chunk=5, actions=()):
        require(type(data) is bytes and 0 < len(data) <= MAX_BYTES, 'Range')
        require(isinstance(identity, Identity), 'Identity')
        for value in identity.__dict__.values():
            label(value)
        require(type(chunk) is int and 0 < chunk <= MAX_BYTES, 'Range')
        require(len(actions) <= 32, 'Range')
        self._data = data
        self.identity = identity
        self.generation = 1
        self.closed = False
        self.chunk = chunk
        self.actions = list(actions)
        self.reads = 0
        self.actual_bytes = 0
        self._selection = None

    def select(self, offset, length, logical_bytes=None):
        end = add(offset, length)
        require(0 < length <= MAX_BYTES and end <= len(self._data), 'Range')
        logical = uint(length if logical_bytes is None else logical_bytes)
        self._selection = Selection(self.identity, self.generation, offset, length, logical)
        return self._selection

    def check(self, selection):
        require(isinstance(selection, Selection) and not self.closed and selection is self._selection
                and selection.generation == self.generation
                and selection.identity == self.identity, 'Stale')

    def mutate(self):
        self.generation = add(self.generation, 1)

    def close(self):
        self.closed = True

    def read_at(self, offset, remaining):
        self.reads += 1
        action = self.actions.pop(0) if self.actions else self.chunk
        if action == 'interrupt':
            raise InterruptedError('synthetic interruption')
        if action == 'io':
            raise OSError('synthetic read error')
        if action == 'oversize':
            return b'', remaining + 1
        require(type(action) is int and action >= 0, 'ReaderCount')
        count = min(action, remaining)
        data = self._data[offset:offset+count]
        self.actual_bytes += len(data)
        return data, len(data)


class PackedTensorLease:
    """Opaque object-identity capability; no caller-provided range or token numbers."""
    __slots__ = ()


@dataclass
class _Entry:
    slot: int
    generation: int
    token: PackedTensorLease
    owner: str
    source: SyntheticSource
    selection: Selection
    step: Step
    category: int
    cap: int
    scratch: int
    protected: bool
    phase: str = 'reserved'
    owned: bool = True
    pinned: bool = False
    pending: str = ''
    cancelling: bool = False
    capacity_held: bool = True
    staging_held: bool = True
    scratch_held: bool = True
    staging: bytearray | None = None
    resident: bytes | None = None
    published: bool = False
    actual: int = 0
    interrupts: int = 0


class StorageFixture:
    """Serial event reference, at most four slots; no paging/production allocator."""
    def __init__(self, total, limits, baseline=(0,)*6, slots=4):
        self.total = uint(total)
        require(len(limits) == len(baseline) == 6, 'Budget')
        self.limits = tuple(uint(v) for v in limits)
        self.baseline = tuple(uint(v) for v in baseline)
        require(self.baseline[1] == self.baseline[3] == self.baseline[4] == 0, 'Budget')
        self._validate_budget(self.baseline)
        require(type(slots) is int and 0 < slots <= 4, 'Slots')
        self.slots = slots
        self._ledger = list(self.baseline)
        self._entries = {}
        self._generations = [0]*slots
        self.closed = False
        self.allocations = 0
        self.dispatches = 0
        self.max_materialized_payload = 0

    @property
    def ledger(self):
        return tuple(self._ledger)

    @property
    def live_slots(self):
        return len(self._entries)

    def _validate_budget(self, vector):
        total = 0
        for value, limit in zip(vector, self.limits):
            total = add(total, value)
            require(value <= limit, 'Budget')
        require(total <= self.total, 'Budget')

    @staticmethod
    def _step_check(selection, step, boundary):
        require(isinstance(step, Step) and isinstance(boundary, Boundary), 'Identity')
        for value in (step.request, step.checkpoint, step.graph, step.recipe):
            label(value)
        label(boundary.request)
        require(step.request == boundary.request, 'Identity')
        fields = (step.epoch, step.position, step.count, step.context_limit,
                  boundary.epoch, boundary.position)
        require(all(type(v) is int and 0 <= v <= U64_MAX for v in fields), 'Identity')
        require(step.count > 0 and step.position + step.count <= step.context_limit
                and step.position + step.count <= U64_MAX, 'Identity')
        require((step.epoch, step.position) == (boundary.epoch, boundary.position), 'Identity')
        i = selection.identity
        require((step.checkpoint, step.graph, step.recipe) == (i.checkpoint, i.graph, i.recipe), 'Identity')

    def reserve(self, source, selection, step, boundary, owner, *, category='experts',
                scratch=0, scratch_override=None, protected=False, cancelled=False):
        require(not self.closed, 'Phase')
        require(not cancelled, 'Cancelled')
        label(owner)
        require(isinstance(source, SyntheticSource), 'Identity')
        source.check(selection)
        self._step_check(selection, step, boundary)
        require(category in ('trunk', 'experts'), 'Identity')
        require(type(protected) is bool, 'Identity')
        scratch = uint(scratch if scratch_override is None else scratch_override)
        cap = add(selection.length, 7) // 8 * 8
        require(cap <= MAX_BYTES, 'Range')
        idx = CATEGORIES.index(category)
        new = list(self.ledger)
        for index, amount in ((idx,cap),(3,scratch),(4,cap)):
            new[index] = add(new[index], amount)
        self._validate_budget(new)
        require(len(self._entries) < self.slots, 'Slots')
        slot = next(s for s in range(self.slots) if s not in self._entries)
        generation = add(self._generations[slot], 1)
        token = PackedTensorLease()
        entry = _Entry(slot,generation,token,owner,source,selection,step,idx,cap,scratch,protected)
        self._entries[slot] = entry
        self._generations[slot] = generation
        self._ledger = new
        return token

    def _entry(self, h, owner, *, need_owner=True, allow_cancelled=False):
        e = next((e for e in self._entries.values() if e.token is h), None)
        require(e is not None and e.generation == self._generations[e.slot], 'Stale')
        require(owner == e.owner, 'Owner')
        if need_owner:
            require(e.owned, 'Owner')
        if not allow_cancelled:
            require(not e.cancelling and e.phase != 'cancelled', 'Cancelled')
        return e

    def _return_transient(self,e):
        if e.staging_held:
            self._ledger[4] -= e.cap
            e.staging_held = False
        if e.scratch_held:
            self._ledger[3] -= e.scratch
            e.scratch_held = False
        e.staging = None

    def _drop_capacity(self,e):
        if e.capacity_held:
            self._ledger[e.category] -= e.cap
            e.capacity_held = False
        e.resident = None
        e.published = False

    def _cancel_quiescent(self,e):
        assert not e.pending
        self._return_transient(e)
        if not e.pinned and not (e.protected and e.published):
            self._drop_capacity(e)
        e.phase = 'cancelled'
        e.cancelling = False

    def _materialized_peak(self):
        materialized = sum((e.cap if e.staging is not None else 0)
                           +(e.cap if e.resident is not None else 0)
                           for e in self._entries.values())
        self.max_materialized_payload = max(self.max_materialized_payload, materialized)

    def begin_read(self,h,owner,*,fault=None):
        e = self._entry(h,owner)
        require(e.phase == 'reserved', 'Phase')
        try:
            e.source.check(e.selection)
            require(fault != 'error', 'Allocation')
            e.staging = bytearray(e.cap)
            self.allocations += 1
            self._materialized_peak()
            e.phase = 'reading'
            e.pending = 'read'
        except (Refusal, MemoryError) as error:
            self._cancel_quiescent(e)
            if isinstance(error, MemoryError):
                raise Refusal('Allocation') from error
            raise

    def read(self,h,owner):
        e = self._entry(h,owner,allow_cancelled=True)
        require(e.pending == 'read', 'Phase')
        if e.cancelling:
            e.pending = ''
            self._cancel_quiescent(e)
            return True
        try:
            e.source.check(e.selection)
            remaining = e.selection.length-e.actual
            try:
                data,count = e.source.read_at(e.selection.offset+e.actual,remaining)
            except InterruptedError:
                e.interrupts += 1
                require(e.interrupts <= 4,'InterruptLimit')
                return False
            except OSError as error:
                raise Refusal('Read') from error
            require(type(count) is int and 0 <= count <= remaining and len(data) == count,'ReaderCount')
            require(count > 0,'ShortRead')
            e.staging[e.actual:e.actual+count] = data
            e.actual += count
            e.source.check(e.selection)
            if e.actual == e.selection.length:
                e.pending = ''
                e.phase = 'read_complete'
                return True
            return False
        except (Refusal, MemoryError) as error:
            e.pending = ''
            self._cancel_quiescent(e)
            if isinstance(error, MemoryError):
                raise Refusal('Allocation') from error
            raise

    def admit(self,h,owner,*,fault=None):
        e = self._entry(h,owner)
        require(e.phase == 'read_complete', 'Phase')
        try:
            e.source.check(e.selection)
            require(fault != 'error','Admission')
            # memoryview avoids a staging slice copy; resident and staging overlap.
            e.resident = bytes(memoryview(e.staging)[:e.selection.length])
            self.allocations += 1
            self._materialized_peak()
            e.source.check(e.selection)
            if fault == 'cancel':
                self._cancel_quiescent(e)
                raise Refusal('Cancelled')
            self._ledger[4] -= e.cap
            e.staging_held = False
            e.staging = None
            e.published = True
            e.phase = 'ready'
        except (Refusal, MemoryError) as error:
            self._cancel_quiescent(e)
            if isinstance(error, MemoryError):
                raise Refusal('Allocation') from error
            raise

    def payload(self,h,owner):
        e = self._entry(h,owner)
        require(e.phase in ('ready','dispatched','completed') and e.resident is not None,'Phase')
        # Test observation copy outside modeled adapter capacity, bounded <=4096.
        # A real adapter needs a lifetime-guarded pin borrow, never this accessor.
        return bytes(memoryview(e.resident))

    def transfer(self,h,owner,new_owner):
        e = self._entry(h,owner)
        require(not e.pending,'InFlight')
        require(not e.pinned,'Pinned')
        label(new_owner)
        e.token = PackedTensorLease()
        e.owner = new_owner
        return e.token

    def pin(self,h,owner):
        e = self._entry(h,owner)
        require(e.phase in ('ready','completed'),'Phase')
        require(not e.pinned,'Pinned')
        e.pinned = True

    def unpin(self,h,owner):
        e = self._entry(h,owner,allow_cancelled=True)
        require(not e.pending,'InFlight')
        require(e.pinned,'Phase')
        e.pinned = False
        if e.phase == 'cancelled' and not (e.protected and e.published):
            self._drop_capacity(e)

    def dispatch(self,h,owner,step,boundary,*,fault=None):
        e = self._entry(h,owner)
        require(e.phase == 'ready','Phase')
        self._step_check(e.selection,step,boundary)
        require(step == e.step,'Identity')
        if fault == 'error':
            # Refused submission has no outstanding native operation.
            # A pin, if present, still owns bytes and cannot be invalidated.
            self._cancel_quiescent(e)
            raise Refusal('Dispatch')
        if fault == 'cancel':
            require(not (e.protected and e.published),'Protected')
        self.dispatches += 1
        e.phase = 'dispatched'
        e.pending = 'dispatch'
        if fault == 'cancel':
            e.cancelling = True

    def acknowledge(self,h,owner):
        e = self._entry(h,owner,allow_cancelled=True)
        require(e.pending == 'dispatch','Phase')
        e.pending = ''
        if e.cancelling:
            self._cancel_quiescent(e)
            status = 'cancelled'
        else:
            e.phase = 'completed'
            self._return_transient(e)
            status = 'completed'
        return Receipt(e.step,status)

    def cancel(self,h,owner):
        e = self._entry(h,owner,allow_cancelled=True)
        if e.phase == 'cancelled' or e.cancelling:
            return
        require(not (e.protected and e.published),'Protected')
        if e.pending:
            e.cancelling = True
        else:
            self._cancel_quiescent(e)

    def release(self,h,owner):
        e = self._entry(h,owner,need_owner=False,allow_cancelled=True)
        require(not e.pending,'InFlight')
        require(not e.pinned,'Pinned')
        require(e.owned,'Owner')
        self._return_transient(e)
        if e.resident is None:
            self._drop_capacity(e)
        e.owned = False
        e.phase = 'released'

    def evict(self,h,owner):
        e = self._entry(h,owner,need_owner=False,allow_cancelled=True)
        require(not e.pending,'InFlight')
        require(not e.pinned,'Pinned')
        require(not e.owned or e.phase == 'cancelled','Owner')
        require(not (e.protected and e.published),'Protected')
        self._return_transient(e)
        self._drop_capacity(e)
        del self._entries[e.slot]

    def audit(self):
        expected = list((0,)*6 if self.closed else self.baseline)
        assert len(self._entries) <= self.slots
        for e in self._entries.values():
            assert e.generation == self._generations[e.slot]
            assert not e.pinned or e.resident is not None
            assert not e.pending or e.owned
            if e.capacity_held: expected[e.category] += e.cap
            if e.staging_held: expected[4] += e.cap
            if e.scratch_held: expected[3] += e.scratch
            assert e.resident is None or e.capacity_held
            assert not e.published or e.resident is not None
            assert e.phase not in ('ready','dispatched','completed') or e.published
            assert e.staging is None or e.staging_held
        assert tuple(expected) == self.ledger
        self._validate_budget(self.ledger)

    def close(self):
        require(not self.closed,'Phase')
        require(not self._entries,'Owner')
        self._ledger = [0]*6
        self.closed = True
