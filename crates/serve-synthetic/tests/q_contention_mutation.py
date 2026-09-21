#!/usr/bin/env python3
"""Execute isolated source mutants and reread exact behavioral failures."""
import argparse
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from q_capture import capture,clean_env
from q_result_validator import read_capture
HERE=Path(__file__).resolve().parent
MUTANTS=[
 ('omitted_admission','sdk_client.py','    holder.await_admission()\n','    pass # omitted admission\n','AA_ADMISSION_WAIT_OMITTED'),
 ('swallowed_failure','sdk_client.py','                self.failure = error\n','                pass # swallowed failure\n','AA_HOLDER_FAILURE_SWALLOWED'),
 ('premature_release','sdk_client.py','    holder.await_admission()\n','    holder.await_admission()\n    holder.release.set()\n','AA_HOLDER_RELEASED_BEFORE_CONTENDER'),
 ('weakened_busy','sdk_client.py','    assert body.get("type") == "rate_limit_error", "CONTENDER_WRONG_BUSY_TYPE"\n','    pass # weakened type check\n','AA_WRONG_BUSY_TYPE_ACCEPTED'),
 ('lost_finally','sdk_client.py','                self.finished.set()\n','                pass # lost finally signal\n','AA_FINALLY_SIGNAL_LOST'),
 ('metadata_failure_absence','test_ci_campaign.py',"    if result.returncode!=0:raise RuntimeError('WORKSPACE_METADATA_FAILED')\n",'    if result.returncode!=0:return set()\n','AA_METADATA_FAILURE_ACCEPTED'),
 ('noop_control','sdk_client.py',None,None,None),
]

def save(path,value):
    with path.open('x') as stream:json.dump(value,stream,indent=2);stream.write('\n')
    path.chmod(0o600)
def sha(body):return hashlib.sha256(body).hexdigest()
def classify(terminal,output,case,assertion):
    if terminal['code']==0 and output.count('AA_ORACLE_PASS '+case)==1:return 'SURVIVED'
    failures=re.findall(r'^AssertionError: (.*)$',output,re.M)
    if terminal['code']==1 and failures==[assertion]:return 'SEMANTIC_KILL'
    raise RuntimeError('NONSEMANTIC_OR_WRONG_ASSERTION_FAILURE')
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path);args=parser.parse_args()
    root=args.root.absolute() if args.root else Path(tempfile.mkdtemp(prefix='aa-mutants-'))
    if args.root:root.mkdir(mode=0o700)
    (root/'tmp').mkdir(mode=0o700);(root/'cache').mkdir(mode=0o700)
    env=clean_env(root)
    for name,file,old,new,assertion in MUTANTS:
        case=root/name;case.mkdir(mode=0o700)
        source=HERE/file;original=source.read_bytes();mutant=case/file
        text=original.decode()
        if old is not None:
            if text.count(old)!=1:raise RuntimeError('MUTATION_ANCHOR_CARDINALITY_CHANGED '+name)
            text=text.replace(old,new,1)
        else:text+='\n# Deliberate no-op surviving control.\n'
        mutant.write_text(text);mutant.chmod(0o600)
        sdk=mutant if file=='sdk_client.py' else HERE/'sdk_client.py';member=mutant if file=='test_ci_campaign.py' else HERE/'test_ci_campaign.py'
        oracle_case='genuine_busy' if name=='noop_control' else name
        def command(client,membership):return [sys.executable,'-I','-B',str(HERE/'aa_behavior_oracle.py'),'--client',str(client),'--membership',str(membership),'--case',oracle_case]
        pristine=capture(command(HERE/'sdk_client.py',HERE/'test_ci_campaign.py'),str(HERE),env,case/'pristine',timeout=30,termination_grace=5)
        reread,output,files=read_capture(case/'pristine')
        if pristine!=reread or classify(reread,output,oracle_case,assertion)!='SURVIVED':raise RuntimeError('PRISTINE_NOT_PASS')
        terminal=capture(command(sdk,member),str(HERE),env,case/'mutant',timeout=30,termination_grace=5)
        reread,output,files=read_capture(case/'mutant')
        if terminal!=reread:raise RuntimeError('RAW_TERMINAL_READBACK_MISMATCH')
        outcome=classify(reread,output,oracle_case,assertion)
        if name=='noop_control':
            if outcome!='SURVIVED':raise RuntimeError('FALSE_KILL_CONTROL')
            outcome='SURVIVED_CONTROL'
        elif outcome!='SEMANTIC_KILL':raise RuntimeError('MUTANT_SURVIVED '+name)
        save(case/'result.json',{'id':name,'case':oracle_case,'expected_assertion':assertion,'outcome':outcome,'pristine_sha256':sha(original),'mutant_sha256':sha(mutant.read_bytes()),'raw_readback':files,'terminal':reread})
        print('AA_MUTATION '+name+' '+outcome,flush=True)
    print('AA_MUTATIONS_OK root='+str(root))
if __name__=='__main__':main()
