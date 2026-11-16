"""Independent, CPU-only GLM-5.3-Flash cold reference. No model CLI.

All values are real finite; BF16 edges use an F32 carrier. Unquantized reference
accumulations use independent CPU binary64 sums/products; router scores and
explicit FP32 program boundaries are F32. Never import candidate/MLX or accept
routes or golden intermediates from another program. Source anchors:
PipeNetwork/glm53-flash-mlx a61a7c7d..., language.py:24-104,252-307,382-409,
560-636,665-690,707-734. mlx-vlm 8d79dbcf..., gated_delta.py:133-175 and
hyper_connection.py:183-265. This is one position and one stream only.
"""
from typing import NamedTuple

import numpy as np

from studio017_ref_store import bf, finite, require


class Geometry(NamedTuple):
    hidden: int
    vocab: int
    layers: int
    linear_heads: int
    linear_dim: int
    kh: int
    kv_rank: int
    vd: int
    qr: int
    index_heads: int
    index_dim: int
    dense: int
    sparse: int
    experts: int
    top_k: int


REAL=Geometry(4096,154880,45,64,128,64,512,256,1536,32,128,12288,2048,288,8)
TINY=Geometry(8,32,5,2,4,2,4,4,4,2,4,12,4,10,8)


def d(a):
    return np.asarray(a,dtype=np.float64)


def f(a):
    return finite(np.asarray(a,dtype=np.float32))


def sigmoid(a):
    x=d(a)
    z=np.exp(-np.abs(x))
    return np.where(x>=0,1/(1+z),z/(1+z))


def rms(x,weight,eps):
    x=d(x)
    return x/np.sqrt(np.mean(x*x,axis=-1,keepdims=True)+eps)*d(weight)


def silu_bf(x):
    # Source SiLU = x * sigmoid(x): the sigmoid edge itself has BF16 dtype,
    # even when the backend fuses the typed expression into one kernel.
    return bf(d(x)*d(bf(sigmoid(x))))


def gate_activation(gate,up):
    g=np.minimum(gate,10)
    return bf(d(silu_bf(g))*d(np.clip(up,-10,10)))


def sinkhorn(logits,eps,iters):
    m=d(logits)
    e=np.exp(m-m.max(axis=-1,keepdims=True))
    v=e/(e.sum(axis=-1,keepdims=True)+eps)+eps  # fused Metal mathematical contract
    v/=v.sum(axis=-2,keepdims=True)+eps
    for _ in range(iters-1):
        v/=v.sum(axis=-1,keepdims=True)+eps
        v/=v.sum(axis=-2,keepdims=True)+eps
    return f(v)


def collapse(store,s,prefix,h,eps=1e-5):
    n,w=s.shape
    fn=store.dense(prefix+'.fn',((2+n)*n,n*w))
    base=store.dense(prefix+'.base',((2+n)*n,),'F32')
    scale=store.dense(prefix+'.scale',(3,),'F32')
    z=f(rms(s.reshape(-1),1,eps))
    mixes=f(d(fn)@d(z))
    pre=f(sigmoid(f(mixes[:n]*scale[0]+base[:n]))+h)
    post=f(2*sigmoid(f(mixes[n:2*n]*scale[1]+base[n:2*n])))
    comb=sinkhorn(f(mixes[2*n:]*scale[2]+base[2*n:]).reshape(n,n),h,20)
    return bf(d(pre)@d(s)),post,comb,np.concatenate([pre,post,comb.reshape(-1)])


def expand(s,branch,post,comb):
    return bf(d(post)[:,None]*d(branch)+d(comb).T@d(s))


def choose(logits,bias,k=8,factor=2.5):
    # Canonical tie rule: lower expert ID; selection and weighted reductions
    # use independent values. The validator additionally rejects any ambiguous
    # production cutoff under the preregistered uncertainty.
    p=f(sigmoid(f(logits)))
    corrected=f(p+f(bias))
    require(corrected.ndim==1 and 0<k<len(corrected),'top k')
    ranking=np.lexsort((np.arange(len(p)), -corrected))
    selected=ranking[:k]
    weights=f(f(p[selected]/f(d(p[selected]).sum()))*np.float32(factor))
    return selected,weights,corrected,float(corrected[selected[-1]])-float(corrected[ranking[k]])


def attach(emit,op,arrays,**meta):
    # Sink must synchronously consume or serialize arrays before returning.
    # No future state passed back into the reference.
    for x in arrays.values():
        finite(x)
    emit(op, meta, arrays)


def ffn(store,x,prefix,width,expert=None,pop=288):
    plane=None if expert is None else (pop,int(expert))
    bits=8 if plane is None else 4
    g=store.projection(prefix+'.gate_proj',x,width,plane,bits)
    u=store.projection(prefix+'.up_proj',x,width,plane,bits)
    return store.projection(prefix+'.down_proj',gate_activation(g,u),len(x),plane,bits)


