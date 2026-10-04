#!/usr/bin/env python3
"""Frozen synthetic control evidence; invoke only after exact review admission."""
import copy
from fractions import Fraction as F
import json
from pathlib import Path
import struct
import f020_selected_authority_v2 as A
import f020_selected_snapshot_v2 as S
import f020_selected_r1_v2 as R
import f020_selected_compare_v2 as C
from f020_selected_process_v2 import private_json
from f020_expert_mlp_r1_v1 import activation


def refusal(action,expected):
    try:action()
    except ValueError as error:
        A.require(expected in str(error),'wrong control refusal: '+str(error))
        return str(error)
    raise ValueError('mutation/refusal survived: '+expected)


def replace_pointer(value,pointer,replacement):
    parts=pointer.lstrip('/').split('/');target=value
    for p in parts[:-1]:target=target[int(p)] if type(target) is list else target[p]
    key=int(parts[-1]) if type(target) is list else parts[-1]
    target[key]=replacement


def reference_authority(document,identity):
    A.require(document.get('schema')=='pulsarmlx.selected-original-r1/2'
        and document.get('authority')=='original snapshot and original x; candidate-independent'
        and all(document.get(k)==v for k,v in identity.items()),'independent R1 authority')


def host_controls(manifest,base_path,binding,input_bytes,reference_document,positive_report,out):
    """All inputs here are hash-verified synthetic A artifacts from the caller."""
    out=Path(out);out.mkdir(mode=0o700,exist_ok=False)
    raw=A.bounded(base_path,16*1024*1024)
    A.require(A.sha(raw)==binding['snapshot_sha256'],'synthetic base binding')
    size=struct.unpack_from('<Q',raw,8)[0];header=A.strict(raw[16:16+size])
    original=S.read_snapshot(base_path,binding)
    results=[]
    def add(ident,evidence):results.append({'id':ident,'status':'PASS','evidence':evidence,'native_numerical_calls':0})
    def header_case(control,expected):
        h=copy.deepcopy(header);replace_pointer(h,control['pointer'],control['value'])
        detail=refusal(lambda:S.decode_header(json.dumps(h).encode(),binding),expected)
        add(control['id'],detail)
    expected_identity={'source':'metadata binding','layer':'role identity','expert':'integer binding',
                       'role':'role identity','recipe':'integer binding','shape':'integer binding'}
    for control in manifest['refusals']:
        ident=control['id']
        if ident in ('input-floor','down-floor-guard'):
            k=4096 if ident=='input-floor' else 2048
            data=bytearray(input_bytes if k==4096 else struct.pack('<f',1)*2048)
            data[:4]=struct.pack('<I',0x2f000000)
            add(ident,refusal(lambda:R.original_input(bytes(data),k),'R-DOMAIN-X-RANGE'))
        elif ident=='metadata-floor':
            p=list(original['gate']);data=bytearray(p[1]);data[:2]=struct.pack('<H',0x2f00);p[1]=bytes(data)
            add(ident,refusal(lambda:next(R.Plane('gate',tuple(p)).groups(0)),'R-DOMAIN-META-RANGE'))
        elif ident in ('gate-margin','up-margin','computed-hidden-margin'):
            parts=dict(original)
            changes=[('gate' if ident=='gate-margin' else 'up',8.5)] if ident!='computed-hidden-margin' else [('gate',2**-21),('up',.5)]
            for role,bias in changes:
                p=list(parts[role]);scales=bytearray(p[1]);biases=bytearray(p[2]);scales[:128]=bytes(128)
                word=struct.unpack('<I',struct.pack('<f',bias))[0]>>16
                biases[:128]=struct.pack('<H',word)*64;p[1]=bytes(scales);p[2]=bytes(biases);parts[role]=tuple(p)
            expected='prospective activation margin' if ident!='computed-hidden-margin' else 'prospective down nonzero floor margin'
            add(ident,refusal(lambda:R.references(parts,input_bytes),expected))
        elif ident.startswith('identity-'):
            header_case(control,expected_identity[ident.removeprefix('identity-')])
        elif ident.startswith('range-digest-'):
            i=control['edit']['range'];offset=16+size+sum(S.LENGTHS[:i]);mutated=bytearray(raw);mutated[offset]^=255
            path=out/(ident+'.snapshot');path.write_bytes(mutated);path.chmod(0o400)
            add(ident,refusal(lambda:S.read_snapshot(path,binding),'range digest'))
        elif ident=='framing-length':
            h=copy.deepcopy(header);h['payload_lengths'][0]=1
            add(ident,refusal(lambda:S.decode_header(json.dumps(h).encode(),binding),'integer binding'))
        elif ident=='framing-duplicate':
            duplicate=b'{"schema":"duplicate",'+raw[16:16+size].lstrip()[1:]
            add(ident,refusal(lambda:S.decode_header(duplicate,binding),'duplicate key'))
        elif ident=='framing-trailing':
            path=out/(ident+'.snapshot');path.write_bytes(raw+b'\0');path.chmod(0o400)
            add(ident,refusal(lambda:S.read_snapshot(path,binding),'file bound'))
        else:raise ValueError('unimplemented refusal '+ident)
    for ident in ('role-swap','expert-swap','reinterpret-8-bit'):
        h=copy.deepcopy(header)
        if ident=='role-swap':h['owned']['plan']['planes'][0],h['owned']['plan']['planes'][2]=h['owned']['plan']['planes'][2],h['owned']['plan']['planes'][0];expected='role identity'
        elif ident=='expert-swap':h['owned']['plan']['request']['expert']=1;expected='integer binding'
        else:h['owned']['plan']['planes'][0]['bits']=8;expected='integer binding'
        add(ident,refusal(lambda:S.decode_header(json.dumps(h).encode(),binding),expected))
    reference=C.deserialize(reference_document['reference'])
    identity={k:reference_document[k] for k in ('commit','tree','snapshot_sha256','input_sha256','review_sha256')}
    report=copy.deepcopy(positive_report);report.pop('down_admission')
    add('skip-down-admission',refusal(lambda:C.compare(report,reference,original,identity),'actual down admission record required'))
    doc=copy.deepcopy(reference_document);doc['authority']='candidate-hidden'
    add('candidate-fed-reference',refusal(lambda:reference_authority(doc,identity),'independent R1 authority'))
    expected=[v['id'] for v in manifest['refusals']]+[v['id'] for v in manifest['mutations'] if v['kind'] in ('host-custody','report-audit','authority-audit')]
    A.require(len(results)==len(expected) and {r['id'] for r in results}==set(expected),'complete host controls')
    private_json(out/'host-controls.json',{'schema':'pulsarmlx.selected-host-controls/2','status':'PASS','results':results})
    return results


