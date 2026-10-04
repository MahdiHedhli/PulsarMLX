"""MIT. PulsarMLX serial synthetic single-step adapter; no native/weight support.

Private fields are controlled fault seams, not a Python security boundary.
Capacity ledgers describe logical encodings, never Python heap or physical RAM.
"""
from dataclasses import dataclass, field
import hashlib
import math
import struct

from scripts.research.glm53_flash.native_preparation_model_state_v1 import state as model
from scripts.research.glm53_flash.native_preparation_storage_v1 import fixture as storage

OWNER = 'host-adapter-v1'
IDLE = (16384, 0, 0, 0)
ACTIVE = (65536, 32768, 8192, 8192)
SUCCESS = (16384, 32768, 0, 0)
LABELS = ('0', '3', '4', '7')


class AdapterRefusal(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def require(condition, code):
    if not condition:
        raise AdapterRefusal(code)


def integer(value, lo, hi, code):
    require(type(value) is int and lo <= value <= hi, code)


def label(value, code='Identity'):
    require(type(value) is str and 1 <= len(value) <= 64, code)
    try:
        value.encode('utf-8')
    except UnicodeError as error:
        raise AdapterRefusal(code) from error


@dataclass(frozen=True)
class StepV2:
    checkpoint_descriptor_id: str
    graph_version: str
    recipe_version: str
    request: str
    epoch: int
    revision: int
    origin: int
    capacity: int
    endpoint: int
    position: int
    count: int


class Grant:
    __slots__ = ()


class Intent:
    __slots__ = ()


class Completion:
    __slots__ = ()


@dataclass(frozen=True)
class _Grant:
    source: object
    selection: object
    shape: tuple


@dataclass(frozen=True)
class _Proof:
    grant: object
    source: object
    selection: object
    identity: object
    shape: tuple
    owner: str
    token: object
    storage: object
    slot: int
    generation: int
    step: StepV2
    revision: int
    dispatch_id: int
    digest: str
    decoded: object


@dataclass
class _Lease:
    grant: object
    record: _Grant
    token: object
    copy: object = None
    proof: object = None
    completion: object = None
    receipt: object = None


@dataclass
class _Work:
    token: Intent
    step: StepV2
    before: object
    grants: tuple
    records: list = field(default_factory=list)
    decoded: dict = field(default_factory=dict)
    phase: str = 'intent'
    reading: int = 0
    admitted: int = 0
    captured: bool = False
    cancelled: bool = False
    proposal: object = None
    proposal_required: tuple = ()
    proposal_consumed: tuple = ()
    committed: bool = False
    lost: set = field(default_factory=set)


def decode(data, kind, count):
    """One bounded immutable decode, with scalar-by-scalar unpack (no flat copy)."""
    integer(count, 1, 8, 'Geometry')
    require(kind in ('kda', 'sparse'), 'Geometry')
    parts = (7,2,1) if kind == 'kda' else (2,2,2,1,3,3,3)
    require(type(data) is bytes and len(data) == 8*sum(parts)*count, 'Geometry')
    offset = 0
    tokens = []
    for _ in range(count):
        token = []
        for size in parts:
            values = []
            for _ in range(size):
                value = struct.unpack_from('<d', data, offset)[0]
                require(math.isfinite(value) and abs(value) <= 8, 'Geometry')
                values.append(value)
                offset += 8
            token.append(values[0] if size == 1 else tuple(values))
        tokens.append(tuple(token))
    return tuple(tokens)


class Adapter:
    def __init__(self, descriptor, storage_fixture, *, caps=ACTIVE):
        require(type(descriptor) is tuple and len(descriptor) == 3, 'Identity')
        for value in descriptor:
            label(value)
        require(isinstance(storage_fixture, storage.StorageFixture), 'Identity')
        require(not storage_fixture.closed and not storage_fixture.live_slots
                and not any(storage_fixture._generations) and not storage_fixture.dispatches, 'Used')
        require(type(caps) is tuple and len(caps) == 4, 'LogicalBudget')
        for value, limit, baseline in zip(caps, ACTIVE, IDLE):
            integer(value, baseline, limit, 'LogicalBudget')
        self._engine = model.Engine(descriptor)
        self._storage = storage_fixture
        self._caps = caps
        self._ledger = IDLE
        self._grants = {}
        self._receipts = {}
        self._active = None
        self._terminal = None
        self._used = False
        self._outbox = None
        self._issued = 0
        self._dispatch_id = 0
        self._events = []
        self._cleanup_refusals = []
        self._cleanup_errors = ()
        self._prepare_calls = 0
        self._commit_calls = 0

    @property
    def prepare_calls(self):
        return self._prepare_calls

    @property
    def commit_calls(self):
        return self._commit_calls

    @property
    def ledger(self):
        return self._ledger

    @property
    def events(self):
        return tuple(self._events)

    @property
    def cleanup_refusals(self):
        return tuple(self._cleanup_refusals)

    @property
    def cleanup_errors(self):
        return self._cleanup_errors

    def _room(self, needed=1):
        # Admit the entire fixed phase graph, including its cleanup events.
        require(len(self._events)+needed <= 64, 'LogicalBudget')

    def _event(self, name):
        require(len(self._events) < 128, 'LogicalBudget')
        s = self._storage
        self._events.append((name, s.ledger, s.live_slots, tuple(s._generations), self.ledger))

    def _idle(self):
        require(self._active is None and self._outbox is None, 'Busy')
        require(not self._used, 'Used')

    def create(self, request, layers, *, origin=0, capacity=8, initial=None):
        self._idle()
        label(request)
        self._engine.create(request, layers, origin=origin, limit=capacity, initial=initial)

    def snapshot(self, request):
        return self._engine.snapshot(request)

    def step(self, request, count):
        c = self.snapshot(request)
        result = StepV2(*c.descriptor, c.request, c.epoch, c.revision, c.origin,
                        c.limit, c.origin+c.limit, c.position, count)
        self._check_step(result, c)
        return result

    def _check_step(self, step, context):
        require(type(step) is StepV2, 'Step')
        for value in (step.checkpoint_descriptor_id, step.graph_version, step.recipe_version, step.request):
            label(value, 'Step')
        for value in (step.epoch, step.revision, step.endpoint, step.position, step.count):
            integer(value, 0, 2**31-1, 'Step')
        integer(step.origin, 0, 2**31-9, 'Step')
        integer(step.capacity, 1, 8, 'Step')
        require(step.endpoint == step.origin+step.capacity and step.count > 0
                and step.origin <= step.position < step.endpoint
                and step.position+step.count <= step.endpoint, 'Step')
        require((step.checkpoint_descriptor_id,step.graph_version,step.recipe_version) == context.descriptor
                and (step.request,step.epoch,step.revision,step.origin,step.capacity,step.position)
                == (context.request,context.epoch,context.revision,context.origin,context.limit,context.position), 'Step')

    def _identity(self, selection):
        require(type(selection) is storage.Selection and type(selection.identity) is storage.Identity, 'Identity')
        identity = selection.identity
        for value in identity.__dict__.values():
            label(value)
        descriptor = self._engine.descriptor
        require((identity.checkpoint,identity.graph,identity.recipe) == descriptor, 'Identity')
        if identity.layer == 'trunk':
            expected = ('trunk', 'trunk-provenance', 'none')
        else:
            require(identity.layer in LABELS, 'Identity')
            expected = ('tokens/'+identity.layer, 'token-operands', 'none')
        require((identity.tensor,identity.role,identity.expert) == expected, 'Identity')

    def seal(self, source, selection, shape):
        self._idle()
        require(len(self._grants) < 4, 'Slots')
        require(isinstance(source, storage.SyntheticSource), 'Identity')
        source.check(selection)
        self._identity(selection)
        require(type(shape) is tuple and 1 <= len(shape) <= 2, 'Geometry')
        for value in shape:
            integer(value, 1, 1024, 'Geometry')
        require(all(g.source is not source for g in self._grants.values()), 'Authority')
        integer(selection.offset, 0, storage.U64_MAX, 'Geometry')
        integer(selection.length, 1, 1024, 'Geometry')
        require(selection.offset+selection.length <= len(source._data)
                and selection.offset+selection.length <= storage.U64_MAX
                and selection.logical_bytes == selection.length, 'Geometry')
        token = Grant()
        self._grants[token] = _Grant(source, selection, shape)
        return token

    def _preflight(self, records):
        s = self._storage
        require(s.live_slots+len(records) <= s.slots, 'Slots')
        require(all(cap >= amount for cap,amount in zip(self._caps,ACTIVE)), 'LogicalBudget')
        proposed = list(s.ledger)
        for r in records:
            cap = storage.add(r.selection.length,7)//8*8
            require(cap <= 4096, 'Geometry')
            category = 0 if r.selection.identity.layer == 'trunk' else 1
            for idx,amount in ((category,cap),(3,8),(4,cap)):
                proposed[idx] = storage.add(proposed[idx],amount)
        try:
            s._validate_budget(proposed)
        except storage.Refusal as error:
            raise AdapterRefusal('Budget') from error

    def intent(self, step, grants):
        self._idle()
        require(type(step) is StepV2, 'Step')
        try:
            before = self.snapshot(step.request)
        except ValueError as error:
            raise AdapterRefusal('Step') from error
        self._check_step(step, before)
        require(type(grants) is tuple, 'Authority')
        require(all(type(g) is Grant and g in self._grants for g in grants), 'Authority')
        require(len(set(grants)) == len(grants), 'Geometry')
        records = tuple(self._grants[g] for g in grants)
        for r in records:
            r.source.check(r.selection)
            self._identity(r.selection)
        expected = tuple(str(lid) for lid,_ in before.layers)+('trunk',)
        require(tuple(r.selection.identity.layer for r in records) == expected, 'Geometry')
        for r in records:
            lid = r.selection.identity.layer
            shape = (16,) if lid == 'trunk' else (step.count,16 if lid in ('3','7') else 10)
            length = 16 if lid == 'trunk' else 8*shape[0]*shape[1]
            require(type(r.shape) is tuple and all(type(x) is int for x in r.shape)
                    and r.shape == shape and r.selection.length == length
                    and r.selection.logical_bytes == length, 'Geometry')
        self._preflight(records)
        self._room(56)
        token = Intent()
        self._active = _Work(token, step, before, grants)
        self._ledger = ACTIVE
        self._event('intent')
        return token

    def _work(self, token, phases=None):
        if self._active is None or token is not self._active.token:
            raise AdapterRefusal('Phase' if token is self._terminal else 'Authority')
        w = self._active
        require(not w.cancelled, 'Phase')
        if phases is not None:
            require(w.phase in phases, 'Phase')
        return w

    def _index(self, w, i):
        integer(i, 0, len(w.records)-1, 'Geometry')

    def _storage_step(self, step):
        return storage.Step(step.request,step.checkpoint_descriptor_id,step.graph_version,
                            step.recipe_version,step.epoch,step.position,step.count,step.endpoint)

    def _boundary(self, step):
        return storage.Boundary(step.request,step.epoch,step.position)

    def _entry(self, rec):
        return self._storage._entry(rec.token,OWNER,allow_cancelled=True)

    def _live(self, w):
        require(self.snapshot(w.step.request) == w.before, 'Step')
        self._check_step(w.step, w.before)
        for rec in w.records:
            rec.record.source.check(rec.record.selection)
            entry = self._entry(rec)
            require(entry.selection is rec.record.selection and entry.source is rec.record.source
                    and entry.step == self._storage_step(w.step), 'Authority')

    def _operation(self, w, phase, index, function):
        self._room()
        try:
            return function()
        except Exception as original:
            self._event(f'error:{phase}:{index() if callable(index) else index}')
            try:
                self.drain(w.token)
            except Exception as cleanup:
                self._cleanup_errors = (type(cleanup).__name__, str(cleanup))
                raise original from cleanup
            raise

    def reserve(self, token):
        w = self._work(token, ('intent',))
        failed_index = [-1]
        def act():
            for i,g in enumerate(w.grants):
                failed_index[0] = i
                r = self._grants[g]
                trunk = r.selection.identity.layer == 'trunk'
                try:
                    lease = self._storage.reserve(r.source,r.selection,self._storage_step(w.step),
                        self._boundary(w.step),OWNER,category='trunk' if trunk else 'experts',scratch=8,protected=trunk)
                except storage.Refusal as error:
                    if error.code in ('Budget','Slots'):
                        raise AdapterRefusal('Invariant') from error
                    raise
                self._used = True
                w.records.append(_Lease(g,r,lease))
                self._event(f'reserve:{i}')
            w.phase = 'reserved'
        self._operation(w,'reserve',lambda: failed_index[0],act)

    def begin_read(self, token, i):
        w = self._work(token, ('reserved',))
        self._index(w,i)
        require(i == w.reading, 'Phase')
        def act():
            self._storage.begin_read(w.records[i].token,OWNER)
            w.phase = 'reading'
            self._event(f'begin_read:{i}')
        self._operation(w,'begin_read',i,act)

    def read(self, token, i):
        w = self._work(token, ('reading',))
        self._index(w,i)
        require(i == w.reading, 'Phase')
        def act():
            done = self._storage.read(w.records[i].token,OWNER)
            if done:
                w.reading += 1
                w.phase = 'read_complete' if w.reading == len(w.records) else 'reserved'
                self._event(f'read_complete:{i}')
            return done
        return self._operation(w,'read',i,act)

    def admit(self, token, i):
        w = self._work(token, ('read_complete',))
        self._index(w,i)
        require(i == w.admitted, 'Phase')
        def act():
            self._storage.admit(w.records[i].token,OWNER)
            w.admitted += 1
            if w.admitted == len(w.records):
                w.phase = 'ready'
            self._event(f'admit:{i}')
        self._operation(w,'admit',i,act)

    def capture(self, token):
        w = self._work(token)
        require(not w.captured, 'CopyOnce')
        require(w.phase == 'ready', 'Phase')
        def act():
            for rec in w.records:
                require(rec.copy is None, 'CopyOnce')
                rec.copy = self._storage.payload(rec.token,OWNER)
                lid = rec.record.selection.identity.layer
                if lid != 'trunk':
                    require(int(lid) not in w.decoded, 'CopyOnce')
                    w.decoded[int(lid)] = decode(rec.copy,'sparse' if lid in ('3','7') else 'kda',w.step.count)
            w.captured = True
            w.phase = 'captured'
            self._event('capture')
        self._operation(w,'capture',-1,act)

    def pin(self, token):
        w = self._work(token, ('captured',))
        def act():
            for i,rec in enumerate(w.records):
                self._storage.pin(rec.token,OWNER)
                self._event(f'pin:{i}')
            w.phase = 'pinned'
        self._operation(w,'pin',-1,act)

    def dispatch(self, token):
        w = self._work(token, ('pinned',))
        def act():
            self._live(w)
            for i,rec in enumerate(w.records):
                entry = self._entry(rec)
                require(entry.pinned and entry.phase == 'ready', 'Authority')
                self._storage.dispatch(rec.token,OWNER,self._storage_step(w.step),self._boundary(w.step))
                self._dispatch_id += 1
                lid = rec.record.selection.identity.layer
                rec.proof = _Proof(rec.grant,rec.record.source,rec.record.selection,
                    rec.record.selection.identity,rec.record.shape,OWNER,rec.token,self._storage,
                    entry.slot,entry.generation,w.step,w.before.revision,self._dispatch_id,
                    hashlib.sha256(rec.copy).hexdigest(),None if lid == 'trunk' else w.decoded[int(lid)])
                self._event(f'dispatch:{i}')
            w.phase = 'dispatched'
        self._operation(w,'dispatch',-1,act)

    def _proofs(self, w):
        self._live(w)
        for i,rec in enumerate(w.records):
            p = rec.proof
            e = self._entry(rec)
            require(p is not None and p.grant is rec.grant and p.source is rec.record.source
                    and p.selection is rec.record.selection and p.identity == rec.record.selection.identity
                    and p.shape == rec.record.shape and p.owner == OWNER and p.token is rec.token
                    and p.storage is self._storage and (p.slot,p.generation) == (e.slot,e.generation)
                    and p.step == w.step and p.revision == w.before.revision and p.dispatch_id == i+1
                    and hashlib.sha256(rec.copy).hexdigest() == p.digest and e.pinned, 'Authority')
            lid = p.identity.layer
            require(p.decoded is (None if lid == 'trunk' else w.decoded[int(lid)]), 'Authority')

    def prepare(self, token):
        w = self._work(token, ('dispatched',))
        def act():
            self._proofs(w)
            require(all(self._entry(r).pending == 'dispatch' for r in w.records), 'Authority')
            w.proposal_required = tuple(r.proof for r in w.records)
            w.proposal_consumed = tuple(r.proof for r in w.records if r.proof.decoded is not None)
            self._prepare_calls += 1
            w.proposal = self._engine.prepare(model.Step(w.before.descriptor,w.step.request,w.step.epoch,
                w.step.position,w.step.count,w.step.capacity),w.decoded)
            w.phase = 'prepared'
            self._event('prepare')
        self._operation(w,'prepare',-1,act)

    def complete(self, token, i):
        w = self._work(token, ('prepared',))
        self._index(w,i)
        rec = w.records[i]
        require(rec.completion is None, 'Phase')
        def act():
            receipt = self._storage.acknowledge(rec.token,OWNER)
            capability = Completion()
            self._receipts[capability] = (rec.proof,receipt)
            rec.completion = capability
            rec.receipt = receipt
            self._event(f'ack:{i}:{receipt.status}')
            return capability
        return self._operation(w,'ack',i,act)

    def _required(self, w):
        expected = tuple(r.proof for r in w.records)
        require(len(w.proposal_required) == len(expected)
                and all(x is y for x,y in zip(w.proposal_required,expected))
                and w.proposal_consumed == tuple(p for p in expected if p.decoded is not None), 'Authority')

    def _bound_proof(self, w, i, rec):
        try:
            rec.record.source.check(rec.record.selection)
        except storage.Refusal as error:
            raise AdapterRefusal('Authority') from error
        p = rec.proof
        e = self._entry(rec)
        lid = p.identity.layer
        require(p.grant is rec.grant and p.identity == rec.record.selection.identity
                and p.shape == rec.record.shape and p.step == w.step
                and p.revision == w.before.revision and p.dispatch_id == i+1
                and p.slot == e.slot and p.token is rec.token and p.storage is self._storage and p.generation == e.generation
                and p.selection is e.selection and p.source is e.source and p.owner == e.owner
                and p.digest == hashlib.sha256(rec.copy).hexdigest()
                and p.decoded is (None if lid == 'trunk' else w.decoded[int(lid)]), 'Authority')

    def _validate_receipts(self, w, completions):
        require(type(completions) is tuple and len(completions) == len(w.records)
                and len(set(completions)) == len(completions), 'Completion')
        self._required(w)
        require(all(type(c) is Completion and c in self._receipts for c in completions), 'Authority')
        require(set(completions) == {r.completion for r in w.records}, 'Authority')
        for rec in w.records:
            proof,receipt = self._receipts[rec.completion]
            require(proof is rec.proof and receipt is rec.receipt and receipt.step == self._storage_step(w.step), 'Authority')
        for i,rec in enumerate(w.records):
            self._bound_proof(w,i,rec)
        require(all(self._receipts[c][1].status == 'completed'
                    and not self._receipts[c][1].state_advance_owned_by_storage for c in completions)
                and all(not self._entry(r).pending and self._entry(r).pinned
                        and self._entry(r).phase == 'completed' for r in w.records), 'Completion')
        require(self.snapshot(w.step.request) == w.before, 'CAS')

    def commit(self, token, completions):
        w = self._work(token, ('prepared',))
        def act():
            self._validate_receipts(w,completions)
            try:
                outputs = self._engine.commit(w.proposal)
            except ValueError as error:
                raise AdapterRefusal('CAS') from error
            self._commit_calls += 1
            w.proposal = None
            self._issued += 1
            self._outbox = (self._issued,outputs)
            w.committed = True
            self._event('commit')
            self.drain(token)
            return self._issued
        return self._operation(w,'commit',-1,act)

    def _cleanup_entry(self, w, i, rec):
        if i in w.lost:
            return None
        try:
            return self._entry(rec)
        except storage.Refusal as error:
            if error.code not in ('Stale', 'Owner'):
                raise
            # No authority to touch this entry. Its rightful owner keeps its charges.
            w.lost.add(i)
            self._cleanup_refusals.append((i,error.code))
            self._event(f'orphan:{i}:{error.code}')
            return None

    def cancel(self, token):
        if token is self._terminal:
            return
        require(self._active is not None and token is self._active.token, 'Authority')
        w = self._active
        if w.cancelled or w.committed:
            return
        self._room()
        w.cancelled = True
        if w.proposal is not None:
            self._engine.cancel(w.proposal)
            w.proposal = None
        for i,rec in enumerate(w.records):
            e = self._cleanup_entry(w,i,rec)
            if e is None:
                continue
            if e.phase != 'cancelled' and not (e.protected and e.published):
                self._storage.cancel(rec.token,OWNER)
                self._event(f'cancel:{i}')

    def drain(self, token):
        if token is self._terminal:
            return
        require(self._active is not None and token is self._active.token, 'Authority')
        w = self._active
        require(len(self._events)+32 <= 128, 'LogicalBudget')
        if w.proposal is not None:
            self._engine.cancel(w.proposal)
            w.proposal = None
        for i,rec in enumerate(w.records):
            e = self._cleanup_entry(w,i,rec)
            if e is None:
                continue
            if e.pending == 'read':
                if not e.cancelling:
                    self._storage.cancel(rec.token,OWNER)
                    self._event(f'cancel:{i}')
                self._storage.read(rec.token,OWNER)
                self._event(f'drain_read:{i}')
            elif e.pending == 'dispatch':
                receipt = self._storage.acknowledge(rec.token,OWNER)
                self._event(f'drain_ack:{i}:{receipt.status}')
            elif e.phase not in ('completed','cancelled') and not (e.protected and e.published):
                self._storage.cancel(rec.token,OWNER)
                self._event(f'cancel:{i}')
        for i,rec in enumerate(w.records):
            e = self._cleanup_entry(w,i,rec)
            if e is None:
                continue
            if e.pinned:
                self._storage.unpin(rec.token,OWNER)
                self._event(f'unpin:{i}')
            if e.owned:
                self._storage.release(rec.token,OWNER)
                self._event(f'release:{i}')
            if not (e.protected and e.published):
                self._storage.evict(rec.token,OWNER)
                self._event(f'evict:{i}')
            rec.copy = None
        w.decoded.clear()
        w.proposal_required = ()
        w.proposal_consumed = ()
        for rec in w.records:
            rec.proof = None
            rec.completion = None
            rec.receipt = None
        w.records.clear()
        self._grants.clear()
        self._receipts.clear()
        self._active = None
        self._terminal = token
        self._ledger = SUCCESS if self._outbox is not None else IDLE
        self._event('idle')

    def reset(self, request, *, origin=0):
        require(self._outbox is None, 'Busy')
        c = self.snapshot(request)
        integer(origin,0,2**31-9,'Step')
        integer(c.epoch+1,0,2**31-1,'Step')
        integer(c.revision+1,0,2**31-1,'Step')
        self._room()
        w = self._active
        if w is not None:
            self.cancel(w.token)
        self._engine.reset(request,origin=origin)
        self._event('reset')
        if w is not None:
            self.drain(w.token)

    def _output(self, cid):
        integer(cid,1,2**31-1,'UnknownOutput')
        if self._outbox is None or cid != self._outbox[0]:
            raise AdapterRefusal('Expired' if cid <= self._issued else 'UnknownOutput')
        return self._outbox[1]

    def deliver(self, commit_id, sink=None):
        output = self._output(commit_id)
        if sink is not None:
            sink(output)
        return output

    def ack(self, commit_id):
        self._output(commit_id)
        self._room()
        self._outbox = None
        self._ledger = IDLE
        self._event('output_ack')

    def abandon(self, commit_id):
        self._output(commit_id)
        self._room()
        self._outbox = None
        self._ledger = IDLE
        self._event('output_abandon')

    def run(self, token):
        w = self._work(token, ('intent',))
        self.reserve(token)
        for i in range(len(w.records)):
            self.begin_read(token,i)
            while not self.read(token,i):
                pass
        for i in range(len(w.records)):
            self.admit(token,i)
        self.capture(token)
        self.pin(token)
        self.dispatch(token)
        self.prepare(token)
        receipts = tuple(self.complete(token,i) for i in range(len(w.records)))
        return self.commit(token,receipts)