def cold_delta(q,k,v,forget,beta):
    # Reference state is [heads, value_dim, key_dim], not [key_dim,value_dim].
    # Materialize zero state and physical output; this also witnesses gates.
    heads,dk=k.shape
    require(q.shape==k.shape==forget.shape and v.shape[0]==heads and beta.shape==(heads,),'KDA axes')
    st=np.zeros((heads,v.shape[1],dk),dtype='<f4')
    np.multiply(st,forget[:,None,:],out=st)
    old_inner=np.einsum('hvk,hk->hv',st,k,dtype='f8')
    delta=f((d(v)-old_inner)*d(beta)[:,None])
    st+=f(d(delta)[:,:,None]*d(k)[:,None,:])
    r=np.einsum('hvk,hk->hv',st,q,dtype='f8')
    return bf(r),finite(st)


def cold_cache(rows,width,keep):
    """Append actual rows to a cold cache; offset counts appended rows before retention."""
    a=np.asarray(rows,dtype='<f4')
    require(a.ndim==2 and a.shape==(1,width) and keep>0,'cold cache append')
    finite(a)
    history=np.zeros((keep-1,width),dtype='<f4')
    image=np.concatenate((history,a),axis=0)
    return image[-keep:],image.shape[0]-history.shape[0]


def normalized_index_key(k,w,b,eps=1e-6):
    u=d(k)-np.mean(d(k))
    return bf(u/np.sqrt(np.mean(u*u)+eps)*d(w)+d(b))


def linear(store,x,p,emit,layer,geo):
    H,K,D=geo.linear_heads,geo.linear_dim,geo.hidden
    def proj(s,v,n): return store.projection(p+'.'+s,v,n)
    raw=np.concatenate([proj(j+'_proj',x,H*K) for j in ('q','k','v')])
    taps=store.dense(p+'.conv1d.weight',(3*H*K,4,1))[:,:,0]
    # Suffix has 3 chronological rows; current element uses the last tap.
    suffix,pos=cold_cache(raw[None,:],3*H*K,3)
    conv=bf(d(raw)*d(taps[:,-1]))
    q,k,v=np.split(silu_bf(conv).reshape(3*H,K),3)
    q=bf(d(q)/np.sqrt(np.sum(d(q)**2,axis=-1,keepdims=True)+1e-6)/np.sqrt(K))
    k=bf(d(k)/np.sqrt(np.sum(d(k)**2,axis=-1,keepdims=True)+1e-6))
    a=proj('forget_gate.f_b_proj',proj('forget_gate.f_a_proj',x,K),H*K).reshape(H,K)
    dt=store.dense(p+'.forget_gate.dt_bias',(H*K,),'F32').reshape(H,K)
    al=store.dense(p+'.forget_gate.A_log',(H,),'F32')
    decay=f(np.exp(-5*d(sigmoid(f(np.exp(d(al)))[:,None]*f(a+dt)))))
    beta=bf(sigmoid(proj('b_proj',x,H)))
    out,state=cold_delta(q,k,v,decay,beta)
    gate=proj('g_b_proj',proj('g_a_proj',x,K),H*K).reshape(H,K)
    g=bf(rms(out,store.dense(p+'.o_norm.weight',(K,)),1e-5)*sigmoid(gate)).reshape(-1)
    attach(emit,'kda',dict(state=state,suffix=suffix,decay=decay,qkv_beta=np.concatenate([q.ravel(),k.ravel(),v.ravel(),beta])),layer=layer,position=pos)
    return proj('o_proj',g,D)


def sparse(store,x,p,emit,layer,geo):
    H,K,V,D=geo.kh,geo.kv_rank,geo.vd,geo.hidden
    def proj(s,v,n): return store.projection(p+'.'+s,v,n)
    qr=bf(rms(proj('q_a_proj',x,geo.qr),store.dense(p+'.q_a_layernorm.weight',(geo.qr,)),1e-5))
    q=proj('q_b_proj',qr,H*V).reshape(H,V)
    latent=bf(rms(proj('kv_a_proj_with_mqa',x,K),store.dense(p+'.kv_a_layernorm.weight',(K,)),1e-5))
    # The publisher short-context bypass occurs after the indexer state write.
    # Its q projection is dead for one token; evaluate it to guard its shape.
    iq=proj('indexer.wq_b',qr,geo.index_heads*geo.index_dim).reshape(geo.index_heads,geo.index_dim)
    k=proj('indexer.wk',x,geo.index_dim)
    kn=normalized_index_key(k,store.dense(p+'.indexer.k_norm.weight',(geo.index_dim,)),
                            store.dense(p+'.indexer.k_norm.bias',(geo.index_dim,)))
    cg=bf(d(store.dense(p+'.indexer.index_kpool_compress_gate',(geo.index_dim,D)))@d(x))
    latent_cache,lp=cold_cache(latent[None,:],K,1)
    index_cache,ip=cold_cache(np.concatenate([kn,cg,np.ones(1,dtype=np.float32)])[None,:],2*geo.index_dim+1,1)
    require(lp==ip,'latent/indexer positions differ')
    latent,packed=latent_cache[-1],index_cache[-1]
    # The publisher one-position branch embeds q into latent space; with
    # exactly one finite accessible key softmax(s)[0] is exactly 1. Evaluate
    # s to detect nonfinite inputs, and keep per-head scores as witnesses.
    heads=[];scores=[]
    for i in range(H):
        eq=store.projection(p+'.embed_q',q[i],K,(H,i),8)
        scores.append(float(d(eq)@d(latent))/np.sqrt(V))
        heads.append(store.projection(p+'.unembed_out',latent,V,(H,i),8))
    attach(emit,'mla',dict(latent_k=latent,latent_v=latent,indexer_cache=packed,
                          index_query=iq,scores=f(scores)),layer=layer,position=ip,
           selected='short-context dense bypass',index_topk=2048)
    return proj('o_proj',np.concatenate(heads),D)


