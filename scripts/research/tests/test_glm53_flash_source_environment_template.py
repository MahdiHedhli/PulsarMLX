"""Prospectively classified inert template rendering and rejected dependencies."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest
if not os.environ.get('FLASH_ADMITTED_PHASE'):
    raise unittest.SkipTest('admitted external runner required; NOT_EXECUTED')
PHASE=Path(os.environ['FLASH_ADMITTED_PHASE']);ROOT=PHASE.parent/'repos/PulsarMLX'
sys.path.insert(0,str(ROOT/'scripts/research/glm53_flash/source_environment'))
import guard
guard.verify_child_interpreter(PHASE)
import template
from jinja2 import UndefinedError

class TemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture=json.loads((ROOT/'fixtures/research/glm53-flash-source-environment-v1/template.json').read_text())
        cls.records=[]
    @classmethod
    def tearDownClass(cls):
        print(json.dumps({'event':'template_observations','records':cls.records,
                          'tool_declaration_rendering':'NOT_QUALIFIED',
                          'tokenization_media_model':'NOT_EXECUTED'}),flush=True)
    def test_text_exact(self):
        f=self.fixture;output,receipt=template.render(PHASE,dict(f['base'],messages=f['text_messages']))
        self.assertEqual(output,f['prospective']['text_exact'])
        self.records.append({'case':'text-exact','output':output,'output_sha256':hashlib.sha256(output.encode()).hexdigest(),**receipt})
    def test_tool_shaped_inert_message(self):
        f=self.fixture;output,receipt=template.render(PHASE,dict(f['base'],messages=f['tool_shaped_messages']))
        self.assertIn(f['prospective']['tool_call_fragment'],output)
        self.records.append({'case':'assistant-tool-shaped-string-arguments','output':output,**receipt})
    def test_missing_malformed_message_fields(self):
        f=self.fixture
        for data in (dict(f['base']),dict(f['base'],messages=[{'content':'x'}]),dict(f['base'],messages=[{'role':'user'}])):
            with self.assertRaises(UndefinedError):template.render(PHASE,data)
        with self.assertRaises(ValueError):template.render(PHASE,dict(f['base'],messages='malformed'))
        self.records.append({'case':'missing-messages-role-content-malformed-container','outcome':'REJECTED'})
    def test_tool_declaration_dependency_unqualified(self):
        f=self.fixture
        with self.assertRaisesRegex(TypeError,"ensure_ascii") as caught:
            template.render(PHASE,dict(f['base'],messages=f['text_messages'],tools=f['tool_definitions']))
        self.records.append({'case':'tool-declaration','outcome':'NOT_QUALIFIED',
                             'dependency_error':str(caught.exception),'custom_filter_enabled':False})
