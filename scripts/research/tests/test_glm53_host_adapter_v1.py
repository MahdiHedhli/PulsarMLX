"""MIT. PulsarMLX independent host interoperability contract tests, never native."""
import copy
from contextlib import ExitStack
import inspect
import textwrap
from dataclasses import replace
import math
import unittest
from unittest.mock import patch

from scripts.research.glm53_flash.host_adapter_v1 import adapter as a
from scripts.research.glm53_flash.host_adapter_v1 import oracle as o
from scripts.research.glm53_flash.native_preparation_storage_v1 import fixture as s
from scripts.research.glm53_flash.native_preparation_model_state_v1 import state as m


class FaultStorage(s.StorageFixture):
    """Serial synthetic faults, no asynchronous or physical evidence."""
    fault = None
    calls = 0

    def reserve(self, *args, **kwargs):
        i = self.calls
        self.calls += 1
        if self.fault and self.fault[:2] == ('reserve', i):
            if self.fault[2] == 'Stale':
                args[0].mutate()
            else:
                raise s.Refusal(self.fault[2])
        return super().reserve(*args, **kwargs)

    def begin_read(self, handle, owner, **kw):
        if self.fault == ('begin_read', self._entry(handle, owner).slot, 'error'):
            kw['fault'] = 'error'
        return super().begin_read(handle, owner, **kw)

    def admit(self, handle, owner, **kw):
        if self.fault == ('admit', self._entry(handle, owner).slot, 'error'):
            kw['fault'] = 'error'
        return super().admit(handle, owner, **kw)

    def dispatch(self, handle, owner, *args, **kw):
        if self.fault == ('dispatch', self._entry(handle, owner).slot, 'error'):
            kw['fault'] = 'error'
        return super().dispatch(handle, owner, *args, **kw)


class OracleFailure(AssertionError):
    """Only explicit unittest oracle mismatches qualify a mutation witness."""


