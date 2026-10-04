"""MIT. Source-metadata and tiny text-boundary probes, not a runtime loader."""
import math
from scripts.research.glm53_flash import candidate as primitive

SPARSE = (3,7,11,15,19,23,27,31,35,39,43)


def dispatch(config):
    fixed = {'model_type':'glm5_next_text','num_hidden_layers':45,'first_k_dense_replace':3,
             'n_routed_experts':288,'n_shared_experts':1,'num_experts_per_tok':8,
             'n_group':1,'topk_group':1,'topk_method':'noaux_tc','scoring_func':'sigmoid',
             'routed_scaling_factor':2.5,'norm_topk_prob':True,'hc_mult':4,'mhc':True,
             'mla_use_nope':True,'qk_rope_head_dim':0,'tie_word_embeddings':False,
             'hidden_size':4096,'intermediate_size':12288,'moe_intermediate_size':2048,
             'num_attention_heads':64,'num_key_value_heads':64,'q_lora_rank':1536,
             'kv_lora_rank':512,'qk_nope_head_dim':256,'qk_head_dim':256,'v_head_dim':256,
             'swiglu_limit':10.0,'hc_sinkhorn_iters':20,'hc_eps':1e-6,'rms_norm_eps':1e-5,
             'index_kpool':4,'index_topk':2048,'index_kpool_always_select_tail':True,
             'index_kpool_compress':True,'index_n_heads':32,'index_head_dim':128,
             'indexer_rope_interleave':True,'moe_router_dtype':'float32',
             'num_nextn_predict_layers':1,'vocab_size':154880,'pad_token_id':154820,
             'attention_bias':False,'hidden_act':'silu','max_position_embeddings':1048576}
    if not isinstance(config,dict):
        raise ValueError('CONFIG_OBJECT')
    for key,wanted in fixed.items():
        if type(config.get(key)) is not type(wanted) or config[key]!=wanted:
            raise ValueError('CONFIG:'+key)
    linear = [i for i in range(45) if i not in SPARSE]
    lc=config.get('linear_attn_config')
    if not isinstance(lc,dict) or lc.get('kda_layers')!=linear or lc.get('full_attn_layers')!=list(SPARSE):
        raise ValueError('ATTENTION_LISTS')
    nested={'gate_lower_bound':-5.0,'short_conv_kernel_size':4,'num_heads':64,'head_dim':128}
    for key,wanted in nested.items():
        if type(lc.get(key)) is not type(wanted) or lc[key]!=wanted:
            raise ValueError('LINEAR_CONFIG:'+key)
    for key in ('kda_layers','full_attn_layers'):
        if type(lc[key]) is not list or any(type(i) is not int for i in lc[key]):
            raise ValueError('LAYER_INDEX_TYPE')
    if config.get('eos_token_id')!=[154820,154827,154829] or any(type(i) is not int for i in config['eos_token_id']):
        raise ValueError('EOS_METADATA')
    expected=['deepseek_sparse_attention' if i in SPARSE else 'linear_attention' for i in range(45)]
    if config.get('layer_types')!=expected or config.get('mlp_layer_types')!=['dense']*3+['sparse']*42:
        raise ValueError('LAYER_DISPATCH')
    return tuple((i,'sparse' if name=='deepseek_sparse_attention' else 'kda','dense' if i<3 else 'moe') for i,name in enumerate(expected))


def route(scores,bias,k):
    # Retained source normalizes only when top_k > 1.
    return primitive.route_scores(scores,bias,k,2.5,normalize=k>1)


def ffn(x,weights):
    return primitive.clamped_mlp(x,weights['gate'],weights['up'],weights['down']).output


def moe(x,scores,bias,experts,shared,k):
    selected=route(scores,bias,k)
    branches=[ffn(x,experts[i]) for i in selected.ids]
    trunk=ffn(x,shared)
    return tuple(math.fsum(weight*branch[d] for weight,branch in zip(selected.weights,branches))+trunk[d] for d in range(len(x)))


def boundary(case,streams=None):
    embedding=primitive.matrix(case['embedding'],rows=5,cols=3)
    head=primitive.matrix(case['head'],rows=5,cols=3)
    weight=primitive.vector(case['norm'],3)
    ids=case['ids']
    if not isinstance(ids,tuple) or not 1<=len(ids)<=8 or any(type(i) is not int or not 0<=i<5 for i in ids):
        raise ValueError('TOKEN_IDS')
    embedded=tuple(embedding[i] for i in ids)
    residual=tuple((x,)*4 for x in embedded) if streams is None else streams
    if not isinstance(residual,tuple) or len(residual)!=len(ids):
        raise ValueError('STREAM_SEQUENCE')
    residual=tuple(primitive.matrix(x,4,3) for x in residual)
    logits=[]
    for row in residual:
        mean=tuple(math.fsum(column)/4 for column in zip(*row))
        inv=1/math.sqrt(math.fsum(x*x for x in mean)/3+1e-5)
        norm=tuple(x*inv*w for x,w in zip(mean,weight))
        logits.append(tuple(primitive.dot(norm,w) for w in head))
    return embedded,residual,tuple(logits)
