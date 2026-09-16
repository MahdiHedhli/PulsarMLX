#!/usr/bin/env python3
"""Independently reread original AA durable results and frame review data."""
import argparse
import hashlib
import json
from pathlib import Path
import stat
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from q_result_validator import read_capture,validate_python,validate_rust
HERE=Path(__file__).resolve().parent
def sha(body):return hashlib.sha256(body).hexdigest()
def save(path,value):
    with path.open('x') as stream:json.dump(value,stream,indent=2);stream.write('\n')
    path.chmod(0o600)
def readback(campaign,output):
    rows=json.loads((campaign/'input/matrix.json').read_bytes())['properties'];observed=[]
    for row in rows:
        case=campaign/'evidence'/row['id'];result=json.loads((case/'result.json').read_bytes())
        if result['id']!=row['id'] or result['outcome']!='SEMANTIC_KILL':raise RuntimeError('NON_KILL '+row['id'])
        if sha((case/'original-mutant-source').read_bytes())!=result['mutant_source_sha256']:raise RuntimeError('MUTANT_IDENTITY_MISMATCH')
        before,before_output,_=read_capture(case/'pristine-test');after,after_output,files=read_capture(case/'mutant-test')
        if row['source_path'].endswith('.py'):
            validate_python(before,before_output);outcome=validate_python(after,after_output,row['intended_failing_assertion'])
        else:
            validate_rust(before,before_output,row['pristine_named_test']);outcome=validate_rust(after,after_output,row['pristine_named_test'],row['intended_failing_assertion'])
            for child in ['pristine-compile','mutant-compile']:
                terminal,_,_=read_capture(case/child)
                if terminal['code']!=0:raise RuntimeError('COMPILE_NOT_PASS')
        if outcome!='SEMANTIC_KILL':raise RuntimeError('WRONG_SEMANTIC_OUTCOME')
        observed.append({'id':row['id'],'outcome':outcome,'original_result_sha256':sha((case/'result.json').read_bytes()),'raw_files':files})
    if len(observed)!=20 or len({r['id'] for r in observed})!=20:raise RuntimeError('CENSUS_MISMATCH')
    save(output,{'status':'ORIGINAL_READBACK_PASS','cases':observed})
    print('AA_SEMANTIC_READBACK_OK 20')

def packet(source,outcomes,campaign,transport,output):
    repo=source.parents[1]
    base='c5798a021ba22b06000afea60b739d636ee49d2f'
    commit=subprocess.check_output(['git','rev-parse','HEAD','HEAD^{tree}'],cwd=repo,text=True).splitlines()
    diff=subprocess.check_output(['git','diff','--binary',base,commit[0]],cwd=repo)
    blocks=[b'AA cumulative SOURCE review. Z review remains NOT_ADMITTED; old substring mutations are not qualification. Real-model execution is excluded.\n',json.dumps({'commit':commit[0],'tree':commit[1],'public_prerequisite':base}).encode(),b'\nCUMULATIVE DIFF\n'+diff]
    files=[]
    for pattern in ['src/*.rs','tests/*.py','tests/*.mjs','tests/sdk_smoke.sh','tests/sdk-requirements.txt','Cargo.toml','Cargo.lock']:
        files.extend(source.glob(pattern))
    files.extend([repo/'Cargo.toml',repo/'.github/workflows/serving-synthetic.yml',repo/'.github/workflows/macos.yml'])
    files.extend(transport.glob('*.mjs'))
    files.extend([outcomes/'admission.json',outcomes/'independent-expectations.json',outcomes/'semantic-readback.json'])
    files.extend(outcomes.glob('*.json'));files.extend(outcomes.glob('*.md'))
    # Complete noncompiler raw behavioral outcomes from every retained generation.
    for generation in sorted(outcomes.glob('generation-*')):
        files.extend(p for p in generation.rglob('*') if p.is_file() and p.suffix not in ['.bundle','.tar'] and p.name!='cumulative.diff')
    for case in sorted((campaign/'evidence').iterdir()):
        if not case.is_dir():continue
        files.extend(p for p in case.iterdir() if p.is_file())
        for child in ['pristine-test','mutant-test']:
            files.extend(p for p in (case/child).iterdir() if p.is_file())
        # Successful compiler dependency-progress stdout is nondecisive. Original
        # compile launch/terminal/lifecycle and stderr remain supplied verbatim.
        for child in ['pristine-compile','mutant-compile']:
            if (case/child).exists():files.extend(p for p in (case/child).iterdir() if p.is_file() and p.name!='stdout.raw')
    aliases={};manifest=[]
    for file in sorted(set(files),key=str):
        if file.is_symlink() or not file.is_file():raise RuntimeError('PACKET_NONREGULAR_FILE')
        body=file.read_bytes();digest=sha(body);label=str(file)
        manifest.append({'path':label,'bytes':len(body),'mode':oct(stat.S_IMODE(file.stat().st_mode)),'sha256':digest})
        if file.name=='original-mutant-source':
            identity=json.loads((file.parent/'source-identities.json').read_bytes())
            path=identity.get('source_path',identity['fault']['source_path'])
            pristine=source/path;base_body=pristine.read_bytes()
            prefix=0
            while prefix<min(len(body),len(base_body)) and body[prefix]==base_body[prefix]:prefix+=1
            suffix=0
            while suffix<min(len(body),len(base_body))-prefix and body[-suffix-1]==base_body[-suffix-1]:suffix+=1
            literal=body[prefix:len(body)-suffix if suffix else len(body)]
            blocks.append(('\nBEGIN EXACT SEGMENTED FILE '+label+' BYTES '+str(len(body))+' SHA256 '+digest+'\nBYTE_ALIAS '+str(pristine)+' OFFSET 0 BYTES '+str(prefix)+' SHA256 '+sha(body[:prefix])+'\nLITERAL BYTES '+str(len(literal))+'\n').encode()+literal+('\nBYTE_ALIAS '+str(pristine)+' OFFSET '+str(len(base_body)-suffix)+' BYTES '+str(suffix)+' SHA256 '+sha(body[len(body)-suffix:] if suffix else b'')+'\nEND EXACT SEGMENTED FILE\n').encode())
            continue
        if digest in aliases:blocks.append(('\nALIAS '+label+' SHA256 '+digest+' BODY '+aliases[digest]+'\n').encode());continue
        aliases[digest]=label
        blocks.append(('\nBEGIN FILE '+label+' BYTES '+str(len(body))+' SHA256 '+digest+'\n').encode()+body+('\nEND FILE '+label+'\n').encode())
    body=b'\n'.join(blocks)
    # The V wrapper adds its own framing; leave room below its request bound.
    if len(body)>890000:raise RuntimeError('COMPLETE_PACKET_EXCEEDS_BOUND '+str(len(body)))
    with output.open('xb') as stream:stream.write(body)
    output.chmod(0o400);save(output.with_suffix('.manifest.json'),manifest)
    print('AA_PACKET_OK bytes='+str(len(body))+' sha256='+sha(body))

