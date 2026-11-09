"""Synthetic CPU controls: no native child, scientific grader or physical qualification."""
import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import m1b_admission as m


class Admission(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory(prefix='synthetic-m1b-');self.addCleanup(t.cleanup)
        self.root=Path(t.name).resolve()
        self.prof=m.parse(m.data(m.PROFILE))
        self.sources={k:{**v,'root':str(self.root/k)} for k,v in self.prof['sources'].items()}
        self.sources['S']={'commit':'a'*40,'tree':'b'*40,'root':str(self.root/'S')}
        for src in self.sources.values():Path(src['root']).mkdir()
        self.ids=dict(contract=self.prof['contract'],decision=self.prof['decision'],python=self.prof['python'],
                      child=self.prof['child'],acceptance=self.prof['acceptance'],handoff=self.prof['public_handoff'],
                      native_install='7c2301eb59c037191cd296e3139a7ca4a93e61e27c5e8b05b1ae717888b16523',
                      controller='1'*64,controller_build='2'*64,profile='3'*64)
        self.a=dict(schema='pulsarmlx.studio-m1b-authority/1',purpose='STUDIO_M1B_SCREEN_ONCE',phase='m1b',
                    host_role='m1-ultra-studio',launch_authorized=True,shipping_default='copied',
                    allowances={'campaign':1,'raw':0,'numerical':0},prompt={'commit':'f'*40,
                    'filename':'005__RUST-ENGINE__Mac-Studio-M1-Ultra__synthetic__prompt.md','sha256':'4'*64},
                    sources=self.sources,added_files={k:'5'*64 for k in self.prof['additions']},
                    paths={k:str(self.root/k) for k in m.ROLES},identities=self.ids)

    def test_future_authority_is_closed_and_distinct(self):
        m.authority(self.a,self.prof)
        for key,val in [('phase','m1a'),('purpose','STUDIO_FULL_M1A_ONCE'),('launch_authorized',1),
                        ('allowances',{'campaign':1,'raw':1,'numerical':0}),('arbitrary_child','anything')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                m.authority({**self.a,key:val},self.prof)
        for name in ['014__RUST-ENGINE__MacBook-Pro-M2-Max__synthetic__prompt.md',
                     '004__RUST-ENGINE__Mac-Studio-M1-Ultra__synthetic__prompt.md']:
            a=copy.deepcopy(self.a);a['prompt']['filename']=name
            with self.assertRaises(ValueError):m.authority(a,self.prof)

    def test_source_child_build_and_role_substitution(self):
        for key in ['python','child','acceptance','decision','contract','handoff','native_install']:
            a=copy.deepcopy(self.a);a['identities'][key]='0'*64
            with self.subTest(key=key),self.assertRaises(ValueError):m.authority(a,self.prof)
        for role in ['C','Q','R']:
            a=copy.deepcopy(self.a);a['sources'][role]['tree']='0'*40
            with self.assertRaises(ValueError):m.authority(a,self.prof)
        for edits in [('paths','grader'),('added_files','tools/qualify.py')]:
            a=copy.deepcopy(self.a);a[edits[0]][edits[1]]='new'
            with self.assertRaises(ValueError):m.authority(a,self.prof)

    def test_original_view_bytes_and_stream_bounds(self):
        p=self.root/'acceptance.json';original=b'{"scope":"original"}';p.write_bytes(original)
        digest=hashlib.sha256(original).hexdigest()
        self.assertEqual(m.data(p,digest,len(original)),original)
        p.write_bytes(b'{"scope":"sanitized"}')
        with self.assertRaises(ValueError):m.data(p,digest,len(original))
        with self.assertRaises(ValueError):m.data(p,limit=2)
        link=self.root/'link';link.symlink_to(p)
        with self.assertRaises(ValueError):m.data(link)
        p.unlink()
        with self.assertRaises(FileNotFoundError):m.data(p,digest)
        for invalid in [b'{"x":1,"x":2}',b'{"x":NaN}']:
            with self.assertRaises(ValueError):m.parse(invalid)

    def test_historical_location_defeats_copied_install(self):
        originals=self.root/'old';originals.mkdir()
        install=originals/'install.json';install.write_text('{}')
        files={}
        for name in ('freeze','diagnostic_receipt'):
            f=originals/(name+'.json');f.write_text(json.dumps({'native_build_receipt':str(install)}));files[name]=str(f)
        st=self.root/'future';m.state_locations(install,{'native_install':str(install)},files,st,originals/m.CLAIM)
        copy_install=self.root/'install.json';copy_install.write_bytes(install.read_bytes())
        with self.assertRaises(ValueError):m.state_locations(copy_install,{'native_install':str(copy_install)},files,st,self.root/m.CLAIM)
        with self.assertRaises(ValueError):m.state_locations(install,{'native_install':str(install)},files,st,st/m.CLAIM)
        for dest in (originals,originals/'fresh',self.root):
            with self.assertRaises(ValueError):m.disjoint(dest,[originals])

    def test_occupied_state_refuses_without_mutation(self):
        timing=self.root/'new';claim=self.root/m.CLAIM
        m.check_occupancy('pre',timing,claim)
        claim.write_text('spent')
        with self.assertRaises(ValueError):m.check_occupancy('pre',timing,claim)
        with self.assertRaises(ValueError):m.check_occupancy('live',timing,claim)
        timing.mkdir();m.check_occupancy('live',timing,claim)
        self.assertEqual(claim.read_text(),'spent')
        claim.unlink()
        with self.assertRaises(ValueError):m.check_occupancy('pre',timing,claim)

    def test_physical_claims_are_original_not_recreated(self):
        claims={}
        for n in ['f020-m1a-continuation.claim.json','f020-studio-m1a-numerical.claim.json']:
            p=self.root/n;b=n.encode();p.write_bytes(b)
            claims[n]={'original_bytes':len(b),'original_sha256':hashlib.sha256(b).hexdigest()}
        m.old_claims(self.root/'install',{'terminal':{'claims':claims}})
        p.write_bytes(b'other')
        with self.assertRaises(ValueError):m.old_claims(self.root/'install',{'terminal':{'claims':claims}})
        self.assertFalse((self.root/m.CLAIM).exists())

    def test_original_roster_not_a_public_payload_fallback(self):
        # Model all six typed roots; use the same mixed original/public fields
        # as the Studio004 handoff, including projection identity-only rows.
        old={'original_custody':{'native_install':str(self.root/'install'),'diagnostic_receipt':str(self.root/'diag/receipt')},
             'paths':dict.fromkeys(('state','campaign','output'),str(self.root))}
        acc={'authority':old,'readiness':{'authority_path':str(self.root/'authority')}}
        rows=[];b=b'original';h=hashlib.sha256(b).hexdigest()
        for i in range(862):
            role='<CAMPAIGN_ROOT>/'+str(i) if i<3 else '<CONTROL_ROOT>/log-'+str(i)
            rows.append({'role':role,'original_bytes':len(b),'original_sha256':h,'publication_utf8_sha256':'0'*64})
            if i<3:(self.root/str(i)).write_bytes(b)
        m.original_files({'all_record_identities':rows},acc)
        (self.root/'2').write_bytes(b'changed!')
        with self.assertRaises(ValueError):m.original_files({'all_record_identities':rows},acc)
        (self.root/'2').unlink()
        with self.assertRaises(FileNotFoundError):m.original_files({'all_record_identities':rows},acc)

    def test_all_loader_overrides_absent_and_no_legacy_phase(self):
        with patch.dict(os.environ,{'PULSAR_ADOPTION_PHASE':'m1b'},clear=True):
            m.environment()
            for k in ['DYLD_FRAMEWORK_PATH','DYLD_INSERT_LIBRARIES','LD_LIBRARY_PATH','LD_PRELOAD','PYTHONHOME','PYTHONPATH','GIT_CONFIG_GLOBAL','PULSARMLX_MODEL_GGUF','GITHUB_ACTIONS']:
                with patch.dict(os.environ,{k:''}),self.subTest(k=k),self.assertRaises(ValueError):m.environment()
            with patch.dict(os.environ,{'PULSAR_ADOPTION_PHASE':'m1a'}),self.assertRaises(ValueError):m.environment()


if __name__ == '__main__':
    unittest.main()
