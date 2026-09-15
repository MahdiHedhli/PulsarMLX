"""Paired observations around the unchanged admitted FFN caller."""
import math
import types
from pathlib import Path
import mlx.core as mx
import mlx.nn as nn
from . import source, oracle


def _shape(v):
    if type(v) is list:
        if not v:
            raise ValueError('DENSE_FFN_EMPTY_SHAPE')
        child_shapes = [_shape(child) for child in v]
        if any(s != child_shapes[0] for s in child_shapes):
            raise ValueError('DENSE_FFN_RAGGED_SHAPE')
        return (len(v),)+child_shapes[0]
    if type(v) not in (int,float) or not math.isfinite(v):
        raise ValueError('DENSE_FFN_NONFINITE_OR_TYPE')
    return ()


def _close(a,b,tol,expected_shape=None):
    if type(tol) not in (int,float) or not math.isfinite(tol) or tol < 0:
        return False
    try:
        sa, sb = _shape(a), _shape(b)
    except (ValueError,OverflowError):
        return False
    if sa != sb or (expected_shape is not None and sa != tuple(expected_shape)):
        return False
    def compare(x,y):
        if type(x) is list:
            return all(compare(x[i],y[i]) for i in range(len(x)))
        return abs(x-y) <= tol
    return compare(a,b)


def _owner(n,f):
    cfg=types.SimpleNamespace(hc_mult=f['shape'][2],hc_sinkhorn_iters=f['sinkhorn_iters'],
        hc_eps=f['hc_eps'],rms_norm_eps=f['rms_norm_eps'],hidden_size=f['shape'][3],
        intermediate_size=len(f['gate']),swiglu_limit=f['limit'])
    hc=n['HyperConnection'](cfg)
    hc.train()
    for key in ('fn','base','scale'):
        setattr(hc,key,mx.array(f[key],dtype=mx.float32))
    mlp=n['ClampedMLP'](cfg)
    for key in ('gate','up','down'):
        getattr(mlp,key+'_proj').weight=mx.array(f[key],dtype=mx.float32)
    return types.SimpleNamespace(ffn_hc=hc,
        post_attention_layernorm=nn.RMSNorm(f['shape'][3],eps=f['rms_norm_eps']),mlp=mlp)


def _observe(n,owner,x):
    """Copy around calls, return original objects, never edit selected bodies."""
    values, dtypes, branch_calls = {}, {}, []
    def record(name,array):
        mx.eval(array)
        values[name]=array.tolist()
        dtypes[name]=str(array.dtype)
    def wrap(name,function):
        def observed(*args):
            result=function(*args)
            record(name,result)
            return result
        return observed
    hc=owner.ffn_hc
    def observed_hc(argument):
        result=hc(argument)
        for i,name in enumerate(('xc','post','comb')):
            record(name,result[i])
        return result
    plain_ops=n['_hc_ops']
    def observed_ops(*args):
        branch_calls.append({'branch':'_hc_ops','training':hc.training,
                             'sinkhorn_iters':args[-2]})
        return plain_ops(*args)
    expand=n['hc_expand']
    def observed_expand(branch,residual,post,comb):
        record('residual',residual)
        result=expand(branch,residual,post,comb)
        record('output',result)
        return result
    owner.ffn_hc=observed_hc
    owner.post_attention_layernorm=wrap('norm',owner.post_attention_layernorm)
    owner.mlp.gate_proj=wrap('gate',owner.mlp.gate_proj)
    owner.mlp.up_proj=wrap('up',owner.mlp.up_proj)
    owner.mlp.act=wrap('activation',owner.mlp.act)
    owner.mlp=wrap('mlp',owner.mlp)
    n['_hc_ops']=observed_ops
    n['hc_expand']=observed_expand
    try:
        output=n['source_ffn_block'](owner,x)
        mx.eval(output)
    finally:
        n['_hc_ops']=plain_ops
        n['hc_expand']=expand
    return output,values,dtypes,branch_calls


def run(root,fixture,contract):
    bound=source.load(Path(root),mx,nn)
    n=bound.namespace
    x=mx.array(fixture['x'],dtype=mx.float32)
    actual,candidate,dtypes,calls=_observe(n,_owner(n,fixture),x)
    unobserved=n['source_ffn_block'](_owner(n,fixture),x)
    mx.eval(unobserved)
    equivalent=actual.tolist()==unobserved.tolist()
    expected=oracle.run(fixture)
    decisions={name:_close(candidate[name],expected['boundaries'][name],
        contract['tolerances'][name],contract['boundary_shapes'][name])
        for name in contract['boundary_shapes']}
    clamp_ok=(expected['clamp_active_elements']>0 if fixture['clamp_expected']=='active'
              else expected['clamp_active_elements']==0)
    status=(all(decisions.values()) and equivalent and clamp_ok
        and all(v=='mlx.core.float32' for v in dtypes.values())
        and len(calls)==1 and calls[0]['branch']=='_hc_ops' and calls[0]['training'])
    return {'fixture_id':fixture['fixture_id'],'status':'PASS' if status else 'FAIL',
        'candidate':candidate,'oracle':expected['boundaries'],
        'observed_shapes':{name:list(_shape(v)) for name,v in candidate.items()},
        'expected_shapes':contract['boundary_shapes'],'dtypes':dtypes,
        'decisions':decisions,'clamp_active_elements':expected['clamp_active_elements'],
        'clamp_case_decision':clamp_ok,'observation_output_equivalent':equivalent,
        'uninstrumented_output':unobserved.tolist(),'branch_calls':calls,
        'capsule_sha256':bound.provenance['graph_sha256'][source.CAPSULE],
        'candidate_evaluations':2,'oracle_evaluations':1}
