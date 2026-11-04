"""Host-only adversarial admission tests. No native child or grader is executed.
Original private receipts are not embedded: positive ledger values are synthetic;
exact immutable byte verification is exercised separately and is not bypassable
from the production CLI. Platform/executable checks are mocked only in these tests.
"""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import copied_diagnostic as d


def originals():
    f={'schema':'pulsarmlx.adoption-host-freeze/1','source_commit':d.BASE,'source_tree':d.BASE_TREE,
       'host_role':'m1-ultra-studio','contract_sha256':d.CONTRACT,'raw_probe_budget':{'allowed':1,'used':0},
       'binary_sha256':'synthetic-old-binary','native_libraries':{'synthetic':'old'}}
    p={k:f[k] for k in ('source_commit','source_tree','binary_sha256','native_libraries')}
    p['loaded_images_verified']=True
    return {'freeze':f,'failure':{'provenance':copy.deepcopy(p),'quarantine':True,'native_qualification':'FAILED',
            'error':'native-status-3; ownership uncertain; terminate child'},
        'raw_intent':{'attempt':1,'binary_sha256':f['binary_sha256'],'host_role':'m1-ultra-studio'},
        'raw_report':{'provenance':copy.deepcopy(p),'quarantine':True,'control':'P-RAW-LENGTH',
            'outcome':'outside-contract-acceptance','qmm_calls':0,'status':0}}


def receipt(root):
    r={'schema':d.SCHEMA,'mode':d.MODE,'sequence':d.SEQUENCE.copy(),'scope':copy.deepcopy(d.SCOPE),
       'raw_probe':copy.deepcopy(d.RAW),'contract_sha256':d.CONTRACT,'host_role':'m1-ultra-studio',
       'shipping_default':'copied','originals':{k:{'path':str(root/k),'sha256':v} for k,v in d.ORIGINALS.items()},
       'output_root':str(root),'binary':str(root/'unused-candidate'),'binary_sha256':'synthetic-new-binary',
       'native_prefix':str(root/'unused-prefix'),'source_commit':'synthetic-new-source','source_tree':'synthetic-new-tree',
       'native_libraries':{},'host':{},'generator_hashes':{},'dependency_manifest_sha256':'synthetic',
       'fixture_root':str(root/'unused-fixtures'),'fixture_manifest_sha256':d.FIXTURE,'metadata_identities':{}}
    return r


