"""Bounded model/state preparation contracts; no native backend imports."""
import ast
from dataclasses import replace
import hashlib
import itertools
import json
import math
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts.research.glm53_flash.native_preparation_model_state_v1 import fixtures as f
from scripts.research.glm53_flash.native_preparation_model_state_v1 import oracle as o
from scripts.research.glm53_flash.native_preparation_model_state_v1 import contract as c
from scripts.research.glm53_flash.native_preparation_model_state_v1 import state as s

ROOT = Path(__file__).resolve().parents[3]
SPEC = ROOT/'specs/020-mlx-safetensors-affine/parallel-preparation/model-state-v1'


class Preparation(unittest.TestCase):
    def close(self, a, b):
        if isinstance(b, (tuple,list)):
            self.assertEqual(len(a),len(b))
            for x,y in zip(a,b):
                self.close(x,y)
        else:
            self.assertTrue(math.isfinite(a) and abs(a-b) <= 1e-12+1e-10*abs(b), (a,b))

    def setup_engine(self, name='a', origin=13, initial=True):
        engine = s.Engine(('synthetic-descriptor-v1','graph-v1','recipe-v1'))
        engine.create(name, (0,3,4,7), origin=origin,
                      initial=f.initial_kda() if initial else None)
        return engine

    def operands(self, start=0, end=7, salt=0):
        return {0:f.kda_tokens(salt=salt)[start:end],3:f.sparse_tokens(salt=salt)[start:end],
                4:f.kda_tokens(salt=salt+2)[start:end],7:f.sparse_tokens(salt=salt+2)[start:end]}

    def step(self, engine, name, operands):
        ctx = engine.snapshot(name)
        return s.Step(ctx.descriptor,name,ctx.epoch,ctx.position,len(operands[0]),ctx.limit)

    def execute(self, engine, name, operands):
        return engine.commit(engine.prepare(self.step(engine,name,operands),operands))

    def test_source_pins_and_oracle_independence(self):
        pins = json.loads((SPEC/'source-pins.json').read_text())['files']
        self.assertGreaterEqual(len(pins),30)
        for path,digest in pins.items():
            self.assertEqual(hashlib.sha256((ROOT/path).read_bytes()).hexdigest(),digest,path)
        tree = ast.parse(Path(o.__file__).read_text())
        imports = [n for n in ast.walk(tree) if isinstance(n,(ast.Import,ast.ImportFrom))]
        self.assertEqual([ast.unparse(n) for n in imports],['import math'])

    def test_all_45_dispatch_and_mutations(self):
        config = json.loads((ROOT/'scripts/research/glm53_flash/decoder_topology/upstream-config.json').read_text())['text_config']
        plan = c.dispatch(config)
        self.assertEqual(len(plan),45)
        self.assertEqual([i for i,a,_ in plan if a=='sparse'],list(range(3,44,4)))
        self.assertEqual([i for i,_,m in plan if m=='dense'],[0,1,2])
        self.assertEqual(sum(a=='kda' for _,a,_ in plan),34)
        mutations = [('first_k_dense_replace',4),('n_routed_experts',256),('scoring_func','softmax'),
                     ('model_type','qwen'),('mla_use_nope',False),('norm_topk_prob',False),
                     ('swiglu_limit',7.0),('hc_sinkhorn_iters',19),('hc_eps',1e-5),
                     ('rms_norm_eps',1e-6),('index_kpool',2),('index_topk',1024),
                     ('index_kpool_always_select_tail',False),('index_kpool_compress',False),
                     ('moe_router_dtype','bfloat16'),('num_nextn_predict_layers',2),
                     ('hidden_size',2048),('hc_mult',2),('mhc',False)]
        for key,value in mutations:
            with self.subTest(key=key), self.assertRaises(ValueError):
                c.dispatch({**config,key:value})
        for key,value in [('gate_lower_bound',None),('short_conv_kernel_size',3),
                          ('num_heads',32),('head_dim',64)]:
            bad=json.loads(json.dumps(config)); bad['linear_attn_config'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError): c.dispatch(bad)
        bad=json.loads(json.dumps(config)); bad['linear_attn_config']['kda_layers'][0]=False
        with self.assertRaises(ValueError): c.dispatch(bad)
        for field in ('layer_types','mlp_layer_types'):
            bad = json.loads(json.dumps(config)); bad[field][3] = bad[field][0]
            with self.assertRaises(ValueError): c.dispatch(bad)
        bad = json.loads(json.dumps(config)); bad['linear_attn_config']['kda_layers'][0] = 3
        with self.assertRaises(ValueError): c.dispatch(bad)

    def test_router_bias_original_mix_and_exact_ties(self):
        for scores,bias,k in [((.875,.25,.5,.125),(-1,.75,0,0),2),
                              ((.5,.5,.5,.5),(0,0,0,0),2),
                              ((.875,.25,.5,.125),(-1,.75,0,0),1)]:
            actual = c.route(scores,bias,k)
            ids,weights = o.route(scores,bias,k)
            self.assertEqual(actual.ids,ids); self.close(actual.weights,weights)
        self.assertEqual(c.route((.5,)*4,(0,)*4,2).ids,(0,1))
        actual = c.route((.875,.25,.5,.125),(-1,.75,0,0),2)
        self.assertEqual(actual.ids,(1,2))
        wrong = tuple(2.5*actual.corrected_scores[i]/sum(actual.corrected_scores[j] for j in actual.ids) for i in actual.ids)
        self.assertNotEqual(actual.weights,wrong)

    def test_dense_routed_shared_and_clamp_edges(self):
        x = (.375,-.5,.25)
        experts = [f.mlp_weights(i) for i in range(4)]; shared = f.mlp_weights(7)
        self.close(c.ffn(x,experts[0]),o.mlp(x,experts[0]))
        scores,bias=(.875,.25,.5,.125),(-1,.75,0,0)
        ids,weights=o.route(scores,bias,2)
        routed=tuple(sum(weights[j]*o.mlp(x,experts[i])[d] for j,i in enumerate(ids)) for d in range(3))
        expected=tuple(routed[d]+o.mlp(x,shared)[d] for d in range(3))
        got=c.moe(x,scores,bias,experts,shared,2)
        self.close(got,expected); self.assertNotEqual(got,routed)
        clamp=c.primitive.clamped_swiglu((-11,10,11),(-11,10,11))
        self.close(clamp,tuple(min(g,10)/(1+math.exp(-min(g,10)))*min(10,max(-10,u)) for g,u in zip((-11,10,11),(-11,10,11))))

    def test_mhc_orientation_nonidentity(self):
        case=f.mhc_case(); expected=o.mhc(case)
        collapsed=c.primitive.mhc_collapse(case['streams'],case['fn'],case['scale'],case['base'])
        expanded=c.primitive.mhc_expand(case['branch'],case['streams'],collapsed.post,collapsed.comb)
        self.close((collapsed.collapsed,collapsed.post,collapsed.comb,expanded),expected)
        wrong=c.primitive.mhc_expand(case['branch'],case['streams'],collapsed.post,tuple(zip(*collapsed.comb)))
        self.assertGreater(max(abs(a-b) for x,y in zip(expanded,wrong) for a,b in zip(x,y)),1e-4)

    def test_embedding_mean_weighted_norm_untied_head(self):
        case=f.boundary_case()
        self.close(c.boundary(case),o.boundary(case))
        streams=tuple(tuple(tuple((t+h+d-3)/8 for d in range(3)) for h in range(4)) for t in range(3))
        got=c.boundary(case,streams); self.close(got,o.boundary(case,streams))
        self.assertNotEqual(got[-1],c.boundary({**case,'head':case['embedding']},streams)[-1])
        self.assertNotEqual(got[-1],c.boundary({**case,'norm':(1,1,1)},streams)[-1])
        for ids in ((-1,), (5,), (True,)):
            with self.assertRaises(ValueError): c.boundary({**case,'ids':ids})

    def test_nonzero_unequal_kda_and_sparse_positions(self):
        engine=self.setup_engine(); result=dict(self.execute(engine,'a',self.operands()))
        ctx=engine.snapshot('a')
        for lid,salt in ((0,0),(4,2)):
            expected,rec,suffix=o.kda(f.kda_tokens(salt=salt),f.kernels(),f.initial_kda())
            self.close(result[lid],expected)
            state=dict(ctx.layers)[lid]
            self.close(state.recurrent,rec); self.close(state.suffix,suffix)
            self.assertEqual((len(state.recurrent),len(state.recurrent[0])),(2,3))
        for lid,salt in ((3,0),(7,2)):
            expected,indices=o.sparse(f.sparse_tokens(salt=salt),13)
            self.close(result[lid][0],expected); self.assertEqual(result[lid][1],indices)
            self.assertTrue(all(all(13<=j<=13+t for j in row) for t,row in enumerate(indices)))
        self.assertEqual(ctx.position,20)
        self.assertTrue(all(st.position==20 and st.epoch==0 for _,st in ctx.layers))

    def test_all_64_chunk_partitions_equal_prefill(self):
        reference=self.setup_engine(); whole=dict(self.execute(reference,'a',self.operands()))
        for cuts in itertools.product((False,True),repeat=6):
            engine=self.setup_engine(); outputs={i:[] for i in (0,3,4,7)}; selections={3:[],7:[]}
            edges=[0]+[i+1 for i,v in enumerate(cuts) if v]+[7]
            for a,b in zip(edges,edges[1:]):
                result=dict(self.execute(engine,'a',self.operands(a,b)))
                for lid in outputs:
                    outputs[lid].extend(result[lid][0] if lid in selections else result[lid])
                    if lid in selections: selections[lid].extend(result[lid][1])
            for lid in outputs:
                self.close(outputs[lid],whole[lid][0] if lid in selections else whole[lid])
                if lid in selections: self.assertEqual(tuple(selections[lid]),whole[lid][1])
            self.assertEqual(engine.snapshot('a').layers,reference.snapshot('a').layers)

    def test_reset_epoch_and_interleaved_contexts(self):
        engine=self.setup_engine(initial=False); engine.create('b',(0,3,4,7),origin=41)
        separate=self.setup_engine(name='b',origin=41,initial=False)
        for a,b in ((0,2),(2,3),(3,7)):
            self.execute(engine,'a',self.operands(a,b))
            self.assertEqual(self.execute(engine,'b',self.operands(a,b,1)),self.execute(separate,'b',self.operands(a,b,1)))
        self.assertEqual(engine.snapshot('b'),separate.snapshot('b'))
        stale=self.step(engine,'a',self.operands(0,1))
        engine.reset('a',origin=13)
        self.assertEqual(engine.snapshot('a').epoch,1)
        with self.assertRaises(ValueError): engine.prepare(stale,self.operands(0,1))
        fresh=self.setup_engine(initial=False)
        self.assertEqual(self.execute(engine,'a',self.operands()),self.execute(fresh,'a',self.operands()))

    def test_cancel_rollback_stale_commit_and_no_publication(self):
        engine=self.setup_engine(); before=engine.snapshot('a'); ops=self.operands(0,3)
        a=engine.prepare(self.step(engine,'a',ops),ops); b=engine.prepare(self.step(engine,'a',ops),ops)
        self.assertEqual(engine.snapshot('a'),before)
        self.assertIsNone(engine.cancel(a)); self.assertIsNone(engine.cancel(a))
        with self.assertRaises(ValueError): engine.commit(a)
        self.assertEqual(engine.snapshot('a'),before)
        self.assertEqual(engine.commit(b),self.execute(self.setup_engine(),'a',ops))
        committed=engine.snapshot('a'); engine.cancel(b); self.assertEqual(engine.snapshot('a'),committed)
        with self.assertRaises(ValueError): engine.commit(b)
        ops=self.operands(3,4)
        a=engine.prepare(self.step(engine,'a',ops),ops); b=engine.prepare(self.step(engine,'a',ops),ops)
        engine.commit(a)
        with self.assertRaises(ValueError): engine.commit(b)

    def test_position_identity_bounds_and_failed_prepare_atomicity(self):
        engine=self.setup_engine(); before=engine.snapshot('a'); ops=self.operands(0,1)
        step=self.step(engine,'a',ops)
        for changes in ({'position':12},{'position':14},{'epoch':1},{'count':0},{'count':True},
                        {'limit':7},{'descriptor':('different','graph-v1','recipe-v1')},{'request':'missing'}):
            with self.subTest(changes=changes),self.assertRaises(ValueError): engine.prepare(replace(step,**changes),ops)
            self.assertEqual(engine.snapshot('a'),before)
        bad=dict(ops); bad[7]=(((),(),(),(),.75),)
        with self.assertRaises(ValueError): engine.prepare(step,bad)
        self.assertEqual(engine.snapshot('a'),before)
        for bad in ({k:v for k,v in ops.items() if k!=4},{**ops,1:ops[0]}):
            with self.assertRaises(ValueError): engine.prepare(step,bad)
        self.execute(engine,'a',self.operands())
        self.execute(engine,'a',ops)
        with self.assertRaises(ValueError): engine.prepare(self.step(engine,'a',ops),ops)

    def test_state_and_edge_mutations_detected(self):
        engine=self.setup_engine(); ops=self.operands(0,2)
        self.execute(engine,'a',ops); ctx=engine.snapshot('a')
        for lid in (0,3):
            st=dict(ctx.layers)[lid]
            for changes in ({'position':st.position-1},{'epoch':st.epoch+1}):
                bad=replace(st,**changes)
                with self.assertRaises(ValueError): s.validate_layer(bad,ctx)
        st=dict(ctx.layers)[0]
        with self.assertRaises(ValueError): s.validate_layer(replace(st,recurrent=tuple(zip(*st.recurrent))),ctx)
        st=dict(ctx.layers)[3]
        with self.assertRaises(ValueError): s.validate_layer(replace(st,history=st.history[::-1]),ctx)
        with self.assertRaises(ValueError): s.validate_layer(replace(st,origin=st.origin+1),ctx)
        expected=o.kda(f.kda_tokens(),f.kernels(),f.initial_kda())[0]
        wrong=o.kda(f.kda_tokens(),tuple(tuple(reversed(row)) for row in f.kernels()),f.initial_kda())[0]
        self.assertGreater(max(abs(a-b) for x,y in zip(expected,wrong) for a,b in zip(x,y)),1e-4)
        zero=(((0.,)*3,)*2,((0.,)*7,)*2)
        self.assertNotEqual(expected,o.kda(f.kda_tokens(),f.kernels(),zero)[0])
        # Mutate an actual candidate boundary result: dropped tail is discriminated.
        result=dict(self.execute(self.setup_engine(),'a',self.operands()))[3]
        mutated=tuple(tuple(j for j in row if j!=13+t) for t,row in enumerate(result[1]))
        self.assertNotEqual(mutated,o.sparse(f.sparse_tokens(),13)[1])

    def test_sparse_exact_tie_tail_and_future_mutations(self):
        tokens=tuple(((.25,.5),(0.,0.),(.5,.25),.75,(.25,.5,-.125),
                      (t/8,-(t+1)/16,.375),(t/8,(t+1)/8,-t/16)) for t in range(7))
        expected,indices=o.sparse(tokens,101)
        engine=s.Engine(('d','g','r')); engine.create('x',(3,),origin=101)
        ctx=engine.snapshot('x'); step=s.Step(ctx.descriptor,'x',0,101,7,8)
        result=dict(engine.commit(engine.prepare(step,{3:tokens})))[3]
        self.close(result[0],expected); self.assertEqual(result[1],indices)
        self.assertEqual(indices[-1],(101,102,107))
        changed=list(tokens); changed[-1]=((7.,7.),(7.,7.),(7.,7.),.75,(7.,7.,7.),(7.,7.,7.),(7.,7.,7.))
        other=s.Engine(('d','g','r')); other.create('x',(3,),origin=101)
        mutated=dict(other.commit(other.prepare(step,{3:tuple(changed)})))[3]
        self.assertEqual(mutated[0][:-1],result[0][:-1])

    def test_sparse_index_attention_separation_and_state_ownership(self):
        engine=self.setup_engine(); ops=self.operands(); result=dict(self.execute(engine,'a',ops))[3]
        history=dict(engine.snapshot('a').layers)[3].history
        for offset,entry in enumerate(history):
            token=f.sparse_tokens()[offset]
            self.assertEqual(entry,(13+offset,token[0],token[1],token[5],token[6]))
            self.assertEqual(len(entry),5)  # no cached query or head weight
        altered=dict(ops)
        # Wrong-role mutation, padded to avoid relying only on the unequal-axis guard.
        altered[3]=tuple((*token[:5],(*token[0],0.),token[6]) for token in ops[3])
        wrong=dict(self.execute(self.setup_engine(),'a',altered))[3]
        self.assertEqual(wrong[1],result[1])  # index decisions unaffected
        self.assertGreater(max(abs(a-b) for row,expected in zip(wrong[0],result[0])
                               for a,b in zip(row,expected)),1e-5)
        # Direct role miswire fails before any publication because 2 != 3.
        altered[3]=tuple((*token[:5],token[0],token[6]) for token in ops[3])
        fresh=self.setup_engine(); before=fresh.snapshot('a')
        with self.assertRaises(ValueError): fresh.prepare(self.step(fresh,'a',altered),altered)
        self.assertEqual(fresh.snapshot('a'),before)

    def test_computation_failure_and_semantic_mutants(self):
        engine=self.setup_engine(); before=engine.snapshot('a'); ops=self.operands()
        # Fault arrives after KDA computation: all-layer publication must still be atomic.
        with patch.object(s,'sparse_transition',side_effect=ValueError('synthetic late failure')):
            with self.assertRaisesRegex(ValueError,'synthetic late failure'):
                engine.prepare(self.step(engine,'a',ops),ops)
        self.assertEqual(engine.snapshot('a'),before)
        self.assertEqual(engine._pending,{})
        expected=dict(self.execute(self.setup_engine(),'a',ops))
        original=s.kda_transition
        def lost_suffix(state,tokens):
            return original(replace(state,suffix=((0.,)*7,)*2),tokens)
        with patch.object(s,'kda_transition',lost_suffix):
            changed=dict(self.execute(self.setup_engine(),'a',ops))
        self.assertNotEqual(changed[0],expected[0])
        original_sparse=s.sparse_transition
        def shifted_indices(state,tokens):
            after,(values,indices)=original_sparse(state,tokens)
            return after,(values,tuple(tuple(i-state.origin for i in row) for row in indices))
        with patch.object(s,'sparse_transition',shifted_indices):
            changed=dict(self.execute(self.setup_engine(),'a',ops))
        self.assertNotEqual(changed[3][1],expected[3][1])
        # Corrupted internal layer wiring must be rejected, not re-dispatched by state tag.
        ctx=engine.snapshot('a'); layers=dict(ctx.layers)
        layers[0],layers[3]=layers[3],layers[0]
        engine._contexts['a']=replace(ctx,layers=tuple(sorted(layers.items())))
        with self.assertRaisesRegex(ValueError,'STATE_KIND'):
            engine.prepare(self.step(engine,'a',ops),ops)

    def test_invalid_nonfinite_operands_and_reset_invalidates_proposal(self):
        engine=self.setup_engine(); ops=self.operands(0,1); before=engine.snapshot('a')
        for bad in (float('nan'),float('inf'),True,9.):
            altered=dict(ops); row=list(altered[0][0]); row[0]=(bad,)+row[0][1:]; altered[0]=(tuple(row),)
            with self.assertRaises(ValueError): engine.prepare(self.step(engine,'a',altered),altered)
            self.assertEqual(engine.snapshot('a'),before)
        handle=engine.prepare(self.step(engine,'a',ops),ops)
        engine.reset('a',origin=3)
        with self.assertRaises(ValueError): engine.commit(handle)
        self.assertEqual(engine.snapshot('a').position,3)


if __name__=='__main__': unittest.main()
