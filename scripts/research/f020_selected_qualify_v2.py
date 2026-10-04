#!/usr/bin/env python3
"""Selected qualification workers: explicit exact review required; static default.

All original real values and results stay in the supplied private Studio audit.
No worker can observe numerical data with only a preliminary host review.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import sys
import time
from fractions import Fraction
import f020_selected_authority_v2 as A
from f020_selected_process_v2 import private_json, owned_child
import f020_selected_snapshot_v2 as S
import f020_selected_r1_v2 as R
import f020_selected_compare_v2 as C
import f020_selected_ledger_v2 as L
from f020_selected_controls_v2 import reference_authority, host_controls, native_control

ROOT=Path(__file__).resolve().parents[2]
CONTRACT='specs/020-mlx-safetensors-affine/selected-numerical-v2/contracts/selected-numerical-v2.json'
REAL_SHA='43e251a64d1d475900214d3c51b9b21ca988e7b6634d3891fbc6c3a0d5733305'


def receipt(cap,key):
    record=cap[key];raw=A.bounded(record['path'],private=True)
    A.require(A.sha(raw)==record['sha256'],'private receipt binding '+key)
    return A.strict(raw)


def qualified_real(cap,d,contract,manifest):
    ids=[v['id'] for k in ('cases','refusals','mutations') for v in manifest[k]]
    binding=cap['real_binding']
    for key in ('snapshot_sha256','snapshot_bytes','metadata_sha256','ranges_sha256'):
        A.require(binding[key]==contract[key],'fixed original capture '+key)
    q=receipt(cap,'synthetic_qualification')
    A.require(q['schema']=='pulsarmlx.selected-synthetic-qualification/2' and q['status']=='PASS','synthetic qualification')
    for key in ('commit','tree','executable_sha256','population_sha256'):
        A.require(q[key]==d[key],'synthetic exact version '+key)
    A.require(q['review_sha256']==cap['review_sha256'] and q['positive_count']==2 and q['refusal_count']==24
        and q['mutation_count']==13 and q['mutation_survivors']==0 and q['primitive_regressions']==363
        and q['plane_regressions']==32,'full synthetic/regression gate')
    A.require(q['passed_ids']==ids,'exact full population ID evidence')
    return binding


def verified(cap):
    A.require(cap['schema']=='pulsarmlx.selected-capability/2','capability schema')
    d=A.verify_current(cap['repo'],cap['capsule_path'],cap['review_path'],cap['capsule_sha256'],
        cap['review_sha256'],cap['executable'],Path(cap['repo'])/CONTRACT,cap['population_path'],cap['input_path'])
    contract=A.strict(A.bounded(Path(cap['repo'])/CONTRACT))
    A.require(contract['input']['sha256']==R.INPUT_SHA256==d['input_sha256'],'fixed input version')
    A.require(contract['snapshot_sha256']==REAL_SHA,'fixed original snapshot')
    A.require(contract['fixed']['E_act']=='1/128' and contract['fixed']['beta_B']=='5201/4194304'
              and contract['fixed']['down_floor']=='1/2^32','fixed numerical definitions')
    manifest=A.strict(A.bounded(cap['population_path']))
    A.require(manifest['population']=={'full_shape_positive':2,'host_refusal_and_guard':24,'mutation':13,'total':39},'complete population counts')
    A.require(len(manifest['cases'])==2 and len(manifest['refusals'])==24 and len(manifest['mutations'])==13,'complete population lengths')
    ids=[v['id'] for k in ('cases','refusals','mutations') for v in manifest[k]]
    A.require(len(set(ids))==39,'unique complete population IDs')
    if cap['kind']=='synthetic':
        cases=[v for v in manifest['cases'] if v['id']==cap['case_id']]
        A.require(len(cases)==1,'synthetic positive identity')
        binding=cases[0]['binding']
    elif cap['kind']=='real':
        A.require(not cap.get('control_id'),'no real mutation controls')
        binding=qualified_real(cap,d,contract,manifest)
        L.verify(cap,d,binding)
    else:raise ValueError('unknown selected scope')
    out=Path(cap['out']).resolve();repo=Path(cap['repo']).resolve()
    A.require(out.is_dir() and not out.is_relative_to(repo) and out.stat().st_mode&0o077==0
              and out.stat().st_uid==os.getuid(),'private external output')
    return d,contract,manifest,binding,out


def identity(cap,d,binding):
    return {**{k:d[k] for k in ('commit','tree','executable_sha256','contract_sha256','population_sha256','input_sha256')},
            'snapshot_sha256':binding['snapshot_sha256'],'review_sha256':cap['review_sha256'],
            **({'real_attempt_sha256':L.capability_sha(cap)} if cap['kind']=='real' else {})}


def resource_record(start):
    peak=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # This worker is admitted only on Darwin, where ru_maxrss is bytes.
    A.require(sys.platform=='darwin','Studio Darwin RSS units')
    return {'status':'PASS' if peak<=256*1024*1024 else 'FAIL','process_peak_rss_bytes':peak,
            'acceptance_cap_bytes':256*1024*1024,'elapsed_seconds':time.monotonic()-start,
            'hard_global_ram_claim':False}


def reference_worker(cap):
    d,contract,manifest,binding,out=verified(cap)
    started=time.monotonic();base=identity(cap,d,binding)
    if cap['kind']=='real':L.begin_reference(cap,d,binding)
    # Create-only attempt marker precedes any selected snapshot read. A refused
    # fixed real attempt cannot silently be rerun in this audit directory.
    private_json(out/'reference-started.json',{'schema':'pulsarmlx.selected-reference-start/2',**base,'kind':cap['kind']})
    result={'schema':'pulsarmlx.selected-r1-admission/2',**base,'status':'REFUSED','kind':cap['kind'],
            'candidate_observations':0,'original_checkpoint_bytes_read':0}
    try:
        parts=S.read_snapshot(cap['snapshot_path'],binding)
        result['selected_snapshot_bytes_read']=binding['snapshot_bytes']
        raw=A.bounded(cap['input_path'],16384)
        reference=R.references(parts,raw)
        resources=resource_record(started)
        result['resources']=resources
        A.require(resources['status']=='PASS','reference scratch/RSS acceptance cap')
        document={'schema':'pulsarmlx.selected-original-r1/2',**base,
                  'authority':'original snapshot and original x; candidate-independent',
                  'reference':C.serialize(reference)}
        path=out/'original-r1.json';private_json(path,document)
        result['reference']={'path':str(path),'sha256':A.sha(A.bounded(path,private=True))}
        result['resources']=resource_record(started)
        A.require(result['resources']['status']=='PASS','reference post-serialization RSS cap')
        result['status']='ADMITTED'
    except (ValueError,OSError,KeyError,ArithmeticError) as error:
        result['reason']=str(error)
        if hasattr(error,'evidence'):result['original_byte_refusal_evidence']=error.evidence
        result['resources']=resource_record(started)
    private_json(out/'pre-admission.json',result)
    return result['status']=='ADMITTED'


def comparison_worker(cap):
    d,contract,manifest,binding,out=verified(cap)
    started=time.monotonic();base=identity(cap,d,binding)
    admission=receipt(cap,'pre_admission')
    A.require(admission['status']=='ADMITTED' and all(admission[k]==v for k,v in base.items()),'admitted original R1 authority')
    reference_receipt=admission['reference']
    raw=A.bounded(reference_receipt['path'],private=True)
    A.require(A.sha(raw)==reference_receipt['sha256'],'original R1 result digest')
    ref=A.strict(raw)
    reference_authority(ref,base)
    candidate=A.strict(A.bounded(out/'native-result.json',private=True))
    parts=S.read_snapshot(cap['snapshot_path'],binding)
    result={'schema':'pulsarmlx.selected-stage-qualification/2',**base,'status':'FAIL','kind':cap['kind']}
    try:
        stages=C.compare(candidate,C.deserialize(ref['reference']),parts,base)
        resources=resource_record(started);A.require(resources['status']=='PASS','comparison scratch/RSS cap')
        result.update(status='PASS',stages=stages,resources=resources)
    except (ValueError,KeyError,ArithmeticError) as error:
        result.update(reason=str(error),resources=resource_record(started))
    private_json(out/'stage-qualification.json',result)
    return result['status']=='PASS'


def run_positive(cap):
    """Supervisor entry; each worker independently repeats exact review checks."""
    d,contract,manifest,binding,out=verified(cap)
    job=out/'capability-reference.json';private_json(job,cap)
    command=[sys.executable,str(Path(__file__).resolve()),'--reference-worker',str(job)]
    w=owned_child(command,out/'reference-process',256*1024*1024)
    if w['status']!='PASS':return False
    admission=out/'pre-admission.json';ar=A.strict(A.bounded(admission,private=True))
    if ar['status']!='ADMITTED':return False
    cap=dict(cap,pre_admission={'path':str(admission),'sha256':A.sha(A.bounded(admission,private=True))})
    native_cap=out/'capability-native.json';private_json(native_cap,cap)
    env=dict(os.environ,MLX_ENABLE_TF32='0')
    for key in ('MLX_METAL_GPU_ARCH','MLX_MAX_OPS_PER_BUFFER','MLX_MAX_MB_PER_BUFFER','DYLD_INSERT_LIBRARIES'):
        A.require(key not in env,'unsupported native environment '+key)
    w=owned_child([cap['executable'],'--selected',str(native_cap)],out/'native-process',1024*1024*1024,env=env)
    if w['status']!='PASS':return False
    w=owned_child([sys.executable,str(Path(__file__).resolve()),'--comparison-worker',str(native_cap)],out/'comparison-process',256*1024*1024)
    return w['status']=='PASS'



NATIVE_CONTROLS=('omit-gate-bias','omit-up-bias','nibble-order','gate-up-swap','lower-gate-clamp',
                 'missing-upper-gate-clamp','missing-up-upper-clamp','missing-up-lower-clamp')


def controls_worker(cap,native=False):
    d,_,manifest,binding,out=verified(cap)
    A.require(cap['kind']=='synthetic','synthetic controls only')
    started=time.monotonic();base=identity(cap,d,binding)
    admission=receipt(cap,'pre_admission')
    A.require(admission['status']=='ADMITTED' and all(admission[k]==v for k,v in base.items()),'control original admission')
    rr=admission['reference'];raw=A.bounded(rr['path'],private=True)
    A.require(A.sha(raw)==rr['sha256'],'control original R1 digest')
    ref=A.strict(raw);reference_authority(ref,base)
    if native:
        ident=cap['control_id'];A.require(ident in NATIVE_CONTROLS,'native control scope')
        report=A.strict(A.bounded(out/'native-result.json',private=True))
        for key in ('commit','tree','snapshot_sha256','input_sha256','review_sha256'):
            A.require(report[key]==base[key],'control native identity '+key)
        parts=S.read_snapshot(cap['snapshot_path'],binding)
        result=native_control(report,ident,C.deserialize(ref['reference']),parts,A.bounded(cap['input_path'],16384))
        result['resources']=resource_record(started)
        A.require(result['resources']['status']=='PASS','control reference resources')
        private_json(out/'control-qualification.json',result)
    else:
        report=A.strict(A.bounded(Path(cap['positive_out'])/'native-result.json',private=True))
        results=host_controls(manifest,cap['snapshot_path'],binding,A.bounded(cap['input_path'],16384),ref,report,out/'host-fixtures')
        result={'status':'PASS','results':results,'resources':resource_record(started)}
        A.require(result['resources']['status']=='PASS','host control resources')
        private_json(out/'host-control-qualification.json',result)
    return True


def regression_summaries(cap,descriptor):
    records={}
    for key,count in (('primitives',363),('planes',32)):
        record=cap['regressions'][key]
        raw=A.bounded(record['summary_path']);A.require(A.sha(raw)==record['summary_sha256'],'regression summary hash')
        summary=A.strict(raw)
        A.require(summary['result']=='PASS' and summary['candidate_commit']==descriptor['commit']
                  and summary['worktree_dirty'] is False,'exact clean regression result')
        actual_count=len(summary['cases']) if key=='primitives' else summary['case_accounting']['case_ids']
        A.require(actual_count==count,'regression case count')
        if key=='primitives':
            A.require(summary['frozen']['case_count']==count,'frozen primitive count')
        A.require(all(g['cases']==g['passed'] for g in summary['gate_counts'].values()),'regression gate counts')
        A.require(summary.get('failures')==[],'regression failures')
        raw_child=A.bounded(record['report_path'])
        A.require(A.sha(raw_child)==summary['child']['report_sha256'],'regression raw child digest')
        child=A.strict(raw_child);provenance=child['provenance']
        expected_build=descriptor['build']
        A.require(provenance['build']['qualify_executable_sha256']==expected_build['regression_executables']['qualify']['sha256'],
                  'reviewed regression child executable')
        parent='native_qualification' if key=='primitives' else 'composition_qualification'
        A.require(record['parent_executable_sha256']==expected_build['regression_executables'][parent]['sha256'],
                  'reviewed regression parent executable')
        for library in ('libmlx','libmlxc','metallib'):
            A.require(provenance[library]['sha256']==expected_build['native_libraries'][library]['sha256'],
                      'reviewed regression native library')
        records[key]={'count':count,'summary_sha256':A.sha(raw),'child_sha256':A.sha(raw_child)}
    return records


def full_synthetic(cap):
    d,_,manifest,_,out=verified(cap)
    A.require(cap['kind']=='synthetic' and not cap.get('control_id'),'full synthetic mode')
    # Fail before any new numerical observations if inherited evidence is absent.
    regressions=regression_summaries(cap,d)
    population_root=Path(cap['population_path']).parent
    passed=[];positive_caps=[];evidence={}
    for case in manifest['cases']:
        case_out=out/case['id'];case_out.mkdir(mode=0o700,exist_ok=False)
        case_cap=dict(cap,case_id=case['id'],out=str(case_out),snapshot_path=str(population_root/case['snapshot']))
        A.require(run_positive(case_cap),'full positive failed '+case['id'])
        ar=case_out/'pre-admission.json'
        case_cap['pre_admission']={'path':str(ar),'sha256':A.sha(A.bounded(ar,private=True))}
        positive_caps.append(case_cap);passed.append(case['id'])
        evidence[case['id']]=A.sha(A.bounded(case_out/'stage-qualification.json',private=True))
    first=positive_caps[0]
    host_out=out/'host-controls';host_out.mkdir(mode=0o700,exist_ok=False)
    host_cap=dict(first,out=str(host_out),positive_out=first['out'])
    job=host_out/'capability.json';private_json(job,host_cap)
    w=owned_child([sys.executable,str(Path(__file__).resolve()),'--host-controls-worker',str(job)],host_out/'process',256*1024*1024)
    A.require(w['status']=='PASS','host control worker')
    host_result=A.strict(A.bounded(host_out/'host-control-qualification.json',private=True))
    A.require(host_result['status']=='PASS','host controls')
    outcomes={r['id']:r for r in host_result['results']}
    for ident in NATIVE_CONTROLS:
        control_out=out/ident;control_out.mkdir(mode=0o700,exist_ok=False)
        cc=dict(first,out=str(control_out),control_id=ident)
        job=control_out/'capability.json';private_json(job,cc)
        env=dict(os.environ,MLX_ENABLE_TF32='0')
        w=owned_child([cc['executable'],'--selected',str(job)],control_out/'native-process',1024*1024*1024,env=env)
        A.require(w['status']=='PASS','native control process '+ident)
        w=owned_child([sys.executable,str(Path(__file__).resolve()),'--native-control-worker',str(job)],control_out/'reference-process',256*1024*1024)
        A.require(w['status']=='PASS','native control reference '+ident)
        result=A.strict(A.bounded(control_out/'control-qualification.json',private=True))
        A.require(result['status']=='PASS' and result['id']==ident,'native control result')
        outcomes[ident]=result
    for case in manifest['refusals']+manifest['mutations']:
        A.require(case['id'] in outcomes and outcomes[case['id']]['status']=='PASS','missing/surviving control')
        passed.append(case['id'])
    A.require(len(passed)==39 and len(set(passed))==39 and len(outcomes)==37,'exact full synthetic population')
    summary={'schema':'pulsarmlx.selected-synthetic-qualification/2','status':'PASS',
       **{k:d[k] for k in ('commit','tree','executable_sha256','population_sha256')},
       'review_sha256':cap['review_sha256'],'positive_count':2,'refusal_count':24,'mutation_count':13,
       'mutation_survivors':0,'primitive_regressions':363,'plane_regressions':32,
       'passed_ids':passed,'positive_evidence':evidence,'controls':outcomes,'regressions':regressions}
    private_json(out/'synthetic-qualification.json',summary)
    return True


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--reference-worker',type=Path)
    mode.add_argument('--comparison-worker',type=Path)
    mode.add_argument('--run-positive',type=Path)
    mode.add_argument('--host-controls-worker',type=Path)
    mode.add_argument('--native-control-worker',type=Path)
    mode.add_argument('--run-synthetic',type=Path)
    args=parser.parse_args()
    if not any(vars(args).values()):
        print(json.dumps({'status':'STATIC_ONLY','selected_numerical_calls':0}));return
    path=args.reference_worker or args.comparison_worker or args.run_positive or args.host_controls_worker or args.native_control_worker or args.run_synthetic
    cap=A.strict(A.bounded(path,1024*1024,private=True))
    if args.reference_worker:ok=reference_worker(cap)
    elif args.comparison_worker:ok=comparison_worker(cap)
    elif args.host_controls_worker:ok=controls_worker(cap)
    elif args.native_control_worker:ok=controls_worker(cap,True)
    elif args.run_synthetic:ok=full_synthetic(cap)
    else:ok=run_positive(cap)
    if not ok:raise SystemExit(1)


if __name__=='__main__':main()
