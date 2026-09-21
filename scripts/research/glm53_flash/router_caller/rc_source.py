"""Exact source-composed router nodes with explicit research namespace seams.

PipeNetwork source is Apache-2.0; mlx-vlm is MIT. Full notices, source
buffers and exact revisions are retained in the phase source-node admission.
This module executes selected definitions only, never either full module.
"""
import ast,hashlib,math,symtable,types
from pathlib import Path
import rc_guard as guard

class SourceGuardError(ValueError):pass
class DomainError(ValueError):pass

NODES={
 'group_expert_select':{'file':'mlx-vlm/mlx_vlm/models/deepseek_v32/language.py','file_sha':'cd210c73ce3e569ab5270a47a92941cd5ec1450c6ff7b55b8be57c51263f4cb6','node_sha':'4efab08404da68c50faa1f2a4ebe3235436a1b2aa09bac6e77e20dc0fba35ad9','globals':{'mx'}},
 'MoEGate':{'file':'mlx-vlm/mlx_vlm/models/deepseek_v32/language.py','file_sha':'cd210c73ce3e569ab5270a47a92941cd5ec1450c6ff7b55b8be57c51263f4cb6','node_sha':'7ffeb78d43c856bdd389cbaa5bdf51d33c600873beeaab78dee23c562472771a','globals':{'nn','mx','ModelConfig','super','group_expert_select'}},
 'Glm5NextMoEGate':{'file':'pipenetwork/glm53_flash_mlx/glm5_next/language.py','file_sha':'6de479b6eafc0731e5e965f01f28797a58eecb606e7d5d5657db13642c230196','node_sha':'ff08475c6fc93a110abda7f6efc3c5f1f3b2da5e8a48404608f159569b51921f','globals':{'MoEGate','mx','_dsv32'}}}

# These are named test derivatives, never represented as unchanged upstream.
CALLER_MUTATIONS={
 'omit-input-cast':('x.astype(mx.float32)','x'),
 'omit-weight-cast':('self.weight.astype(mx.float32)','self.weight'),
 'omit-both-casts':('x.astype(mx.float32) @ self.weight.astype(mx.float32).T','x @ self.weight.T'),
 'omit-weight-transpose':('self.weight.astype(mx.float32).T','self.weight.astype(mx.float32)')}

def digest(raw):return hashlib.sha256(raw).hexdigest()
def inventory(text):
    table=symtable.symtable(text,'router-capsule','exec');rows=[];names=set()
    def walk(t):
        gs=sorted(s.get_name() for s in t.get_symbols() if s.is_global() and s.is_referenced())
        rows.append({'scope':t.get_name(),'kind':t.get_type(),'globals':gs,'free':sorted(s.get_name() for s in t.get_symbols() if s.is_free())});names.update(gs)
        for child in t.get_children():walk(child)
    walk(table);return names,rows
def audit_node(name,text,expected_globals=None):
    parsed=ast.parse(text)
    if len(parsed.body)!=1 or getattr(parsed.body[0],'name',None)!=name:raise SourceGuardError('NODE_SHAPE_MISMATCH')
    node=parsed.body[0];names,rows=inventory(text)
    allowed=NODES[name]['globals'] if expected_globals is None else expected_globals
    if names!=allowed:raise SourceGuardError('UNLISTED_GLOBAL: '+str(sorted(names)))
    if name=='group_expert_select':
        if not isinstance(node,ast.FunctionDef) or [ast.unparse(d) for d in node.decorator_list]!=['mx.compile']:raise SourceGuardError('DECORATOR_MISMATCH')
    else:
        base='nn.Module' if name=='MoEGate' else 'MoEGate'
        if not isinstance(node,ast.ClassDef) or node.decorator_list or [ast.unparse(x) for x in node.bases]!=[base]:raise SourceGuardError('CLASS_BASE_MISMATCH')
    return rows
def load_nodes(phase,raw_override=None):
    raw_override={} if raw_override is None else raw_override
    texts={};records=[];whole={}
    for name,row in NODES.items():
        f=guard.confined(phase,Path(phase)/'source'/row['file'])
        if row['file'] not in whole:
            raw=f.read_bytes()
            if len(raw)>1024**2 or digest(raw)!=row['file_sha']:raise SourceGuardError('WHOLE_SOURCE_DIGEST_MISMATCH')
            whole[row['file']]=raw
        raw=whole[row['file']];text=raw.decode();tree=ast.parse(text);lines=text.splitlines(keepends=True)
        selected=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name==name]
        if len(selected)!=1:raise SourceGuardError('NODE_NOT_UNIQUE')
        node=selected[0];first=min([node.lineno]+[d.lineno for d in node.decorator_list])
        part=''.join(lines[first-1:node.end_lineno]).encode()
        if name in raw_override:part=raw_override[name]
        if digest(part)!=row['node_sha']:raise SourceGuardError('SOURCE_NODE_DIGEST_MISMATCH')
        cap=guard.confined(phase,Path(phase)/'source/capsules'/(name+'.py'))
        if cap.read_bytes()!=part:raise SourceGuardError('RETAINED_CAPSULE_MISMATCH')
        scopes=audit_node(name,part.decode());texts[name]=part.decode()
        records.append({'name':name,'whole_source_sha256':row['file_sha'],'node_sha256':row['node_sha'],'first_line':first,'last_line':node.end_lineno,'scopes':scopes})
    pipe=ast.parse(whole[NODES['Glm5NextMoEGate']['file']].decode())
    imports=[n for n in pipe.body if isinstance(n,ast.ImportFrom)]
    alias=[n for n in imports if n.module=='mlx_vlm.models.deepseek_v32' and [(a.name,a.asname) for a in n.names]==[('language','_dsv32')]]
    base=[n for n in imports if n.module=='mlx_vlm.models.deepseek_v32.language' and [(a.name,a.asname) for a in n.names]==[('MoEGate',None)]]
    if len(alias)!=1 or len(base)!=1 or alias[0].level or base[0].level:raise SourceGuardError('UPSTREAM_IMPORT_BINDING_MISMATCH')
    return texts,records,{'selector_alias':ast.unparse(alias[0]),'base_import':ast.unparse(base[0]),'whole_module_imported':False}

