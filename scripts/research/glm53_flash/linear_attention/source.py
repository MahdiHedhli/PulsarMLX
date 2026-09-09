"""Verified whole source nodes and metadata-only instrumentation.

The recurrent and module algorithms remain literal upstream definitions.
Only the finite Dk=Dv32 launch admission and counters belong to this harness.
"""
import ast
from functools import partial
import hashlib
import json
import symtable
import types
from typing import Any, Optional, Tuple

PREFIX = 'scripts/research/glm53_flash/linear_attention/'
REC = 'scripts/research/glm53_flash/recurrent_dispatch/'
sha = lambda raw: hashlib.sha256(raw).hexdigest()


def verify_module(raw, original, provenance):
    if sha(original) != '6de479b6eafc0731e5e965f01f28797a58eecb606e7d5d5657db13642c230196' or sha(raw) != provenance['capsule_sha256']:
        raise ValueError('MODULE_SOURCE_BINDING')
    wanted = ('Glm5NextRMSNormGated','Glm5NextForgetGate','_l2norm','Glm5NextLinearAttention')
    observed = ast.parse(raw).body
    origins = [n for n in ast.parse(original).body if getattr(n,'name',None) in wanted]
    if tuple(getattr(n,'name',None) for n in observed) != wanted or len(provenance['source_spans']) != 4:
        raise ValueError('MODULE_CLOSURE')
    for a,b,span in zip(origins,observed,provenance['source_spans']):
        selected = original[span['byte_start']:span['byte_end']]
        if (span['name'] != a.name or sha(selected) != span['sha256']
                or ast.dump(a,include_attributes=False) != ast.dump(b,include_attributes=False)
                or ast.dump(ast.parse(selected).body[0],include_attributes=False) != ast.dump(a,include_attributes=False)):
            raise ValueError('MODULE_WHOLE_NODE_OR_SPAN')
    globals_seen = set()
    def walk(table):
        globals_seen.update(s.get_name() for s in table.get_symbols() if s.is_referenced() and s.is_global())
        for child in table.get_children(): walk(child)
    walk(symtable.symtable(raw.decode(),'literal-module','exec'))
    if sorted(globals_seen) != provenance['global_name_census']:
        raise ValueError('MODULE_GLOBAL_CENSUS')
    module = observed[-1]
    call = next(n for n in module.body if isinstance(n,ast.FunctionDef) and n.name=='__call__')
    updates = [n for n in ast.walk(call) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='gated_delta_update']
    if len(updates)!=1 or {k.arg for k in updates[0].keywords} != {'state','lower_bound'}:
        raise ValueError('MODULE_MASK_CONTRACT')
    if any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr in ('eval','tolist','item') for node in observed for n in ast.walk(node)):
        raise ValueError('ORIGINAL_INNER_BARRIER')
    return observed


def kernel_buffers(arguments, input_names):
    """Bounds conditional on32-lane SIMD/x-major packing; not device proof."""
    if input_names != ['q','k','v','g','beta','state_in','T'] or len(arguments['inputs']) != 7:
        raise ValueError('MODULE_KERNEL_INPUTS')
    q,k,v,g,beta,state,T = arguments['inputs']
    if len(q.shape)!=4:
        raise ValueError('MODULE_KERNEL_RANK')
    B,S,H,D = q.shape
    if (B not in (1,2) or not 1<=S<=5 or H not in (1,2) or D!=32 or type(T) is not int or T!=S):
        raise ValueError('MODULE_KERNEL_DOMAIN')
    expected = [(B,S,H,32)]*4 + [(B,S,H),(B,H,32,32)]
    for value,dims in zip(arguments['inputs'][:6],expected):
        count=1
        for d in dims: count*=d
        if value.shape!=dims or value.dtype!=mx.float32 or value.size!=count or count>4096:
            raise ValueError('MODULE_KERNEL_BUFFER')
    if (arguments['grid']!=(32,32,B*H) or arguments['threadgroup']!=(32,4,1)
            or arguments['output_shapes']!=[(B,S,H,32),(B,H,32,32)]
            or arguments['output_dtypes']!=[mx.float32,mx.float32]
            or dict(arguments['template'])!={'InT':mx.float32,'StT':mx.float32,'Dk':32,'Dv':32,'Hk':H,'Hv':H}):
        raise ValueError('MODULE_KERNEL_GEOMETRY')
    return {'B':B,'S':S,'H':H,'Dk':32,'Dv':32,'max_state_float32_elements':B*H*1024,
            'packing_assumption':'32-lane SIMD groups and x-major packing on the admitted tested device; NOT_PROVED_BY_METADATA',
            'index_bounds':'n<B*H; b=n//H<B; hv=n%H<H; hk=hv. dk=threadgroup.x0..31; n_per_t=1; s=dk. dv=grid.y0..31. Eight exact groups of4 coverDv32; every state address (n*32+dv)*32+s is belowB*H*1024. Time strides remain withinS.',
            'contiguity':'Original metal_kernel default ensure_row_contiguous=True; input views canonicalized by admitted API. Metadata does not expose physical buffer strides.',
            'maximum_external_bytes_per_array':16384}


