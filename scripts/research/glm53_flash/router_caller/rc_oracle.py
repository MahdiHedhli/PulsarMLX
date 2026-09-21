"""Independent scalar reference: stdlib only, no candidate or MLX imports."""
import math,struct
U=2.0**-24
def f32(x):return struct.unpack('>f',struct.pack('>f',float(x)))[0]
def bits32(x):return struct.unpack('>I',struct.pack('>f',float(x)))[0]
def bf16_word(x):
    b=bits32(x);return ((b+0x7fff+((b>>16)&1))>>16)&0xffff
def bf16(x):return struct.unpack('>f',struct.pack('>I',bf16_word(x)<<16))[0]
def represented(value,dtype):
    if isinstance(value,list):return [represented(x,dtype) for x in value]
    return bf16(value) if dtype=='bfloat16' else f32(value)
def words(value,dtype):
    if isinstance(value,list):return [words(x,dtype) for x in value]
    return format(bf16_word(value),'04x') if dtype=='bfloat16' else format(bits32(value),'08x')
def shape(value):
    if not isinstance(value,list):return ()
    children=[shape(x) for x in value]
    if children and any(x!=children[0] for x in children):raise ValueError('ragged scalar reference input')
    return (len(value),)+(children[0] if children else ())
def vectors(x):
    if not isinstance(x[0],list):return [x]
    return [v for child in x for v in vectors(child)]
def sigmoid(x):return 1/(1+math.exp(-x)) if x>=0 else math.exp(x)/(1+math.exp(x))
def projection(x,weight):return [math.fsum(a*b for a,b in zip(x,row)) for row in weight]
def select(logits,bias,config):
    scores=[sigmoid(x) for x in logits];corrected=[x+b for x,b in zip(scores,bias)]
    e=len(scores);g=config['n_group'];group_margin=None;retained=list(range(g))
    if g>1:
        n=e//g;gs=[sum(sorted(corrected[i*n:(i+1)*n],reverse=True)[:2]) for i in range(g)]
        order=sorted(range(g),key=lambda i:gs[i],reverse=True);keep=config['topk_group']
        group_margin=gs[order[keep-1]]-gs[order[keep]];retained=order[:keep]
        corrected=[s if i//n in retained else 0.0 for i,s in enumerate(corrected)]
    order=sorted(range(e),key=lambda i:corrected[i],reverse=True);k=config['num_experts_per_tok'];ids=order[:k]
    margin=corrected[order[k-1]]-corrected[order[k]] if k<e else None
    total=math.fsum(scores[i] for i in ids);scale=config['routed_scaling_factor']
    out={str(i):scores[i]*scale/(total if k>1 and config['norm_topk_prob'] else 1.0) for i in ids}
    return {'selected_ids':ids,'scores_by_id':out,'selected_sigmoid_sum':total,'selection_margin':margin,'group_margin':group_margin,'retained_groups':retained,'logits':logits}
def reference(case,round_projection_to_bf16=False):
    c=case['config'];out=[]
    for x in vectors(case['represented_input']):
        logits=projection(x,case['represented_weight'])
        if round_projection_to_bf16:logits=[bf16(v) for v in logits]
        out.append(select(logits,case['bias'],c))
    return {'input_shape':list(shape(case['represented_input'])),'output_shape':list(shape(case['represented_input'])[:-1])+[c['num_experts_per_tok']],'rows':out}
def error_bounds(case):
    c=case['config'];h=c['hidden_size'];k=c['num_experts_per_tok'];scale=c['routed_scaling_factor']
    gamma_h=h*U/(1-h*U);gamma_k=k*U/(1-k*U)
    projection_error=max(gamma_h*sum(abs(a*b) for a,b in zip(x,w)) for x in vectors(case['represented_input']) for w in case['represented_weight'])
    # Preserve the predecessor engineering allowance of 16u for sigmoid.
    sigmoid_error=16*U+.25*projection_error+2e-12
    ranking_error=sigmoid_error+U*(1+max(abs(x) for x in case['bias'])+sigmoid_error)
    bound=[]
    ref=reference(case)
    for row in ref['rows']:
        total=row['selected_sigmoid_sum'];ds=k*sigmoid_error+gamma_k*(total+k*sigmoid_error)
        if k>1 and c['norm_topk_prob']:
            assert total>ds
            ratio_error=sigmoid_error/(total-ds)+ds/(total*(total-ds))+U*(1+sigmoid_error)/(total-ds)
        else:ratio_error=sigmoid_error
        score_error=scale*ratio_error+U*scale*(1+ratio_error)+2e-12
        bound.append({'projection_abs_bound':projection_error,'sigmoid_abs_bound':sigmoid_error,'ranking_abs_bound':ranking_error,'score_abs_bound':score_error,'selection_margin':row['selection_margin'],'group_margin':row['group_margin']})
    return bound