class ResearchConfig:
    """Inert attribute seam for the selected constructor, not model config code."""
    __slots__=('num_experts_per_tok','norm_topk_prob','n_routed_experts','routed_scaling_factor','n_group','topk_group','hidden_size','topk_method')
    def __init__(self,values):
        if type(values) is not dict or set(values)!=set(self.__slots__):raise DomainError('CONFIG_FIELDS')
        for key in ('num_experts_per_tok','n_routed_experts','n_group','topk_group','hidden_size'):
            if type(values[key]) is not int:raise DomainError('CONFIG_INTEGER_TYPE')
        e,h,k,g,keep=[values[x] for x in ('n_routed_experts','hidden_size','num_experts_per_tok','n_group','topk_group')]
        if not (2<=e<=288 and 1<=h<=16 and 1<=k<=min(8,e) and 1<=g<=4 and e%g==0 and 1<=keep<=g):raise DomainError('CONFIG_BOUNDS')
        if g>1 and (e//g<2 or keep==g or k>keep*(e//g)):raise DomainError('GROUP_DOMAIN')
        if type(values['norm_topk_prob']) is not bool or type(values['topk_method']) is not str:raise DomainError('CONFIG_TYPE')
        scale=values['routed_scaling_factor']
        if type(scale) not in (int,float) or not math.isfinite(scale) or not 0<scale<=4:raise DomainError('CONFIG_SCALE')
        for key in self.__slots__:object.__setattr__(self,key,values[key])
    def __setattr__(self,key,value):raise DomainError('CONFIG_IMMUTABLE')

class Builder:
    def __init__(self,phase,mx,nn,manifest):
        self.phase=Path(phase);self.mx=mx;self.nn=nn;self.manifest=manifest
        self.module_origins=[guard.verify_origin(m,phase,manifest) for m in (mx,nn)]
        self.retained=[];self.sequence=0
    def new(self,variant=None,raw_override=None,binding_mutation=False):
        texts,source,imports=load_nodes(self.phase,raw_override)
        if variant is not None:
            if variant not in CALLER_MUTATIONS:raise SourceGuardError('UNLISTED_VARIANT')
            before,after=CALLER_MUTATIONS[variant]
            if texts['Glm5NextMoEGate'].count(before)!=1:raise SourceGuardError('VARIANT_SOURCE_SITE_MISMATCH')
            texts['Glm5NextMoEGate']=texts['Glm5NextMoEGate'].replace(before,after)
            allowed=NODES['Glm5NextMoEGate']['globals']-({'mx'} if variant=='omit-both-casts' else set())
            audit_node('Glm5NextMoEGate',texts['Glm5NextMoEGate'],allowed)
        builtins={'__build_class__':__build_class__,'super':super}
        dsv={'__name__':'pulsarmlx_research_dsv32','__builtins__':builtins,'mx':self.mx,'nn':self.nn,'ModelConfig':ResearchConfig}
        exec(compile(texts['group_expert_select'],'capsule:group_expert_select','exec'),dsv)
        exec(compile(texts['MoEGate'],'capsule:MoEGate','exec'),dsv)
        selected=dsv['group_expert_select'];base=dsv['MoEGate']
        namespace=types.SimpleNamespace(group_expert_select=selected)
        if binding_mutation:namespace.group_expert_select=lambda *a:None
        if type(namespace) is not types.SimpleNamespace or set(vars(namespace))!={'group_expert_select'} or namespace.group_expert_select is not selected:raise SourceGuardError('SELECTOR_BINDING_MISMATCH')
        glm={'__name__':'pulsarmlx_research_glm','__builtins__':builtins,'mx':self.mx,'MoEGate':base,'_dsv32':namespace}
        exec(compile(texts['Glm5NextMoEGate'],'capsule:Glm5NextMoEGate','exec'),glm)
        caller=glm['Glm5NextMoEGate']
        if caller.__bases__!=(base,) or caller.__init__ is not base.__init__ or base.__bases__!=(self.nn.Module,):raise SourceGuardError('REAL_BASE_CONSTRUCTOR_BINDING_MISMATCH')
        self.sequence+=1
        record={'sequence':self.sequence,'variant':variant or 'UNCHANGED_UPSTREAM','source_nodes':source,'import_binding':imports,'caller_executed_body_sha256':digest(texts['Glm5NextMoEGate'].encode()),'selector_object_id':id(selected),'base_class_object_id':id(base),'caller_class_object_id':id(caller),'fresh_function_objects':True,'compile_cache_claim':'new selected function/class objects; no claim of cold native kernel/driver cache','namespace_seams':['actual admitted mx/nn','inert ResearchConfig annotation/attribute seam','selected MoEGate base','_dsv32 namespace contains only selected selector','minimal class-construction builtins and __name__'],'other_stdlib_bindings_in_upstream_namespace':[]}
        result={'caller':caller,'base':base,'selector':selected,'record':record}
        # Keep references alive to make per-step identity/reset assertions reliable.
        self.retained.append(result)
        if len({x['record']['selector_object_id'] for x in self.retained})!=len(self.retained):raise SourceGuardError('FRESH_SELECTOR_IDENTITY_FAILED')
        return result
