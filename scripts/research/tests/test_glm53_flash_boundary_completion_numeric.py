"""Prospective numerical successor cases and exact-mechanism controls."""
import copy,json,math,os
from pathlib import Path
import sys,unittest
if not os.environ.get('FLASH_BOUNDARY_COMPLETION_PHASE'):
    raise unittest.SkipTest('successor supervisor required; NOT_EXECUTED')
PHASE=Path(os.environ['FLASH_BOUNDARY_COMPLETION_PHASE']);SOURCE=PHASE.parent/'repos/PulsarMLX'
sys.path.insert(0,str(SOURCE/'scripts/research/glm53_flash/boundary_completion'))
import bc_guard
bc_guard.verify_child_interpreter(PHASE)
import backend,oracle as prior_oracle
import bc_checks as check
import bc_numeric,bc_oracle

class NumericTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture=SOURCE/'fixtures/research/glm53-flash-boundary-completion-v1'
        cls.f=json.loads((fixture/'numeric.json').read_text());cls.controls=json.loads((fixture/'controls.json').read_text())
        cls.prior=json.loads((SOURCE/'fixtures/research/glm53-flash-source-environment-v1/cases.json').read_text())
        cls.old=json.loads((SOURCE/'fixtures/research/glm53-flash-tiny-v1/arithmetic.json').read_text())
        cls.b=bc_numeric.Boundaries(PHASE);cls.records=[];cls.mutations=[];cls.probes=[]
    @classmethod
    def tearDownClass(cls):
        print(json.dumps({'event':'numeric_observations','backend':os.environ['FLASH_ADMITTED_BACKEND'],
                          'records':cls.records,'controls':cls.mutations,'classifier_probes':cls.probes,
                          'fixture_evaluations':cls.b.evaluations,'distinct_controls':len({m['id'] for m in cls.mutations}),
                          'survivors':[m['id'] for m in cls.mutations if m['outcome']=='SURVIVOR'],
                          'harness_failures':[m['id'] for m in cls.mutations if m['outcome']=='HARNESS_FAILURE'],
                          'SELECTOR_EXECUTION':'EXTRACTED_CAPSULE','FULL_UPSTREAM_CONV_CALL_PATH':'NOT_EXECUTED_NOT_QUALIFIED'}),flush=True)
    def route(self,case,label):
        ids,weights=self.b.route(case)
        check.exact(set(ids),{0,3},'ROUTE_IDS_MISMATCH')
        expected=bc_oracle.route(case,ids)
        metrics=check.close(weights,expected,4e-5,4e-6,'NORMALIZATION_OFF_MISMATCH' if not case['normalize'] else 'ROUTING_WEIGHT_MISMATCH')
        self.records.append({'case':label,'normalize':case['normalize'],'raw_ids':ids,'raw_paired_weights':weights,'expected':expected,'metrics':metrics,'order':'UNSPECIFIED'})
        return dict(zip(ids,weights))
    def test_normalization_off_discriminates(self):
        case=self.f['normalization_case'];d=self.f['scalar_derivation']
        self.assertGreater(d['selection_margin'],self.f['criteria']['minimum_margin'])
        self.assertGreater(d['selected_sigmoid_sum'],1.08)
        off=self.route(case,'normalization-off');on=self.route(dict(case,normalize=True),'normalization-on')
        difference=max(abs(off[i]-on[i]) for i in off)
        self.assertGreater(difference,.01)
        self.records.append({'case':'paired-mode-discrimination','selected_sigmoid_sum':d['selected_sigmoid_sum'],'selection_margin':d['selection_margin'],'maximum_observed_mode_difference':difference,'expected_f64_mode_difference':d['maximum_mode_difference'],'scope':'GENERIC_FUNCTION; configured artifact norm remains true'})
    def kernel(self,x,state,label,mutation=False):
        before=copy.deepcopy(state)
        actual=self.b.conv_state(x,self.f['kernel_one']['weights'],state,retain_input_mutation=mutation)
        expected=bc_oracle.kernel_one(x,self.f['kernel_one']['weights'])
        self.assertEqual(state,before,'caller state mutated')
        raw=check.close(actual['raw'],expected['raw'],2e-5,2e-6,'CONV_NUMERIC_MISMATCH')
        act=check.close(actual['silu'],expected['silu'],4e-5,4e-6,'SILU_NUMERIC_MISMATCH')
        check.exact(actual['state'],expected['state'],'KERNEL_ONE_SUFFIX_MISMATCH')
        self.records.append({'case':label,'input_shape':list(backend.shape(x)),'state':actual['state'],'raw':raw,'silu':act})
        return actual
    def test_kernel_one_prefix_chunks_interleaving(self):
        f=self.f['kernel_one'];x=f['input'];full=self.kernel(x,f['empty_state'],'kernel-one-full')
        for chunks in ([1]*5,f['chunks']):
            start=0;state=copy.deepcopy(f['empty_state']);out=[[],[]];act=[[],[]]
            for size in chunks:
                result=self.kernel([batch[start:start+size] for batch in x],state,'kernel-one-chunk')
                state=result['state'];start+=size
                for b in range(2):out[b]+=result['raw'][b];act[b]+=result['silu'][b]
                prefix=self.kernel([batch[:start] for batch in x],None,'kernel-one-prefix')
                check.close(out,prefix['raw'],2e-5,2e-6,'KERNEL_ONE_PREFIX_MISMATCH');check.exact(state,prefix['state'],'KERNEL_ONE_SUFFIX_MISMATCH')
            check.close(out,full['raw'],2e-5,2e-6,'KERNEL_ONE_FULL_MISMATCH');check.close(act,full['silu'],4e-5,4e-6,'KERNEL_ONE_SILU_MISMATCH')
        states=[None,None];out=[[],[]]
        for t in range(5):
            for b in (t%2,1-t%2):
                r=self.kernel([[x[b][t]]],states[b],'kernel-one-independent-stream');states[b]=r['state'];out[b]+=r['raw'][0]
        check.close(out,full['raw'],2e-5,2e-6,'KERNEL_ONE_INTERLEAVE_MISMATCH')
        for state in states:self.assertEqual(state,{'shape':[1,0,3],'values':[[]]})
    def test_predecessor_kernel_one_expected_agreement(self):
        f=self.f['kernel_one'];raw,act,suffix=self.b.conv(f['input'],f['weights'])
        expected=bc_oracle.kernel_one(f['input'],f['weights'])
        check.close(raw,expected['raw'],2e-5,2e-6,'PREDECESSOR_K1_DIAGNOSTIC');check.close(act,expected['silu'],4e-5,4e-6,'PREDECESSOR_K1_DIAGNOSTIC');check.exact(suffix,[[],[]],'PREDECESSOR_K1_SUFFIX')
        self.records.append({'case':'predecessor-kernel-one-diagnostic','outcome':'EXPECTED_AGREEMENT_OBSERVED','empty_values_shape_metadata':'successor makes B,0,C explicit; predecessor lists carry B,0 only','historical_failure_claimed':False})
    def test_classifier_rejects_wrong_mechanisms(self):
        classes={'backend.DomainError':backend.DomainError,'builtins.NameError':NameError,'builtins.ValueError':ValueError,'bc_checks.NumericMismatch':check.NumericMismatch,'bc_checks.TemplateMismatch':check.TemplateMismatch}
        def raiser(exc):raise exc
        for name,spec in self.controls['controls'].items():
            wrong_type=check.classify(lambda:raiser(RuntimeError(spec['message_contains'][0])),spec)
            wrong_message=check.classify(lambda:raiser(classes[spec['exception_type']]('unrelated classifier probe')),spec)
            survivor=check.classify(lambda:None,spec)
            self.assertEqual(wrong_type['outcome'],'HARNESS_FAILURE');self.assertEqual(wrong_message['outcome'],'HARNESS_FAILURE');self.assertEqual(survivor['outcome'],'SURVIVOR')
            self.probes.append({'id':name,'wrong_type':wrong_type['outcome'],'wrong_message':wrong_message['outcome'],'no_exception':survivor['outcome']})
    def test_ten_specific_numeric_mutations(self):
        b=self.b;case=self.f['normalization_case'];old_case=self.prior['router'];conv=self.prior['convolution']
        raw=(bc_guard.OLD/'source/group_expert_select.capsule.py').read_bytes()
        def source_normal():
            b.select=backend.capsule(bc_guard.OLD,b.mx)
            self.route(case,'source-control-normal-restored')
        def wrong_origin():
            before=b.mx.__file__
            try:
                b.mx.__file__=str(PHASE/'scratch/synthetic-wrong-origin.so')
                backend.capsule(bc_guard.OLD,b.mx)
            finally:b.mx.__file__=before
        def drop_bias():
            ids,_=b.route(dict(old_case,bias=[0.0]*4));check.exact(set(ids),{0,3},'ROUTE_IDS_MISMATCH')
        def aggregate(wrong=False):
            ids,ws=b.route(old_case);experts=prior_oracle.expert_values(self.old['composition'])
            expected,bounds=prior_oracle.aggregate(old_case,ids,experts);actual=b.aggregate(ids,ws,experts,wrong_association=wrong)
            if any(abs(a-v)>limit for a,v,limit in zip(actual,expected,bounds)):raise check.NumericMismatch('EXPERT_PAIRING_MISMATCH')
        def convolution(mutation=None):
            actual=b.conv(conv['impulse'],conv['weights'],mutation=mutation);expected=prior_oracle.convolution(conv['impulse'],conv['weights'])
            check.close(actual[0],expected[0],2e-5,2e-6,'CONV_NUMERIC_MISMATCH')
        def force_normalization():
            ids,ws=b.route(dict(case,normalize=True));expected=bc_oracle.route(case,ids)
            check.close(ws,expected,4e-5,4e-6,'NORMALIZATION_OFF_MISMATCH')
        def k1(mutation=False):return self.kernel(self.f['kernel_one']['input'],None,'kernel-one-control',mutation)
        operations={
            'changed-source-hash':(source_normal,lambda:backend.capsule(bc_guard.OLD,b.mx,raw_override=raw+b'\n')),
            'missing-mx-binding':(source_normal,lambda:backend.capsule(bc_guard.OLD,b.mx,bindings_override={})),
            'unexpected-selector-global':(source_normal,lambda:backend.validate_capsule_text(raw.replace(b'mx.sigmoid(',b'np.sigmoid('))),
            'wrong-module-origin':(source_normal,wrong_origin),
            'dropped-routing-bias':(lambda:self.route(old_case,'bias-control'),drop_bias),
            'wrong-weight-id-association':(aggregate,lambda:aggregate(True)),
            'reversed-convolution-taps':(convolution,lambda:convolution('reversed-convolution-taps')),
            'swapped-convolution-axes':(convolution,lambda:convolution('swapped-convolution-axes')),
            'forced-normalization':(lambda:self.route(case,'normalization-control'),force_normalization),
            'kernel-one-retained-input':(k1,lambda:k1(True))}
        for name in self.controls['numeric_ids']:
            with self.subTest(control=name):
                normal,mutant=operations[name];normal();before=b.evaluations;spec=self.controls['controls'][name]
                outcome=check.classify(mutant,spec);delta=b.evaluations-before
                outcome.update({'id':name,'normal_before':True,'restored_after':False,'evaluation_delta':delta})
                self.mutations.append(outcome)
                normal();outcome['restored_after']=True
                if outcome['outcome']!='INTENDED_REJECTION':raise check.HarnessFailure(name+': '+outcome['outcome'])
                if spec['requires_evaluation'] and delta<1:raise check.HarnessFailure(name+': required evaluation absent')
                if not spec['requires_evaluation'] and delta!=0:raise check.HarnessFailure(name+': wrong execution boundary')
        self.assertEqual({r['id'] for r in self.mutations},set(self.controls['numeric_ids']))
