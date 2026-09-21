"""Strict inert research JSON adapter; historical producer correspondence UNKNOWN."""
import json,math,re
from pathlib import Path
import bc_guard
import custody
class InputPolicyError(ValueError):pass
class FilterPolicyError(TypeError):pass
class OutputLimitError(ValueError):pass

MAX_INPUT=65536

def validate_plain(value):
    budget={'nodes':0,'strings':0};active=set()
    def walk(v,depth):
        budget['nodes']+=1
        if depth>16:raise InputPolicyError('INERT_DEPTH')
        if budget['nodes']>4096:raise InputPolicyError('INERT_NODES')
        t=type(v)
        if v is None or t is bool:return
        if t is int:
            if abs(v)>2**53-1:raise InputPolicyError('INERT_INTEGER_RANGE')
            return
        if t is float:
            if not math.isfinite(v):raise InputPolicyError('INERT_NONFINITE')
            return
        if t is str:
            try:n=len(v.encode('utf-8'))
            except UnicodeEncodeError:raise InputPolicyError('INERT_UNICODE') from None
            budget['strings']+=n
            if n>32768 or budget['strings']>65536:raise InputPolicyError('INERT_STRING_BYTES')
            return
        if t not in (dict,list):raise InputPolicyError('INERT_TYPE')
        if id(v) in active:raise InputPolicyError('INERT_CYCLE')
        active.add(id(v))
        if t is dict:
            for k,item in v.items():
                if type(k) is not str:raise InputPolicyError('INERT_KEY_TYPE')
                walk(k,depth+1);walk(item,depth+1)
        else:
            for item in v:walk(item,depth+1)
        active.remove(id(v))
    walk(value,0)
    # Only exact checked builtins reach the serializer; no user methods/defaults.
    size=sum(len(chunk.encode('utf-8')) for chunk in json.JSONEncoder(ensure_ascii=False,allow_nan=False).iterencode(value))
    if size>MAX_INPUT:raise InputPolicyError('INERT_INPUT_BYTES')
    return {'serialized_input_bytes':size,**budget}

def json_filter(value,ensure_ascii=False,**kwargs):
    if kwargs:raise FilterPolicyError('JSON_FILTER_KWARG')
    if type(ensure_ascii) is not bool:raise FilterPolicyError('JSON_FILTER_BOOL')
    validate_plain(value)
    # Pinned Transformers convention, with the explicitly stricter finite policy.
    return json.dumps(value,ensure_ascii=ensure_ascii,indent=None,separators=None,sort_keys=False,allow_nan=False)

def identifier(value,code):
    if type(value) is not str or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,63}',value):raise InputPolicyError(code)

