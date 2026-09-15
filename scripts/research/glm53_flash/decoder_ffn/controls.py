import types
from pathlib import Path
import mlx.core as mx
import mlx.nn as nn
from . import source, oracle


def _nested(v): return v.tolist()
def _close(a,b,tol):
    if isinstance(a,list): return all(_close(x,y,tol) for x,y in zip(a,b))
    return abs(a-b) <= tol


def run(root, fixture):
    bound=source.load(Path(root),mx,nn); n=bound.namespace; f=fixture
    cfg=types.SimpleNamespace(hc_mult=f['shape'][2],hc_sinkhorn_iters=f['sinkhorn_iters'],hc_eps=f['hc_eps'],rms_norm_eps=f['rms_norm_eps'],hidden_size=f['shape'][3],intermediate_size=len(f['gate']),swiglu_limit=f['limit'])
    hc=n['HyperConnection'](cfg); hc.train()
    hc.fn=mx.array(f['fn'],dtype=mx.float32); hc.base=mx.array(f['base'],dtype=mx.float32); hc.scale=mx.array(f['scale'],dtype=mx.float32)
    mlp=n['ClampedMLP'](cfg); mlp.gate_proj.weight=mx.array(f['gate'],dtype=mx.float32); mlp.up_proj.weight=mx.array(f['up'],dtype=mx.float32); mlp.down_proj.weight=mx.array(f['down'],dtype=mx.float32)
    owner=types.SimpleNamespace(ffn_hc=hc,post_attention_layernorm=nn.RMSNorm(f['shape'][3],eps=f['rms_norm_eps']),mlp=mlp)
    actual=n['source_ffn_block'](owner,mx.array(f['x'],dtype=mx.float32)); expected=oracle.run(f)
    value=_nested(actual)
    if not _close(value,expected['output'],f['tolerance']): raise AssertionError('DENSE_FFN_SCALAR_MISMATCH')
    return {'output':value,'expected':expected,'branch':'PURE_OPS_TRAINING_TRUE','source_digest':bound.provenance['capsule_sha256']}


def mutants(root, fixture):
    bound=source.load(Path(root),mx,nn); n=bound.namespace; f=fixture
    cfg=types.SimpleNamespace(hc_mult=f['shape'][2],hc_sinkhorn_iters=f['sinkhorn_iters'],hc_eps=f['hc_eps'],rms_norm_eps=f['rms_norm_eps'],hidden_size=f['shape'][3],intermediate_size=len(f['gate']),swiglu_limit=f['limit'])
    hc=n['HyperConnection'](cfg); hc.train(); hc.fn=mx.array(f['fn'],dtype=mx.float32); hc.base=mx.array(f['base'],dtype=mx.float32); hc.scale=mx.array(f['scale'],dtype=mx.float32)
    mlp=n['ClampedMLP'](cfg); mlp.gate_proj.weight=mx.array(f['gate'],dtype=mx.float32); mlp.up_proj.weight=mx.array(f['up'],dtype=mx.float32); mlp.down_proj.weight=mx.array(f['down'],dtype=mx.float32)
    norm=nn.RMSNorm(f['shape'][3],eps=f['rms_norm_eps']); x=mx.array(f['x'],dtype=mx.float32)
    xc,post,comb=hc(x); canonical=n['hc_expand'](mlp(norm(xc)),x,post,comb)
    no_norm=n['hc_expand'](mlp(xc),x,post,comb)
    bypass=mx.broadcast_to(mlp(norm(x[:,:,0,:]))[:,:,None,:], x.shape)
    wrong_residual=n['hc_expand'](mlp(norm(xc)),mx.zeros_like(x),post,comb)
    c=_nested(canonical)
    return {'remove_post_attention_normalization': not _close(c,_nested(no_norm),f['tolerance']), 'bypass_ffn_hc': not _close(c,_nested(bypass),f['tolerance']), 'wrong_hc_expand_residual': not _close(c,_nested(wrong_residual),f['tolerance'])}
