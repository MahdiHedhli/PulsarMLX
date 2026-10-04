"""Independent expectations for the storage preparation fixture; no model inputs."""
import dataclasses
import importlib.util
import itertools
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parents[1] / 'glm53_flash/native_preparation_storage_v1'
SPEC = importlib.util.spec_from_file_location('storage_preparation_fixture', HERE / 'fixture.py')
m = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = m
SPEC.loader.exec_module(m)

PAYLOAD = bytes.fromhex('00112233445566778899aabbcc')  # 13 packed bytes, cap 16
BASE = (8, 0, 16, 0, 0, 8)


def setup(total=256, limits=None, actions=(), baseline=BASE, slots=4):
    identity = m.Identity('synthetic-checkpoint', 'opaque.tensor', 'declared-role',
                          'opaque-layer', 'opaque-expert', 'recipe-A', 'graph-v1')
    source = m.SyntheticSource(PAYLOAD, identity, chunk=5, actions=actions)
    selection = source.select(0, 13, logical_bytes=10**12)
    step = m.Step('request-A', identity.checkpoint, identity.graph, identity.recipe,
                  7, 11, 2, 16)
    boundary = m.Boundary('request-A', 7, 11)
    machine = m.StorageFixture(total, limits or (256,)*6, baseline, slots=slots)
    return machine, source, selection, step, boundary


def reserve(x, **kwargs):
    machine, source, selection, step, boundary = x
    return machine.reserve(source, selection, step, boundary, 'producer', scratch=8, **kwargs)


def loaded(x):
    h = reserve(x)
    x[0].begin_read(h, 'producer')
    while not x[0].read(h, 'producer'):
        pass
    x[0].admit(h, 'producer')
    return h