def validate_context(data):
    info=validate_plain(data)
    if type(data) is not dict or set(data)!={'messages','tools','add_generation_prompt'}:raise InputPolicyError('CONTEXT_FIELDS')
    if type(data['add_generation_prompt']) is not bool:raise InputPolicyError('GENERATION_PROMPT_BOOL')
    messages,tools=data['messages'],data['tools']
    if type(messages) is not list or len(messages)>16:raise InputPolicyError('MESSAGE_CONTAINER_LIMIT')
    if type(tools) is not list or len(tools)>8:raise InputPolicyError('TOOL_CONTAINER_LIMIT')
    for tool in tools:
        if type(tool) is not dict or set(tool)!={'type','function'} or tool['type']!='function':raise InputPolicyError('TOOL_WRAPPER')
        fn=tool['function']
        if type(fn) is not dict or not {'name','parameters'}<=set(fn) or not set(fn)<={'name','parameters','description','strict','defer_loading'}:raise InputPolicyError('TOOL_FUNCTION_FIELDS')
        identifier(fn['name'],'TOOL_NAME')
        if type(fn['parameters']) is not dict:raise InputPolicyError('TOOL_PARAMETERS_MAPPING')
        if 'description' in fn and type(fn['description']) is not str:raise InputPolicyError('TOOL_DESCRIPTION_STRING')
        if 'strict' in fn and type(fn['strict']) is not bool:raise InputPolicyError('TOOL_STRICT_BOOL')
        if 'defer_loading' in fn and fn['defer_loading'] is not False:raise InputPolicyError('DEFERRED_TOOL_UNSUPPORTED')
    for message in messages:
        if type(message) is not dict or not {'role','content'}<=set(message):raise InputPolicyError('MESSAGE_REQUIRED_FIELDS')
        role=message['role']
        if role not in ('user','system','assistant'):raise InputPolicyError('MESSAGE_ROLE_UNSUPPORTED')
        if type(message['content']) is not str:raise InputPolicyError('MESSAGE_TEXT_STRING')
        expected={'role','content'} if role!='assistant' else {'role','content','reasoning_content','tool_calls'}
        if set(message)!=expected:raise InputPolicyError('MESSAGE_FIELDS')
        if role=='assistant':
            if type(message['reasoning_content']) is not str:raise InputPolicyError('REASONING_STRING')
            calls=message['tool_calls']
            if type(calls) is not list or len(calls)>8:raise InputPolicyError('CALL_CONTAINER_LIMIT')
            for call in calls:
                if type(call) is not dict or set(call)!={'function'}:raise InputPolicyError('CALL_WRAPPER')
                fn=call['function']
                if type(fn) is not dict or set(fn)!={'name','arguments'}:raise InputPolicyError('CALL_FUNCTION_FIELDS')
                identifier(fn['name'],'CALL_NAME')
                if type(fn['arguments']) is not dict or len(fn['arguments'])>32:raise InputPolicyError('CALL_ARGUMENTS_MAPPING')
                for key in fn['arguments']:identifier(key,'CALL_ARGUMENT_KEY')
    return info

class Renderer:
    def __init__(self,phase,output_limit=16*1024**2):
        phase=Path(phase);bc_guard.verify_child_interpreter(phase)
        if type(output_limit) is not int or not 1<=output_limit<=16*1024**2:raise ValueError('output ceiling')
        import jinja2,jinja2.sandbox,jinja2.ext
        manifest=bc_guard.verify_environment(phase)
        self.imports=[bc_guard.verify_origin(m,phase,manifest) for m in (jinja2,jinja2.sandbox,jinja2.ext)]
        body,self.custody=custody.read_bounded(phase,['source','chat_template.jinja'],custody.EXPECTED['chat_template.jinja'])
        self.env=jinja2.sandbox.SandboxedEnvironment(undefined=jinja2.StrictUndefined,loader=None,extensions=['jinja2.ext.loopcontrols'],autoescape=False)
        self.env.globals={k:self.env.globals[k] for k in ('range','namespace')}
        self.env.filters['tojson']=self._filter
        self.template=self.env.from_string(body.decode('utf-8'))
        self.output_limit=output_limit;self.render_count=0;self.render_attempts=0;self.force_ascii=False
    def _filter(self,value,ensure_ascii=False,**kwargs):
        if type(self.force_ascii) is not bool:raise FilterPolicyError('MUTATION_FLAG_BOOL')
        if kwargs:raise FilterPolicyError('JSON_FILTER_KWARG')
        if type(ensure_ascii) is not bool:raise FilterPolicyError('JSON_FILTER_BOOL')
        return json_filter(value,True if self.force_ascii else ensure_ascii)
    def render(self,data):
        self.render_attempts+=1
        info=validate_context(data);chunks=[];size=0
        for chunk in self.template.generate(**data):
            size+=len(chunk.encode('utf-8'))
            if size>self.output_limit:raise OutputLimitError('RENDER_OUTPUT_LIMIT')
            chunks.append(chunk)
        self.render_count+=1
        return ''.join(chunks),{**info,'output_bytes':size,'template_sha256':self.custody['sha256'],'render_count':self.render_count}
