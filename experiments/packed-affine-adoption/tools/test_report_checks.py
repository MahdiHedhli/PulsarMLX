"""Host-only adversarial evidence controls. Never launches a child."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from report_checks import CONTRACT, admit_entries, admit_report, admit_raw, confined, expected_population
class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.expected={'group-0-adopted':(['a','b','a'],'adopted','group')}
        self.freeze={'binary_sha256':'bin','source_commit':'commit','source_tree':'tree','native_libraries':{'lib':'hash'},'fixture_manifest_sha256':'fixture'}
        self.report={'config_sha256':'cfg','provenance':{**self.freeze,'loaded_images_verified':True},'lifetime':{'parent_counts':[1,1],'view_counts':[2,2],'output_counts':[1,1],'live':0,'created':4,'freed':4,'early_free_count':0,'completed_callbacks':1,'quarantine':False},'identity':{'contract_sha256':CONTRACT,'fixture_manifest_sha256':'fixture'},'outputs':[{'id':s} for s in ('a','b','a')]}
        self.outcome={'outcome':'EXIT_STATUS 0','binary_sha256':'bin','config_sha256':'cfg'}
    def admit(self):return admit_report(self.freeze,self.expected,'group-0-adopted',self.report,self.outcome,'cfg')
    def test_valid_aba(self):self.assertEqual(len(self.admit()),3)
    def test_duplicate_missing_and_extra(self):
        row={'label':'group-0-adopted','report':'group-0-adopted/run.json'}
        self.assertEqual(admit_entries({'reports':[row]},self.expected),[row])
        for rows in ([],[row,row],[row,{'label':'extra','report':'extra/run.json'}]):
            with self.assertRaises(ValueError):admit_entries({'reports':rows},self.expected)
    def test_crossed_path(self):
        with self.assertRaises(ValueError):admit_entries({'reports':[{'label':'group-0-adopted','report':'other/run.json'}]},self.expected)
    def test_crossed_source_or_library(self):
        for key in ('source_commit','source_tree','native_libraries','binary_sha256'):
            saved=self.report['provenance'][key];self.report['provenance'][key]='wrong'
            with self.assertRaises(ValueError):self.admit()
            self.report['provenance'][key]=saved
    def test_wrong_fixture(self):
        self.report['identity']['fixture_manifest_sha256']='wrong'
        with self.assertRaises(ValueError):self.admit()
    def test_missing_or_crossed_sequence(self):
        for ids in (('a','b'),('a','a','b'),('a','b','c')):
            self.report['outputs']=[{'id':x} for x in ids]
            with self.assertRaises(ValueError):self.admit()
    def test_unresolved_retirement(self):
        for key,val in (('live',1),('completed_callbacks',0),('early_free_count',1),('quarantine',True),('freed',3),('view_counts',[2,1])):
            saved=self.report['lifetime'][key];self.report['lifetime'][key]=val
            with self.assertRaises(ValueError):self.admit()
            self.report['lifetime'][key]=saved
    def test_nonzero_exit_and_changed_config(self):
        self.outcome['outcome']='EXIT_STATUS 1'
        with self.assertRaises(ValueError):self.admit()
        self.outcome['outcome']='EXIT_STATUS 0';self.report['config_sha256']='different'
        with self.assertRaises(ValueError):self.admit()
    def test_path_escape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'root';root.mkdir();outside=Path(tmp)/'outside';outside.write_text('x');(root/'link').symlink_to(outside)
            for p in ('../outside',str(outside),'link'):
                with self.assertRaises(ValueError):confined(root,p)
    def test_raw_requires_actual_call_and_reaping(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'raw-probe').mkdir()
            e=root/'raw-probe/events.jsonl';o=root/'raw-probe.outcome.json';s=root/'raw-probe-summary.json'
            e.write_text('{"phase":"before-call"}\n');s.write_text('{"raw_probe":"timeout-reaped"}')
            o.write_text(json.dumps({'outcome':'TIMEOUT after 60001 ms (SIGKILL sent; reaped with signal Some(9))'}));admit_raw(root)
            o.write_text(json.dumps({'outcome':'TIMEOUT after 60001 ms (SIGKILL sent; reaped with signal None)'}))
            with self.assertRaises(ValueError):admit_raw(root)
            o.write_text(json.dumps({'outcome':'SIGNAL 9'}));s.write_text('{"raw_probe":"signal","signal":9}');admit_raw(root)
            e.write_text('')
            with self.assertRaises(ValueError):admit_raw(root)
    def test_population_not_satisfied_by_count_only(self):
        m={'small_sequences':[['a','b','a']]*8,'cases':[{'id':str(i),'population_id':'representative-read-into-v1'} for i in range(4)]}
        inherited={'cases':[{'id':str(i),'expected':{'outcome':'accept'}} for i in range(14)]}
        self.assertEqual(len(expected_population(m,inherited)),52)
        inherited['cases'][-1]['id']='0'
        with self.assertRaises(ValueError):expected_population(m,inherited)
if __name__=='__main__':unittest.main()
