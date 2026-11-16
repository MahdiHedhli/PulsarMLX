"""Independent CPU admission of the exact publisher text configuration (data only)."""
import hashlib
import json
import os

CONFIG_SHA256='3ed164a8f60c96dc81d5742b952b7823335fa7656fe0bbcf69c7ea05a4179d1d'
CONFIG_SIZE=124463


def _must(ok,field):
    if not ok: raise ValueError('reference text configuration: '+field)


def contract():
    # Independent representation of the exact studied checkpoint. Fields not
    # consumed by the one-token text path are still pinned. Never fall back
    # to a default when an explicit publisher value is absent or malformed.
    mla=[3,7,11,15,19,23,27,31,35,39,43]
    kda=[i for i in range(45) if i not in mla]
    return {
        'model_type':'glm5_next_text','dtype':'bfloat16','vocab_size':154880,
        'hidden_size':4096,'intermediate_size':12288,'moe_intermediate_size':2048,
        'num_hidden_layers':45,'layer_types':['deepseek_sparse_attention' if i in mla else 'linear_attention' for i in range(45)],
        'mlp_layer_types':['dense']*3+['sparse']*42,'indexer_types':['full']*45,
        'linear_attn_config':dict(num_heads=64,head_dim=128,short_conv_kernel_size=4,gate_lower_bound=-5.0,kda_layers=kda,full_attn_layers=mla),
        'rms_norm_eps':1e-5,'mhc':True,'hc_eps':1e-6,'hc_mult':4,'hc_sinkhorn_iters':20,
        'hidden_act':'silu','swiglu_limit':10.0,'first_k_dense_replace':3,
        'n_routed_experts':288,'num_experts_per_tok':8,'n_shared_experts':1,'moe_router_dtype':'float32',
        'n_group':1,'topk_group':1,'routed_scaling_factor':2.5,'norm_topk_prob':True,
        'scoring_func':'sigmoid','topk_method':'noaux_tc','output_router_logits':False,'router_aux_loss_coef':.001,
        'qk_head_dim':256,'qk_nope_head_dim':256,'qk_rope_head_dim':0,'head_dim':0,'mla_use_nope':True,
        'q_lora_rank':1536,'kv_lora_rank':512,'num_attention_heads':64,'num_key_value_heads':64,'v_head_dim':256,
        'attention_bias':False,'attention_dropout':0.,'index_head_dim':128,'index_kpool':4,
        'index_kpool_always_select_tail':True,'index_kpool_compress':True,'index_n_heads':32,
        'index_topk':2048,'index_share_for_mtp_iteration':True,'indexer_rope_interleave':True,
        'max_position_embeddings':1048576,'use_cache':True,'tie_word_embeddings':False,
        'initializer_range':.02,'pad_token_id':154820,'eos_token_id':[154820,154827,154829],
        'num_nextn_predict_layers':1,
    }


def validate_document(document):
    model=contract()
    def match(a,b,key):
        _must(type(a) is type(b),key+' type')
        if type(b) is dict:
            _must(set(a)==set(b),key+' field population')
            for k,val in b.items():match(a[k],val,key+'.'+k)
        elif type(b) is list:
            _must(len(a)==len(b),key+' population')
            for i,val in enumerate(b):match(a[i],val,key+'['+str(i)+']')
        else:_must(a==b,key)
    for k,v in {'model_type':'glm5_next','architectures':['Glm5NextForConditionalGeneration'],'tie_word_embeddings':False}.items():
        match(document.get(k),v,k)
    match(document.get('text_config'),model,'text_config')


def validate_witnessed(path,witness,opened,fdstamp):
    with opened(path,CONFIG_SIZE) as (fd,stat):
        _must(stat.st_size==CONFIG_SIZE and fdstamp(stat)==witness,'original file witness')
        raw=os.pread(fd,CONFIG_SIZE+1,0)
        _must(len(raw)==CONFIG_SIZE and hashlib.sha256(raw).hexdigest()==CONFIG_SHA256,'original bytes')
        def one(items):
            d={}
            for k,v in items:
                _must(k not in d,'duplicate '+k);d[k]=v
            return d
        def bad(x): raise ValueError('nonfinite text metadata: '+x)
        validate_document(json.loads(raw,object_pairs_hook=one,parse_constant=bad))
        _must(fdstamp(os.fstat(fd))==witness,'file changed')
    return CONFIG_SHA256
