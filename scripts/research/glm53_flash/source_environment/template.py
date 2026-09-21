"""Bounded inert rendering; no tokenizer, media processor or model objects."""
import json
import os
from pathlib import Path
import guard
import custody

LIMIT = 16*1024*1024

def render(phase, data):
    guard.verify_child_interpreter(phase)
    if os.environ.get('FLASH_ADMITTED_PHASE') != str(phase):
        raise ValueError('supervised admission required')
    # A JSON round trip refuses arbitrary objects/callables; enforce input size first.
    raw_data=json.dumps(data,allow_nan=False)
    if len(raw_data.encode()) > 64*1024:
        raise ValueError('inert input cap')
    data=json.loads(raw_data)
    if 'messages' in data and not isinstance(data['messages'],list):
        raise ValueError('messages must be a bounded list')
    if len(data.get('messages',[]))>16:
        raise ValueError('message count cap')
    import jinja2
    import jinja2.sandbox
    import jinja2.ext
    manifest=guard.verify_environment(phase)
    imports=[guard.verify_origin(m,phase,manifest) for m in (jinja2,jinja2.sandbox,jinja2.ext)]
    body,custody_receipt=custody.working_body(phase,'chat_template.jinja')
    env=jinja2.sandbox.SandboxedEnvironment(undefined=jinja2.StrictUndefined,loader=None,
                                          extensions=['jinja2.ext.loopcontrols'],autoescape=False)
    # Reviewed installed Jinja builtins only; required by the exact template's macros.
    env.globals={k:env.globals[k] for k in ('range','namespace')}
    candidate=env.from_string(body.decode('utf-8'))
    chunks=[];size=0
    for chunk in candidate.generate(**data):
        size+=len(chunk.encode('utf-8'))
        if size>LIMIT:raise ValueError('render output cap')
        chunks.append(chunk)
    return ''.join(chunks),{'imports':imports,'metadata_sha256':custody_receipt['sha256'],
                           'bytes':size,'globals':['range','namespace'],
                           'extension':'jinja2.ext.loopcontrols','extra_custom_filters':[]}