class StorageContracts(unittest.TestCase):
    def refusal(self, code, call):
        with self.assertRaises(m.Refusal) as caught:
            call()
        self.assertEqual(caught.exception.code, code)

    def delta(self, machine, expected):
        self.assertEqual(tuple(a-b for a,b in zip(machine.ledger, machine.baseline)), tuple(expected))
        machine.audit()

    def test_literal_adversarial_corpus(self):
        corpus = json.loads((HERE/'adversarial.json').read_text())
        self.assertEqual(corpus['schema'],'storage-v1.adversarial/1')
        self.assertEqual(corpus['read_chunk'],5)
        self.assertEqual(corpus['scratch'],8)
        self.assertEqual(bytes.fromhex(corpus['payload_hex']), PAYLOAD)
        for trace in corpus['cases']:
            with self.subTest(trace=trace['name']):
                x = setup(); machine=x[0]; h=None
                for event, expected in trace['events']:
                    def operation():
                        nonlocal h
                        if event == 'reserve': h=reserve(x)
                        elif event == 'begin': machine.begin_read(h,'producer')
                        elif event == 'admit': machine.admit(h,'producer')
                        elif event == 'dispatch': machine.dispatch(h,'producer',x[3],x[4])
                        elif event == 'ack': machine.acknowledge(h,'producer')
                        else: getattr(machine,event)(h,'producer')
                    before=machine.ledger
                    if isinstance(expected,str):
                        self.refusal(expected,operation)
                        self.assertEqual(machine.ledger,before)
                    else:
                        operation(); self.delta(machine,expected)
                self.assertEqual(machine.ledger,BASE)

    def test_budget_before_read_or_allocation(self):
        # Baseline 32 + cap16 + staging16 + scratch8 = exact72.
        for total in (71,72,73):
            x=setup(total=total)
            if total < 72:
                self.refusal('Budget',lambda:reserve(x)); self.assertEqual(x[0].ledger,BASE)
            else:
                reserve(x); self.delta(x[0],(0,16,0,8,16,0))
            self.assertEqual((x[1].reads,x[0].allocations),(0,0))
        for category in range(6):
            caps=list((256,)*6); caps[category]=BASE[category]
            if category in (1,3,4):
                x=setup(limits=tuple(caps)); self.refusal('Budget',lambda:reserve(x))
                self.assertEqual((x[1].reads,x[0].allocations),(0,0))
        self.refusal('Budget',lambda:m.StorageFixture(31,(256,)*6,BASE))

    def test_multiple_reservations_account_peak_and_slot_limit(self):
        x=setup(total=111,slots=2)
        first=reserve(x)
        self.refusal('Budget',lambda:reserve(x))
        x[0].cancel(first,'producer'); x[0].evict(first,'producer')
        x=setup(slots=2); a=reserve(x); b=reserve(x)
        self.delta(x[0],(0,32,0,16,32,0))
        self.refusal('Slots',lambda:reserve(x))
        for h in (a,b): x[0].cancel(h,'producer'); x[0].evict(h,'producer')
        self.assertEqual(x[0].ledger,BASE)

    def test_u64_ranges_and_forged_selection_pre_read(self):
        x=setup(); src=x[1]
        for offset,length,code in ((0,0,'Range'),(-1,1,'Overflow'),(2**64-1,2,'Overflow'),(12,2,'Range')):
            self.refusal(code,lambda:src.select(offset,length))
        forged=dataclasses.replace(x[2],offset=1)
        self.refusal('Stale',lambda:x[0].reserve(src,forged,x[3],x[4],'producer',scratch=8))
        self.assertEqual((src.reads,x[0].allocations),(0,0))
        self.refusal('Overflow',lambda:reserve(x,scratch_override=2**64))

    def test_packed_fidelity_partial_reads_source_close_and_transfer(self):
        x=setup(); h=loaded(x); machine=x[0]
        self.assertEqual(x[1].reads,3)
        self.assertEqual(machine.payload(h,'producer'),PAYLOAD)
        x[1].close()
        new=machine.transfer(h,'producer','consumer')
        for fn in ('payload','release','evict'):
            self.refusal('Stale',lambda:getattr(machine,fn)(h,'producer'))
        self.refusal('Owner',lambda:machine.payload(new,'producer'))
        self.assertEqual(machine.payload(new,'consumer'),PAYLOAD)
        machine.release(new,'consumer'); self.delta(machine,(0,16,0,0,0,0))
        machine.evict(new,'consumer'); self.assertEqual(machine.ledger,BASE)
        self.refusal('Stale',lambda:machine.evict(new,'consumer'))

    def test_identity_and_descriptor_staleness(self):
        x=setup(); x[1].mutate()
        self.refusal('Stale',lambda:reserve(x)); self.assertEqual(x[1].reads,0)
        for field in ('checkpoint','recipe','graph'):
            x=setup(); bad=dataclasses.replace(x[3],**{field:'wrong'})
            self.refusal('Identity',lambda:x[0].reserve(x[1],x[2],bad,x[4],'producer',scratch=8))
        x=setup(); h=reserve(x); x[0].begin_read(h,'producer'); x[0].read(h,'producer')
        x[1].mutate(); self.refusal('Stale',lambda:x[0].read(h,'producer'))
        self.assertEqual(x[0].ledger,BASE)
        x=setup(); h=reserve(x); x[0].begin_read(h,'producer')
        while not x[0].read(h,'producer'): pass
        x[1].mutate(); self.refusal('Stale',lambda:x[0].admit(h,'producer'))
        self.assertEqual(x[0].ledger,BASE)

    def test_read_faults_no_partial_publication_and_cleanup(self):
        for actions,code in (((3,0),'ShortRead'),((3,'io'),'Read'),(('oversize',),'ReaderCount'),(('interrupt',)*5,'InterruptLimit')):
            x=setup(actions=actions); h=reserve(x); x[0].begin_read(h,'producer')
            def run():
                while not x[0].read(h,'producer'): pass
            self.refusal(code,run)
            self.refusal('Cancelled',lambda:x[0].payload(h,'producer'))
            self.assertEqual(x[0].ledger,BASE)
            x[0].evict(h,'producer')
        x=setup(actions=('interrupt',2,3)); h=loaded(x)
        self.assertEqual(x[0].payload(h,'producer'),PAYLOAD)

    def test_faults_during_allocation_admission_dispatch(self):
        for phase,code in (('begin_read','Allocation'),('admit','Admission'),('dispatch','Dispatch')):
            x=setup(); h=reserve(x)
            if phase != 'begin_read':
                x[0].begin_read(h,'producer')
                while not x[0].read(h,'producer'): pass
            if phase=='dispatch': x[0].admit(h,'producer')
            args=(h,'producer',x[3],x[4]) if phase=='dispatch' else (h,'producer')
            self.refusal(code,lambda:getattr(x[0],phase)(*args,fault='error'))
            self.assertEqual(x[0].ledger,BASE); x[0].evict(h,'producer')

    def test_cancel_before_each_boundary(self):
        x=setup(); self.refusal('Cancelled',lambda:reserve(x,cancelled=True))
        self.assertEqual((x[1].reads,x[0].allocations),(0,0))
        for phase in ('begin_read','admit','dispatch'):
            x=setup(); h=reserve(x)
            if phase != 'begin_read':
                x[0].begin_read(h,'producer')
                while not x[0].read(h,'producer'): pass
            if phase=='dispatch': x[0].admit(h,'producer')
            x[0].cancel(h,'producer'); counters=(x[1].reads,x[0].allocations,x[0].dispatches)
            args=(h,'producer',x[3],x[4]) if phase=='dispatch' else (h,'producer')
            self.refusal('Cancelled',lambda:getattr(x[0],phase)(*args))
            self.assertEqual(counters,(x[1].reads,x[0].allocations,x[0].dispatches))
            x[0].cancel(h,'producer'); self.assertEqual(x[0].ledger,BASE)

    def test_cancel_during_admission_and_dispatch(self):
        x=setup(); h=reserve(x); x[0].begin_read(h,'producer')
        while not x[0].read(h,'producer'): pass
        self.refusal('Cancelled',lambda:x[0].admit(h,'producer',fault='cancel'))
        self.assertEqual(x[0].ledger,BASE)
        x=setup(); h=loaded(x)
        x[0].dispatch(h,'producer',x[3],x[4],fault='cancel')
        self.delta(x[0],(0,16,0,8,0,0))
        self.refusal('InFlight',lambda:x[0].release(h,'producer'))
        receipt=x[0].acknowledge(h,'producer')
        self.assertEqual(receipt.status,'cancelled'); self.assertEqual(receipt.step,x[3])
        self.assertFalse(receipt.state_advance_owned_by_storage)
        self.assertEqual(x[4],m.Boundary('request-A',7,11)); self.assertEqual(x[0].ledger,BASE)

    def test_step_envelope_and_no_state_advance(self):
        for change in ({'epoch':6},{'position':12},{'count':6},{'count':0},{'epoch':-1}):
            x=setup(); bad=dataclasses.replace(x[3],**change)
            self.refusal('Identity',lambda:x[0].reserve(x[1],x[2],bad,x[4],'producer',scratch=8))
            self.assertEqual((x[1].reads,x[0].allocations),(0,0))
        x=setup(); h=loaded(x)
        for field,value in (('request','B'),('checkpoint','B'),('graph','B'),('recipe','B'),('epoch',8),('position',12),('count',1),('context_limit',17)):
            self.refusal('Identity',lambda:x[0].dispatch(h,'producer',dataclasses.replace(x[3],**{field:value}),x[4]))
        self.refusal('Identity',lambda:x[0].dispatch(h,'producer',x[3],m.Boundary('request-A',8,11)))
        self.refusal('Identity',lambda:x[0].dispatch(h,'producer',x[3],m.Boundary('other-request',7,11)))
        x[0].dispatch(h,'producer',x[3],x[4]); receipt=x[0].acknowledge(h,'producer')
        self.assertEqual(receipt.status,'completed'); self.assertEqual(receipt.step,x[3])
        self.assertEqual(x[4],m.Boundary('request-A',7,11))
        self.refusal('Phase',lambda:x[0].acknowledge(h,'producer'))
        self.refusal('Phase',lambda:x[0].dispatch(h,'producer',x[3],x[4]))

    def test_pins_protection_foreign_and_reused_tokens(self):
        x=setup(); h=loaded(x); x[0].pin(h,'producer')
        for name in ('release','evict','transfer'):
            args=(h,'producer','B') if name=='transfer' else (h,'producer')
            self.refusal('Pinned',lambda:getattr(x[0],name)(*args))
        y=setup(); self.refusal('Stale',lambda:y[0].release(h,'producer'))
        x[0].unpin(h,'producer'); x[0].release(h,'producer'); x[0].evict(h,'producer')
        new=reserve(x); self.refusal('Stale',lambda:x[0].cancel(h,'producer'))
        x[0].cancel(new,'producer'); x[0].evict(new,'producer')
        x=setup(); h=reserve(x,category='trunk',protected=True)
        x[0].begin_read(h,'producer')
        while not x[0].read(h,'producer'): pass
        x[0].admit(h,'producer'); x[0].release(h,'producer')
        self.delta(x[0],(16,0,0,0,0,0)); self.refusal('Protected',lambda:x[0].evict(h,'producer'))

    def test_release_reserved_and_closed_source_error(self):
        x=setup(); h=reserve(x); x[0].release(h,'producer')
        self.delta(x[0],(0,0,0,0,0,0))  # unused reservation refunds before eviction
        x[0].evict(h,'producer')
        self.assertEqual(x[0].ledger,BASE)
        x=setup(); h=reserve(x); x[1].close()
        self.refusal('Stale',lambda:x[0].begin_read(h,'producer'))
        self.assertEqual(x[0].ledger,BASE)

    def test_read_complete_release_refunds_before_eviction(self):
        x=setup(); h=reserve(x); x[0].begin_read(h,'producer')
        while not x[0].read(h,'producer'): pass
        self.delta(x[0],(0,16,0,8,16,0))
        x[0].release(h,'producer'); self.delta(x[0],(0,0,0,0,0,0))
        x[0].evict(h,'producer'); self.assertEqual(x[0].ledger,BASE)

    def test_repeated_cycles_and_teardown(self):
        x=setup()
        for n in range(128):
            h=loaded(x)
            if n%2: x[0].cancel(h,'producer')
            else: x[0].release(h,'producer')
            x[0].evict(h,'producer'); self.assertEqual(x[0].ledger,BASE); x[0].audit()
        self.assertEqual(x[0].live_slots,0)
        self.assertEqual(x[0].max_materialized_payload,32)  # staging+resident capacities
        h=loaded(x); self.refusal('Owner',x[0].close)
        x[0].cancel(h,'producer'); x[0].evict(h,'producer'); x[0].close()
        self.assertEqual(x[0].ledger,(0,)*6)
        self.refusal('Phase',lambda:reserve(x))

    def test_independent_event_permutations(self):
        # Prospective guards: every ordering of pin, cancel, release, evict.
        for events in itertools.permutations(('pin','cancel','release','evict')):
            x=setup(); h=loaded(x); owned=True; pin=False; cancelled=False; evicted=False
            for event in events:
                if evicted: expected='Stale'
                elif event=='pin': expected='Owner' if not owned else ('Cancelled' if cancelled else None)
                elif event=='cancel': expected='Owner' if not owned else None
                elif event=='release': expected='Pinned' if pin else ('Owner' if not owned else None)
                else: expected='Pinned' if pin else ('Owner' if owned and not cancelled else None)
                call=lambda:getattr(x[0],event)(h,'producer')
                if expected: self.refusal(expected,call)
                else:
                    call()
                    if event=='pin': pin=True
                    if event=='cancel': cancelled=True
                    if event=='release': owned=False
                    if event=='evict': evicted=True
                x[0].audit()
            if not evicted:
                if pin: x[0].unpin(h,'producer')
                if owned and not cancelled: x[0].release(h,'producer')
                x[0].evict(h,'producer')
            self.assertEqual(x[0].ledger,BASE)

    def test_pinned_dispatch_cancellation_retains_until_unpin(self):
        x=setup(); h=loaded(x); x[0].pin(h,'producer')
        x[0].dispatch(h,'producer',x[3],x[4]); x[0].cancel(h,'producer')
        self.refusal('InFlight',lambda:x[0].unpin(h,'producer'))
        self.refusal('Cancelled',lambda:x[0].transfer(h,'producer','B'))
        x[0].acknowledge(h,'producer'); self.delta(x[0],(0,16,0,0,0,0))
        self.refusal('Pinned',lambda:x[0].release(h,'producer'))
        x[0].unpin(h,'producer'); self.assertEqual(x[0].ledger,BASE)
        x[0].evict(h,'producer')

    def test_scratch_release_on_completion_and_reserved_transfer(self):
        x=setup(); h=reserve(x); before=x[0].ledger
        h2=x[0].transfer(h,'producer','B'); self.assertEqual(x[0].ledger,before)
        self.refusal('Stale',lambda:x[0].begin_read(h,'producer'))
        x[0].begin_read(h2,'B')
        while not x[0].read(h2,'B'): pass
        x[0].admit(h2,'B'); x[0].dispatch(h2,'B',x[3],x[4])
        x[0].acknowledge(h2,'B'); self.delta(x[0],(0,16,0,0,0,0))
        x[0].release(h2,'B'); x[0].evict(h2,'B'); self.assertEqual(x[0].ledger,BASE)

    def test_metadata_forgery_and_overflow_refuse_atomically(self):
        x=setup(); h=reserve(x); before=x[0].ledger
        self.refusal('Stale',lambda:x[0].cancel(m.PackedTensorLease(),'producer'))
        self.assertEqual(x[0].ledger,before)
        x[0].cancel(h,'producer'); x[0].evict(h,'producer')
        self.refusal('Overflow',lambda:reserve(x,scratch_override=2**64-1))
        self.assertEqual(x[0].ledger,BASE)
        self.refusal('Identity',lambda:reserve(x,category='logical_decoded'))
        self.refusal('Slots',lambda:m.StorageFixture(256,(256,)*6,BASE,slots=5))
        for category in (0,2,5):
            limits=list((256,)*6); limits[category]=BASE[category]-1
            self.refusal('Budget',lambda:m.StorageFixture(256,tuple(limits),BASE))
        self.assertEqual((x[1].reads,x[0].allocations),(0,0))

    def test_stale_source_detected_after_injected_read_before_publication(self):
        x=setup(); h=reserve(x); original=x[1].read_at
        def changed(offset,remaining):
            result=original(offset,remaining); x[1].mutate(); return result
        x[1].read_at=changed
        x[0].begin_read(h,'producer')
        self.refusal('Stale',lambda:x[0].read(h,'producer'))
        self.assertEqual(x[0].ledger,BASE)
        self.refusal('Cancelled',lambda:x[0].payload(h,'producer'))

    def test_api_refusal_does_not_mutate_ledger(self):
        x=setup(); h=reserve(x); before=x[0].ledger
        for fn in ('payload','admit','pin','acknowledge'):
            self.refusal('Phase',lambda:getattr(x[0],fn)(h,'producer'))
            self.assertEqual(x[0].ledger,before)
        self.refusal('Owner',lambda:x[0].begin_read(h,'wrong'))
        x[0].begin_read(h,'producer')
        self.refusal('Phase',lambda:x[0].begin_read(h,'producer'))
        self.refusal('InFlight',lambda:x[0].evict(h,'producer'))
        x[0].cancel(h,'producer'); counters=(x[0].allocations,x[1].reads)
        x[0].read(h,'producer'); self.assertEqual(counters,(x[0].allocations,x[1].reads))
        x[0].audit(); self.assertEqual(x[0].ledger,BASE)

    def test_protected_resident_dispatch_faults_retain_storage(self):
        for fault in ('error','cancel'):
            x=setup(); h=reserve(x,category='trunk',protected=True)
            x[0].begin_read(h,'producer')
            while not x[0].read(h,'producer'): pass
            x[0].admit(h,'producer'); before=x[0].ledger
            self.refusal('Protected',lambda:x[0].cancel(h,'producer'))
            self.assertEqual(x[0].ledger,before)
            code='Dispatch' if fault=='error' else 'Protected'
            self.refusal(code,lambda:x[0].dispatch(h,'producer',x[3],x[4],fault=fault))
            if fault=='error': self.delta(x[0],(16,0,0,0,0,0))
            else:
                self.assertEqual(x[0].ledger,before)
                self.assertEqual(x[0].dispatches,0)
                x[0].dispatch(h,'producer',x[3],x[4])
                self.refusal('Protected',lambda:x[0].cancel(h,'producer'))
                x[0].acknowledge(h,'producer'); self.delta(x[0],(16,0,0,0,0,0))
            x[0].release(h,'producer')
            self.refusal('Protected',lambda:x[0].evict(h,'producer'))
            self.delta(x[0],(16,0,0,0,0,0))

    def test_protected_pinned_dispatch_error_survives_unpin(self):
        x=setup(); h=reserve(x,category='trunk',protected=True)
        x[0].begin_read(h,'producer')
        while not x[0].read(h,'producer'): pass
        x[0].admit(h,'producer'); x[0].pin(h,'producer')
        self.refusal('Dispatch',lambda:x[0].dispatch(h,'producer',x[3],x[4],fault='error'))
        self.delta(x[0],(16,0,0,0,0,0))
        x[0].unpin(h,'producer'); self.delta(x[0],(16,0,0,0,0,0))
        x[0].release(h,'producer'); self.refusal('Protected',lambda:x[0].evict(h,'producer'))

    def test_protected_admission_cancel_discards_unpublished_copy(self):
        x=setup(); h=reserve(x,category='trunk',protected=True)
        x[0].begin_read(h,'producer')
        while not x[0].read(h,'producer'): pass
        self.refusal('Cancelled',lambda:x[0].admit(h,'producer',fault='cancel'))
        self.assertEqual(x[0].ledger,BASE)
        self.refusal('Cancelled',lambda:x[0].payload(h,'producer'))
        x[0].evict(h,'producer'); x[0].audit(); x[0].close()

    def test_protected_post_copy_stale_discards_unpublished_copy(self):
        x=setup(); h=reserve(x,category='trunk',protected=True)
        x[0].begin_read(h,'producer')
        while not x[0].read(h,'producer'): pass
        original=x[1].check; checks=0
        def post_copy_mutation(selection):
            nonlocal checks
            checks+=1
            if checks==2: x[1].mutate()
            return original(selection)
        with mock.patch.object(x[1],'check',side_effect=post_copy_mutation):
            self.refusal('Stale',lambda:x[0].admit(h,'producer'))
        self.assertEqual(checks,2)
        self.assertEqual(x[0].ledger,BASE)
        self.refusal('Cancelled',lambda:x[0].payload(h,'producer'))
        x[0].evict(h,'producer'); x[0].audit(); x[0].close()

    def test_stale_foreign_transferred_reused_completion_refusal(self):
        x=setup(); h=loaded(x); h2=x[0].transfer(h,'producer','B')
        before=x[0].ledger
        self.refusal('Stale',lambda:x[0].acknowledge(h,'producer'))
        y=setup(); self.refusal('Stale',lambda:y[0].acknowledge(h2,'B'))
        self.assertEqual(x[0].ledger,before); self.assertEqual(y[0].ledger,BASE)
        x[0].dispatch(h2,'B',x[3],x[4]); x[0].acknowledge(h2,'B')
        x[0].release(h2,'B'); x[0].evict(h2,'B'); newer=reserve(x)
        before=x[0].ledger
        self.refusal('Stale',lambda:x[0].acknowledge(h2,'B'))
        self.assertEqual(x[0].ledger,before)
        x[0].cancel(newer,'producer'); x[0].evict(newer,'producer')

    def test_memory_errors_at_allocation_read_publication_cleanup(self):
        x=setup(); h=reserve(x)
        with mock.patch.object(m,'bytearray',side_effect=MemoryError('injected allocation'),create=True):
            self.refusal('Allocation',lambda:x[0].begin_read(h,'producer'))
        self.assertEqual(x[0].ledger,BASE)
        x=setup(); h=reserve(x); x[0].begin_read(h,'producer')
        with mock.patch.object(x[1],'read_at',side_effect=MemoryError('injected read buffer')):
            self.refusal('Allocation',lambda:x[0].read(h,'producer'))
        self.assertEqual(x[0].ledger,BASE)
        x=setup(); h=reserve(x); x[0].begin_read(h,'producer')
        while not x[0].read(h,'producer'): pass
        with mock.patch.object(m,'bytes',side_effect=MemoryError('injected publication'),create=True):
            self.refusal('Allocation',lambda:x[0].admit(h,'producer'))
        self.assertEqual(x[0].ledger,BASE)
        self.refusal('Cancelled',lambda:x[0].payload(h,'producer'))

    def test_unselected_or_wrong_request_boundary_refuses_pre_side_effect(self):
        x=setup(); source=m.SyntheticSource(PAYLOAD,x[2].identity)
        self.refusal('Stale',lambda:x[0].reserve(source,None,x[3],x[4],'producer',scratch=8))
        self.refusal('Identity',lambda:x[0].reserve(x[1],x[2],x[3],m.Boundary('B',7,11),'producer',scratch=8))
        self.assertEqual((x[1].reads,source.reads,x[0].allocations),(0,0,0))
        self.assertEqual(x[0].ledger,BASE)

    def test_mutation_witnesses_detect_leak_and_double_release(self):
        # Deliberate broken adapters; same behavioral evidence must reject them.
        class Leaking(m.StorageFixture):
            def evict(self,h,owner):
                before=self.ledger
                super().evict(h,owner)
                self._ledger=list(before)  # mutation: discarded storage remains charged
        class RetainedUnusedReservation(m.StorageFixture):
            def _drop_capacity(self,e):
                if e.phase in ('reserved','read_complete'): return  # mutation: omit refund
                super()._drop_capacity(e)
        class DoubleRelease(m.StorageFixture):
            def release(self,h,owner):
                try: super().release(h,owner)
                except m.Refusal as e:
                    if e.code != 'Owner': raise
                    self._ledger[1]-=16  # mutation: repeated release refunds resident again
        x=setup(); x=(Leaking(256,(256,)*6,BASE),*x[1:]); h=loaded(x)
        x[0].release(h,'producer'); x[0].evict(h,'producer')
        self.assertNotEqual(x[0].ledger,BASE)
        with self.assertRaises(AssertionError): x[0].audit()
        x=setup(); x=(RetainedUnusedReservation(256,(256,)*6,BASE),*x[1:]); h=reserve(x)
        x[0].release(h,'producer'); x[0].audit()  # internally consistent wrong policy
        self.assertNotEqual(x[0].ledger,BASE)  # literal release expectation detects it
        x[0].evict(h,'producer'); self.assertEqual(x[0].ledger,BASE)
        x=setup(); x=(DoubleRelease(256,(256,)*6,BASE),*x[1:]); h=loaded(x)
        x[0].release(h,'producer'); x[0].release(h,'producer')
        self.assertNotEqual(x[0].ledger,(8,16,16,0,0,8))
        with self.assertRaises(AssertionError): x[0].audit()


if __name__ == '__main__': unittest.main()
