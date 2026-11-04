"""Host-only controls of production admission. Native/API boundaries are mocked.

Semantic vectors are explicitly sanitized TEST DATA, never original receipts.
No production evidence hash, allowance or launch bypass is installed.
"""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import m1a_continuation as m
import report_checks as checks


class ContinuationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve(); self.campaign = self.root/'campaign'; self.campaign.mkdir()
        self.pins = m.read(m.REPO/m.EXP/'continuation-studio-originals-v1.json')
        self.values = m.read(Path(__file__).with_name('continuation_test_vectors.json'))['values']
        self.paths = {k: str(self.root/k) for k in self.pins}
        for p in self.paths.values(): Path(p).write_text('{}')
        self.r = self.receipt(False)

    def receipt(self, ci):
        return {'schema':m.SCHEMA, 'authority':m.AUTHORITY, 'contract_sha256':m.CONTRACT,
                'phase':'m1a', 'campaign_identity':m.CAMPAIGN, 'shipping_default':'copied', 'M1b_released':False,
                'host_role':'native-ci' if ci else 'm1-ultra-studio', 'raw_policy':m.CI if ci else m.STUDIO,
                'raw_probe_budget':{'allowed':1,'used':int(not ci)}, 'raw_execution_authorized':ci,
                'raw_provenance':{'evidence_kind':'current_binary' if ci else 'historical_host_native_stack',
                                  'applies_to_current_binary':ci}, **m.FIXED_INPUTS,
                'population':{'group-0-copied':(['a','b','a'],'copied','group')},
                'campaign':str(self.campaign), 'parent':str(self.root/'parent'), 'binary':str(self.root/'child'),
                'native_build_receipt':str(self.root/'install.json')}

    def save(self):
        (self.root/'install.json').write_text('{}')
        (self.campaign/'freeze.json').write_bytes(m.canonical(self.r))
        p=m.stable_claim_path(self.r)
        p.write_bytes(m.canonical({'campaign_identity':m.CAMPAIGN,'campaign':str(self.campaign),
                                  'receipt_sha256':m.sha(self.campaign/'freeze.json')}))

    def semantic(self):
        return m.validate_studio_values(self.values,self.pins,self.paths)

    def test_closed_policy_pairs(self):
        for ci in (True,False):m.scope(self.receipt(ci))
        for key,value in [('host_role','macbook'),('raw_policy',m.CI),('phase','m1b'),('schema','unknown'),
                          ('M1b_released',True),('raw_probe_budget',{'allowed':1,'used':0}),
                          ('raw_execution_authorized',True),('authority',{}),('shipping_default','adopted')]:
            r=copy.deepcopy(self.r);r[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):m.scope(r)

    def test_historical_cannot_be_relabelled_current(self):
        for key,value in [('applies_to_current_binary',True),('evidence_kind','current_binary')]:
            r=copy.deepcopy(self.r);r['raw_provenance'][key]=value
            with self.assertRaises(ValueError):m.scope(r)

    def test_semantic_original_chain(self):
        result=self.semantic()
        self.assertFalse(result['applies_to_current_binary'])
        self.assertEqual(result['source_commit'],'190c64213135a756f5e3d61059036b9af2d78d7a')
        self.assertEqual(result['termination'],'EXIT_STATUS 0')

    def test_missing_altered_and_sanitized_originals_refused(self):
        with self.assertRaises(ValueError):m.original_studio({})
        with self.assertRaises(ValueError):m.original_studio(self.paths)
        # Even truthful sanitized content cannot satisfy exact original hashes.
        for name,value in self.values.items():Path(self.paths[name]).write_bytes(m.canonical(value))
        with self.assertRaises(ValueError):m.original_studio(self.paths)
        Path(self.paths[sorted(self.pins)[0]]).unlink()
        with self.assertRaises(FileNotFoundError):m.original_studio(self.paths)

    def test_crossed_source_binary_native_and_diagnostic_links(self):
        mutations=[('freeze','source_commit','wrong'),('raw_outcome','binary_sha256','wrong'),
                   ('raw_outcome','config_sha256','wrong'),('diagnostic_receipt','native_libraries',{}),
                   ('diagnostic_receipt','binary_sha256','wrong'),('diagnostic_receipt','source_tree','wrong'),
                   ('diagnostic_receipt','rust_grader_sha256','wrong'),('diagnostic_config','diagnostic_receipt_sha256','wrong'),
                   ('diagnostic_check','report_sha256','wrong'),('diagnostic_check','rust_gates_sha256','wrong'),
                   ('diagnostic_outcome','outcome','UNKNOWN')]
        original=copy.deepcopy(self.values)
        for obj,key,value in mutations:
            self.values=copy.deepcopy(original);self.values[obj][key]=value
            with self.subTest(obj=obj,key=key),self.assertRaises(ValueError):self.semantic()

    def test_raw_call_sequence_and_consumed_state(self):
        self.values['raw_events'][2]['status']=1
        with self.assertRaises(ValueError):self.semantic()
        self.values=m.read(Path(__file__).with_name('continuation_test_vectors.json'))['values']
        self.values['freeze']['raw_probe_budget']['used']=1
        with self.assertRaises(ValueError):self.semantic()

    def test_old_blank_os_does_not_override_independent_host(self):
        self.assertEqual(self.values['freeze']['host']['os'],'')
        self.semantic()
        self.values['host001']['os_build']='changed'
        with self.assertRaises(ValueError):self.semantic()

    def test_admit_once_and_unknown_attempt_consumed(self):
        self.save()
        with patch.object(m,'revalidate',side_effect=lambda r:r):
            m.admit(self.campaign,Path(self.r['parent']),Path(self.r['binary']))
            with self.assertRaises(ValueError):m.admit(self.campaign,Path(self.r['parent']),Path(self.r['binary']))
        self.assertTrue((self.campaign/'continuation-attempt.json').exists())

    def test_crossed_actual_parent_refused_before_attempt(self):
        self.save()
        with patch.object(m,'revalidate',side_effect=lambda r:r):
            with self.assertRaises(ValueError):m.admit(self.campaign,self.root/'other',Path(self.r['binary']))
        self.assertFalse((self.campaign/'continuation-attempt.json').exists())

    def test_new_output_location_does_not_refund_stable_claim(self):
        self.save();other=self.root/'other';other.mkdir()
        (other/'freeze.json').write_bytes((self.campaign/'freeze.json').read_bytes())
        with self.assertRaises(ValueError):m.require_claim(self.r,other)

    def test_studio_zero_raw_child_claims(self):
        self.save();(self.campaign/'m1a').mkdir()
        m.create(self.campaign/'continuation-attempt.json',m.binding(self.campaign))
        with patch.object(m,'revalidate',side_effect=lambda r:r):
            with self.assertRaises(ValueError):m.before_child(self.campaign,'raw-probe')
            m.before_child(self.campaign,'group-0-copied')
            with self.assertRaises(FileExistsError):m.before_child(self.campaign,'group-0-copied')
        self.assertFalse(any((self.campaign/'m1a').glob('raw*')))
        m.admit_raw_policy(self.campaign,self.r)
        (self.campaign/'m1a/raw-probe-summary.json').write_text('{}')
        with self.assertRaises(ValueError):m.admit_raw_policy(self.campaign,self.r)

    def test_source_or_native_binding_failure_precedes_child_claim(self):
        self.save();(self.campaign/'m1a').mkdir()
        with patch.object(m,'revalidate',side_effect=ValueError('changed protected source/native identity')):
            with self.assertRaises(ValueError):m.before_child(self.campaign,'group-0-copied')
        self.assertEqual(list((self.campaign/'m1a').iterdir()),[])

    def test_ci_raw_claim_at_most_once(self):
        self.r=self.receipt(True)
        grant=self.root/'grant.json';grant.write_text('{}')
        self.r['raw_provenance']['grant']=str(grant)
        self.save();(self.campaign/'m1a').mkdir()
        m.create(self.campaign/'continuation-attempt.json',m.binding(self.campaign))
        with patch.object(m,'revalidate',side_effect=lambda r:r):
            m.before_child(self.campaign,'raw-probe')
            with self.assertRaises(FileExistsError):m.before_child(self.campaign,'raw-probe')
        self.assertTrue((self.campaign/'m1a/raw-probe.continuation-intent.json').exists())

    def test_actual_native_patch_and_library_binding(self):
        prefix=self.root/'native';(prefix/'lib').mkdir(parents=True)
        for name in ('libmlx.dylib','libmlxc.dylib','mlx.metallib'):(prefix/'lib'/name).write_bytes(b'test-only fake library')
        receipt=self.root/'native.json'
        data={'source_pins':m.PINS,'patches':m.PATCHES};receipt.write_bytes(m.canonical(data))
        with patch.object(m.subprocess,'check_output',return_value='fake-library:\n\t/usr/lib/libSystem.B.dylib (compatibility version 1)\n'):
            first=m.native_state(prefix,receipt,'native-ci')
            (prefix/'lib/libmlx.dylib').write_bytes(b'changed test-only bytes')
            self.assertNotEqual(first,m.native_state(prefix,receipt,'native-ci'))
            data['patches']={};receipt.write_bytes(m.canonical(data))
            with self.assertRaises(ValueError):m.native_state(prefix,receipt,'native-ci')

    def test_population_requires_52_labels_84_outputs(self):
        manifest={'small_sequences':[[f'a{i}',f'b{i}',f'a{i}'] for i in range(8)],
                  'cases':[{'id':f'rep{i}','population_id':'representative-read-into-v1'} for i in range(4)]}
        inherited={'cases':[{'id':f'inherited{i}','expected':{'outcome':'accept'}} for i in range(14)]}
        expected=checks.expected_population(manifest,inherited)
        self.assertEqual([len(expected),sum(len(v[0]) for v in expected.values())],[52,84])
        rows=[{'label':k,'report':k+'/run.json'} for k in expected]
        self.assertEqual(checks.admit_entries({'reports':rows},expected),rows)
        for bad in (rows[:-1],rows+[rows[0]],rows[:1],[{'label':'copied-child','report':'copied-child/run.json'}]):
            with self.assertRaises(ValueError):checks.admit_entries({'reports':bad},expected)

    def test_fresh_host_os_fallback_and_changed_build(self):
        outputs={'machdep.cpu.brand_string':'Apple M1 Ultra','hw.model':'Mac13,2','hw.memsize':'137438953472',
                 'hw.pagesize':'16384','-productVersion':'26.0','-buildVersion':'25A354'}
        with patch.object(m.platform,'system',return_value='Darwin'),patch.object(m.platform,'machine',return_value='arm64'),\
             patch.object(m.platform,'mac_ver',return_value=('',(),'')),patch.dict(os.environ,{},clear=True),\
             patch.object(m.subprocess,'check_output',side_effect=lambda args,**kw:outputs[args[-1]]):
            self.assertEqual(m.host_facts('m1-ultra-studio')['os'],'26.0')
            outputs['-buildVersion']='changed'
            with self.assertRaises(ValueError):m.host_facts('m1-ultra-studio')


class CiGrantTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name).resolve()
        self.event=self.root/'event.json';self.event.write_text('{"inputs":{"mode":"full"}}')
        self.capture=self.root/'admission.json';self.capture.write_text('{}')
        self.env={'GITHUB_ACTIONS':'true','GITHUB_EVENT_NAME':'workflow_dispatch','GITHUB_REPOSITORY':'MahdiHedhli/PulsarMLX',
                  'GITHUB_REF':'refs/heads/'+m.BRANCH,'GITHUB_RUN_ATTEMPT':'1','PULSAR_ADOPTION_PHASE':'m1a',
                  'GITHUB_EVENT_PATH':str(self.event),'GITHUB_RUN_ID':'42','GITHUB_SHA':'H','GITHUB_WORKSPACE':str(self.root)}
        self.grant={'schema':'pulsarmlx.m1a-ci-continuation-grant/1','authority':m.AUTHORITY,'candidate':'C','candidate_tree':'T',
                    'inventory_sha256':m.hashlib.sha256(m.canonical([])).hexdigest(),'campaign_identity':m.CAMPAIGN,
                    'run_attempt':1,'run_id':42,'controller_commit':'H','controller_tree':'HT',
                    'raw_budget':{'allowed':1,'used':0,'additional':0},'historical_run_ids':[41481802750],
                    'current_history_ids':[41481802750,42],
                    'predecessor':{'attempt':1,'job_id':125402293053,'runner_id':0,'steps':[],'artifacts':0,
                                   'head':'015d748fe14ed555027ead7c0a2fb2a84a39fa35','tree':'de7afb423e274a41e37fa06cc475b10c5b4ca345'},
                    'admission_evidence':str(self.capture),'admission_sha256':m.sha(self.capture)}
        self.path=self.root/'grant.json'

    def call(self):
        self.path.write_bytes(m.canonical(self.grant))
        def git(*args,**kwargs):return '' if args[0]=='status' else 'HT' if args[-1]=='HEAD^{tree}' else 'H'
        with patch.dict(os.environ,self.env,clear=True),patch.object(m,'git',side_effect=git):
            return m.ci_grant(self.path,'C','T',[])

    def test_exact_grant(self):
        self.assertTrue(self.call()['applies_to_current_binary'])

    def test_attempt2_wrong_ref_event_phase_and_head(self):
        for key,value in [('GITHUB_RUN_ATTEMPT','2'),('GITHUB_REF','refs/heads/main'),('GITHUB_EVENT_NAME','push'),
                          ('PULSAR_ADOPTION_PHASE','m1b'),('GITHUB_SHA','other')]:
            old=self.env[key];self.env[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.call()
            self.env[key]=old

    def test_wrong_C_missing_extra_history_and_consumed_budget(self):
        for key,value in [('candidate','old'),('candidate_tree','old'),('historical_run_ids',[]),
                          ('current_history_ids',[42]),('current_history_ids',[41481802750,42,43]),
                          ('run_attempt',2),('raw_budget',{'allowed':1,'used':1,'additional':0})]:
            old=self.grant[key];self.grant[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.call()
            self.grant[key]=old

    def test_predecessor_execution_and_changed_capture_refused(self):
        for key,value in [('runner_id',1),('steps',[{}]),('artifacts',1),('attempt',2),('tree','wrong')]:
            old=self.grant['predecessor'][key];self.grant['predecessor'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):self.call()
            self.grant['predecessor'][key]=old
        self.capture.write_text('changed')
        with self.assertRaises(ValueError):self.call()

    def test_exact_payload_only(self):
        for inputs in ({},{'mode':'evidence'},{'mode':'full','packed_affine_m1a':True}):
            self.event.write_text(json.dumps({'inputs':inputs}))
            with self.assertRaises(ValueError):self.call()


class CompleteReportTests(unittest.TestCase):
    """Real report admission over synthetic saved files, not native acceptance."""
    setUp = ContinuationTests.setUp
    receipt = ContinuationTests.receipt
    save = ContinuationTests.save
    def build_reports(self):
        manifest={'small_sequences':[[f'a{i}',f'b{i}',f'a{i}'] for i in range(8)],
                  'cases':[{'id':f'rep{i}','population_id':'representative-read-into-v1'} for i in range(4)]}
        fixtures=self.root/'fixtures';fixtures.mkdir();(fixtures/'manifest.json').write_bytes(m.canonical(manifest))
        inherited=m.REPO/'fixtures/native-composition'
        expected=checks.expected_population(manifest,m.read(inherited/'manifest.json'))
        self.r.update(source_commit='TEST_ONLY_C',source_tree='TEST_ONLY_TREE',binary_sha256='TEST_ONLY_BINARY',
                      native_libraries={'test-only-library':'hash'},host={'machine':'TEST_ONLY_HOST'},
                      generator_hashes={'test-only':'hash'},dependency_manifest_sha256='test-only',
                      fixture_root=str(fixtures),fixture_manifest_sha256=m.sha(fixtures/'manifest.json'),
                      inherited_root=str(inherited),inherited_manifest_sha256=m.sha(inherited/'manifest.json'),population=expected)
        self.save();root=self.campaign/'m1a';root.mkdir()
        m.create(self.campaign/'continuation-attempt.json',m.binding(self.campaign))
        m.create(root/'injected-controls.json',{'C-GEOMETRY':{'reached':True,'native_calls':0},'C-CALLBACK':{'reached':True,'injected':True,'native_fallback_claim':False}})
        entries=[]
        for label,(ids,arm,kind) in expected.items():
            child=root/label;child.mkdir()
            config={'arm':arm,'host':self.r['host']}
            config.update(sequence=ids) if kind=='group' else config.update(case_id=ids[0])
            m.create(root/(label+'.config.json'),config);cfg=m.sha(root/(label+'.config.json'))
            m.create(root/(label+'.continuation-intent.json'),m.binding(self.campaign))
            m.create(root/(label+'.outcome.json'),{'outcome':'EXIT_STATUS 0','binary_sha256':self.r['binary_sha256'],'config_sha256':cfg})
            outputs=[]
            for i,name in enumerate(ids):
                path=child/f'output-{i}.f32';path.write_bytes(b'\0'*4)
                outputs.append({'id':name,'file':path.name,'dtype':'F32','shape':[1,1],'sha256':m.sha(path)})
            report={'config_sha256':cfg,'frozen_host':self.r['host'],
                    'provenance':{**{k:self.r[k] for k in ('source_commit','source_tree','binary_sha256','native_libraries')},'loaded_images_verified':True},
                    'source_binding':{k:self.r[k] for k in ('source_commit','source_tree','dependency_manifest_sha256','generator_hashes')},
                    'lifetime':{'live':0,'created':3,'freed':3,'early_free_count':0,'completed_callbacks':int(arm=='adopted'),
                                'parent_counts':[1,1],'view_counts':[1,1],'output_counts':[1,1],'quarantine':False}}
            if kind=='group':report.update(identity={'contract_sha256':m.CONTRACT,'fixture_manifest_sha256':self.r['fixture_manifest_sha256']},outputs=outputs)
            else:report.update(population='inherited_slice2c_changed_import',id=ids[0],output=outputs[0])
            m.create(child/'run.json',report);entries.append({'label':label,'report':label+'/run.json'})
        mechanism={k:self.r[k] for k in ('contract_sha256','source_commit','source_tree','binary_sha256','fixture_manifest_sha256','host_role')}
        mechanism.update(mechanism='PASS',M1b_released=False,reports=entries,continuation=m.binding(self.campaign))
        m.create(root/'mechanism.json',mechanism)
        return root

    def admit_reports(self):
        # Only the physical host/artifact observation boundary is replaced.
        # All saved-file, report, policy, ownership and population gates are real.
        with patch.object(m,'revalidate',side_effect=lambda r:r):return checks.check_campaign(self.campaign)

    def test_complete_set_shared_admission_then_mutations(self):
        root=self.build_reports();self.assertEqual(len(self.admit_reports()[2]),52)
        report_path=root/'group-0-copied/run.json';original=m.read(report_path)
        for key,value in [('frozen_host',{'machine':'crossed'}),('diagnostic_only',True),
                          ('source_binding',{}),('outputs',original['outputs'][:1])]:
            v=copy.deepcopy(original);v[key]=value;report_path.write_bytes(m.canonical(v))
            with self.subTest(key=key),self.assertRaises(ValueError):self.admit_reports()
        v=copy.deepcopy(original);v['provenance']['source_commit']='OLD_CANDIDATE';report_path.write_bytes(m.canonical(v))
        with self.assertRaises(ValueError):self.admit_reports()
        v=copy.deepcopy(original);v['lifetime']['completed_callbacks']=1;report_path.write_bytes(m.canonical(v))
        with self.assertRaises(ValueError):self.admit_reports()
        report_path.write_bytes(m.canonical(original))
        (root/'group-0-copied/output-0.f32').write_bytes(b'changed')
        with self.assertRaises(ValueError):self.admit_reports()

    def test_complete_set_missing_duplicate_and_diagnostic_only(self):
        root=self.build_reports();p=root/'mechanism.json';original=m.read(p)
        for rows in (original['reports'][:-1],original['reports']+[original['reports'][0]],original['reports'][:1]):
            v=copy.deepcopy(original);v['reports']=rows;p.write_bytes(m.canonical(v))
            with self.assertRaises(ValueError):self.admit_reports()


if __name__ == '__main__':unittest.main()
