"""Finite complete-module composition, full outer observations and controls."""
import copy
import hashlib
import json
from pathlib import Path
import resource
import types
import unittest

FIXTURE='fixtures/research/glm53-flash-linear-attention-v1/fixtures.json'
FIXTURE_SHA256='7262c2f5bfbf58b3730ca14a6b35fcc3430c9fad26547168a661b4c3df6fccdf'


class Mismatch(AssertionError):
    pass


def emit(event, **values):
    print(json.dumps({'event':event,**values},sort_keys=True,separators=(',',':'),allow_nan=False),flush=True)


def leaves(value,prefix=''):
    if isinstance(value,dict):
        result={}
        for name,child in value.items(): result.update(leaves(child,prefix+'.'+name if prefix else name))
        return result
    if isinstance(value,list):
        result={}
        for index,child in enumerate(value): result.update(leaves(child,prefix+'.'+str(index)))
        return result
    return {prefix:value}


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


class Engine:
    def __init__(self,context,fixture,case,cache_fixture,backend,serial,mutation=None):
        oracle.validate(case)
        self.case,self.fixture,self.backend,self.serial,self.mutation=case,fixture,backend,serial,mutation
        self.bound=source.load(context,fixture,mutation)
        self.stats=self.bound.stats
        self.cache_classes,_,self.cache_binding=cache_source.load(context,cache_fixture)
        self.module=self.bound.namespace['Glm5NextLinearAttention'](types.SimpleNamespace(**case['config']))
        if self.module.fuse_in is not True or self.module._fused_ready is not False:
            raise Mismatch('ORIGINAL_INITIAL_FUSE_STATE')
        for name,value in case['parameters'].items():
            owner=self.module
            parts=name.split('.')
            for part in parts[:-1]: owner=getattr(owner,part)
            setattr(owner,parts[-1],mx.array(value,dtype=mx.float32))
        actual=leaves(self.module.parameters())
        if set(actual)!=set(case['parameters']): raise Mismatch('LIVE_PARAMETER_CENSUS')
        mx.eval(*actual.values());self.stats['parameter_admission_barriers']+=1
        census=[]
        for name,value in actual.items():
            if value.dtype!=mx.float32 or value.shape!=oracle.shape(case['parameters'][name]) or value.tolist()!=case['parameters'][name]:
                raise Mismatch('SYNTHETIC_WEIGHT_INSTALL')
            census.append({'name':name,'shape':list(value.shape),'dtype':str(value.dtype),'fixture_sha256':digest(case['parameters'][name])})
        for name in ('q_proj','k_proj','v_proj','b_proj','g_a_proj','g_b_proj','o_proj'):
            module=getattr(self.module,name)
            if not isinstance(module,nn.Linear) or any(hasattr(module,k) for k in ('scales','biases','group_size','bits')):
                raise Mismatch('UNQUALIFIED_PARAMETER_KIND')
        for module in (self.module.forget_gate.f_a_proj,self.module.forget_gate.f_b_proj):
            if not isinstance(module,nn.Linear) or any(hasattr(module,k) for k in ('scales','biases','group_size','bits')):
                raise Mismatch('UNQUALIFIED_FORGET_PROJECTION')
        if not isinstance(self.module.conv1d,nn.Conv1d): raise Mismatch('ACTUAL_CONV_CONSTRUCTOR')
        self.cache=self.cache_classes.source_make_cache()
        self.cache.state=[None if case[k] is None else mx.array(case[k],dtype=mx.float32) for k in ('cache0','cache1')]
        self.cache.prepare(case['initial_lengths'])
        self.cache.left_padding=mx.array(case['initial_padding'])
        self.offset=0
        self.calls=[]
        if (mx.default_device()==mx.gpu)!=(backend=='metal'): raise Mismatch('DEFAULT_DEVICE')
        if self.stats['_make_gated_delta_kernel']!=4 or self.stats['factory_API_calls']!=4:
            raise Mismatch('ORIGINAL_FACTORY_INITIALIZERS')
        emit('module_parameter_admission',serial=serial,case=case['name'],mutation=mutation,census=census,
             live_leaves=len(actual),all_live_parameters_replaced=True,cache_class=type(self.cache).__name__,
             source=self.bound.binding,stats=dict(self.stats),actual_default_device=str(mx.default_device()))

    def invoke(self,length,label):
        start=self.offset
        case=self.case
        x=mx.array([r[start:start+length] for r in case['inputs']],dtype=mx.float32)
        mask=None if case['mask'] is None else mx.array([r[start:start+length] for r in case['mask']],dtype=mx.bool_)
        before=dict(self.stats)
        previous_cache0,previous_cache1=self.cache[0],self.cache[1]
        submission_start=len(self.bound.submissions)
        emit('module_call_before',serial=self.serial,label=label,offset=start,length=length,
             actual_cache_carried=start>0,initial_cache0_present=previous_cache0 is not None,
             initial_cache1_present=previous_cache1 is not None,source=self.bound.binding)
        y=self.module(x,mask=mask,cache=self.cache)
        # The only scientific observation boundary: complete returned output,
        # both actual cache tensors and the actual cache bookkeeping views.
        c0,c1=self.cache.state
        lengths,padding=self.cache.lengths,self.cache.left_padding
        mx.eval(y,c0,c1,lengths,padding);self.stats['outer_barriers']+=1
        self.offset+=length
        if any(v.dtype!=mx.float32 for v in (y,c0,c1)): raise Mismatch('RETURN_FP32')
        delta={k:self.stats[k]-before[k] for k in self.stats}
        actual={'output':y.tolist(),'cache0':c0.tolist(),'cache1':c1.tolist(),
                'advance':{'lengths':lengths.tolist(),'padding':padding.tolist(),
                           'lengths_advance':self.cache._lengths_advance,'padding_advance':self.cache._left_padding_advance},
                'delta':delta,'fused':copy.deepcopy(self.bound.fused_records[-1]),
                'kernel_submissions':copy.deepcopy(self.bound.submissions[submission_start:]),
                'cache_object_retained':True,'actual_tensor_carry':start>0,
                'inner_barriers':delta['inner_barriers']}
        expected=self.fixture['expected'][case['name']]
        event=expected['events'][self.offset-1]
        wanted={'output':[r[start:self.offset] for r in expected['output']],
                'cache0':event['cache0'],'cache1':event['cache1'],
                'advance':{'lengths':[n-self.offset for n in case['initial_lengths']],
                           'padding':[n-self.offset for n in case['initial_padding']],
                           'lengths_advance':self.offset,'padding_advance':self.offset},'inner_barriers':0}
        predicates={k:oracle.close(actual[k],wanted[k]) for k in ('output','cache0','cache1')}
        predicates['advance']=actual['advance']==wanted['advance']
        predicates['inner_barriers']=actual['inner_barriers']==0
        H=case['config']['linear_num_heads'];Q=H*32
        correct_splits=[Q,2*Q,3*Q,3*Q+32,3*Q+64]
        expected_counts={'module_calls':1,'fused_calls':1,'fused_builds':int(start==0),'fused_reuses':int(start>0),
            'l2_calls':2,'norm_calls':1,'compute_g':int(case['config']['linear_lower_bound'] is None),
            'compute_g_safe':int(case['config']['linear_lower_bound'] is not None),
            'gated_delta_update':1,'gated_delta_ops':int(self.backend=='cpu'),
            'gated_delta_kernel':int(self.backend=='metal'),'_gated_delta_step_ops':length if self.backend=='cpu' else 0,
            'kernel_API_submissions':int(self.backend=='metal'),'outer_barriers':1,'inner_barriers':0,
            'module_constructors':0,'forget_constructors':0,'norm_constructors':0,'_make_gated_delta_kernel':0,
            'factory_API_calls':0,'parameter_admission_barriers':0}
        predicates['source_counts']=delta==expected_counts
        predicates['fused_binding']=(actual['fused']['split_points']==correct_splits and actual['fused']['quantized'] is False
            and actual['fused']['weight_shape']==[3*Q+64+H,case['config']['hidden_size']]
            and actual['fused']['previously_ready']==(start>0) and actual['fused']['same_fused_object']==(start>0))
        maxima={k:max(abs(a-e) for a,e in zip(oracle.flat(actual[k]),oracle.flat(wanted[k]))) for k in ('output','cache0','cache1')}
        record={'serial':self.serial,'case':case['name'],'label':label,'mutation':self.mutation,'offset':start,'length':length,
                'actual':actual,'predicates':predicates,'maximum_absolute_errors':maxima,
                'expected_binding':{'fixture_sha256':FIXTURE_SHA256,'case':case['name'],'through_time':self.offset-1}}
        self.calls.append(record)
        emit('module_observation',**record)
        return record


