"""Run only through the external supervisor; ambient collection is not evidence."""
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import unittest

if not os.environ.get('FLASH_ADMITTED_PHASE'):
    raise unittest.SkipTest('admitted external runner required; NOT_EXECUTED')
PHASE = Path(os.environ['FLASH_ADMITTED_PHASE'])
ROOT = PHASE.parent / 'repos/PulsarMLX'
sys.path.insert(0, str(ROOT / 'scripts/research/glm53_flash/source_environment'))
import guard
guard.verify_child_interpreter(PHASE)
import backend
import custody
import oracle

class BoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = json.loads((ROOT / 'fixtures/research/glm53-flash-source-environment-v1/cases.json').read_text())
        old = ROOT / cls.cases['old_fixture']['path']
        if guard.sha(old) != cls.cases['old_fixture']['sha256']:
            raise ValueError('predecessor fixture changed')
        cls.old = json.loads(old.read_text())
        cls.bound = backend.Boundaries(PHASE)
        cls.metrics, cls.records, cls.mutants = [], [], []

    @classmethod
    def tearDownClass(cls):
        print(json.dumps({'event':'boundary_observations', 'backend':os.environ['FLASH_ADMITTED_BACKEND'],
                          'records':cls.records, 'comparisons':cls.metrics, 'mutants':cls.mutants,
                          'distinct_mutations':len({r['id'] for r in cls.mutants}),
                          'survivors':[r['id'] for r in cls.mutants if not r['detected']],
                          'fixture_evaluations':cls.bound.evaluations,
                          'selector_execution':'EXTRACTED_CAPSULE',
                          'full_upstream_conv_call_path':'NOT_EXECUTED_NOT_QUALIFIED'}), flush=True)

    def compare(self, actual, expected, kind, label):
        self.assertEqual(backend.shape(actual), backend.shape(expected), label)
        a,b = list(backend.flat(actual)), list(backend.flat(expected))
        self.assertTrue(all(math.isfinite(v) for v in a+b), label)
        criteria = self.cases['criteria'][kind]
        errors = [abs(x-y) for x,y in zip(a,b)]
        self.metrics.append({'label':label,'kind':kind,'count':len(a),
                             'max_abs':max(errors,default=0),
                             'rmse':math.sqrt(sum(e*e for e in errors)/max(1,len(errors)))})
        self.assertTrue(all(abs(x-y)<=criteria['atol']+criteria['rtol']*abs(y) for x,y in zip(a,b)),label)

    def route(self, case, label, *, separated=True, configured=False):
        ids, weights = self.bound.route(case, configured=configured)
        original, required, eligible, gap, group_gap, suppressed = oracle.selection(case)
        self.assertEqual(len(ids),case['top_k'])
        self.assertEqual(len(set(ids)), len(ids))
        self.assertTrue(required <= set(ids) <= eligible, label)
        if separated:
            if gap is not None:
                self.assertGreater(gap, 1e-4)
            if group_gap is not None:
                self.assertGreater(group_gap, 1e-4)
            self.assertGreater(sum(original[i] for i in ids),0.1)
        self.compare(weights, oracle.weights(case,ids),'routing_weight',label)
        self.records.append({'case':label,'raw_ids':ids,'raw_paired_weights':weights,
                             'selection_margin':gap,'group_margin':group_gap,
                             'suppressed_groups':suppressed,'order_guarantee':'UNSPECIFIED'})
        return ids, weights

    def conv(self, x, weights, state, label):
        actual = self.bound.conv(x,weights,state)
        expected = oracle.convolution(x,weights,state)
        self.compare(actual[0],expected[0],'raw_conv',label+' raw')
        self.compare(actual[1],expected[1],'silu',label+' SiLU')
        self.assertEqual(actual[2],expected[2],label+' exact dyadic suffix')
        return actual

    def test_router_bias_normalization_and_scale(self):
        case = self.cases['router']
        biased,_ = self.route(case,'bias-enabled')
        plain = dict(case,bias=[0.0]*len(case['bias']))
        unbiased,_ = self.route(plain,'bias-disabled')
        self.assertNotEqual(set(biased),set(unbiased))
        self.route(dict(case,normalize=False),'normalization-disabled')
        self.route(dict(case,top_k=1),'single-selected-no-normalization')
        self.route(dict(case,scale=1.0),'unit-scaling')

    def test_live_group_selection(self):
        case = self.cases['grouped']
        ids,_ = self.route(case,'generic-grouped-bias')
        plain,_ = self.route(dict(case,bias=[0.0]*8),'generic-grouped-no-bias')
        self.assertEqual({i//4 for i in ids},{0})
        self.assertEqual({i//4 for i in plain},{1})

    def test_mask_diagnostic_and_tie_membership(self):
        ids,_ = self.route(self.cases['negative_group_mask_diagnostic'],'negative-zero-mask-diagnostic',separated=False)
        self.assertEqual({i//4 for i in ids},{1})
        self.records.append({'finding':'FLSH-SELECTOR-MASK','status':'OPEN_GENERIC_DOMAIN',
                             'behavior':'zero-masked suppressed group selected ahead of negative corrected scores',
                             'group_exclusion_intent':'NOT_QUALIFIED','configured_n_group_1':'UNAFFECTED'})
        for index in range(3):
            self.route(self.cases['ties'],'exact-ties-repeat-'+str(index),separated=False)

    def test_configured_selector(self):
        raw, receipt = custody.working_body(PHASE,'config.json')
        data = json.loads(raw,object_pairs_hook=custody.unique_object)
        conf = data.get('text_config',data)
        names = ('n_routed_experts','num_experts_per_tok','n_group','topk_group','norm_topk_prob','routed_scaling_factor','scoring_func','topk_method')
        params = {name:conf[name] for name in names}
        frozen = json.loads((ROOT/'fixtures/research/glm53-flash-source-environment-v1/configured.json').read_text())
        self.assertEqual(params,frozen['parameters'])
        e = params['n_routed_experts']
        case = {'gates':[(i-(e-1)/2)/64 for i in range(e)],'bias':[2.0]+[0.0]*(e-1),
                'top_k':params['num_experts_per_tok'],'n_group':params['n_group'],
                'topk_group':params['topk_group'],'normalize':params['norm_topk_prob'],
                'scale':params['routed_scaling_factor']}
        self.assertEqual(params['scoring_func'],'sigmoid');self.assertEqual(params['topk_method'],'noaux_tc')
        self.route(case,'artifact-configured-selector-only',configured=True)
        self.records.append({'configured_parameters':params,'metadata_sha256':receipt['sha256'],
                             'instantiated_experts':0,'upstream_logits_projection':'NOT_EXECUTED'})

    def test_conv_raw_silu_impulses_and_fresh_state(self):
        c = self.cases['convolution']
        self.conv(c['input'],c['weights'],None,'zero-state-ramp')
        self.conv(c['input'],c['weights'],c['nonzero_state'],'nonzero-left-state')
        self.conv(c['impulse'],c['weights'],None,'asymmetric-impulses')
        first = self.conv(c['input'],c['weights'],None,'fresh-first')
        second = self.conv(c['input'],c['weights'],None,'fresh-second')
        self.assertEqual(first,second)

    def test_conv_prefix_token_chunk_and_interleaved_streams(self):
        c = self.cases['convolution']; x,w = c['input'],c['weights']
        full = self.conv(x,w,c['nonzero_state'],'full-prefix')
        for chunks in ([1]*7,c['chunks']):
            state=copy.deepcopy(c['nonzero_state']); joined=[[],[]]; activated=[[],[]]; start=0
            for width in chunks:
                raw,act,state=self.conv([r[start:start+width] for r in x],w,state,'continuation-'+str(chunks)+'-'+str(start))
                for b in range(2): joined[b]+=raw[b];activated[b]+=act[b]
                start+=width
                prefix=self.conv([r[:start] for r in x],w,c['nonzero_state'],'prefix-'+str(start))
                self.compare(joined,prefix[0],'raw_conv','prefix/continuation')
                self.assertEqual(state,prefix[2])
            self.compare(joined,full[0],'raw_conv','full/chunks')
            self.compare(activated,full[1],'silu','full/chunks SiLU')
            self.assertEqual(state,full[2])
        states=[[copy.deepcopy(c['nonzero_state'][b])] for b in range(2)]; outputs=[[],[]]
        for t in range(7):
            for b in (t%2,1-t%2):
                raw,_,states[b]=self.conv([[x[b][t]]],w,states[b],'interleaved-'+str(b)+'-'+str(t))
                outputs[b]+=raw[0]
        self.compare(outputs,full[0],'raw_conv','independent-interleaved-streams')
        for b in range(2):self.assertEqual(states[b],[full[2][b]])

    def test_predecessor_convolution_bridge(self):
        k = self.old['kda']
        x=[[q+key+v for q,key,v in zip(k['q'],k['k'],k['v'])]]
        w=[[[value] for value in channel] for channel in k['conv']]
        full=self.conv(x,w,None,'old-qkv-convolution-only')
        state=None;result=[]
        for token in x[0]:
            raw,_,state=self.conv([[token]],w,state,'old-qkv-token')
            result+=raw[0]
        self.compare([result],full[0],'raw_conv','old-qkv-continuation')
        self.records.append({'edge':'C4','domain':'old dyadic q/k/v input and convolution kernels',
                             'kda_recurrent_update':'NOT_EXECUTED_NOT_QUALIFIED'})

    def aggregation_check(self, wrong=False):
        case=self.cases['router'];ids,ws=self.bound.route(case)
        experts=oracle.expert_values(self.old['composition'])
        expected,limits=oracle.aggregate(case,ids,experts)
        actual=self.bound.aggregate(ids,ws,experts,wrong_association=wrong)
        self.assertTrue(all(abs(a-b)<=bound for a,b,bound in zip(actual,expected,limits)), 'expert ID/weight composition')
        self.records.append({'case':'source-selector-to-four-fictional-experts','ids':ids,'weights':ws,
                             'actual':actual,'expected':expected,'absolute_bounds':limits})

    def test_router_expert_composition(self):
        self.aggregation_check()

    def test_eight_normal_mutated_restored_controls(self):
        c=self.cases['convolution'];case=self.cases['router'];b=self.bound
        raw=(PHASE/'source/group_expert_select.capsule.py').read_bytes()
        def normal():
            self.route(case,'control-normal-restored')
            self.conv(c['impulse'],c['weights'],None,'control-normal-restored')
            self.aggregation_check()
        def origin_mutation():
            original=b.mx.__file__
            try:
                b.mx.__file__=str(PHASE/'scratch/synthetic-wrong-origin.so')
                backend.capsule(PHASE,b.mx)
            finally:b.mx.__file__=original
        def dropped_bias():
            ids,_=b.route(dict(case,bias=[0.0]*4))
            _,required,eligible,*_=oracle.selection(case)
            self.assertTrue(required<=set(ids)<=eligible,'routing correction bias omitted')
        def conv_mutant(name):
            actual=b.conv(c['impulse'],c['weights'],None,mutation=name)
            self.compare(actual[0],oracle.convolution(c['impulse'],c['weights'])[0],'raw_conv',name)
        controls=[('changed-source-hash',lambda:backend.capsule(PHASE,b.mx,raw_override=raw+b'\n')),
                  ('missing-mx-binding',lambda:backend.capsule(PHASE,b.mx,bindings_override={})),
                  ('unexpected-selector-global',lambda:backend.validate_capsule_text(raw.replace(b'mx.sigmoid(',b'np.sigmoid('))),
                  ('wrong-module-origin',origin_mutation),('dropped-routing-bias',dropped_bias),
                  ('wrong-weight-id-association',lambda:self.aggregation_check(wrong=True)),
                  ('reversed-convolution-taps',lambda:conv_mutant('reversed-convolution-taps')),
                  ('swapped-convolution-axes',lambda:conv_mutant('swapped-convolution-axes'))]
        for name,mutant in controls:
            with self.subTest(mutation=name):
                normal();detected=False;failure=None
                try:mutant()
                except (AssertionError,ValueError,RuntimeError,NameError) as exc:
                    detected=True;failure=type(exc).__name__+': '+str(exc)[:240]
                self.mutants.append({'id':name,'detected':detected,'observation':failure,
                                     'normal_before':True,'restored_after':False})
                normal();self.mutants[-1]['restored_after']=True
                self.assertTrue(detected,name+' survived')
        self.assertEqual({m['id'] for m in self.mutants},set(self.cases['criteria']['mutation_ids'])|{'unexpected-selector-global'})

    def test_nonfinite_rejection(self):
        for value in (float('nan'),float('inf'),-float('inf')):
            for field in ('gates','bias'):
                case=copy.deepcopy(self.cases['router']);case[field][0]=value
                with self.assertRaises(backend.DomainError):self.bound.route(case)
            c=copy.deepcopy(self.cases['convolution']);c['input'][0][0][0]=value
            with self.assertRaises(backend.DomainError):self.bound.conv(c['input'],c['weights'])
        for field in ('gates','bias'):
            case=copy.deepcopy(self.cases['router']);case[field][0]=1e300
            with self.assertRaises(backend.DomainError):self.bound.route(case)
        underflow=dict(self.cases['router'],gates=[-1000.0]*4)
        evaluated_before=self.bound.evaluations
        with self.assertRaisesRegex(backend.DomainError,'nonfinite, nonnumeric or oversized value') as caught:
            self.bound.route(underflow)
        self.assertEqual(self.bound.evaluations,evaluated_before+1)
        with self.assertRaisesRegex(backend.DomainError,'selector domain'):
            self.bound.route(dict(self.cases['grouped'],topk_group=2))
        self.records.append({'case':'finite-logit-normalization-underflow',
                             'source_nonfinite_output':'REJECTED_AFTER_EVALUATION',
                             'observed_exception':str(caught.exception),'evaluation_count_increment':1,
                             'finite_numerical_parity':'NOT_CLAIMED'})
