"""Independent literal bytes, parser checks, typed rejections and real JSON mutant."""
import copy,hashlib,json,os
from pathlib import Path
import sys,unittest
if not os.environ.get('FLASH_BOUNDARY_COMPLETION_PHASE'):
    raise unittest.SkipTest('successor supervisor required; NOT_EXECUTED')
PHASE=Path(os.environ['FLASH_BOUNDARY_COMPLETION_PHASE']);SOURCE=PHASE.parent/'repos/PulsarMLX'
sys.path.insert(0,str(SOURCE/'scripts/research/glm53_flash/boundary_completion'))
import bc_guard
bc_guard.verify_child_interpreter(PHASE)
import bc_template as adapter
import bc_checks as check

class TemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture=SOURCE/'fixtures/research/glm53-flash-boundary-completion-v1'
        cls.f=json.loads((fixture/'template.json').read_text());cls.controls=json.loads((fixture/'controls.json').read_text())
        cls.r=adapter.Renderer(PHASE);cls.records=[];cls.mutations=[]
    @classmethod
    def tearDownClass(cls):
        print(json.dumps({'event':'template_observations','records':cls.records,'controls':cls.mutations,
                          'render_attempts':cls.r.render_attempts,'completed_renders':cls.r.render_count,
                          'module_origins':cls.r.imports,'template_sha256':cls.r.custody['sha256'],
                          'adapter_correspondence':'RESEARCH_CONTRACT; HISTORICAL_PRODUCER_UNKNOWN',
                          'tool_execution':'NOT_EXECUTED','tokenizer_model':'NOT_EXECUTED'}),flush=True)
    def render_check(self,context,expected,label):
        output,receipt=self.r.render(context)
        check.exact(output.encode('utf-8'),expected.encode('utf-8'),'TEMPLATE_UTF8_BYTES_MISMATCH',template=True)
        self.records.append({'case':label,'output':output,'output_sha256':hashlib.sha256(output.encode()).hexdigest(),**receipt})
        return output
    def test_actual_one_multiple_declarations(self):
        f=self.f
        for count,key in ((1,'expected_one_tool'),(2,'expected_multiple_tools')):
            context=copy.deepcopy(f['base']);context['tools']=copy.deepcopy(f['tools'][:count])
            output=self.render_check(context,f[key],'declarations-'+str(count))
            embedded=output.split('<tools>\n',1)[1].split('</tools>',1)[0]
            parsed=[json.loads(line) for line in embedded.splitlines() if line.strip()]
            self.assertEqual(parsed,[t['function'] for t in context['tools']])
            self.assertIn('Café',output);self.assertIn(r'\n\t',output);self.assertIn('<&>',output)
        context=copy.deepcopy(f['base']);context['tools']=[copy.deepcopy(f['tools'][0])]
        context['tools'][0]['function'].update(strict=True,defer_loading=False)
        self.render_check(context,f['expected_one_tool'],'source-skips-strict-and-false-defer-fields')
    def test_assistant_arguments_string_and_json_forms(self):
        f=self.f;context=copy.deepcopy(f['base']);context['messages']=[f['assistant_message']]
        output=self.render_check(context,f['expected_assistant_call'],'assistant-mapping-arguments')
        args=f['assistant_message']['tool_calls'][0]['function']['arguments']
        for key,literal in f['literal_argument_fragments'].items():
            fragment='<arg_key>'+key+'</arg_key><arg_value>'+literal+'</arg_value>'
            self.assertIn(fragment,output)
            if type(args[key]) is not str:self.assertEqual(json.loads(literal),args[key])
    def test_filter_exact_json_scalars_and_order(self):
        f=self.f
        for tool,literal in zip(f['tools'],f['literal_json_declarations']):
            self.assertEqual(json.loads(literal),tool['function'])
            actual=adapter.json_filter(tool['function'],ensure_ascii=False)
            self.assertIs(type(actual),str);self.assertEqual(actual,literal)
        value='"\\\b\f\n\r\t\x00';literal=r'"\"\\\b\f\n\r\t\u0000"'
        self.assertEqual(json.loads(literal),value);self.assertEqual(adapter.json_filter(value),literal)
        self.assertEqual(adapter.json_filter('<>&'),r'"<>&"')
        self.assertEqual(adapter.json_filter('Été',ensure_ascii=True),r'"\u00c9t\u00e9"')
        self.assertEqual(adapter.json_filter({'z':True,'a':None,'n':2.5}),'{'+'"z": true, "a": null, "n": 2.5}')
        self.records.append({'case':'filter-exact-json','ordering':'insertion','separators':'comma-space/colon-space','return_type':'str','HTML_escaping':'not added','Unicode_and_control_escapes':'literal byte checks passed'})
    def test_filter_unsupported_kwargs_types_and_nonfinite(self):
        for kwargs in ({'indent':2},{'separators':(',',':')},{'sort_keys':True}):
            with self.assertRaisesRegex(adapter.FilterPolicyError,'JSON_FILTER_KWARG'):adapter.json_filter({},**kwargs)
        for value in (0,1,None,'false'):
            with self.assertRaisesRegex(adapter.FilterPolicyError,'JSON_FILTER_BOOL'):adapter.json_filter({},ensure_ascii=value)
        for value in (float('nan'),float('inf'),-float('inf')):
            with self.assertRaisesRegex(adapter.InputPolicyError,'INERT_NONFINITE'):adapter.json_filter(value)
        self.records.append({'case':'filter-outside-domain','outcome':'EXPLICIT_REJECTION_NOT_FEATURE_QUALIFICATION'})
    def test_inert_policy_does_not_invoke_objects(self):
        called=[]
        class Trap:
            def __str__(self):called.append('str');raise AssertionError('object method invoked')
            def __iter__(self):called.append('iter');raise AssertionError('object method invoked')
        class TrapList(list):
            def __iter__(self):called.append('iter');raise AssertionError('subclass method invoked')
        for value in (Trap(),TrapList([1]),lambda:called.append('call')):
            with self.assertRaisesRegex(adapter.InputPolicyError,'INERT_TYPE'):adapter.json_filter(value)
        self.assertEqual(called,[])
        probes=[(2**53,'INERT_INTEGER_RANGE'),('\ud800','INERT_UNICODE'),('x'*32769,'INERT_STRING_BYTES'),([0]*4096,'INERT_NODES'),({1:'x'},'INERT_KEY_TYPE')]
        deep=0
        for _ in range(17):deep=[deep]
        cycle=[];cycle.append(cycle)
        probes += [(deep,'INERT_DEPTH'),(cycle,'INERT_CYCLE'),(['x'*32768,'x'*32768],'INERT_INPUT_BYTES')]
        for value,code in probes:
            with self.assertRaisesRegex(adapter.InputPolicyError,code):adapter.json_filter(value)
        self.records.append({'case':'inert-type-depth-size-finite-policy','arbitrary_methods_invoked':called,'rejection_probes':len(probes)+3})
    def test_missing_malformed_render_fields_and_limits(self):
        base=self.f['base'];probes=[]
        c=copy.deepcopy(base);del c['messages'];probes.append((c,'CONTEXT_FIELDS'))
        c=copy.deepcopy(base);c['messages']='wrong';probes.append((c,'MESSAGE_CONTAINER_LIMIT'))
        c=copy.deepcopy(base);c['messages']=[{'role':'user'}];probes.append((c,'MESSAGE_REQUIRED_FIELDS'))
        c=copy.deepcopy(base);c['messages'][0]['content']={};probes.append((c,'MESSAGE_TEXT_STRING'))
        c=copy.deepcopy(base);c['tools']=[copy.deepcopy(self.f['tools'][0])];del c['tools'][0]['function']['name'];probes.append((c,'TOOL_FUNCTION_FIELDS'))
        c=copy.deepcopy(base);c['tools']=[copy.deepcopy(self.f['tools'][0])];c['tools'][0]['function']['parameters']=[];probes.append((c,'TOOL_PARAMETERS_MAPPING'))
        c=copy.deepcopy(base);c['tools']=[copy.deepcopy(self.f['tools'][0])]*9;probes.append((c,'TOOL_CONTAINER_LIMIT'))
        c=copy.deepcopy(base);c['messages']=[{'role':'user','content':'x'}]*17;probes.append((c,'MESSAGE_CONTAINER_LIMIT'))
        c=copy.deepcopy(base);c['messages']=[copy.deepcopy(self.f['assistant_message'])];c['messages'][0]['tool_calls'][0]['function']['arguments']='{"city":"Paris"}';probes.append((c,'CALL_ARGUMENTS_MAPPING'))
        for context,code in probes:
            with self.assertRaisesRegex(adapter.InputPolicyError,code):self.r.render(context)
        limited=adapter.Renderer(PHASE,output_limit=64)
        with self.assertRaisesRegex(adapter.OutputLimitError,'RENDER_OUTPUT_LIMIT'):limited.render(base)
        self.assertEqual(limited.render_count,0)
        self.records.append({'case':'missing-malformed-limits','domain_rejections':len(probes),'output_cap_probe':{'limit':64,'attempts':limited.render_attempts,'completed':limited.render_count}})
    def test_real_json_semantic_mutation_and_restore(self):
        f=self.f;context=copy.deepcopy(f['base']);context['tools']=[f['tools'][0]];expected=f['expected_one_tool']
        self.render_check(context,expected,'json-control-normal')
        before=self.r.render_count;spec=self.controls['controls']['json-forced-ascii'];self.r.force_ascii=True
        try:outcome=check.classify(lambda:self.render_check(context,expected,'json-semantic-mutant'),spec)
        finally:self.r.force_ascii=False
        outcome.update({'id':'json-forced-ascii','normal_before':True,'restored_after':False,'evaluation_delta':self.r.render_count-before})
        self.mutations.append(outcome);self.render_check(context,expected,'json-control-restored');outcome['restored_after']=True
        self.assertEqual(outcome['outcome'],'INTENDED_REJECTION');self.assertEqual(outcome['evaluation_delta'],1)
    def test_text_only_preserved_and_sandbox_configuration(self):
        self.render_check(self.f['base'],self.f['expected_text'],'text-preservation')
        import jinja2
        self.assertIs(self.r.env.undefined,jinja2.StrictUndefined);self.assertIsNone(self.r.env.loader)
        self.assertEqual(set(self.r.env.globals),{'range','namespace'})