class AdapterContracts(unittest.TestCase):
    failureException = OracleFailure

    def originals(self):
        targets = [(a.Adapter,n) for n in (
            "_preflight", "_storage_step", "_validate_receipts", "_required", "_bound_proof",
            "drain", "deliver", "_live", "intent", "dispatch", "prepare")]
        targets += [(s.StorageFixture,n) for n in ("evict","release","close","unpin")]
        targets += [(m.Engine,"commit"),(a,"decode")]
        return [(obj,name,getattr(obj,name)) for obj,name in targets]

    def make(self, layers=(0,3), count=1, origin=13, limits=None, total=None,
             caps=(65536,32768,8192,8192), token=o.K, bad=None, fault=None,
             actions=(), baseline=(0,)*6):
        if limits is None:
            limits = (16,288,0,32,304,0) if len(layers)==3 else (
                (16,1664,0,24,1680,0) if count==8 else (16,256,0,24,224,0))
        if total is None:
            total = 640 if len(layers)==3 else (3384 if count==8 else 472)
        storage = FaultStorage(total, limits, baseline=baseline)
        storage.fault = fault
        adapter = a.Adapter(o.DESCRIPTOR, storage, caps=caps)
        adapter.create('A', layers, origin=origin, capacity=8, initial=o.INITIAL)
        sources, grants = [], []
        for lid in layers:
            data = o.payload(o.S if lid in (3,7) else token, count)
            if bad is not None and lid == layers[0]: data = bad + data[8:]
            identity = s.Identity(o.DESCRIPTOR[0], 'tokens/'+str(lid), 'token-operands', str(lid), 'none', o.DESCRIPTOR[2], o.DESCRIPTOR[1])
            source = s.SyntheticSource(data, identity, chunk=5, actions=actions if lid==3 else ())
            sources.append(source)
            grants.append(adapter.seal(source, source.select(0,len(data)), (count,16 if lid in (3,7) else 10)))
        identity = s.Identity(o.DESCRIPTOR[0], 'trunk', 'trunk-provenance', 'trunk', 'none', o.DESCRIPTOR[2], o.DESCRIPTOR[1])
        source = s.SyntheticSource(o.TRUNK, identity, chunk=5, actions=())
        sources.append(source)
        grants.append(adapter.seal(source, source.select(0,16), (16,)))
        return adapter, storage, sources, tuple(grants), adapter.step('A',count)

    def code(self, code, fn, *args, **kw):
        with self.assertRaises((a.AdapterRefusal,s.Refusal)) as caught:
            fn(*args, **kw)
        self.assertEqual(caught.exception.code, code)

    def near(self, x, y):
        if isinstance(y, tuple):
            self.assertEqual(len(x),len(y))
            for v,w in zip(x,y): self.near(v,w)
        else: self.assertLessEqual(abs(x-y),1e-12+1e-12*abs(y))

    def phase(self, adapter, intent, n=3, until='prepare'):
        adapter.reserve(intent)
        if until=='reserved': return
        for i in range(n):
            adapter.begin_read(intent,i)
            if until=='reading': return
            while not adapter.read(intent,i): pass
        if until=='read_complete': return
        for i in range(n): adapter.admit(intent,i)
        if until=='ready': return
        adapter.capture(intent)
        if until=='captured': return
        adapter.pin(intent)
        if until=='pinned': return
        adapter.dispatch(intent)
        if until=='dispatched': return
        adapter.prepare(intent)
        if until=='partial': adapter.complete(intent,0)

    def terminal(self, adapter, storage, retained=True):
        self.assertEqual(storage.ledger, o.TERMINAL if retained else o.ZERO)
        self.assertEqual(storage.live_slots, 1 if retained else 0)
        self.assertEqual(adapter.ledger,o.IDLE)
        self.assertEqual(tuple(storage._generations),(1,1,1,0))
        self.assertEqual(adapter.commit_calls,0)

    def test_literal_success_and_protected_terminal(self):
        ad,st,src,g,step=self.make();before=ad.snapshot('A');h=ad.intent(step,g)
        self.assertEqual(ad.ledger,o.ACTIVE);cid=ad.run(h);outputs=dict(ad.deliver(cid))
        self.assertEqual(outputs[0],((0.,0.,0.),));self.assertEqual(outputs[3],(((1.,-2.,3.),),((13,),)))
        after=ad.snapshot('A');self.assertEqual((after.epoch,after.position,after.revision),(0,14,1))
        self.near(after.layers[0][1].recurrent,o.kda_expected()[1])
        self.assertEqual(after.layers[1][1].history,((13,o.S[0],o.S[1],o.S[5],o.S[6]),))
        seen={e[0]:e for e in ad.events}
        for label,ledger,slots in o.SUCCESS_EVENTS:
            self.assertEqual(seen[label][1:3],(ledger,slots))
        self.assertEqual(st.ledger,o.TERMINAL);self.assertEqual(ad.ledger,o.SUCCESS)
        self.assertEqual((ad.prepare_calls,ad.commit_calls,st.dispatches),(1,1,3))
        self.code('Owner',st.close)
        e=next(iter(st._entries.values()));self.code('Protected',st.evict,e.token,e.owner)
        self.assertNotEqual(before,after);ad.ack(cid);self.assertEqual(ad.ledger,o.IDLE)
        self.code('Used',ad.intent,ad.step('A',1),g)

    def test_nonzero_unequal_axes_and_origin_zero(self):
        for origin in (0,13):
            ad,st,_,g,step=self.make(origin=origin,token=o.NZ)
            out=dict(ad.deliver(ad.run(ad.intent(step,g))))
            expected=o.kda_expected(o.NZ)
            self.near(out[0],expected[0]);state=ad.snapshot('A').layers[0][1]
            self.near(state.recurrent,expected[1]);self.near(state.suffix,expected[2])
            self.assertEqual(out[3][1],((origin,),))

    def test_three_layers_and_count_eight(self):
        for layers,count,total in (((0,3,4),1,640),((0,3),8,3384)):
            ad,st,_,g,step=self.make(layers=layers,count=count)
            cid=ad.run(ad.intent(step,g));out=dict(ad.deliver(cid))
            self.assertEqual(st.total,total);self.assertEqual(st.ledger,o.TERMINAL)
            events={e[0]:e for e in ad.events}
            reserves=((0,80,0,8,80,0),(0,208,0,16,208,0),(0,288,0,24,288,0),(16,288,0,32,304,0)) if count==1 else ((0,640,0,8,640,0),(0,1664,0,16,1664,0),(16,1664,0,24,1680,0))
            admissions=((16,288,0,32,224,0),(16,288,0,32,96,0),(16,288,0,32,16,0),(16,288,0,32,0,0)) if count==1 else ((16,1664,0,24,1040,0),(16,1664,0,24,16,0),(16,1664,0,24,0,0))
            for i,(reserve,admit) in enumerate(zip(reserves,admissions)):
                self.assertEqual(events[f'reserve:{i}'][1:3],(reserve,i+1))
                self.assertEqual(events[f'admit:{i}'][1],admit)
                scratch=(24,16,8,0)[i] if count==1 else (16,8,0)[i]
                self.assertEqual(events[f'ack:{i}:completed'][1],(16,288 if count==1 else 1664,0,scratch,0,0))
            self.assertEqual(tuple(st._generations),(1,1,1,1) if len(layers)==3 else (1,1,1,0))
            self.assertEqual(ad.snapshot('A').position,13+count)
            self.near(ad.snapshot('A').layers[0][1].recurrent,o.kda_expected(count=count)[1])
            if count==8:
                self.assertEqual(out[3][1],((13,),(13,14),(13,14,15),(13,14),(13,14,17),(13,14),(13,14,19),(13,14)))
                ad.ack(cid);self.code('Step',ad.step,'A',1)

    def test_preflight_zero_effect_refusals(self):
        for limits,total,caps,expected in (
            ((16,207,0,24,224,0),472,(65536,32768,8192,8192),'Budget'),
            ((16,256,0,23,224,0),472,(65536,32768,8192,8192),'Budget'),
            ((16,256,0,24,224,0),471,(65536,32768,8192,8192),'Budget'),
            ((16,256,0,24,224,0),472,(65535,32768,8192,8192),'LogicalBudget')):
            ad,st,src,g,step=self.make(limits=limits,total=total,caps=caps)
            self.code(expected,ad.intent,step,g);self.assertEqual(st.calls,0)
            self.assertEqual((st.ledger,st.live_slots,tuple(st._generations)),(o.ZERO,0,(0,0,0,0)))
            self.assertEqual(ad.ledger,o.IDLE);self.assertEqual(sum(x.reads for x in src),0)
        ad,st,_,g,step=self.make(baseline=(16,0,0,0,0,0))
        self.code('Budget',ad.intent,step,g);self.assertEqual(st.calls,0)

    def test_step_and_identity_mutations_zero_effect(self):
        fields={'endpoint':(8,22,True),'count':(0,-1,True,2**32),'origin':(14,-1,2**31),'capacity':(0,9),'position':(12,21),'epoch':(1,True),'revision':(1,True),'request':('B','x'*65),'graph_version':('bad',),'recipe_version':('bad',),'checkpoint_descriptor_id':('bad',)}
        for key,values in fields.items():
            for value in values:
                with self.subTest(key=key,value=value):
                    ad,st,_,g,step=self.make();self.code('Step',ad.intent,replace(step,**{key:value}),g)
                    self.assertEqual(st.calls,0);self.assertEqual(ad.snapshot('A').position,13)

    def test_decode_literals_signed_zero_endian_and_refusals(self):
        for word in ('0000000000000080','3ff0000000000000'):
            ad,st,_,g,step=self.make(bad=bytes.fromhex(word));h=ad.intent(step,g);self.phase(ad,h,until='captured')
            value=ad._active.decoded[0][0][0][0]
            self.assertEqual(value,o.decode_word(bytes.fromhex(word)))
            self.assertEqual(math.copysign(1,value),math.copysign(1,o.decode_word(bytes.fromhex(word))))
            ad.cancel(h);ad.drain(h);self.terminal(ad,st)
        for word in ('000000000000f87f','000000000000f07f','0000000000002240'):
            ad,st,_,g,step=self.make(bad=bytes.fromhex(word));before=ad.snapshot('A')
            self.code('Geometry',ad.run,ad.intent(step,g));self.terminal(ad,st)
            self.assertEqual((st.dispatches,ad.prepare_calls),(0,0));self.assertEqual(ad.snapshot('A'),before)

    def test_partial_reserve_never_rolls_generation_back(self):
        for error,expected in (('Stale','Stale'),('Budget','Invariant'),('Slots','Invariant')):
            ad,st,_,g,step=self.make(fault=('reserve',1,error))
            self.code(expected,ad.run,ad.intent(step,g));self.assertEqual(st.ledger,o.ZERO)
            self.assertEqual((st.live_slots,tuple(st._generations)),(0,(1,0,0,0)))
            self.assertEqual(ad.ledger,o.IDLE);self.assertEqual(ad.commit_calls,0)

    def test_read_and_admission_failure_literals(self):
        cases=[(('begin_read',0,'error'),(), 'Allocation',(16,128,0,16,144,0)),
               (None,('io',),'Read',(16,80,0,16,96,0)),
               (None,(0,),'ShortRead',(16,80,0,16,96,0)),
               (None,('oversize',),'ReaderCount',(16,80,0,16,96,0)),
               (None,('interrupt',)*5,'InterruptLimit',(16,80,0,16,96,0)),
               (('admit',1,'error'),(),'Admission',(16,80,0,16,16,0)),
               (('admit',2,'error'),(),'Admission',(0,208,0,16,0,0))]
        for fault,actions,code,ledger in cases:
            with self.subTest(fault=fault,actions=actions):
                ad,st,_,g,step=self.make(fault=fault,actions=actions)
                self.code(code,ad.run,ad.intent(step,g));self.terminal(ad,st,False)
                errors=[e for e in ad.events if e[0].startswith('error:')]
                self.assertEqual(errors[0][1],ledger)

    def test_dispatch_and_prepare_failures_quiesce_normally(self):
        for i in range(3):
            ad,st,_,g,step=self.make(fault=('dispatch',i,'error'));before=ad.snapshot('A')
            self.code('Dispatch',ad.run,ad.intent(step,g));self.terminal(ad,st)
            self.assertEqual(ad.snapshot('A'),before)
            receipts=[e[0] for e in ad.events if e[0].startswith('drain_ack:')]
            self.assertEqual(receipts,[f'drain_ack:{j}:completed' for j in range(i)])
        for target in ('prepare','sparse_transition'):
            ad,st,_,g,step=self.make();before=ad.snapshot('A')
            obj=ad._engine if target=='prepare' else m
            with patch.object(obj,target,side_effect=ValueError('injected prepare failure')):
                with self.assertRaises(ValueError):ad.run(ad.intent(step,g))
            self.terminal(ad,st);self.assertEqual(ad.snapshot('A'),before)
            self.assertEqual([e[0] for e in ad.events if e[0].startswith('drain_ack:')],[f'drain_ack:{j}:completed' for j in range(3)])

    def test_cancel_and_reset_every_phase_other_context_unchanged(self):
        for phase in ('reserved','reading','read_complete','ready','captured','pinned','dispatched','prepare','partial'):
            for reset in (False,True):
                with self.subTest(phase=phase,reset=reset):
                    ad,st,_,g,step=self.make();ad.create('B',(4,7),origin=2,capacity=8)
                    other=ad.snapshot('B');before=ad.snapshot('A');h=ad.intent(step,g);self.phase(ad,h,until=phase)
                    if reset:ad.reset('A',origin=20)
                    else:ad.cancel(h);ad.drain(h)
                    ev={e[0]:e[1] for e in ad.events}
                    expected={}
                    if phase in ('reserved','read_complete'):
                        expected={'cancel:0':(16,128,0,16,144,0),'cancel:1':(16,0,0,8,16,0),'cancel:2':o.ZERO}
                    elif phase=='reading':
                        expected={'cancel:0':(16,208,0,24,224,0),'cancel:1':(16,80,0,16,96,0),'cancel:2':(0,80,0,8,80,0),'drain_read:0':o.ZERO}
                    elif phase in ('ready','captured'):
                        expected={'cancel:0':(16,128,0,16,0,0),'cancel:1':(16,0,0,8,0,0),'release:2':o.TERMINAL}
                    elif phase=='pinned':
                        expected={'cancel:0':(16,208,0,16,0,0),'cancel:1':(16,208,0,8,0,0),'unpin:0':(16,128,0,8,0,0),'unpin:1':(16,0,0,8,0,0),'release:2':o.TERMINAL}
                    else:
                        expected={'drain_ack:1:cancelled':(16,208,0,8,0,0),'drain_ack:2:completed':(16,208,0,0,0,0),'unpin:0':(16,128,0,0,0,0),'unpin:1':o.TERMINAL}
                        if phase!='partial':expected['drain_ack:0:cancelled']=(16,208,0,16,0,0)
                    for label,ledger in expected.items():self.assertEqual(ev[label],ledger,(phase,reset,label))
                    retained=phase not in ('reserved','reading','read_complete')
                    self.terminal(ad,st,retained);self.assertEqual(ad.snapshot('B'),other)
                    if reset:
                        c=ad.snapshot('A');self.assertEqual((c.epoch,c.revision,c.origin,c.position),(1,1,20,20))
                        self.assertEqual(ad.step('A',1).endpoint,28)
                    else:self.assertEqual(ad.snapshot('A'),before)
                    self.code('Phase',ad.dispatch,h)
                    for e in ad.events:
                        if e[0].startswith('drain_ack:2:'):self.assertEqual(e[0],'drain_ack:2:completed')

    def test_pending_cancel_pin_charge_and_pure_phase_checks(self):
        ad,st,_,g,step=self.make();h=ad.intent(step,g);self.phase(ad,h,until='dispatched')
        before=(st.ledger,ad.events);self.code('Phase',ad.dispatch,h);self.assertEqual((st.ledger,ad.events),before)
        e=st._entries[0];self.code('InFlight',st.unpin,e.token,e.owner)
        ad.cancel(h);self.assertEqual(st.ledger,(16,208,0,24,0,0));self.assertEqual(ad.ledger,o.ACTIVE)
        self.code('Phase',ad.prepare,h);ad.drain(h);self.terminal(ad,st)
        ad,st,_,g,step=self.make();h=ad.intent(step,g);self.phase(ad,h,until='captured')
        before=(st.ledger,ad.events);self.code('CopyOnce',ad.capture,h);self.assertEqual((st.ledger,ad.events),before)
        ad.cancel(h);ad.drain(h)

    def test_completion_identity_subset_duplicate_and_cas(self):
        for kind,code in (('subset','Completion'),('duplicate','Completion'),('clone','Authority'),('cas','CAS')):
            ad,st,_,g,step=self.make();h=ad.intent(step,g);self.phase(ad,h)
            receipts=tuple(ad.complete(h,i) for i in range(3));before=ad.snapshot('A')
            if kind=='subset':receipts=receipts[:2]
            elif kind=='duplicate':receipts=(receipts[0],receipts[0],receipts[2])
            elif kind=='clone':receipts=(copy.copy(receipts[0]),)+receipts[1:]
            else:
                ad._engine._contexts['A']=replace(before,revision=7);before=ad.snapshot('A')
            self.code(code,ad.commit,h,receipts);self.terminal(ad,st);self.assertEqual(ad.snapshot('A'),before)

    def test_stale_context_before_dispatch_no_submission(self):
        ad,st,_,g,step=self.make();h=ad.intent(step,g);self.phase(ad,h,until='pinned')
        changed=replace(ad.snapshot('A'),revision=7);ad._engine._contexts['A']=changed
        self.code('Step',ad.dispatch,h);self.terminal(ad,st)
        self.assertEqual(st.dispatches,0);self.assertEqual(ad.snapshot('A'),changed)

    def test_output_redelivery_backpressure_ack_abandon_expiry(self):
        for abandon in (False,True):
            ad,st,_,g,step=self.make();h=ad.intent(step,g);cid=ad.run(h);state=ad.snapshot('A')
            out=ad.deliver(cid);counts=(ad.prepare_calls,ad.commit_calls,st.dispatches)
            def fail(_):raise OSError('synthetic delivery failure')
            with self.assertRaises(OSError):ad.deliver(cid,fail)
            self.assertIs(ad.deliver(cid),out);self.assertEqual((ad.prepare_calls,ad.commit_calls,st.dispatches),counts)
            self.code('Busy',ad.reset,'A',origin=20);self.code('Busy',ad.intent,ad.step('A',1),g)
            ad.cancel(h);self.assertEqual(ad.snapshot('A'),state);self.assertEqual(ad.ledger,o.SUCCESS)
            (ad.abandon if abandon else ad.ack)(cid);self.assertEqual(ad.snapshot('A'),state)
            self.code('Expired',ad.deliver,cid);self.code('UnknownOutput',ad.deliver,cid+1)
            ad.reset('A',origin=20);self.assertEqual((ad.snapshot('A').epoch,ad.snapshot('A').revision),(1,2))
            self.assertEqual(st.ledger,o.TERMINAL);self.code('Used',ad.intent,ad.step('A',1),g)


    def test_canonical_roles_extents_grant_identity_and_slot_five(self):
        for field,value in (('layer','00'),('layer','+3'),('layer','9'),('role','weights'),('expert','0'),('tensor','bad'),('recipe','bad'),('graph','x'*65)):
            ad,st,src,g,step=self.make()
            ident=replace(src[0].identity,**{field:value})
            bad=s.SyntheticSource(o.payload(o.K),ident,chunk=5)
            # A fresh registry isolates identity validation from the four-slot limit.
            fresh=a.Adapter(o.DESCRIPTOR,s.StorageFixture(472,(16,256,0,24,224,0)))
            self.code('Identity',fresh.seal,bad,bad.select(0,80),(1,10))
            self.assertEqual(st.calls,0)
        for transform,code in ((lambda ad,g:(copy.copy(g[0]),)+g[1:],'Authority'),
                               (lambda ad,g:g[:-1],'Geometry'),
                               (lambda ad,g:(g[0],g[0],g[2]),'Geometry')):
            ad,st,_,g,step=self.make();self.code(code,ad.intent,step,transform(ad,g));self.assertEqual(st.calls,0)
        for shape in ((1,9),(True,10),(1,10,1)):
            ad,st,_,g,step=self.make()
            rec=ad._grants[g[0]];ad._grants[g[0]]=replace(rec,shape=shape)
            self.code('Geometry',ad.intent,step,g);self.assertEqual(st.calls,0)
        ad=a.Adapter(o.DESCRIPTOR,s.StorageFixture(2000,(16,1024,0,40,1040,0)))
        ad.create('A',(0,3,4,7),origin=13,capacity=8)
        grants=[]
        for lid in (0,3,4,7):
            data=o.payload(o.S if lid in (3,7) else o.K)
            ident=s.Identity(o.DESCRIPTOR[0],'tokens/'+str(lid),'token-operands',str(lid),'none',o.DESCRIPTOR[2],o.DESCRIPTOR[1])
            source=s.SyntheticSource(data,ident,chunk=5)
            grants.append(ad.seal(source,source.select(0,len(data)),(1,16 if lid in (3,7) else 10)))
        ident=s.Identity(o.DESCRIPTOR[0],'trunk','trunk-provenance','trunk','none',o.DESCRIPTOR[2],o.DESCRIPTOR[1])
        source=s.SyntheticSource(o.TRUNK,ident,chunk=5);sel=source.select(0,16)
        self.code('Slots',ad.seal,source,sel,(16,));self.assertEqual(ad._storage.live_slots,0)
        saved=ad._grants.pop(grants[0]);trunk=ad.seal(source,sel,(16,));ad._grants[grants[0]]=saved
        self.code('Slots',ad.intent,ad.step('A',1),tuple(grants)+(trunk,))
        self.assertEqual(tuple(ad._storage._generations),(0,0,0,0))

    def test_source_selection_generation_and_stale_read(self):
        for when in ('selection','generation','read','dispatch','commit'):
            ad,st,src,g,step=self.make()
            if when=='selection':
                src[0].select(0,80);self.code('Stale',ad.intent,step,g);self.assertEqual(st.calls,0);continue
            if when=='generation':
                src[0].mutate();self.code('Stale',ad.intent,step,g);self.assertEqual(st.calls,0);continue
            h=ad.intent(step,g)
            if when=='read':
                ad.reserve(h);ad.begin_read(h,0);src[0].mutate();self.code('Stale',ad.read,h,0);self.terminal(ad,st,False)
            elif when=='dispatch':
                self.phase(ad,h,until='pinned');src[0].mutate();self.code('Stale',ad.dispatch,h);self.terminal(ad,st)
            else:
                self.phase(ad,h);receipts=tuple(ad.complete(h,i) for i in range(3));src[0].mutate()
                self.code('Authority',ad.commit,h,receipts);self.terminal(ad,st)

    def test_same_selection_foreign_token_receipt_and_provenance_mutations(self):
        for mutation in ('alien','digest','trunk','decoded','receipt'):
            ad,st,src,g,step=self.make();h=ad.intent(step,g);self.phase(ad,h)
            receipts=tuple(ad.complete(h,i) for i in range(3))
            if mutation=='alien':
                foreign=s.StorageFixture(200,(0,80,0,8,80,0));ss=ad._storage_step(step);boundary=s.Boundary('A',0,13)
                token=foreign.reserve(src[0],src[0]._selection,ss,boundary,a.OWNER,scratch=8)
                foreign.begin_read(token,a.OWNER)
                while not foreign.read(token,a.OWNER):pass
                foreign.admit(token,a.OWNER);foreign.pin(token,a.OWNER);foreign.dispatch(token,a.OWNER,ss,boundary)
                receipt=foreign.acknowledge(token,a.OWNER)
                proof,_=ad._receipts[receipts[0]]
                ad._receipts[receipts[0]]=(replace(proof,token=token,storage=foreign),receipt)
                self.code('Authority',ad.commit,h,receipts)
                foreign.unpin(token,a.OWNER);foreign.release(token,a.OWNER);foreign.evict(token,a.OWNER)
                self.assertEqual(foreign.ledger,o.ZERO)
            elif mutation=='receipt':
                proof,receipt=ad._receipts[receipts[0]]
                ad._receipts[receipts[0]]=(proof,copy.copy(receipt))
                self.code('Authority',ad.commit,h,receipts)
            elif mutation=='digest':
                proof,receipt=ad._receipts[receipts[0]]
                ad._receipts[receipts[0]]=(replace(proof,digest='0'*64),receipt)
                self.code('Authority',ad.commit,h,receipts)
            elif mutation=='trunk':
                ad._active.proposal_required=ad._active.proposal_required[:-1]
                self.code('Authority',ad.commit,h,receipts)
            else:
                ad._active.decoded[0]=(o.NZ,)
                self.code('Authority',ad.commit,h,receipts)
            self.terminal(ad,st)

    def test_permuted_completions_duplicate_and_cancelled_phase(self):
        import itertools
        for order in itertools.permutations(range(3)):
            ad,st,_,g,step=self.make();h=ad.intent(step,g);self.phase(ad,h)
            receipts=tuple(ad.complete(h,i) for i in order)
            before=(st.ledger,ad.events);self.code('Phase',ad.complete,h,order[0]);self.assertEqual((st.ledger,ad.events),before)
            cid=ad.commit(h,receipts);self.assertEqual(ad.snapshot('A').revision,1);ad.ack(cid)
        ad,st,_,g,step=self.make();h=ad.intent(step,g);self.phase(ad,h);ad.cancel(h)
        self.code('Phase',ad.commit,h,());ad.drain(h);self.terminal(ad,st)

    def test_meaningful_executed_mutation_controls(self):
        # Each defective operation is run and must contradict the same contract assertion.
        witnessed=[]
        originals=self.originals()
        def detect(name,check):
            with ExitStack() as controls:
                for obj,method,original in originals:
                    controls.enter_context(patch.object(obj,method,original))
                check()
            with self.assertRaises(OracleFailure,msg=name):check()
            witnessed.append(name)
        def preflight_check():
            ad,st,_,g,step=self.make(limits=(16,207,0,24,224,0))
            self.code('Budget',ad.intent,step,g)
            self.assertEqual(st.calls,0)
        with patch.object(a.Adapter,'_preflight',return_value=None):detect('aggregate-preflight',preflight_check)
        def endpoint_check():
            ad,st,_,g,step=self.make()
            try:ad.run(ad.intent(step,g))
            except (a.AdapterRefusal,s.Refusal):pass
            self.assertEqual(ad.snapshot('A').position,14)
        original=a.Adapter._storage_step
        with patch.object(a.Adapter,'_storage_step',lambda self,step:replace(original(self,step),context_limit=step.capacity)):
            detect('relative-endpoint',endpoint_check)
        def decode_check():
            ad,st,_,g,step=self.make(bad=bytes.fromhex('000000000000f87f'))
            try:ad.run(ad.intent(step,g))
            except (a.AdapterRefusal,s.Refusal,ValueError):pass
            self.assertEqual(st.dispatches,0)
        with patch.object(a,'decode',lambda data,kind,count:(o.K if kind=='kda' else o.S,)*count):detect('invalid-content-dispatch',decode_check)
        def missing_check():
            ad,st,_,g,step=self.make();h=ad.intent(step,g);self.phase(ad,h)
            receipt=ad.complete(h,0);self.code('Completion',ad.commit,h,(receipt,))
        with patch.object(a.Adapter,'_validate_receipts',return_value=None):detect('premature-subset-commit',missing_check)
        old_drain=a.Adapter.drain
        def bad_drain(ad,h):
            old_drain(ad,h);ad._storage._generations[:]=[0]*ad._storage.slots
        def generation_check():
            ad,st,_,g,step=self.make(fault=('reserve',1,'Stale'))
            self.code('Stale',ad.run,ad.intent(step,g));self.assertEqual(tuple(st._generations),(1,0,0,0))
        with patch.object(a.Adapter,'drain',bad_drain):detect('generation-rollback',generation_check)
        evict=s.StorageFixture.evict
        def omit(st,token,owner):
            if st._entry(token,owner,need_owner=False,allow_cancelled=True).slot!=1:evict(st,token,owner)
        def success_check():
            ad,st,_,g,step=self.make();ad.run(ad.intent(step,g));self.assertEqual(st.ledger,o.TERMINAL)
        with patch.object(s.StorageFixture,'evict',omit):detect('missing-sibling-cleanup',success_check)
        release=s.StorageFixture.release
        def free_trunk(st,token,owner):
            e=st._entry(token,owner,need_owner=False,allow_cancelled=True)
            if e.protected:e.protected=False
            release(st,token,owner)
        with patch.object(s.StorageFixture,'release',free_trunk):detect('trunk-free',success_check)
        def close_check():
            ad,st,_,g,step=self.make();ad.run(ad.intent(step,g));self.code('Owner',st.close)
        with patch.object(s.StorageFixture,'close',return_value=None):detect('ignored-close-refusal',close_check)
        deliver=a.Adapter.deliver
        def rerun(ad,cid,sink=None):
            c=ad.snapshot('A');p=ad._engine.prepare(m.Step(c.descriptor,c.request,c.epoch,c.position,1,c.limit),{0:(o.K,),3:(o.S,)})
            ad._engine.cancel(p);return deliver(ad,cid,sink)
        def retry_check():
            ad,st,_,g,step=self.make();cid=ad.run(ad.intent(step,g));seq=ad._engine._sequence
            ad.deliver(cid);self.assertEqual(ad._engine._sequence,seq)
        with patch.object(a.Adapter,'deliver',rerun):detect('redelivery-reprepare',retry_check)
        self.assertEqual(len(witnessed),9)



    def test_remaining_geometry_order_lifetime_boundaries(self):
        ad,st,src,g,step=self.make();h=ad.intent(step,g);ad.reserve(h);ad.begin_read(h,0)
        before=(st.ledger,ad.events);self.code('Phase',ad.begin_read,h,1);self.assertEqual((st.ledger,ad.events),before)
        ad.cancel(h);self.assertEqual(st.ledger,(0,80,0,8,80,0));self.assertEqual(ad.ledger,o.ACTIVE)
        ad.drain(h);self.terminal(ad,st,False)
        ad,st,_,g,step=self.make();h=ad.intent(step,g);self.phase(ad,h,until='captured')
        before=(st.ledger,ad.events);self.code('Phase',ad.dispatch,h);self.assertEqual((st.ledger,ad.events),before)
        ad.pin(h);ad.dispatch(h);ad.prepare(h)
        receipts=tuple(ad.complete(h,i) for i in range(3))
        e=st._entries[0];self.code('Phase',st.dispatch,e.token,e.owner,e.step,s.Boundary('A',0,13))
        cid=ad.commit(h,receipts);self.code('Phase',ad.commit,h,receipts);ad.ack(cid)
        self.code('Used',a.Adapter,o.DESCRIPTOR,st)
        for length in (79,81):
            st=s.StorageFixture(472,(16,256,0,24,224,0));ad=a.Adapter(o.DESCRIPTOR,st);ad.create('A',(0,))
            ident=s.Identity(o.DESCRIPTOR[0],'tokens/0','token-operands','0','none',o.DESCRIPTOR[2],o.DESCRIPTOR[1])
            src=s.SyntheticSource(bytes(length),ident,chunk=5);grant=ad.seal(src,src.select(0,length),(1,10))
            ident=replace(ident,tensor='trunk',role='trunk-provenance',layer='trunk')
            trunk=s.SyntheticSource(o.TRUNK,ident,chunk=5);tr=ad.seal(trunk,trunk.select(0,16),(16,))
            self.code('Geometry',ad.intent,ad.step('A',1),(grant,tr));self.assertEqual(st.live_slots,0)

    def test_externally_transferred_authority_remains_owned_and_charged(self):
        ad,st,_,g,step=self.make();h=ad.intent(step,g);self.phase(ad,h,until='ready');before=ad.snapshot('A')
        old=ad._active.records[0].token;new=st.transfer(old,a.OWNER,'test-owner')
        self.code('Stale',st.pin,old,a.OWNER);self.code('Stale',ad.capture,h)
        self.assertEqual(ad.snapshot('A'),before)
        self.assertEqual(st.ledger,(16,80,0,8,0,0));self.assertEqual(st.live_slots,2)
        self.assertEqual(ad.cleanup_refusals,((0,'Stale'),));self.assertEqual(ad.cleanup_errors,())
        self.assertIsNone(ad._active);self.assertEqual(ad.ledger,o.IDLE)
        self.code('Phase',ad.dispatch,h);ad.cancel(h);ad.drain(h)
        # Only the transferred lease belongs to the test owner. S was evicted by
        # the adapter and T released/retained by the adapter, without impersonation.
        st.cancel(new,'test-owner');st.release(new,'test-owner');st.evict(new,'test-owner')
        self.assertEqual(st.ledger,o.TERMINAL);self.assertIsNot(old,new)

    def test_additional_executed_mutants(self):
        witnessed=[]
        originals=self.originals()
        def detect(name,check):
            with ExitStack() as controls:
                for obj,method,original in originals:
                    controls.enter_context(patch.object(obj,method,original))
                check()
            with self.assertRaises(OracleFailure,msg=name):check()
            witnessed.append(name)
        def stale_check():
            ad,st,_,g,step=self.make();h=ad.intent(step,g);self.phase(ad,h,until='pinned')
            ad._engine._contexts['A']=replace(ad.snapshot('A'),revision=3)
            self.code('Step',ad.dispatch,h)
        with patch.object(a.Adapter,'_live',return_value=None):detect('stale-dispatch',stale_check)
        def provenance_check(kind):
            ad,st,_,g,step=self.make();h=ad.intent(step,g);self.phase(ad,h)
            receipts=tuple(ad.complete(h,i) for i in range(3))
            if kind=='trunk':ad._active.proposal_required=ad._active.proposal_required[:-1]
            else:
                proof,receipt=ad._receipts[receipts[0]]
                forged=replace(proof,digest='f'*64)
                ad._active.records[0].proof=forged
                ad._receipts[receipts[0]]=(forged,receipt)
                ad._active.proposal_required=tuple(r.proof for r in ad._active.records)
                ad._active.proposal_consumed=tuple(p for p in ad._active.proposal_required if p.decoded is not None)
            self.code('Authority',ad.commit,h,receipts)
        with patch.object(a.Adapter,'_required',return_value=None):
            detect('omitted-trunk-provenance',lambda:provenance_check('trunk'))
        with patch.object(a.Adapter,'_bound_proof',return_value=None):
            detect('wrong-receipt-provenance',lambda:provenance_check('digest'))
        intent=a.Adapter.intent
        for index,name in ((2,'omitted-copy-charge'),(3,'omitted-decoded-charge')):
            def uncharged(ad,step,grants,index=index):
                h=intent(ad,step,grants);ledger=list(ad._ledger);ledger[index]=0;ad._ledger=tuple(ledger);return h
            def charge_check():
                ad,st,_,g,step=self.make();h=ad.intent(step,g);self.phase(ad,h,until='captured')
                self.assertEqual(ad.ledger,o.ACTIVE)
            with patch.object(a.Adapter,'intent',uncharged):detect(name,charge_check)
        def rearm(ad,h):
            w=ad._active;r=w.records[0];e=ad._entry(r);e.phase='ready'
            ad._storage.dispatch(r.token,a.OWNER,e.step,s.Boundary('A',0,13))
        normal_dispatch=a.Adapter.dispatch
        def reuse_check():
            ad,st,_,g,step=self.make();h=ad.intent(step,g)
            with patch.object(a.Adapter,'dispatch',normal_dispatch):self.phase(ad,h)
            for i in range(3):ad.complete(h,i)
            self.code('Phase',ad.dispatch,h)
        with patch.object(a.Adapter,'dispatch',rearm):detect('completed-lease-reuse',reuse_check)
        def early(st,token,owner):
            e=st._entry(token,owner,allow_cancelled=True);e.pinned=False;st._drop_capacity(e)
        def pin_check():
            ad,st,_,g,step=self.make();h=ad.intent(step,g);self.phase(ad,h,until='dispatched')
            e=st._entries[0];self.code('InFlight',st.unpin,e.token,e.owner)
        with patch.object(s.StorageFixture,'unpin',early):detect('early-pending-unpin',pin_check)
        commit=m.Engine.commit
        def double(engine,handle):
            result=commit(engine,handle);c=engine.snapshot('A')
            engine._contexts['A']=replace(c,position=c.position+1,revision=c.revision+1);return result
        def once_check():
            ad,st,_,g,step=self.make();ad.run(ad.intent(step,g));self.assertEqual(ad.snapshot('A').revision,1)
        with patch.object(m.Engine,'commit',double):detect('double-state-advance',once_check)
        def retry_prepare(ad,h):
            w=ad._active
            try:ad._engine.prepare(None,{})
            except ValueError:pass
            w.proposal_required=tuple(r.proof for r in w.records)
            w.proposal_consumed=tuple(p for p in w.proposal_required if p.decoded is not None)
            w.proposal=m.Engine.prepare(ad._engine,m.Step(w.before.descriptor,w.step.request,w.step.epoch,w.step.position,w.step.count,w.step.capacity),w.decoded)
            w.phase='prepared'
        def failure_check():
            ad,st,_,g,step=self.make()
            with patch.object(ad._engine,'prepare',side_effect=ValueError('synthetic failed prepare')):
                with self.assertRaises(ValueError):ad.run(ad.intent(step,g))
        with patch.object(a.Adapter,'prepare',retry_prepare):detect('commit-after-prepare-failure',failure_check)
        self.assertEqual(len(witnessed),9)



    def test_intent_cancel_and_aggregate_scratch_io_mutants(self):
        ad,st,_,g,step=self.make();before=ad.snapshot('A');h=ad.intent(step,g)
        ad.cancel(h);ad.drain(h)
        self.assertEqual((st.ledger,st.live_slots,tuple(st._generations)),(o.ZERO,0,(0,0,0,0)))
        self.assertEqual(ad.ledger,o.IDLE);self.assertEqual(ad.snapshot('A'),before)
        for index,limits in ((3,(16,256,0,23,224,0)),(4,(16,256,0,24,223,0))):
            def undercount(ad,records,index=index):
                proposed=list(ad._storage.ledger)
                for r in records:
                    size=r.selection.length
                    proposed[0 if r.selection.identity.layer=='trunk' else 1]+=size
                    proposed[3]+=8;proposed[4]+=size
                proposed[index]-=8
                ad._storage._validate_budget(proposed)
            ad,st,_,g,step=self.make(limits=limits)
            self.code('Budget',ad.intent,step,g)
            with patch.object(a.Adapter,'_preflight',undercount):
                with self.assertRaises(OracleFailure):
                    ad,st,_,g,step=self.make(limits=limits)
                    self.code('Budget',ad.intent,step,g)



    def test_missing_receipt_before_all_acks_real_control(self):
        ad,st,_,g,step=self.make();before=ad.snapshot('A');h=ad.intent(step,g);self.phase(ad,h)
        receipt=ad.complete(h,0)
        self.code('Completion',ad.commit,h,(receipt,))
        self.terminal(ad,st);self.assertEqual(ad.snapshot('A'),before)
        labels=[e[0] for e in ad.events]
        self.assertIn('error:commit:-1',labels)
        self.assertEqual([x for x in labels if x.startswith('drain_ack:')],['drain_ack:1:completed','drain_ack:2:completed'])

    def test_individual_token_storage_slot_binding_mutants(self):
        source=textwrap.dedent(inspect.getsource(a.Adapter._bound_proof))
        def control(field):
            ad,st,_,g,step=self.make();before=ad.snapshot('A');h=ad.intent(step,g);self.phase(ad,h)
            receipts=tuple(ad.complete(h,i) for i in range(3));w=ad._active;rec=w.records[0]
            value={'token':s.PackedTensorLease(),'storage':s.StorageFixture(0,(0,)*6),'slot':3}[field]
            forged=replace(rec.proof,**{field:value});rec.proof=forged
            ad._receipts[receipts[0]]=(forged,rec.receipt)
            w.proposal_required=tuple(r.proof for r in w.records)
            w.proposal_consumed=tuple(p for p in w.proposal_required if p.decoded is not None)
            self.code('Authority',ad.commit,h,receipts)
            self.terminal(ad,st);self.assertEqual(ad.snapshot('A'),before)
        for field,clause in (('token','p.token is rec.token'),('storage','p.storage is self._storage'),('slot','p.slot == e.slot')):
            control(field)  # mandatory real-implementation positive control
            self.assertEqual(source.count(clause),1)
            namespace=dict(vars(a));exec(compile(source.replace(clause,'True'),'<public synthetic guard mutant>','exec'),namespace)
            with patch.object(a.Adapter,'_bound_proof',namespace['_bound_proof']):
                with self.assertRaises(OracleFailure,msg=field):control(field)

    def test_exact_success_sequence_generations_logical_ledger_and_prepare_order(self):
        ad,st,_,g,step=self.make();h=ad.intent(step,g);original=ad._engine.prepare;calls=[]
        def observe(model_step,operands):
            self.assertEqual(st.dispatches,3)
            self.assertTrue(all(e.pending=='dispatch' and e.pinned for e in st._entries.values()))
            self.assertEqual([e[0] for e in ad.events[-3:]],['dispatch:0','dispatch:1','dispatch:2'])
            self.assertEqual(operands,{0:(o.K,),3:(o.S,)})
            calls.append(model_step);return original(model_step,operands)
        with patch.object(ad._engine,'prepare',observe):ad.run(h)
        self.assertEqual(len(calls),1)
        expected=[]
        def row(label,ledger,slots=3,generations=(1,1,1,0),logical=o.ACTIVE):
            expected.append((label,ledger,slots,generations,logical))
        row('intent',o.ZERO,0,(0,0,0,0))
        row('reserve:0',(0,80,0,8,80,0),1,(1,0,0,0))
        row('reserve:1',(0,208,0,16,208,0),2,(1,1,0,0))
        row('reserve:2',(16,208,0,24,224,0))
        for i in range(3):
            row(f'begin_read:{i}',(16,208,0,24,224,0));row(f'read_complete:{i}',(16,208,0,24,224,0))
        row('admit:0',(16,208,0,24,144,0));row('admit:1',(16,208,0,24,16,0));row('admit:2',(16,208,0,24,0,0))
        row('capture',(16,208,0,24,0,0))
        for name in ('pin','dispatch'):
            for i in range(3):row(f'{name}:{i}',(16,208,0,24,0,0))
        row('prepare',(16,208,0,24,0,0))
        row('ack:0:completed',(16,208,0,16,0,0));row('ack:1:completed',(16,208,0,8,0,0));row('ack:2:completed',(16,208,0,0,0,0))
        row('commit',(16,208,0,0,0,0));row('unpin:0',(16,208,0,0,0,0));row('release:0',(16,208,0,0,0,0));row('evict:0',(16,128,0,0,0,0),2)
        row('unpin:1',(16,128,0,0,0,0),2);row('release:1',(16,128,0,0,0,0),2);row('evict:1',o.TERMINAL,1)
        row('unpin:2',o.TERMINAL,1);row('release:2',o.TERMINAL,1);row('idle',o.TERMINAL,1,logical=o.SUCCESS)
        self.assertEqual(ad.events,tuple(expected))

    def test_reset_other_request_serially_cancels_active_intent(self):
        ad,st,_,g,step=self.make();ad.create('B',(4,7),origin=2);before=ad.snapshot('A')
        h=ad.intent(step,g);self.phase(ad,h);ad.reset('B',origin=20)
        self.terminal(ad,st);self.assertEqual(ad.snapshot('A'),before)
        self.assertEqual((ad.snapshot('B').epoch,ad.snapshot('B').revision,ad.snapshot('B').origin),(1,1,20))
        self.code('Phase',ad.dispatch,h)

    def test_event_capacity_admits_whole_graph_before_effects(self):
        for resets in (8,9):
            ad,st,_,g,step=self.make()
            for _ in range(resets):ad.reset('A',origin=13)
            step=ad.step('A',1);before=ad.snapshot('A')
            if resets==8:
                ad.run(ad.intent(step,g));self.assertLessEqual(len(ad.events),64)
            else:
                self.code('LogicalBudget',ad.intent,step,g);self.assertEqual(st.ledger,o.ZERO)
                self.assertEqual(st.calls,0);self.assertEqual(ad.ledger,o.IDLE);self.assertEqual(ad.snapshot('A'),before)
        ad,st,_,g,step=self.make()
        for call in (lambda:ad.step('unknown',1),lambda:ad.reset('unknown')):
            with self.assertRaisesRegex(ValueError,'UNKNOWN_CONTEXT'):call()
        self.assertEqual(st.calls,0)


if __name__ == '__main__':
    unittest.main()
