#!/usr/bin/env python3
"""Independent local and ideal stage gates; no candidate-fed ideal reference."""
from fractions import Fraction as F
import hashlib
import struct
import f020_selected_r1_v2 as R
from f020_expert_mlp_r1_v1 import f32, activation


def require(ok,why):
    if not ok:raise ValueError('QUALIFICATION: '+why)


def decode(output,n):
    require(output['shape']==[1,n] and output['dtype']=='F32','output geometry/dtype')
    words=output['f32_bits']
    require(type(words) is list and len(words)==n and all(type(w) is int and 0<=w<2**32 for w in words),'output words')
    raw=b''.join(struct.pack('<I',w) for w in words)
    require(hashlib.sha256(raw).hexdigest()==output['sha256'],'output digest')
    return [f32(w) for w in words],raw


def distance(value,interval):return max(abs(value-interval[0]),abs(value-interval[1]))


def serialize(reference):
    return {name:[[str(v[0]),str(v[1])] if isinstance(v,tuple) else str(v) for v in values]
            for name,values in reference.items()}


def deserialize(reference):
    expected={'g':2048,'u':2048,'bg':2048,'bu':2048,'h':2048,'bh':2048,'y':4096,'propagated':4096}
    require(set(reference)==set(expected),'reference stages')
    out={}
    for name,n in expected.items():
        values=reference[name];require(type(values) is list and len(values)==n,'reference shape')
        if name in ('h','y'):
            require(all(type(v) is list and len(v)==2 for v in values),'interval pairs')
            out[name]=[tuple(F(x) for x in v) for v in values]
            require(all(a<=b for a,b in out[name]),'ordered reference intervals')
            if name=='h':require(all(b-a<=F(1,2**160) for a,b in out[name]),'hidden enclosure width')
        else:out[name]=[F(v) for v in values]
        if name in ('bg','bu','bh','propagated'):
            require(all(v>=0 for v in out[name]),'nonnegative reference budgets')
    return out


def compare(report,reference,parts,identity):
    require(report['outcome']=='executed','candidate incomplete')
    require('down_admission' in report,'actual down admission record required')
    for key in ('commit','tree','snapshot_sha256','input_sha256','review_sha256'):
        require(report[key]==identity[key],'candidate identity '+key)
    clean=report['final_cleanup']
    require(clean['live']==clean['double_frees']==clean['handler_messages']==0 and clean['errors']==[],'cleanup')
    for role,exponent in [('gate',273),('up',273),('down',145)]:
        stage=report[role]
        require(stage['bound_exponent']==exponent and stage['preflight_calls']==0,'family/guard')
        before,after=stage['calls_before'],stage['calls_after']
        require(after[0]-before[0]==5 and after[1]-before[1]==4,'QMM call/import count')
        require(stage['packed_sha256']==hashlib.sha256(parts[role][0]).hexdigest(),'original packed weight identity')
        for label in ('resources_before','resources_after'):
            m=stage[label]
            require(m['active_bytes']<=64*1024*1024 and m['allocator_peak_bytes']<=64*1024*1024
                    and m['process_peak_rss_bytes']<=1024*1024*1024,'native resources')
    g,graw=decode(report['gate']['output'],2048)
    u,uraw=decode(report['up']['output'],2048)
    h,hraw=decode(report['activation']['output'],2048)
    y,_=decode(report['down']['output'],4096)
    require(report['gate']['input_sha256']==report['up']['input_sha256']==identity['input_sha256'],'projection input identity')
    require(report['down']['input_sha256']==hashlib.sha256(hraw).hexdigest(),'actual down input')
    admission=report['down_admission']
    require(admission['decision']=='admitted' and admission['before']==admission['after']
            and admission['input_sha256']==hashlib.sha256(hraw).hexdigest(),'actual down admission')
    a=report['activation'];s=a['stats']
    require(a['status']==0 and a['elements']==2048 and len(s)==8 and s[0]==2 and s[2:]==[9,4,13,1,9,0],'activation ownership/order')
    def clamp_words(raw,gate):
        vals=struct.iter_unpack('<f',raw)
        return [struct.unpack('<I',struct.pack('<f',min(v,10) if gate else min(max(v,-10),10)))[0] for (v,) in vals]
    require(a['gate_clamp_bits']==clamp_words(graw,True) and a['up_clamp_bits']==clamp_words(uraw,False),'exact clamp semantics')
    errors={'gate':[],'up':[],'activation_local':[],'hidden_ideal':[],'down_local':[],'output_ideal':[]}
    for i in range(2048):
        require(abs(g[i]-reference['g'][i])<=reference['bg'][i],'gate local bound')
        require(abs(u[i]-reference['u'][i])<=reference['bu'][i],'up local bound')
        local=activation(g[i],u[i])
        require(distance(h[i],local)<=F(1,128),'activation local E_act')
        require(distance(h[i],reference['h'][i])<=reference['bh'][i],'ideal hidden bound')
        errors['gate'].append(abs(g[i]-reference['g'][i]));errors['up'].append(abs(u[i]-reference['u'][i]))
        errors['activation_local'].append(distance(h[i],local));errors['hidden_ideal'].append(distance(h[i],reference['h'][i]))
    # Candidate hidden is permitted ONLY for this local-down contraction/budget.
    hx=R.original_input(hraw,2048)
    local,rounding=R.affine(R.Plane('down',parts['down']),hx)
    for i in range(4096):
        local_distance=abs(y[i]-local[i]);ideal_distance=distance(y[i],reference['y'][i])
        require(local_distance<=rounding[i],'down local bound')
        require(ideal_distance<=rounding[i]+reference['propagated'][i],'ideal output bound')
        errors['down_local'].append(local_distance);errors['output_ideal'].append(ideal_distance)
    return {'status':'PASS','stage_max_abs_errors':{k:str(max(v)) for k,v in errors.items()},
            'counts':{'gate':2048,'up':2048,'hidden':2048,'output':4096},
            'E_act':'1/128','beta_B':'5201/4194304','candidate_hidden_scope':'local down only'}
