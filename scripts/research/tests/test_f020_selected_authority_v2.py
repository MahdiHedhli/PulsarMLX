"""Synthetic provider parser controls; no review or execution authority issued."""
import copy
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import f020_selected_authority_v2 as a


def documents():
    files={'source.py':{'text':'# synthetic review parser fixture\n'}}
    files['source.py']['sha256']=a.sha(files['source.py']['text'].encode())
    hashes={name:r['sha256'] for name,r in files.items()}
    d={'commit':'1'*40,'tree':'2'*40,'source_sha256':hashes,'package_sha256':a.sha(a.canonical(hashes)),
       'executable_sha256':'3'*64,'contract_sha256':'4'*64,'population_sha256':a.sha(b'{}'),
       'input_sha256':'6'*64,'build':{'scope':'synthetic parser test'},'pre_review_selected_numerical_observations':0}
    c={'schema':a.SCHEMA,'purpose':'FINAL_EXECUTION_REVIEW','descriptor':d,'source_files':files,'synthetic_population':{'text':'{}','sha256':a.sha(b'{}')}}
    verdict={'schema':a.SCHEMA,'decision':'ACCEPT','blockers':0,'assessed':copy.deepcopy(d)}
    provider={'type':'result','subtype':'success','is_error':False,
              'modelUsage':{'claude-opus-5-5':{'outputTokens':100}},'result':json.dumps(verdict)}
    return c,provider


def validate(c,p):
    cr,pr=a.canonical(c),a.canonical(p)
    return a.check_documents(cr,pr,a.sha(cr),a.sha(pr))


class Authority(unittest.TestCase):
    def test_parser_accepts_only_complete_matching_descriptor(self):
        c,p=documents();self.assertEqual(validate(c,p),c['descriptor'])
        p['result']='```json\n'+p['result']+'\n```'
        self.assertEqual(validate(c,p),c['descriptor'])

    def test_provider_failure_model_and_preliminary_refused(self):
        for field,value in [('is_error',True),('subtype','error'),('modelUsage',{}),
                            ('result','Not logged in')]:
            c,p=documents();p[field]=value
            with self.assertRaises(ValueError):validate(c,p)
        c,p=documents();c['purpose']='PRELIMINARY_HOST_REVIEW'
        with self.assertRaisesRegex(ValueError,'not final'):validate(c,p)

    def test_verdict_blocker_type_and_exact_version(self):
        for field,value in [('blockers',False),('blockers',1),('decision','BLOCKED'),
                            ('schema','preliminary')]:
            c,p=documents();v=json.loads(p['result']);v[field]=value;p['result']=json.dumps(v)
            with self.assertRaises(ValueError):validate(c,p)
        c,p=documents();v=json.loads(p['result']);v['assessed']['executable_sha256']='7'*64;p['result']=json.dumps(v)
        with self.assertRaisesRegex(ValueError,'assessed'):validate(c,p)

    def test_capsule_source_bytes_and_coverage(self):
        c,p=documents();c['source_files']['source.py']['text']+='changed'
        with self.assertRaisesRegex(ValueError,'source bytes'):validate(c,p)
        c,p=documents();c['source_files']['extra.py']={'text':'x','sha256':a.sha(b'x')}
        with self.assertRaisesRegex(ValueError,'coverage'):validate(c,p)

    def test_raw_digest_and_duplicate_keys(self):
        c,p=documents();cr,pr=a.canonical(c),a.canonical(p)
        with self.assertRaisesRegex(ValueError,'digest'):a.check_documents(cr,pr,'0'*64,a.sha(pr))
        with self.assertRaisesRegex(ValueError,'duplicate'):a.strict(b'{"x":0,"x":1}')

    def test_reviewed_population_text_cannot_differ(self):
        c,p=documents();c['synthetic_population']['text']='{"changed":true}'
        with self.assertRaisesRegex(ValueError,'population digest'):validate(c,p)

    def test_prior_observations_fail_closed(self):
        for value in (False,1,-1):
            c,p=documents();c['descriptor']['pre_review_selected_numerical_observations']=value
            with self.assertRaisesRegex(ValueError,'boundary'):validate(c,p)


if __name__=='__main__':unittest.main()