class DiagnosticAdmission(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name).resolve();self.path=self.root/'diagnostic-receipt.json'
        self.r=receipt(self.root);d.create(self.path,self.r)
    def tearDown(self):
        self.tmp.cleanup()
    def test_historical_original_ledger_resolution(self):
        self.assertEqual(d.validate_originals(originals())['source_commit'],d.BASE)
        self.assertEqual(d.RAW,{'used':1,'allowed':1,'execution_authorized':False})
    def test_current_sanitized_or_tampered_bytes_cannot_replace_originals(self):
        for key,expected in d.ORIGINALS.items():
            path=self.root/key;path.write_text(json.dumps(originals()[key]))
            with self.assertRaisesRegex(ValueError,'original receipt bytes'):
                d.checked(path,expected)
    def test_missing_original(self):
        with self.assertRaises(FileNotFoundError):d.load_originals({k:self.root/k for k in d.ORIGINALS})
    def test_crossed_original_identities(self):
        for which in ('failure','raw_report'):
            for key in ('source_commit','source_tree','binary_sha256','native_libraries'):
                v=originals();v[which]['provenance'][key]='crossed'
                with self.assertRaisesRegex(ValueError,'crossed'):d.validate_originals(v)
    def test_wrong_raw_intent_and_unknown_raw_report(self):
        for target,key,value in [('raw_intent','attempt',2),('raw_report','outcome','unknown'),('raw_report','qmm_calls',1)]:
            v=originals();v[target][key]=value
            with self.assertRaises(ValueError):d.validate_originals(v)
    def test_scope_is_one_exact_copied_sequence(self):
        d.validate_scope(self.r);c=d.config_for(self.r,self.path)
        self.assertEqual(c['mode'],d.MODE);self.assertEqual(c['arm'],'copied');self.assertEqual(c['sequence'],d.SEQUENCE)
        self.assertNotIn('operations',c);self.assertNotIn('inherited_root',c)
    def test_forbidden_modes(self):
        for mode in ('raw-length','adopted','diagnostic','inherited','fill','resident','m1a','m1b'):
            r=copy.deepcopy(self.r);r['mode']=mode
            with self.assertRaises(ValueError):d.validate_scope(r)
    def test_crossed_or_missing_pins(self):
        for name in d.ORIGINALS:
            r=copy.deepcopy(self.r);r['originals'][name]['sha256']='0'*64
            with self.assertRaises(ValueError):d.validate_scope(r)
        r=copy.deepcopy(self.r);del r['originals']['freeze']
        with self.assertRaises(ValueError):d.validate_scope(r)
    def test_raw_counts_never_reset_and_booleans_not_counts(self):
        for raw in ({'used':0,'allowed':1,'execution_authorized':False}, {'used':1,'allowed':2,'execution_authorized':False},
                    {'used':True,'allowed':1,'execution_authorized':False}, {'used':1,'allowed':1,'execution_authorized':True}):
            r=copy.deepcopy(self.r);r['raw_probe']=raw
            with self.assertRaises(ValueError):d.validate_scope(r)
    def test_extra_population_timing_or_retry_refused(self):
        mutations=[('sequence',d.SEQUENCE+['extra']),('operations',1),('phase','m1b'),('inherited_root','x'),('raw_probe_budget',{'used':0})]
        for key,value in mutations:
            r=copy.deepcopy(self.r);r[key]=value
            with self.assertRaises(ValueError):d.validate_scope(r)
        for key,value in [('retry',True),('children',2),('timeout_seconds',301),('M1a_acceptance',True),('performance_claim',True)]:
            r=copy.deepcopy(self.r);r['scope'][key]=value
            with self.assertRaises(ValueError):d.validate_scope(r)
    def invoke(self):
        with patch.dict(os.environ,{'PULSAR_COPIED_DIAGNOSTIC':'studio-copied-only-v1'},clear=True),patch.object(d,'studio_only'),patch.object(d,'revalidate',side_effect=lambda r:d.validate_scope(r)),patch.object(d,'launch_child',return_value={'outcome':'EXIT_STATUS 0','elapsed_ms':0}) as launch:
            result=d.run(self.path)
            return result,launch.call_args_list
    def test_one_launch_and_second_call_refused(self):
        result,calls=self.invoke();self.assertEqual(len(calls),1);self.assertEqual(result['raw_children'],0)
        config=d.read(self.root/'copied.config.json');self.assertEqual(config['sequence'],d.SEQUENCE)
        self.assertEqual(config['arm'],'copied')
        with self.assertRaisesRegex(ValueError,'occupied'):self.invoke()
    def test_occupied_claim_and_outputs_refused_without_launch(self):
        for name in ('launch.intent.json','copied-child','copied.config.json','copied.stdout','outcome.json','diagnostic-check.json'):
            path=self.root/name;path.write_text('preserve')
            with self.assertRaisesRegex(ValueError,'occupied'):self.invoke()
            self.assertEqual(path.read_text(),'preserve');path.unlink()
    def test_occupied_broken_symlink_refused(self):
        (self.root/'copied-child').symlink_to(self.root/'absent')
        with self.assertRaisesRegex(ValueError,'occupied'):self.invoke()
    def test_wrong_runtime_selection_refused(self):
        for env in ({},{'PULSAR_COPIED_DIAGNOSTIC':'m1a'},{'PULSAR_COPIED_DIAGNOSTIC':'studio-copied-only-v1','PULSAR_ADOPTION_PHASE':'m1b'}):
            with patch.dict(os.environ,env,clear=True),patch.object(d,'launch_child') as launch:
                with self.assertRaises(ValueError):d.run(self.path)
                launch.assert_not_called()
    def test_source_drift_prevents_claim_or_launch(self):
        with patch.dict(os.environ,{'PULSAR_COPIED_DIAGNOSTIC':'studio-copied-only-v1'},clear=True),patch.object(d,'studio_only'),patch.object(d,'revalidate',side_effect=ValueError('source drift')),patch.object(d,'launch_child') as launch:
            with self.assertRaisesRegex(ValueError,'source drift'):d.run(self.path)
            self.assertFalse((self.root/'launch.intent.json').exists());launch.assert_not_called()
    def test_drift_after_claim_preserves_spent_claim(self):
        with patch.dict(os.environ,{'PULSAR_COPIED_DIAGNOSTIC':'studio-copied-only-v1'},clear=True),patch.object(d,'studio_only'),patch.object(d,'revalidate',side_effect=[None,ValueError('source drift')]),patch.object(d,'launch_child') as launch:
            with self.assertRaisesRegex(ValueError,'source drift'):d.run(self.path)
            self.assertTrue((self.root/'launch.intent.json').exists());launch.assert_not_called()
    def test_failed_or_unknown_launch_is_preserved_no_retry(self):
        with patch.dict(os.environ,{'PULSAR_COPIED_DIAGNOSTIC':'studio-copied-only-v1'},clear=True),patch.object(d,'studio_only'),patch.object(d,'revalidate'),patch.object(d,'launch_child',return_value={'outcome':'SPAWN_FAILED','elapsed_ms':0}) as launch:
            with self.assertRaisesRegex(ValueError,'did not succeed'):d.run(self.path)
            self.assertEqual(d.read(self.root/'outcome.json')['outcome'],'SPAWN_FAILED')
            with self.assertRaisesRegex(ValueError,'occupied'):d.run(self.path)
            self.assertEqual(launch.call_count,1)
    def test_no_full_qualification_writers(self):
        self.invoke()
        self.assertFalse((self.root/'freeze.json').exists())
        self.assertFalse((self.root/'mechanism.json').exists())
        self.assertFalse((self.root/'m1a-acceptance.json').exists())


