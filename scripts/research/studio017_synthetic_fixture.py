"""Produce a synthetic-only five-layer packed fixture golden, using the independent CPU graph.
Inputs are deterministic scalars; accepts no model/directory/real token or routes. No MLX.
Regenerate before native controls and byte-compare the committed golden, never fit after launch.
"""
import json
import numpy as np
import studio017_ref_graph as g
from studio017_ref_store import bf
from studio017_ref_criteria import golden_margin


def salt(name):
    h=17
    for c in name.encode('ascii'):
        h=(h*3+c)%101
    return h


def unpacked_values(out, width, key, plane=0):
    # Each programmed packed coefficient is 8 + add, scale=1/16, bias=-1/2.
    # Fill all padded columns with code 8 (real zero). Head rows are untied,
    # with a planted distinct largest row, not a passed expected token.
    row=np.arange(out)[:,None]
    col=np.arange(width)[None,:]
    h=salt(key)
    pick=(row+h+plane)%width
    amp=1+(row+plane+h)%5
    if key=='language_model.lm_head':
        amp=np.where(row==17,14,1+row%4)
    return (np.where(col==pick,amp,0)+np.where(col==(pick+1)%width,1,0)).astype('f8')/16


class Weights:
    def dense(self,name,shape,dtype='BF16'):
        h=salt(name); idx=np.arange(np.prod(shape))
        if name.endswith('e_score_correction_bias'): v=idx/16.
        elif name.endswith('.mlp.gate.weight'):return ((np.indices(shape)[0]+np.indices(shape)[1])%5-2).astype('f4')/16.
        elif name.endswith('norm.weight'): v=np.ones_like(idx,dtype='f4')
        elif name.endswith('.fn'): v=((idx+h)%9-4)/128.
        elif name.endswith('.base'): v=((idx*3+h)%13-6)/8.
        elif name.endswith('.scale'): v=np.array([1.,.5,.75])
        elif name.endswith('conv1d.weight'): v=((idx+h)%7+1)/8.
        elif name.endswith('A_log'): v=(idx%3-1)/8.
        elif name.endswith('dt_bias'): v=(idx%7-3)/16.
        elif name.endswith('k_norm.bias'):v=(idx%3-1)/16.
        else:v=((idx+h)%7-3)/32.
        v=v.reshape(shape)
        return bf(v) if dtype=='BF16' else v.astype('f4')

    def projection(self,prefix,x,outputs,group=None,bits=8):
        return bf(unpacked_values(outputs,len(x),prefix,0 if group is None else group[1])@x.astype('f8'))

    def embedding(self,prefix,token,width,vocab):
        # i%7 always >=0 -> finite nonzero embedding, independent of host libm.
        return ((np.arange(width)+token)%7+1).astype('f4')/8.


def generate():
    summary={}
    def emit(k,m,a):
        if k=='route': summary.setdefault('routes',[]).append([m['layer'],m['selected'],a['weights'].tolist()])
        if k=='kda': assert a['state'].any() and a['suffix'][-1].any()
        if k=='mla': assert a['indexer_cache'][-1]==1 and a['latent_k'].any()
        if k=='layer':summary.setdefault('layers',[]).append([m['layer'],a['attention'].tolist(),a['ffn'].tolist(),a['streams'].reshape(-1).tolist()])
    logits,winner,second,margin=g.synthetic_forward(Weights(),10,emit)
    assert golden_margin(logits)['eligible']
    summary.update(logits=logits.tolist(),token=winner,runner=second)
    return json.dumps(summary,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n'

if __name__=='__main__':
    print(generate(),end='')
