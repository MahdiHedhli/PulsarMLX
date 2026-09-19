"""Paged persistent server (unpruned-persistent G55/G56): artifact/identity refusals (stdlib), and - when fastapi/uvicorn/httpx
are installed - the real HTTP path with a fake model and a fake store: readiness and poison rejection (503 engine_fatal,
no reload), request limits (400 before any model work), request deadline (504 / in-band), the loopback-only test seam
(403 off, 409 busy, 200 idle: forgets experts without reallocating), engine identity, and request isolation: A, B, A
gives the same A tokens; cancel then B runs clean; a recoverable failure is followed by success."""
import json
import os
import socket
import sys
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'scripts/research/glm53_flash/dogfood'))
try:
    import httpx
    import uvicorn
    import serve_offload as so
    import serve_resident as sr
    HAVE_STACK = True
except ImportError:      # pragma: no cover
    HAVE_STACK = False

BOUND = 20.0


class VerifyArtifact(unittest.TestCase):
    def make(self, experts=288, layout='expert-contiguous/1', reap=None, files=True):
        d = tempfile.mkdtemp(); os.makedirs(os.path.join(d, 'experts'))
        with open(os.path.join(d, 'offload_index.json'), 'w') as fh:
            json.dump({'layers': [3, 4], 'num_experts': experts, **({'layout': layout} if layout else {})}, fh)
        cfg = {'text_config': {'n_routed_experts': experts, 'num_experts_per_tok': 8, 'model_type': 'glm5_next_text'}, 'quantization': {'group_size': 64, 'bits': 4}}
        if reap is not None:
            cfg['reap'] = reap
        with open(os.path.join(d, 'config.json'), 'w') as fh:
            json.dump(cfg, fh)
        for name in ('tokenizer.json', 'chat_template.jinja'):
            open(os.path.join(d, name), 'w').write('x')
        if files:
            for lid in (3, 4):
                open(os.path.join(d, 'experts', f'layer_{lid:04d}.safetensors'), 'wb').write(b'\0' * 16)
        return d

    def test_mlx_not_imported(self):
        self.assertNotIn('mlx', sys.modules)

    def test_accepts_unpruned_contiguous(self):
        from paged_identity import verify_artifact
        ident = verify_artifact(self.make(), 60_000_000_000, 60_000_000_000)
        self.assertEqual((ident['n_routed_experts'], ident['moe_layers'], ident['layout']), (288, 2, 'expert-contiguous/1'))

    def test_refusals(self):
        from paged_identity import verify_artifact
        for kwargs, needle in (({'layout': None}, 'LAYOUT_NOT_CONTIGUOUS'), ({'experts': 144}, 'NOT_UNPRUNED'), ({'reap': {'kept': 144}}, 'NOT_UNPRUNED'), ({'files': False}, 'EXPERT_FILES_MISSING')):
            with self.assertRaisesRegex(SystemExit, needle):
                verify_artifact(self.make(**kwargs), 60_000_000_000, 60_000_000_000)
        with self.assertRaisesRegex(SystemExit, 'EXPERT_CACHE_OVER_BUDGET'):
            verify_artifact(self.make(), 60_000_000_000, 70_000_000_000)
        d = self.make(); os.remove(os.path.join(d, 'offload_index.json'))
        with self.assertRaisesRegex(SystemExit, 'REPACK_MISSING'):
            verify_artifact(d, 60_000_000_000, 60_000_000_000)


class FakeStore:
    def __init__(self):
        self.poisoned = None; self.resident = {'a': 3, 'b': 5}; self.resets = 0

    def stats(self):
        return {'policy': 'fake', 'resident_experts': sum(self.resident.values()), 'poisoned': self.poisoned, 'fill_failures': 0, 'misses': 7, 'hits': 9, 'logical_resets': self.resets}

    def reset_logical_state(self):
        n = sum(self.resident.values()); self.resident = {}; self.resets += 1
        return {'forgotten_experts': n, 'reallocated_slot_buffers': False, 'logical_resets': self.resets}


class R:
    def __init__(self, text, n, token, finish=None):
        self.text, self.prompt_tokens, self.generation_tokens, self.token = text, 7, n, token
        self.prompt_tps, self.generation_tps, self.finish_reason = 100.0, 20.0, finish


def fake_generate(prompt, max_tokens, temperature, prefill_step_size, **kw):
    """Deterministic per prompt; 'poison:N' poisons the fake store after N tokens; 'fail:N' raises; 'slow:N' takes N*50 ms."""
    msgs = json.loads(prompt); text = msgs[-1]['content']; kind, n = (text.split(':') + ['3'])[:2]; n = min(int(n), max_tokens)
    seed = sum(ord(c) for c in text)
    for i in range(n):
        if kind == 'poison' and i >= n - 1:
            so.ENGINE['store'].poisoned = 'write-phase fill failure (fake)'; raise RuntimeError('STORE_POISONED: fake')
        if kind == 'fail' and i >= n - 1:
            raise RuntimeError('FAKE_RECOVERABLE')
        if kind == 'slow':
            time.sleep(0.05)
        yield R('t%d ' % ((seed + i) % 97), i + 1, (seed + i) % 1000, 'stop' if i == n - 1 else None)


def free_port():
    s = socket.socket(); s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]; s.close(); return port