class TraceAdmission(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'trace.jsonl'
        self.records=[]
        for stage in [24,25,8,26,27]*3:
            for phase in (1,2):
                self.records.append({'function':6,'stage':stage,'phase':phase,'mlx_status':0,
                    'mlx_status_known':phase==2 and stage!=26,'bridge_refusal':0})
        self.snapshot={'trace_records':30,'synchronization_completions':3}
    def tearDown(self):self.tmp.cleanup()
    def save(self):self.path.write_text(''.join(json.dumps(v)+'\n' for v in self.records))
    def test_exact_three_graph_eval_sync_copy_free_sequences(self):
        self.save();d.check_trace(self.path,self.snapshot)
    def test_missing_and_unfinished_trace(self):
        self.path.write_text('')
        with self.assertRaises(ValueError):d.check_trace(self.path,self.snapshot)
        self.records.pop();self.snapshot['trace_records']=29;self.save()
        with self.assertRaisesRegex(ValueError,'unfinished'):d.check_trace(self.path,self.snapshot)
    def test_success_counts_cannot_hide_wrong_call_order(self):
        for e in self.records:
            if e['stage']==25:e['stage']=26
        self.save()
        with self.assertRaisesRegex(ValueError,'order'):d.check_trace(self.path,self.snapshot)
    def test_status_refusal_and_boolean_values_rejected(self):
        original=copy.deepcopy(self.records)
        for key,value in [('mlx_status',17),('bridge_refusal',3),('function',True),('mlx_status_known',1)]:
            self.records=copy.deepcopy(original);self.records[1][key]=value;self.save()
            with self.assertRaises(ValueError):d.check_trace(self.path,self.snapshot)
    def test_crossed_sync_counter_rejected(self):
        self.save();self.snapshot['synchronization_completions']=4
        with self.assertRaisesRegex(ValueError,'disagreement'):d.check_trace(self.path,self.snapshot)

if __name__=='__main__':unittest.main()