def native_control(report,ident,reference,parts,input_bytes):
    A.require(report['outcome']=='executed' and report['control_id']==ident,'native control identity')
    clean=report['final_cleanup'];A.require(clean['live']==clean['double_frees']==clean['handler_messages']==0 and clean['errors']==[],'control cleanup')
    def resources(stage):
        m=stage['resources']
        A.require(m['active_bytes']<=64*1024*1024 and m['allocator_peak_bytes']<=64*1024*1024
            and m['process_peak_rss_bytes']<=1024*1024*1024,'control native resources')
    if ident=='nibble-order':
        stage=report['projection_control'];resources(stage)
        A.require(stage['role']==0 and stage['after'][0]-stage['before'][0]==5
            and stage['after'][1]-stage['before'][1]==4,'packing witness QMM calls')
        witness=(struct.pack('<I',0x76543210)*1048576,struct.pack('<H',0x3f80)*131072,bytes(262144))
        basis=struct.pack('<f',1)+bytes(4095*4)
        A.require(stage['input_sha256']==A.sha(basis) and stage['component_sha256']==[A.sha(v) for v in witness],
                  'original synthetic packing witness bytes')
        original,budget=R.affine(R.Plane('gate',witness),R.original_input(basis,4096))
        actual,_=C.decode(stage['output'],2048)
        # Independent reversed-U32-nibble decoder on the same immutable bytes.
        # Basis x has only j=0 nonzero: all remaining contraction terms vanish.
        mutant=[];mutant_budget=[]
        for row in range(2048):
            word=struct.unpack_from('<I',witness[0],row*2048)[0]
            q=(word>>28)&15
            mutant.append(F(q));mutant_budget.append(R.gamma(4096)*q)
        A.require(all(v==0 and b==0 for v,b in zip(original,budget,strict=True)),'original decoder basis result')
        A.require(all(v==7 for v in mutant),'reversed decoder basis result')
        A.require(all(abs(a-o)<=b for a,o,b in zip(actual,original,budget,strict=True)),'candidate original packing')
        A.require(all(abs(m-o)>b+mb for m,o,b,mb in zip(mutant,original,budget,mutant_budget,strict=True)),
                  'packing mutation survives local budgets')
        return {'id':ident,'status':'PASS','detected_lanes':2048,'native_qmm_calls':1,
                'original_r1':'Plane/affine/code from original packed bytes','mutant':'reverse nibble positions within original U32'}
    if ident in ('omit-gate-bias','omit-up-bias'):
        role='gate' if ident=='omit-gate-bias' else 'up';index=0 if role=='gate' else 1
        stage=report['projection_control'];A.require(stage['role']==index,'bias role')
        resources(stage)
        A.require(stage['after'][0]-stage['before'][0]==5 and stage['after'][1]-stage['before'][1]==4,'control QMM calls')
        actual,_=C.decode(stage['output'],2048)
        modified=list(parts[role]);modified[2]=bytes(len(modified[2]))
        mutant,rounding=R.affine(R.Plane(role,tuple(modified)),R.original_input(input_bytes,4096))
        A.require(all(abs(a-b)<=r for a,b,r in zip(actual,mutant,rounding,strict=True)),'mutant QMM own bound')
        original=reference['g' if role=='gate' else 'u'];budget=reference['bg' if role=='gate' else 'bu']
        witnesses=[i for i,(a,b,r) in enumerate(zip(actual,original,budget,strict=True)) if abs(a-b)>r]
        A.require(bool(witnesses),'bias omission survivor')
        return {'id':ident,'status':'PASS','detected_lanes':len(witnesses)}
    runs=report['activation_control'];A.require(len(runs)==2,'baseline+mutant runs')
    for i,run in enumerate(runs):
        resources(run)
        s=run['stats'];A.require(run['mutant'] is bool(i) and run['status']==0 and s[0]==2 and s[2:]==[9,4,13,1,9,0],'control ownership')
    if ident=='gate-up-swap':
        a,_=C.decode(runs[0]['output'],2048);b,_=C.decode(runs[1]['output'],2048)
        normal,swapped=activation(F(1),F(2)),activation(F(2),F(1))
        A.require(all(C.distance(v,normal)<=F(1,128) for v in a),'baseline activation bound')
        A.require(all(C.distance(v,swapped)<=F(1,128) for v in b),'mutant activation bound')
        A.require(all(C.distance(v,reference['h'][0])>reference['bh'][0] for v in b),'gate/up mutation survivor')
    else:
        g,u,gm,um={
            'lower-gate-clamp':(-15,1,-10,1),
            'missing-upper-gate-clamp':(10,2,12,2),
            'missing-up-upper-clamp':(2,10,2,12),
            'missing-up-lower-clamp':(2,-10,2,-12)}[ident]
        word=lambda v:struct.unpack('<I',struct.pack('<f',v))[0]
        for run,eg,eu in ((runs[0],g,u),(runs[1],gm,um)):
            A.require(run['gate_clamp_bits']==[word(eg)]*2048 and run['up_clamp_bits']==[word(eu)]*2048,'exact clamp mutation predicate')
    return {'id':ident,'status':'PASS','detected_lanes':2048}
