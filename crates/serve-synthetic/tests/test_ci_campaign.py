#!/usr/bin/env python3
"""Fast stdlib interface oracle, explicitly using inert campaign/tool stubs."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parent))
import ci_campaign as ci

SOURCE=Path(__file__).resolve().parents[1]
REPOSITORY=SOURCE.parents[1]
WORKFLOW=REPOSITORY/'.github/workflows/serving-synthetic.yml'

def verify_production_workspace_membership(runner=subprocess.run):
    """Fail closed unless root metadata proves the synthetic crate is absent."""
    result=runner(
        ['cargo','metadata','--format-version','1','--no-deps','--quiet'],
        cwd=REPOSITORY,capture_output=True,text=True,timeout=120,
    )
    if result.returncode!=0:raise RuntimeError('WORKSPACE_METADATA_FAILED')
    try:
        metadata=json.loads(result.stdout)
        packages=metadata['packages'];members=metadata['workspace_members']
        names={package['id']:package['name'] for package in packages}
        member_names={names[member] for member in members}
    except (KeyError,TypeError,json.JSONDecodeError) as error:
        raise RuntimeError('WORKSPACE_METADATA_MALFORMED') from error
    if 'pulsar-serve-synthetic' in member_names:
        raise RuntimeError('SYNTHETIC_CRATE_IN_PRODUCTION_WORKSPACE')
    return member_names

class Contract(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.graph=Path(self.tmp.name).resolve()
    def tearDown(self):self.tmp.cleanup()
    def fake_tools(self):return {k:{'path':sys.executable,'sha256':'inert-tool-stub','version':'not-qualification'} for k in ['cargo','rustc']}
    def stub(self,command,source,env,output,seconds):
        self.command=command
        for flag in ['--root','--evidence','--scratch','--target','--matrix','--python']:self.assertIn(flag,command)
        matrix=Path(command[command.index('--matrix')+1]);self.assertTrue(matrix.is_file());self.assertEqual(stat.S_IMODE(matrix.stat().st_mode),0o400)
        for flag in ['--evidence','--scratch','--target']:self.assertFalse(Path(command[command.index(flag)+1]).exists())
        # Parse the exact real argparse block without invoking any mutation.
        tree=ast.parse((SOURCE/'tests/mutation_guards.py').read_bytes());main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main');nodes=[]
        for n in main.body:
            nodes.append(n)
            if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='args' for t in n.targets):break
        scope={'argparse':argparse,'Path':Path,'sys':sys}
        with patch.object(sys,'argv',[command[1],*command[2:]]):exec(compile(ast.Module(body=nodes,type_ignores=[]),'real-parser','exec'),scope)
        self.assertEqual(scope['args'].python,sys.executable)
        return {'code':0,'status':'STUB_INTERFACE_ONLY'}
    def run_stub(self,root=None,launcher=None):
        with patch.dict(os.environ,{'CARGO_HOME':str(self.graph/'cache/cargo')}):return ci.run(SOURCE,root or self.graph/'campaign',sys.executable,launcher=launcher or self.stub,tool_provider=self.fake_tools)
    def test_actual_workflow_helper_and_order(self):
        text=WORKFLOW.read_text();block=text.split('      - name: Mutation guards\n',1)[1].split('\n      - name:',1)[0]
        self.assertIn('tests/ci_campaign.py',block);self.assertIn('--root "$SERVING_GRAPH_ROOT/campaign"',block);self.assertIn('--source crates/serve-synthetic',block)
        self.assertLess(text.index('      - name: CI interface tests'),text.index('      - name: Mutation guards'))
        self.run_stub();self.assertEqual(len(ci.inventory(SOURCE)['properties']),20)
    def test_workspace_membership_failure_modes(self):
        class Result:
            def __init__(self,code,stdout):self.returncode=code;self.stdout=stdout
        valid=json.dumps({'packages':[{'id':'root','name':'pulsarmlx'}],'workspace_members':['root']})
        self.assertEqual(verify_production_workspace_membership(lambda *_,**__:Result(0,valid)),{'pulsarmlx'})
        forbidden=json.dumps({'packages':[{'id':'synthetic','name':'pulsar-serve-synthetic'}],'workspace_members':['synthetic']})
        for result in [Result(1,''),Result(0,'{'),Result(0,'{}'),Result(0,forbidden)]:
            with self.assertRaises(RuntimeError):verify_production_workspace_membership(lambda *_,**__:result)
    def test_actual_membership_and_workflow_boundary(self):
        names=verify_production_workspace_membership();self.assertNotIn('pulsar-serve-synthetic',names)
        text=WORKFLOW.read_text()
        self.assertIn('test_ci_campaign.py --check-membership',text)
        self.assertNotIn('! cargo metadata',text)
    def test_stale_root_refused_before_child(self):
        root=self.graph/'stale';root.mkdir();self.assertRaises(RuntimeError,self.run_stub,root)
    def test_source_output_ancestor_refused(self):
        self.assertRaises(RuntimeError,ci.layout,SOURCE,SOURCE/'new-output')
        self.assertRaises(RuntimeError,ci.layout,SOURCE,SOURCE.parent)
    def test_symlink_root_refused(self):
        root=self.graph/'link';root.symlink_to(self.graph/'absent');self.assertRaises(RuntimeError,self.run_stub,root)
    def test_interpreter_mismatch(self):self.assertRaises(RuntimeError,ci.run,SOURCE,self.graph/'campaign','/inert/not-current-sdk')
    def test_empty_malformed_mismatched_matrix(self):
        for name,b in [('empty',b''),('malformed',b'{'),('mismatch',b'{}')]:
            p=self.graph/name;p.write_bytes(b);p.chmod(0o400)
            with self.assertRaises((RuntimeError,ValueError,KeyError)):ci.admit_matrix(p,SOURCE,hashlib.sha256(b).hexdigest())
    def test_hash_and_writable_matrix_refused(self):
        p=self.graph/'matrix';p.write_text(json.dumps(ci.inventory(SOURCE)));digest=ci.sha(p)
        self.assertRaises(RuntimeError,ci.admit_matrix,p,SOURCE,digest);p.chmod(0o400);self.assertRaises(RuntimeError,ci.admit_matrix,p,SOURCE,'0'*64)
    def test_failure_propagates(self):
        def fails(*a):raise RuntimeError('explicit inert campaign failure')
        with self.assertRaisesRegex(RuntimeError,'explicit inert'):self.run_stub(launcher=fails)
        root=self.graph/'nonzero';self.assertRaises(RuntimeError,self.run_stub,root,lambda *a:{'code':101})
    def test_matrix_current_source_binding(self):
        self.run_stub();path=self.graph/'campaign/input/matrix.json';frozen=json.loads(path.read_bytes());self.assertEqual(frozen,ci.inventory(SOURCE));self.assertEqual(frozen['harness_sha256'],ci.sha(SOURCE/'tests/mutation_guards.py'))
    def test_stale_matrix_refused(self):
        self.run_stub();path=self.graph/'campaign/input/matrix.json';digest=ci.sha(path)
        with patch.object(ci,'inventory',return_value={'status':'source-changed-stub'}):self.assertRaises(RuntimeError,ci.admit_matrix,path,SOURCE,digest)
if __name__=='__main__':
    if '--check-membership' in sys.argv:
        if len(sys.argv)!=2:raise SystemExit('--check-membership takes no value')
        verify_production_workspace_membership()
        print('WORKSPACE_MEMBERSHIP_OK')
    else:unittest.main()
