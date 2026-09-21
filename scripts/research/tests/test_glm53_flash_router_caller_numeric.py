"""Source-composed caller tests under the phase-owned supervisor only."""
import copy,json,os,sys,unittest
from pathlib import Path
if not os.environ.get('FLASH_ROUTER_CALLER_PHASE'):raise unittest.SkipTest('router-caller supervisor required; NOT_EXECUTED')
PHASE=Path(os.environ['FLASH_ROUTER_CALLER_PHASE']);SOURCE=PHASE.parent/'repos/PulsarMLX'
sys.path.insert(0,str(SOURCE/'scripts/research/glm53_flash/router_caller'))
import rc_guard as guard
guard.verify_child_interpreter(PHASE)
import rc_source as source
import rc_oracle as oracle
import rc_runtime as runtime
import rc_checks as checks

class EvidenceCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root=SOURCE/'fixtures/research/glm53-flash-router-caller-v1'
        cls.f=json.loads((root/'cases.json').read_text());cls.table=json.loads((root/'controls.json').read_text())
        cls.cases={c['name']:c for c in cls.f['cases']};cls.r=runtime.Runtime(PHASE)
        cls.controls=[];cls.probes=[];cls.domains=[];cls.compositions=[]
    @classmethod
    def tearDownClass(cls):
        print(json.dumps({'event':'router_observations','mode':os.environ['FLASH_ROUTER_CALLER_MODE'],'backend':os.environ['FLASH_ADMITTED_BACKEND'],
         'case_observations':cls.r.records,'capsule_resets':cls.r.resets,'source_node_bindings':cls.r.builder.retained[0]['record']['source_nodes'] if cls.r.builder.retained else [],
         'source_seams':cls.r.builder.retained[0]['record']['namespace_seams'] if cls.r.builder.retained else [],'module_origins':cls.r.builder.module_origins,
         'domain_outcomes':cls.domains,'controls':cls.controls,'classifier_probes':cls.probes,'composition_assertions':cls.compositions,
         'evaluation_groups':cls.r.evaluations,'caller_evaluations':cls.r.caller_evaluations,'fresh_capsules_retained':len(cls.r.builder.retained),
         'source_execution':'SOURCE_COMPOSED_ROUTER_CALLER_CAPSULE','whole_upstream_import':'NOT_EXECUTED','model_source_qualification':'PARTIAL',
         'scientific_scope':'tiny synthetic router only; BF16 represented operands converted to FP32, not BF16 model/quantized parity'},allow_nan=False),flush=True)
    def validate_reference(self,case):
        self.assertEqual(oracle.reference(case),case['reference'])
        self.assertEqual(oracle.error_bounds(case),case['error_derivation'])
        for row in case['error_derivation']:
            self.assertLess(row['score_abs_bound'],self.f['criteria']['routing_atol'])
            if row['selection_margin'] is not None:self.assertGreater(row['selection_margin'],2*row['ranking_abs_bound'])
            if row['group_margin'] is not None:self.assertGreater(row['group_margin'],4*row['ranking_abs_bound'])

class SingleCase(EvidenceCase):
    def test_complete_source_composed_case(self):
        case=self.cases[self.f['single_case_before_matrix']];self.validate_reference(case)
        self.r.run_case(case,'single-case-producer')
        self.domains.append({'case':case['name'],'dtype':case['dtype'],'status':'QUALIFIED_SINGLE_CASE_OBSERVATION'})