def review_check(out,output):
    launch=json.loads((out/'launch.json').read_bytes());terminal=json.loads((out/'result.json').read_bytes());envelope=json.loads((out/'stdout.json').read_bytes());result=envelope['structured_output']
    if not terminal['valid'] or not terminal['accepted'] or not terminal['reaped'] or not terminal['signaling_authority_retired'] or terminal['stop_reason'] or terminal['signal'] or terminal['code']!=0:raise RuntimeError('REVIEW_NOT_ADMITTED')
    if result['nonce']!=launch['nonce'] or result['candidate_sha256']!=launch['candidate_sha256'] or result['verdict']!='ACCEPT' or any(f['blocking'] for f in result['findings']):raise RuntimeError('REVIEW_BINDING_FAILED')
    if sha((out/'request.txt').read_bytes())!=launch['request_sha256'] or sha((out/'stdout.json').read_bytes())!=terminal['stdout_sha256'] or sha((out/'stderr.txt').read_bytes())!=terminal['stderr_sha256']:raise RuntimeError('REVIEW_RAW_HASH_MISMATCH')
    if list(envelope['modelUsage'])!=['claude-opus-5'] or envelope['permission_denials'] or envelope['subagent_stats']['spawned']!=0 or envelope['usage']['server_tool_use']!={'web_search_requests':0,'web_fetch_requests':0}:raise RuntimeError('REVIEW_TOOL_OR_MODEL_FAILED')
    schema=json.loads(launch['argv_without_prompt'][launch['argv_without_prompt'].index('--json-schema')+1])
    if schema.get('additionalProperties') is not False or set(result)!=set(schema['required']):raise RuntimeError('REVIEW_SCHEMA_FAILED')
    lifecycle=[json.loads(line) for line in (out/'lifecycle.jsonl').read_text().splitlines()]
    if lifecycle[-1]['phase']!='CHILD_CLOSE' or not any(e['phase']=='CHILD_EXIT' for e in lifecycle):raise RuntimeError('REVIEW_LIFECYCLE_FAILED')
    save(output,{'status':'INDEPENDENT_EXACT_REVIEW_READBACK_PASS','launch_sha256':sha((out/'launch.json').read_bytes()),'result':result})
    print('AA_EXACT_REVIEW_READBACK_OK')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['readback','packet','review-check']);parser.add_argument('--campaign',type=Path);parser.add_argument('--source',type=Path);parser.add_argument('--outcomes',type=Path);parser.add_argument('--transport',type=Path);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--review',type=Path);args=parser.parse_args()
    if args.mode=='readback':readback(args.campaign,args.output)
    elif args.mode=='packet':packet(args.source,args.outcomes,args.campaign,args.transport,args.output)
    else:review_check(args.review,args.output)
if __name__=='__main__':main()