def run(context,backend):
    raw=context.read_verified(context.roots['code']/FIXTURE)
    if hashlib.sha256(raw).hexdigest()!=FIXTURE_SHA256: raise ValueError('MODULE_FIXTURE_IDENTITY')
    fixture=json.loads(raw)
    for filename,key,folder in [('oracle.py','oracle_sha256','linear_attention'),('oracle.py','accepted_recurrence_oracle_sha256','recurrent_dispatch')]:
        body=context.read_verified(context.roots['code']/('scripts/research/glm53_flash/'+folder+'/'+filename))
        if hashlib.sha256(body).hexdigest()!=fixture[key]: raise ValueError('MODULE_REFERENCE_IDENTITY')
    cache_fixture=json.loads(context.read_verified(context.roots['code']/'fixtures/research/glm53-flash-cache-lifecycle-v1/fixtures.json'))
    cases={c['name']:c for c in fixture['cases']}
    edges=json.loads(context.read_verified(context.roots['code']/'scripts/research/glm53_flash/linear_attention/edges.json'))
    engines=[];observed={};refusals=[];controls=[]
    def engine(case,mutation=None):
        e=Engine(context,fixture,case,cache_fixture,backend,len(engines)+1,mutation);engines.append(e);return e
    def normal(e,length,label):
        r=e.invoke(length,label)
        failed=[k for k,v in r['predicates'].items() if not v]
        if failed: raise Mismatch('MODULE_COMPARISON:'+','.join(failed))
        return r
    class Checks(unittest.TestCase):
        def test_frozen_reference_and_anchor(self):
            self.assertEqual(fixture['scientific_case_count_including_interleaving'],8)
            for case in cases.values():
                self.assertEqual(oracle.module_reference(case,accepted_recurrence),fixture['expected'][case['name']])
            self.assertEqual(fixture['expected']['dyadic-anchor']['events'][0]['anchor'],
                             {'mixed_b0_c0':.125,'convolution_b0_c0':.0625})

        def test_whole_and_partitions(self):
            for case in cases.values():
                e=engine(case)
                for index,length in enumerate(case['parts']): normal(e,length,'normal:'+str(index))
                observed[case['name']]=e
            for whole,parts in [('ordinary-whole','ordinary-221'),('ordinary-whole','ordinary-131'),('safe-whole','safe-122')]:
                a,b=observed[whole],observed[parts]
                joined=[[t for r in b.calls for t in r['actual']['output'][batch]] for batch in range(b.case['B'])]
                self.assertTrue(oracle.close(joined,a.calls[-1]['actual']['output']))
                for key in ('cache0','cache1'): self.assertTrue(oracle.close(b.calls[-1]['actual'][key],a.calls[-1]['actual'][key]))
                emit('same_backend_partition',whole=whole,partition=parts,status='PASS',criterion='frozen1e-4+1e-5abs(expected)')

        def test_interleaved_actual_caches(self):
            spec=fixture['interleaved_case'];active={name:engine(cases[name]) for name in spec['streams']}
            self.assertIsNot(active[spec['streams'][0]].cache,active[spec['streams'][1]].cache)
            for name,index in spec['schedule']:
                normal(active[name],cases[name]['parts'][index],'interleaved:'+name+':'+str(index))
            emit('interleaved_composition',status='PASS',case=spec['name'],schedule=spec['schedule'],independent_cache_objects=True)

        def test_semantic_controls(self):
            for mutation,spec in fixture['controls'].items():
                case=cases[spec['case']];runs={}
                for phase,selected in [('normal',None),('mutant',mutation),('restored',None)]:
                    e=engine(case,selected)
                    for index,length in enumerate(case['parts']):
                        if selected is None: normal(e,length,mutation+':'+phase+':'+str(index))
                        else: e.invoke(length,mutation+':'+phase+':'+str(index))
                    runs[phase]=e
                detected=any(not r['predicates'][spec['predicate']] for r in runs['mutant'].calls)
                row={'name':mutation,'kind':spec['kind'],'predicate':spec['predicate'],'detected':detected,
                     'normal_serial':runs['normal'].serial,'mutant_serial':runs['mutant'].serial,'restored_serial':runs['restored'].serial,
                     'actual_predicates':[r['predicates'] for r in runs['mutant'].calls],
                     'normal_and_restored_all_pass':True,'fresh_objects':len({id(e.module) for e in runs.values()})==3}
                controls.append(row);emit('semantic_control',**row)
                self.assertTrue(detected,mutation)

        def test_preentry_identity_and_archive_refusals(self):
            before=len(engines)
            bad=copy.deepcopy(cases['ordinary-whole']);bad['config']['linear_head_dim']=31
            def archive_missing():
                p=context.roots['work']/'empty-module-archive';p.mkdir()
                return archive.verify_archive(p,'0'*64)
            checks=[('unsafe_shape_metadata_only',lambda:oracle.validate(bad),oracle.InputError),
                    ('missing_input_identity',lambda:context.read_verified(context.roots['code']/'absent-module-input'),FileNotFoundError),
                    ('bad_fixture_binding',lambda:source.load(context,{**fixture,'capsule_sha256':'0'*64}),ValueError),
                    ('archive_missing_manifest',archive_missing,archive.ArchiveError)]
            for name,call,expected in checks:
                try: call()
                except Exception as exc:
                    row={'name':name,'actual_exception_class':type(exc).__name__,'expected_exception_class':expected.__name__,
                         'exact_class_match':type(exc) is expected,'candidate_started':False}
                    refusals.append(row);emit('preentry_refusal',**row);self.assertIs(type(exc),expected)
                else: self.fail(name+' unexpectedly returned')
            self.assertEqual(before,len(engines))
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(Checks)
    ids=[t._testMethodName for t in suite]
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    context.verify()
    emit('module_summary',backend=backend,engine_count=len(engines),controls=controls,refusals=refusals,
         source_edge_coverage={'tested':edges['active_edge_total'] if result.wasSuccessful() and not result.skipped else 'INCOMPLETE',
                               'total':edges['active_edge_total'],'meaning':edges['coverage_meaning']},
         stats=[{'serial':e.serial,'case':e.case['name'],'mutation':e.mutation,'counts':e.stats} for e in engines],
         physical_GPU_instruction_compile_IO_counts='NOT_OBSERVED',
         scope='FINITE_FP32_FULL_LINEAR_ATTENTION_MODULE_SYNTHETIC_ONLY')
    emit('result',status='PASS' if result.wasSuccessful() and not result.skipped else 'FAIL',test_ids=ids,
         tests_run=result.testsRun,failures=len(result.failures),errors=len(result.errors),skips=len(result.skipped),
         peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    return 0 if result.wasSuccessful() and not result.skipped else 1