class Matrix(EvidenceCase):
    def test_all_declared_cases(self):
        for case in self.f['cases']:
            with self.subTest(case=case['name']):
                self.validate_reference(case)
                before=self.r.caller_evaluations
                try:self.r.run_case(case)
                except Exception as exc:
                    if case['dtype']=='bfloat16' and runtime.is_bf16_unavailable(exc):
                        self.domains.append({'case':case['name'],'dtype':case['dtype'],'status':'UNSUPPORTED_NOT_QUALIFIED','exception_type':type(exc).__module__+'.'+type(exc).__name__,'message':str(exc),'caller_evaluation_delta':self.r.caller_evaluations-before})
                        continue
                    raise
                self.domains.append({'case':case['name'],'dtype':case['dtype'],'status':'MATCHED_FROZEN_REFERENCE','caller_evaluation_delta':self.r.caller_evaluations-before})
    def test_interleaved_independent_instances(self):
        a=self.r.make(self.cases['fp32-small-top2']);b=self.r.make(self.cases['fp32-small-top1'])
        before=[(runtime.value_sha(v['gate'].weight.tolist()),runtime.value_sha(v['gate'].e_score_correction_bias.tolist()),dict(v['initial_attributes'])) for v in (a,b)]
        outputs=[self.r.invoke(v,'interleave-'+name) for v,name in ((a,'A1'),(b,'B1'),(a,'A2'),(b,'B2'))]
        self.assertIsNot(a['gate'],b['gate']);self.assertIsNot(a['gate'].config,b['gate'].config)
        self.assertNotEqual(a['bundle']['record']['selector_object_id'],b['bundle']['record']['selector_object_id'])
        for first,again in ((outputs[0],outputs[2]),(outputs[1],outputs[3])):
            self.assertEqual(first['raw_ids'],again['raw_ids']);self.assertEqual(first['raw_scores'],again['raw_scores'])
        after=[(runtime.value_sha(v['gate'].weight.tolist()),runtime.value_sha(v['gate'].e_score_correction_bias.tolist()),{k:getattr(v['gate'],k) for k in v['initial_attributes']}) for v in (a,b)]
        self.assertEqual(before,after)
        self.compositions.append({'case':'A-B-A-B','distinct_instances_configs_selectors':True,'parameter_and_router_attributes_unchanged':True,'outputs_repeated_exactly':True,'scope':'known numerical/config state only; not cold compile/kernel/driver cache'})
    def test_exact_mechanism_controls(self):
        def raiser(exc):raise exc
        operations={
         'changed-source':lambda case:self.r.builder.new(raw_override={'Glm5NextMoEGate':(PHASE/'source/capsules/Glm5NextMoEGate.py').read_bytes()+b'\n'}),
         'unlisted-global':lambda case:source.audit_node('MoEGate',(PHASE/'source/capsules/MoEGate.py').read_text().replace('mx.zeros(','np.zeros(')),
         'wrong-selector-binding':lambda case:self.r.builder.new(binding_mutation=True),
         'missing-bias':lambda case:self.r.run_case(case,'mutant-missing-bias',mutate=lambda g:setattr(g,'e_score_correction_bias',self.r.mx.zeros_like(g.e_score_correction_bias))),
         'swapped-bias':lambda case:self.r.run_case(case,'mutant-swapped-bias',mutate=lambda g:setattr(g,'e_score_correction_bias',self.r.mx.array(case['bias'][-1:]+case['bias'][:-1],dtype=self.r.mx.float32))),
         'omit-weight-transpose':lambda case:self.r.run_case(case,'mutant-omit-transpose',variant='omit-weight-transpose'),
         'permuted-weight-rows':lambda case:self.r.run_case(case,'mutant-permuted-weight',mutate=lambda g:setattr(g,'weight',self.r.mx.array(case['weight'][::-1],dtype=self.r.mx.float32))),
         'wrong-top-k':lambda case:self.r.run_case(case,'mutant-top-k',mutate=lambda g:setattr(g,'top_k',1)),
         'wrong-scaling':lambda case:self.r.run_case(case,'mutant-scaling',mutate=lambda g:setattr(g,'routed_scaling_factor',.75)),
         'wrong-normalization':lambda case:self.r.run_case(case,'mutant-normalization',mutate=lambda g:setattr(g,'norm_topk_prob',not case['config']['norm_topk_prob'])),
         'wrong-group-count':lambda case:self.r.run_case(case,'mutant-group-count',mutate=lambda g:setattr(g,'n_group',1)),
         'wrong-expert-score-association':lambda case:self.r.run_case(case,'mutant-score-lookup',wrong_id_association=True)}
        def cross_instance(case):
            other=self.r.make(self.cases['fp32-small-top1'])
            self.r.invoke(other,'cross-instance-donor-before')
            def contaminate(g):
                for key in ('top_k','norm_topk_prob','routed_scaling_factor'):setattr(g,key,getattr(other['gate'],key))
            self.r.run_case(case,'mutant-cross-instance-config',mutate=contaminate)
        operations['cross-instance-config']=cross_instance
        for name in ('omit-input-cast','omit-weight-cast','omit-both-casts'):
            operations[name]=lambda case,variant=name:self.r.run_case(case,'mutant-'+variant,variant=variant)
        self.assertEqual(set(operations),set(self.table['controls']))
        for name,spec in self.table['controls'].items():
            with self.subTest(control=name):
                case=self.cases[spec['case']]
                try:normal=self.r.run_case(case,'normal-before-'+name)
                except Exception as exc:
                    if case['dtype']=='bfloat16' and runtime.is_bf16_unavailable(exc):
                        self.controls.append({'id':name,'outcome':'NORMAL_BF16_DOMAIN_UNSUPPORTED','normal_before':False,'restored_after':False,'exception_type':type(exc).__module__+'.'+type(exc).__name__,'message':str(exc),'coverage':'NOT_QUALIFIED'});continue
                    raise
                before_eval=self.r.caller_evaluations;before_all=self.r.evaluations
                outcome=checks.classify(lambda:operations[name](case),spec)
                delta=self.r.caller_evaluations-before_eval
                outcome.update({'id':name,'normal_before':True,'restored_after':False,'caller_evaluation_delta':delta,'all_evaluation_groups_delta':self.r.evaluations-before_all,'normal_bundle_sequence':normal['bundle_sequence']})
                optional=spec['policy'].startswith('DETECTION_OR_')
                if optional and outcome['outcome']=='SURVIVOR':outcome.update({'outcome':'NUMERICALLY_NONDISTINGUISHABLE','coverage':'CAST_OMISSION_CONTROL_NOT_DISCRIMINATING','reason':'native mixed-operand promotion or equivalent computation may preserve FP32 output; no intended rejection claimed'})
                elif optional and outcome['outcome']=='HARNESS_FAILURE':
                    kinds={'builtins.ValueError':ValueError,'builtins.RuntimeError':RuntimeError,'builtins.TypeError':TypeError}
                    typ=kinds.get(outcome.get('exception_type'))
                    if typ is not None and runtime.is_bf16_unavailable(typ(outcome['message'])):outcome.update({'outcome':'NATIVE_BF16_MUTANT_UNSUPPORTED','coverage':'CONTROL_NOT_QUALIFIED'})
                self.controls.append(outcome)
                restored=self.r.run_case(case,'restored-after-'+name);outcome['restored_after']=True;outcome['restored_bundle_sequence']=restored['bundle_sequence']
                self.assertEqual(normal['raw_ids'],restored['raw_ids']);self.assertEqual(normal['raw_scores'],restored['raw_scores'])
                self.assertNotEqual(normal['bundle_sequence'],restored['bundle_sequence'])
                if outcome['outcome']=='INTENDED_REJECTION':
                    if spec['requires_caller_evaluation']:self.assertGreaterEqual(delta,1)
                    else:self.assertEqual(delta,0)
                elif optional and outcome['outcome'] in ('NUMERICALLY_NONDISTINGUISHABLE','NATIVE_BF16_MUTANT_UNSUPPORTED'):
                    if outcome['outcome']=='NUMERICALLY_NONDISTINGUISHABLE':self.assertGreaterEqual(delta,1)
                else:raise checks.HarnessFailure(name+': '+outcome['outcome'])
    def test_wrong_mechanism_classifier(self):
        def throw(exc):raise exc
        classes={'rc_source.SourceGuardError':source.SourceGuardError,'rc_checks.ComparisonError':checks.ComparisonError}
        for name,spec in self.table['controls'].items():
            actual=[checks.classify(lambda:throw(RuntimeError(spec['message_contains'][0])),spec),checks.classify(lambda:throw(classes[spec['exception_type']]('unrelated marker')),spec),checks.classify(lambda:None,spec)]
            self.assertEqual([r['outcome'] for r in actual],['HARNESS_FAILURE','HARNESS_FAILURE','SURVIVOR'])
            self.probes.append({'id':name,'wrong_type':actual[0],'wrong_message':actual[1],'no_exception':actual[2]})

def load_tests(loader,tests,pattern):
    return loader.loadTestsFromTestCase(SingleCase if os.environ['FLASH_ROUTER_CALLER_MODE']=='case' else Matrix)