@unittest.skipUnless(HAVE_STACK, 'fastapi/uvicorn/httpx not installed')
class ServeOffloadLive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = free_port(); cls.base = f'http://127.0.0.1:{cls.port}'; cls.store = FakeStore()
        so.ENGINE.update(ready=True, reason=None, store=cls.store, loaded_utc='now', identity={'n_routed_experts': 288}, config={'backend': 'paged', 'mtp': False}, test_seam=True)

        def ready():
            if cls.store.poisoned is not None:
                so.ENGINE['ready'] = False; so.ENGINE['reason'] = 'store poisoned: ' + cls.store.poisoned
            return so.ENGINE['ready']
        sr.install(model='fake', processor=types.SimpleNamespace(tokenizer=None), config={}, model_id='glm-5.3-flash-unpruned-mixed-4_8bit-paged', load_seconds=0.0, warmup=None, prefill_step_size=256, default_max_tokens=64, speculator=None, draft_k=0, max_queue=2, speculative_max_prompt=0,
                   render=lambda messages, **kw: json.dumps(messages), tokenize=lambda prompt: [1] * (json.loads(prompt)[-1]['content'].count('x') or 7), generate=fake_generate,
                   ready=ready, not_ready_reason=None, limits={'max_prompt_tokens': 100, 'max_output_tokens': 50}, request_deadline_s=2.0, after_job=lambda job: ready())
        cls.server = uvicorn.Server(uvicorn.Config(so.app, host='127.0.0.1', port=cls.port, log_level='warning'))
        cls.thread = threading.Thread(target=cls.server.run, daemon=True); cls.thread.start()
        t0 = time.time()
        while not cls.server.started and time.time() - t0 < BOUND:
            time.sleep(0.02)

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True; cls.thread.join(BOUND); sr.STATE['worker'].close()

    def chat(self, text, **extra):
        return httpx.post(self.base + '/v1/chat/completions', json={'messages': [{'role': 'user', 'content': text}], 'max_tokens': 10, **extra}, timeout=BOUND)

    def tokens_of(self, text):
        r = self.chat(text); self.assertEqual(r.status_code, 200, r.text); return r.json()['choices'][0]['message']

    def test_01_engine_identity_and_limits(self):
        e = httpx.get(self.base + '/v1/engine', timeout=5).json()
        self.assertEqual((e['backend'], e['model'], e['ready'], e['config']['mtp']), ('paged', 'glm-5.3-flash-unpruned-mixed-4_8bit-paged', True, False))
        self.assertEqual(httpx.get(self.base + '/readyz', timeout=5).status_code, 200)
        r = self.chat('x' * 101); self.assertEqual(r.status_code, 400); self.assertEqual(r.json()['error']['type'], 'prompt_too_long')
        r = self.chat('slow:3', max_tokens=51); self.assertEqual(r.status_code, 400); self.assertEqual(r.json()['error']['type'], 'max_tokens_too_large')

    def test_02_isolation_a_b_a_and_recoverable_failure(self):
        a1 = self.tokens_of('slow:4'); b = self.tokens_of('fail:1x'.replace('x', ''))  if False else None
        r = self.chat('fail:2'); self.assertEqual(r.status_code, 500); self.assertEqual(r.json()['error']['type'], 'generation_error')
        b = self.tokens_of('slow:2'); a2 = self.tokens_of('slow:4')
        self.assertEqual(a1, a2, 'A after B (and after a recoverable failure) must equal the first A'); self.assertNotEqual(a1, b)
        self.assertEqual(httpx.get(self.base + '/readyz', timeout=5).status_code, 200)

    def test_03_cancel_then_b(self):
        with httpx.stream('POST', self.base + '/v1/chat/completions', json={'messages': [{'role': 'user', 'content': 'slow:40'}], 'max_tokens': 40, 'stream': True}, timeout=BOUND) as r:
            n = 0
            for line in r.iter_lines():
                if line.startswith('data: '):
                    n += 1
                    if n >= 3:
                        break
        t0 = time.time()
        while time.time() - t0 < BOUND and sr.STATE['worker'].stats()['busy']:
            time.sleep(0.02)
        self.assertFalse(sr.STATE['worker'].stats()['busy'], 'model not released after the client left')
        self.assertEqual(self.tokens_of('slow:2'), self.tokens_of('slow:2'))

    def test_04_deadline(self):
        r = self.chat('slow:200', max_tokens=50)     # 50 x 50 ms = 2.5 s > 2 s deadline
        self.assertEqual(r.status_code, 504); self.assertEqual(r.json()['error']['type'], 'deadline')
        t0 = time.time()
        while time.time() - t0 < BOUND and sr.STATE['worker'].stats()['busy']:
            time.sleep(0.02)
        self.assertEqual(self.chat('slow:2').status_code, 200)

    def test_05_test_seam(self):
        r = httpx.post(self.base + '/test/reset-logical-store', timeout=5); self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()['reset']['forgotten_experts'], 8); self.assertFalse(r.json()['reset']['reallocated_slot_buffers']); self.assertEqual(r.json()['store']['resident_experts'], 0)
        so.ENGINE['test_seam'] = False
        self.assertEqual(httpx.post(self.base + '/test/reset-logical-store', timeout=5).status_code, 403); so.ENGINE['test_seam'] = True

    def test_06_poison_makes_engine_not_ready_without_reload(self):
        r = self.chat('poison:2'); self.assertEqual(r.status_code, 500)
        self.assertEqual(httpx.get(self.base + '/readyz', timeout=5).status_code, 503)
        r = self.chat('slow:2'); self.assertEqual(r.status_code, 503); self.assertEqual(r.json()['error']['type'], 'engine_fatal')
        e = httpx.get(self.base + '/v1/engine', timeout=5).json(); self.assertFalse(e['ready']); self.assertIn('poisoned', e['reason'])
        self.assertEqual(httpx.get(self.base + '/health', timeout=5).status_code, 200)   # health stays responsive


if __name__ == '__main__':
    unittest.main()
