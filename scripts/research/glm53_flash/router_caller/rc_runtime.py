"""Tiny synthetic router execution; whole upstream modules stay unimported."""
import copy,hashlib,json,math
from pathlib import Path
import rc_guard as guard
import rc_source as source
import rc_checks as checks

def value_sha(value):return hashlib.sha256(json.dumps(value,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def validate_case(case):
    c=source.ResearchConfig(case['config']);x=case['input'];w=case['weight'];b=case['bias']
    xs=checks.shape(x)
    if len(xs) not in (1,2,3) or xs[-1]!=c.hidden_size or (len(xs)==3 and (xs[0]>2 or xs[1]>5)) or (len(xs)==2 and xs[0]>5):raise source.DomainError('INPUT_SHAPE_DOMAIN')
    if checks.shape(w)!=(c.n_routed_experts,c.hidden_size) or checks.shape(b)!=(c.n_routed_experts,):raise source.DomainError('WEIGHT_BIAS_SHAPE_DOMAIN')
    values=checks.flat(x)+checks.flat(w)+b
    if len(values)*4>1024**2 or not all(type(v) in (float,int) and math.isfinite(v) and abs(v)<=4 for v in values):raise source.DomainError('FINITE_FP32_ARRAY_DOMAIN')
    if case['dtype'] not in ('float32','bfloat16'):raise source.DomainError('DTYPE_DOMAIN')
    return c
def is_bf16_unavailable(exc):
    text=str(exc).lower()
    return type(exc) in (ValueError,RuntimeError,TypeError) and ('bfloat16' in text or 'bfloat' in text) and ('unsupported' in text or 'not support' in text or 'unavailable' in text)

class Runtime:
    def __init__(self,phase):
        self.phase=Path(phase);guard.verify_child_interpreter(phase)
        self.manifest=guard.verify_environment(phase)
        import mlx.core as mx
        import mlx.nn as nn
        self.mx=mx;self.nn=nn;self.builder=source.Builder(phase,mx,nn,self.manifest)
        self.evaluations=0;self.caller_evaluations=0;self.records=[];self.resets=[];self.instances=[]
    def evaluate(self,*arrays,caller=False):
        self.mx.eval(*arrays);self.mx.synchronize();self.evaluations+=1
        if caller:self.caller_evaluations+=1
    def make(self,case,variant=None):
        config=validate_case(case);bundle=self.builder.new(variant)
        gate=bundle['caller'](config)
        if type(gate) is not bundle['caller'] or gate.__class__.__init__ is not bundle['base'].__init__:raise source.SourceGuardError('REAL_BASE_CONSTRUCTOR_BINDING_MISMATCH')
        self.evaluate(gate.weight,gate.e_score_correction_bias)
        if tuple(gate.weight.shape)!=(config.n_routed_experts,config.hidden_size) or tuple(gate.e_score_correction_bias.shape)!=(config.n_routed_experts,):raise checks.ComparisonError('BASE_INITIAL_SHAPE_MISMATCH')
        if gate.weight.dtype!=self.mx.float32 or gate.e_score_correction_bias.dtype!=self.mx.float32:raise checks.ComparisonError('BASE_INITIAL_DTYPE_MISMATCH')
        if any(checks.flat(gate.weight.tolist())) or any(gate.e_score_correction_bias.tolist()):raise checks.ComparisonError('BASE_INITIAL_ZERO_MISMATCH')
        attributes={'top_k':config.num_experts_per_tok,'norm_topk_prob':config.norm_topk_prob,'n_routed_experts':config.n_routed_experts,'routed_scaling_factor':config.routed_scaling_factor,'n_group':config.n_group,'topk_group':config.topk_group}
        if gate.config is not config or any(getattr(gate,k)!=v or type(getattr(gate,k)) is not type(v) for k,v in attributes.items()):raise checks.ComparisonError('BASE_CONFIG_PROPAGATION_MISMATCH')
        dtype=self.mx.float32 if case['dtype']=='float32' else self.mx.bfloat16
        x=self.mx.array(case['input'],dtype=self.mx.float32).astype(dtype)
        gate.weight=self.mx.array(case['weight'],dtype=self.mx.float32).astype(dtype)
        gate.e_score_correction_bias=self.mx.array(case['bias'],dtype=self.mx.float32)
        self.evaluate(x,gate.weight,gate.e_score_correction_bias)
        if x.tolist()!=case['represented_input'] or gate.weight.tolist()!=case['represented_weight'] or gate.e_score_correction_bias.tolist()!=case['bias']:raise checks.ComparisonError('REPRESENTED_VALUE_MISMATCH')
        result={'bundle':bundle,'gate':gate,'x':x,'case':case,'initial_attributes':attributes}
        self.instances.append(result)
        record=bundle['record']
        self.resets.append({k:record[k] for k in ('sequence','variant','caller_executed_body_sha256','selector_object_id','base_class_object_id','caller_class_object_id','fresh_function_objects','compile_cache_claim')})
        return result
    def invoke(self,instance,label,mutate=None,wrong_id_association=False):
        gate=instance['gate'];case=instance['case'];x=instance['x'];bundle=instance['bundle'];c=case['config']
        if mutate is not None:mutate(gate)
        # This is a separately labeled projection/conversion diagnostic on the
        # same arrays. It is not a capture of the caller's local variables.
        converted_x=x.astype(self.mx.float32);converted_w=gate.weight.astype(self.mx.float32)
        projection=converted_x@converted_w.T
        ids,scores=gate(x)
        ref_ids,ref_scores=bundle['selector'](projection,self.mx.array(case['bias'],dtype=self.mx.float32),c['num_experts_per_tok'],c['n_group'],c['topk_group'],c['routed_scaling_factor'],c['norm_topk_prob'])
        self.evaluate(ids,scores,ref_ids,ref_scores,projection,converted_x,converted_w,caller=True)
        actual_ids=ids.tolist();actual_scores=scores.tolist()
        if converted_x.dtype!=self.mx.float32 or converted_w.dtype!=self.mx.float32 or projection.dtype!=self.mx.float32:raise checks.ComparisonError('CONVERSION_PROJECTION_DTYPE_MISMATCH')
        projection_values=projection.tolist()
        expected_projection=[row['logits'] for row in case['reference']['rows']]
        observed_projection=checks.rows(projection_values)
        diag={'status':'OBSERVED_NOT_YET_COMPARED'}
        record={'case':case['name'],'label':label,'dtype_domain':case['dtype'],'bundle_sequence':bundle['record']['sequence'],'variant':bundle['record']['variant'],'input_shape':list(x.shape),'weight_shape':list(gate.weight.shape),'raw_ids':actual_ids,'raw_scores':actual_scores,'output_shapes':[list(ids.shape),list(scores.shape)],'output_dtype':str(scores.dtype),'order':'UNSPECIFIED','represented_input_sha256':value_sha(x.tolist()),'represented_weight_sha256':value_sha(gate.weight.tolist()),'base_constructor':{'actual_inherited_constructor':True,'initial_zero_shapes':[[c['n_routed_experts'],c['hidden_size']],[c['n_routed_experts']]],'initial_dtype':'float32','initial_attributes':instance['initial_attributes']},'call_attributes':{k:getattr(gate,k) for k in instance['initial_attributes']},'conversion_projection_diagnostic':{'scope':'separate research diagnostic on the same input/weight arrays; not captured caller locals','input_dtype':str(x.dtype),'weight_dtype':str(gate.weight.dtype),'converted_input_dtype':str(converted_x.dtype),'converted_weight_dtype':str(converted_w.dtype),'projection_dtype':str(projection.dtype),'projection_values':projection_values,'metrics':diag},'predecessor_selector_comparison':'same source selector with separately computed FP32 projection and frozen original config; independently checked scalar reference','status':'OBSERVED_NOT_YET_COMPARED'}
        self.records.append(record)
        try:
            record['comparisons']=checks.compare_router(actual_ids,actual_scores,case['reference'],wrong_id_association=wrong_id_association)
            record['conversion_projection_diagnostic']['metrics']=checks.close(observed_projection,expected_projection,2e-6,2e-6,'SEPARATE_PROJECTION_DIAGNOSTIC_MISMATCH')
            checks.compare_router(ref_ids.tolist(),ref_scores.tolist(),case['reference'])
        except checks.ComparisonError:
            record['status']='EXPECTED_COMPARISON_NOT_MET';raise
        record['status']='MATCHED_FROZEN_REFERENCE'
        return record
    def run_case(self,case,label=None,variant=None,mutate=None,wrong_id_association=False):
        instance=self.make(case,variant)
        return self.invoke(instance,label or case['name'],mutate,wrong_id_association)
