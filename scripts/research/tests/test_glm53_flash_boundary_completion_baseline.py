"""One separately classified baseline; no successor JSON filter is enabled."""
import hashlib,json,os
from pathlib import Path
import sys,unittest
if not os.environ.get('FLASH_BOUNDARY_COMPLETION_PHASE'):
    raise unittest.SkipTest('successor supervisor required; NOT_EXECUTED')
PHASE=Path(os.environ['FLASH_BOUNDARY_COMPLETION_PHASE']);SOURCE=PHASE.parent/'repos/PulsarMLX'
sys.path.insert(0,str(SOURCE/'scripts/research/glm53_flash/boundary_completion'))
import bc_guard
bc_guard.verify_child_interpreter(PHASE)
import custody
class Baseline(unittest.TestCase):
    def test_standard_filter_expected_error(self):
        import jinja2,jinja2.sandbox
        manifest=bc_guard.verify_environment(PHASE)
        for m in (jinja2,jinja2.sandbox):bc_guard.verify_origin(m,PHASE,manifest)
        body,receipt=custody.read_bounded(PHASE,['source','chat_template.jinja'],custody.EXPECTED['chat_template.jinja'])
        env=jinja2.sandbox.SandboxedEnvironment(undefined=jinja2.StrictUndefined,loader=None,extensions=['jinja2.ext.loopcontrols'],autoescape=False)
        env.globals={k:env.globals[k] for k in ('range','namespace')}
        template=env.from_string(body.decode());prefix=[];bytes_seen=0
        with self.assertRaisesRegex(TypeError,"unexpected keyword argument 'ensure_ascii'") as caught:
            for chunk in template.generate(messages=[{'role':'user','content':'Hello.'}],tools=[{'function':{'name':'weather','parameters':{'type':'object'}}}],add_generation_prompt=True):
                bytes_seen+=len(chunk.encode());self.assertLessEqual(bytes_seen,16*1024**2);prefix.append(chunk)
        print(json.dumps({'event':'baseline','classification':'EXPECTED_UNSUPPORTED_STANDARD_FILTER',
                          'exception_type':type(caught.exception).__name__,'exception':str(caught.exception),
                          'template_sha256':receipt['sha256'],'yielded_prefix_before_error':''.join(prefix),
                          'prefix_scope':'source-layout observation before any successor adapter implementation/output; no tool declaration completed',
                          'successor_adapter_enabled':False}),flush=True)