def cold_forward(store,token_id,emit):
    """emit(event: str, finite metadata: dict, arrays: dict) -> None, serial.
    Required launcher freezes token_id, full checkpoint/recipe/fd metadata and
    method/criteria, admits memory/time and prohibits duplicate invocation.
    No file output or executable real-reference entry point in this module.
    """
    require(token_id==154820,'only the frozen <|endoftext|> prefix ID')
    return _forward(store,token_id,emit,REAL)


def synthetic_forward(store,token_id,emit):
    return _forward(store,token_id,emit,TINY)


def _forward(store,token_id,emit,geo):
    vocab,hidden,hc=geo.vocab,geo.hidden,4
    require(type(token_id) is int and 0<=token_id<vocab,'frozen token')
    embed=store.embedding('language_model.model.embed_tokens',token_id,hidden,vocab)
    attach(emit,'embedding',dict(embedding=embed),token=token_id,position=0)
    s=np.repeat(embed[None,:],hc,axis=0)
    for i in range(geo.layers):
        p='language_model.model.layers.'+str(i)
        x,post,comb,coeff=collapse(store,s,p+'.attn_hc',1e-6)
        attach(emit,'mhc',dict(coefficients=coeff),layer=i,branch='attn')
        x=bf(rms(x,store.dense(p+'.input_layernorm.weight',(hidden,)),1e-5))
        att=(sparse if i%4==3 else linear)(store,x,p+'.self_attn',emit,i,geo)
        s=expand(s,att,post,comb)
        x,post,comb,coeff=collapse(store,s,p+'.ffn_hc',1e-6)
        attach(emit,'mhc',dict(coefficients=coeff),layer=i,branch='ffn')
        x=bf(rms(x,store.dense(p+'.post_attention_layernorm.weight',(hidden,)),1e-5))
        if i<3:
            branch=ffn(store,x,p+'.mlp',geo.dense)
        else:
            logits=f(d(store.dense(p+'.mlp.gate.weight',(geo.experts,hidden)))@d(x))
            ids,weights,corrected,gap=choose(logits,store.dense(p+'.mlp.gate.e_score_correction_bias',(geo.experts,),'F32'),geo.top_k)
            # Accumulate in wide precision, then round routed result to BF16
            # before adding independently computed shared expert.
            weighted=np.zeros(hidden,dtype=np.float64)
            for j,wt in zip(ids,weights):
                y=ffn(store,x,p+'.mlp.switch_mlp',geo.sparse,j,geo.experts)
                weighted+=d(f(f(y)*wt))
            routed=bf(weighted)
            shared=ffn(store,x,p+'.mlp.shared_experts',geo.sparse)
            branch=bf(d(shared)+d(routed))
            attach(emit,'route',dict(router_logits=logits,corrected=corrected,
                                    weights=weights,routed=routed,shared=shared),layer=i,
                   selected=[int(t) for t in ids],cutoff_gap=gap)
        s=expand(s,branch,post,comb)
        attach(emit,'layer',dict(attention=att,ffn=branch,streams=s),layer=i,position=1)
    pooled=bf(d(s).mean(axis=0))
    z=bf(rms(pooled,store.dense('language_model.model.norm.weight',(hidden,)),1e-5))
    logits=store.projection('language_model.lm_head',z,vocab)
    require(logits.shape==(vocab,) and np.isfinite(logits).all(),'full vocabulary')
    order=np.lexsort((np.arange(vocab),-logits));win,second=map(int,order[:2])
    margin=float(logits[win])-float(logits[second])
    attach(emit,'golden',dict(pooled=pooled,normalized=z,logits=logits),token=win,
           runner_up=second,margin=margin,token_count=1)
    return logits,win,second,margin