def load(context, fixture, mutation=None):
    root = context.roots['code']
    raw = context.read_verified(root/PREFIX/'capsule.py')
    pbytes = context.read_verified(root/PREFIX/'provenance.json')
    prov = json.loads(pbytes)
    original = context.read_verified(root/REC/'upstream-language.txt')
    if sha(raw)!=fixture['capsule_sha256'] or sha(pbytes)!=fixture['provenance_sha256']:
        raise ValueError('MODULE_FIXTURE_SOURCE')
    verify_module(raw,original,prov)
    recurrent_raw = context.read_verified(root/REC/'capsule.py')
    recurrent_origin = context.read_verified(root/REC/'upstream-gated-delta.txt')
    recurrent_provenance = json.loads(context.read_verified(root/REC/'provenance.json'))
    recurrent_verifier.verify(recurrent_raw,recurrent_origin,original,recurrent_provenance)
    changed = raw
    if mutation in prov['mutations']:
        spec=prov['mutations'][mutation]
        if changed.count(spec['before'].encode())!=1: raise ValueError('MODULE_MUTATION_SITE')
        changed=changed.replace(spec['before'].encode(),spec['after'].encode())
        if sha(changed)!=spec['sha256']: raise ValueError('MODULE_MUTATION_BINDING')
    elif mutation not in (None,'illicit_inner_barrier'):
        raise ValueError('MODULE_MUTATION_UNKNOWN')
    stats={key:0 for key in ('module_calls','module_constructors','forget_constructors','norm_constructors',
        'fused_calls','fused_builds','fused_reuses','l2_calls','norm_calls','compute_g','compute_g_safe',
        '_make_gated_delta_kernel','_gated_delta_step_ops','gated_delta_kernel','gated_delta_ops','gated_delta_update',
        'factory_API_calls','kernel_API_submissions','inner_barriers','outer_barriers','parameter_admission_barriers')}
    factories,submissions,handles,originals,fused_records = [],[],[],[],[]
    def factory(**kw):
        stats['factory_API_calls']+=1
        native=mx.fast.metal_kernel(**kw)
        row={'name':kw['name'],'source_sha256':sha(kw['source'].encode()),'input_names':kw['input_names'],
             'compile_options':kw.get('compile_options'),'effective_math':'NOT_OBSERVED'}
        factories.append(row)
        def submit(**args):
            proof=kernel_buffers(args,kw['input_names'])
            stats['kernel_API_submissions']+=1
            submissions.append({**row,'bounds':proof})
            return native(**args)
        handles.extend([native,submit])
        return submit
    class Core:
        fast=types.SimpleNamespace(metal_kernel=factory)
        def __getattr__(self,key): return getattr(mx,key)
    namespace={'__name__':'verified_full_linear_attention','mx':Core(),'nn':nn,'partial':partial,
               'Optional':Optional,'Tuple':Tuple,'Any':Any,'TextConfig':types.SimpleNamespace}
    def function_wrapper(name,fn):
        def wrapped(*args,**kw):
            stats[name]+=1
            result=fn(*args,**kw)
            if mutation=='illicit_inner_barrier' and name=='gated_delta_update':
                mx.eval(*result);stats['inner_barriers']+=1
            return result
        originals.append(fn)
        return wrapped
    # Eleven exact recurrent nodes; the old partial caller seam is unused.
    for node in ast.parse(recurrent_raw).body[:-1]:
        exec(compile(ast.Module(body=[node],type_ignores=[]),'literal-recurrent-node','exec'),namespace)
        if isinstance(node,ast.FunctionDef):
            namespace[node.name]=function_wrapper(node.name,namespace[node.name])
    exec(compile(changed,'literal-linear-attention-module','exec'),namespace)
    def method(cls,name,key):
        fn=getattr(cls,name);originals.append(fn)
        def wrapped(self,*args,**kw):
            stats[key]+=1
            before=self._fused_ready if name=='_fused_in_proj' else None
            old=getattr(self,'_fw',None) if name=='_fused_in_proj' else None
            result=fn(self,*args,**kw)
            if name=='_fused_in_proj':
                stats['fused_reuses' if before else 'fused_builds']+=1
                if before and self._fw is not old: raise ValueError('FUSED_WEIGHT_REBUILT')
                fused_records.append({'previously_ready':before,'split_points':list(self._split_pts),
                    'quantized':self._fq,'weight_shape':list(self._fw.shape),'weight_dtype':str(self._fw.dtype),
                    'same_fused_object':before and self._fw is old})
            return result
        setattr(cls,name,wrapped)
    cls=namespace['Glm5NextLinearAttention']
    method(cls,'__init__','module_constructors');method(cls,'__call__','module_calls');method(cls,'_fused_in_proj','fused_calls')
    method(namespace['Glm5NextForgetGate'],'__init__','forget_constructors')
    method(namespace['Glm5NextRMSNormGated'],'__init__','norm_constructors')
    method(namespace['Glm5NextRMSNormGated'],'__call__','norm_calls')
    namespace['_l2norm']=function_wrapper('l2_calls',namespace['_l2norm'])
    return types.SimpleNamespace(namespace=namespace,stats=stats,factories=factories,submissions=submissions,
        handles=handles,originals=originals,fused_records=fused_records,
        binding={'capsule_sha256':sha(raw),'executed_capsule_sha256':sha(changed),'recurrent_capsule_sha256':sha(recurrent_raw),
                 'mutation':mutation,'whole_original_nodes_and_spans':'PASS','source_decorators':'UNCHANGED',
                 'module_mask_forwarded_to_recurrence':False,'physical_GPU_counts':'NOT_OBSERVED'})
