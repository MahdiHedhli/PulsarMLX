"""Real request handling of the dogfood server (graph 30) with a fake model behind the real HTTP path: a live uvicorn on a
loopback port, httpx clients from threads. Needs fastapi + uvicorn + httpx (the dogfood env); skipped where they are
absent (CI's stdlib venv) - the worker itself is covered by test_glm53_flash_serve_worker.py there.

Scenarios (every wait bounded): an active stream + a concurrent non-streaming request + /health all complete and the
stream is never blocked; a client that disconnects mid-stream releases the model within a token; the queue bound answers
503 + Retry-After without blocking; a generation exception answers 500 (or an in-band SSE error) and the next request
succeeds; reasoning/content split unchanged.
"""
import json
import socket
import sys
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
    import serve_resident
    HAVE_STACK = True
except ImportError:      # pragma: no cover - CI's venv has no fastapi
    HAVE_STACK = False

BOUND = 20.0
TOKEN_S = 0.05


class R:
    def __init__(self, text, n, finish=None):
        self.text, self.prompt_tokens, self.generation_tokens = text, 7, n
        self.prompt_tps, self.generation_tps, self.finish_reason = 100.0, 20.0, finish


def fake_generate(prompt, max_tokens, temperature, prefill_step_size, **kw):
    """Directive in the last user message: 'slow:N' -> N tokens at TOKEN_S each; 'fail:N' -> raise after N tokens;
    'think:N' -> N reasoning tokens, </think>, then two answer tokens."""
    msgs = json.loads(prompt); text = msgs[-1]['content']
    kind, n = text.split(':'); n = min(int(n), max_tokens)
    if kind == 'think':
        pieces = ['r%d ' % i for i in range(n)] + ['</think>', 'a0 ', 'a1']
        for i, p in enumerate(pieces):
            yield R(p, i + 1, 'stop' if i == len(pieces) - 1 else None)
        return
    for i in range(n):
        if kind == 'fail' and i >= n - 1:
            raise RuntimeError('FAKE_METAL_FAILURE')
        time.sleep(TOKEN_S)
        yield R('t%d ' % i, i + 1, 'length' if i == n - 1 else None)


def free_port():
    s = socket.socket(); s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]; s.close(); return port


@unittest.skipUnless(HAVE_STACK, 'fastapi/uvicorn/httpx not installed')
class ServeResidentLive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = free_port(); cls.base = f'http://127.0.0.1:{cls.port}'
        serve_resident.install(model='fake', processor=None, config={}, model_id='fake-model', load_seconds=0.0, warmup=None, prefill_step_size=512,
                               default_max_tokens=64, speculator=None, draft_k=1, max_queue=2, speculative_max_prompt=4096,
                               render=lambda messages, **kw: json.dumps(messages), tokenize=lambda prompt: [1] * 7, generate=fake_generate)
        cls.server = uvicorn.Server(uvicorn.Config(serve_resident.app, host='127.0.0.1', port=cls.port, log_level='warning'))
        cls.thread = threading.Thread(target=cls.server.run, daemon=True); cls.thread.start()
        t0 = time.time()
        while not cls.server.started and time.time() - t0 < BOUND:
            time.sleep(0.02)
        assert cls.server.started

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True; cls.thread.join(BOUND)
        serve_resident.STATE['worker'].close()

    def chat(self, text, stream=False, **extra):
        return {'messages': [{'role': 'user', 'content': text}], 'stream': stream, 'max_tokens': 1000, **extra}

    def health(self):
        return httpx.get(self.base + '/health', timeout=5.0).json()

    def worker(self):
        return self.health()['worker']

    def wait_worker(self, key, value):
        t0 = time.time()
        while time.time() - t0 < BOUND:
            if self.worker()[key] == value:
                return time.time() - t0
            time.sleep(0.02)
        self.fail(f'worker {key} never reached {value}: {self.worker()}')

    def stream_lines(self, text, on_chunk=None, stop_after=None):
        chunks = []
        with httpx.stream('POST', self.base + '/v1/chat/completions', json=self.chat(text, stream=True), timeout=BOUND) as r:
            self.assertEqual(r.status_code, 200)
            for line in r.iter_lines():
                if not line.startswith('data: '):
                    continue
                payload = line[6:]
                if payload == '[DONE]':
                    chunks.append('[DONE]'); break
                chunks.append(json.loads(payload))
                if on_chunk:
                    on_chunk(chunks)
                if stop_after is not None and len(chunks) >= stop_after:
                    break
        return chunks

    def test_stream_with_concurrent_nonstream_and_health(self):
        events = {}; started = threading.Event()
        def nonstream():
            started.wait(BOUND); events['ns_sent'] = time.time()
            r = httpx.post(self.base + '/v1/chat/completions', json=self.chat('slow:2'), timeout=BOUND)
            events['ns_done'] = time.time(); events['ns'] = (r.status_code, r.json())
        def healths():
            started.wait(BOUND); ts = []
            for _ in range(3):
                t = time.time(); h = self.health(); ts.append(time.time() - t); self.assertEqual(h['status'], 'ok')
            events['health_latencies'] = ts
        threads = [threading.Thread(target=nonstream), threading.Thread(target=healths)]
        for t in threads: t.start()
        def on_chunk(chunks):
            if len(chunks) == 2 and not started.is_set():
                events['stream_first'] = time.time(); started.set()
        t0 = time.time(); chunks = self.stream_lines('slow:20', on_chunk=on_chunk); events['stream_done'] = time.time()
        for t in threads: t.join(BOUND)
        self.assertNotIn(None, [t.is_alive() for t in threads]); self.assertFalse(any(t.is_alive() for t in threads), 'a concurrent request hung')
        pieces = [c['choices'][0]['delta'].get('reasoning_content', '') for c in chunks if c != '[DONE]' and c.get('choices')]
        self.assertEqual(''.join(pieces).split(), ['t%d' % i for i in range(20)])
        self.assertEqual(chunks[-1], '[DONE]'); self.assertEqual(chunks[-2]['choices'][0]['finish_reason'], 'length')
        self.assertEqual(chunks[-2]['usage']['completion_tokens'], 20)
        self.assertEqual(events['ns'][0], 200); self.assertEqual(events['ns'][1]['usage']['completion_tokens'], 2)
        self.assertGreaterEqual(events['ns_done'], events['stream_done'] - 0.01, 'non-stream finished before the stream it was queued behind')
        self.assertLess(events['ns_done'] - events['stream_done'], 2.0)
        self.assertLess(max(events['health_latencies']), 1.0, events['health_latencies'])
        self.assertLess(events['stream_done'] - t0, 20 * TOKEN_S + 3.0)
        w = self.worker(); self.assertEqual((w['busy'], w['pending']), (False, 0))

    def test_disconnect_mid_stream_releases_model(self):
        before = self.worker()['cancelled']
        chunks = self.stream_lines('slow:200', stop_after=3)      # 10 s of generation; the client leaves after 3 chunks
        self.assertEqual(len(chunks), 3)
        waited = self.wait_worker('cancelled', before + 1)
        self.assertLess(waited, 2.0, 'model not released within a token of the disconnect')
        t0 = time.time(); r = httpx.post(self.base + '/v1/chat/completions', json=self.chat('slow:1'), timeout=BOUND)
        self.assertEqual(r.status_code, 200); self.assertLess(time.time() - t0, 2.0)

    def test_queue_bound_503(self):
        gate = threading.Event(); results = {}
        def stream():
            results['stream'] = self.stream_lines('slow:30', on_chunk=lambda c: gate.set() if len(c) >= 2 else None)
        def queued():
            gate.wait(BOUND); time.sleep(0.05)
            results['queued'] = httpx.post(self.base + '/v1/chat/completions', json=self.chat('slow:1'), timeout=BOUND).status_code
        ts = [threading.Thread(target=stream), threading.Thread(target=queued)]
        for t in ts: t.start()
        gate.wait(BOUND); time.sleep(0.3)                     # one running + one waiting = max_queue
        t0 = time.time(); r = httpx.post(self.base + '/v1/chat/completions', json=self.chat('slow:1'), timeout=BOUND)
        self.assertLess(time.time() - t0, 1.0)
        self.assertEqual(r.status_code, 503); self.assertEqual(r.headers.get('retry-after'), '1'); self.assertEqual(r.json()['error']['type'], 'overloaded')
        for t in ts: t.join(BOUND)
        self.assertEqual(results['queued'], 200); self.assertEqual(results['stream'][-1], '[DONE]')
        self.assertGreaterEqual(self.worker()['rejected'], 1)

    def test_generation_exception_then_next_request_ok(self):
        failed = self.worker()['failed']
        r = httpx.post(self.base + '/v1/chat/completions', json=self.chat('fail:3'), timeout=BOUND)
        self.assertEqual(r.status_code, 500); self.assertEqual(r.json()['error']['type'], 'generation_error'); self.assertIn('FAKE_METAL_FAILURE', r.json()['error']['message'])
        chunks = self.stream_lines('fail:3')
        self.assertEqual(chunks[-1], '[DONE]'); self.assertIn('error', chunks[-2]); self.assertIn('FAKE_METAL_FAILURE', chunks[-2]['error']['message'])
        self.assertEqual(sum(1 for c in chunks if c != '[DONE]' and c.get('choices') and c['choices'][0]['delta'].get('reasoning_content')), 2)
        r = httpx.post(self.base + '/v1/chat/completions', json=self.chat('slow:2'), timeout=BOUND)
        self.assertEqual(r.status_code, 200); self.assertEqual(r.json()['usage']['completion_tokens'], 2)
        self.assertEqual(self.worker()['failed'], failed + 2)

    def test_reasoning_split_nonstream_and_stream(self):
        r = httpx.post(self.base + '/v1/chat/completions', json=self.chat('think:3'), timeout=BOUND).json()
        msg = r['choices'][0]['message']
        self.assertEqual(msg['reasoning_content'], 'r0 r1 r2'); self.assertEqual(msg['content'], 'a0 a1'); self.assertEqual(r['choices'][0]['finish_reason'], 'stop')
        self.assertFalse(r['usage']['speculative']); self.assertIn('no speculator', r['usage']['speculative_reason'])
        chunks = self.stream_lines('think:3')
        reasoning = ''.join(c['choices'][0]['delta'].get('reasoning_content', '') for c in chunks if c != '[DONE]' and c.get('choices'))
        content = ''.join(c['choices'][0]['delta'].get('content', '') for c in chunks if c != '[DONE]' and c.get('choices'))
        self.assertEqual((reasoning.strip(), content), ('r0 r1 r2', 'a0 a1'))

    def test_bad_requests(self):
        self.assertEqual(httpx.post(self.base + '/v1/chat/completions', json={'messages': []}, timeout=5.0).status_code, 400)
        self.assertEqual(httpx.get(self.base + '/v1/models', timeout=5.0).json()['data'][0]['id'], 'fake-model')


class FakeTokenizer:
    eos_token_ids = [0]
    eos_token_id = 0

    def encode(self, prompt):
        n = int(json.loads(prompt)[-1]['content'].split(':')[1]); return list(range(1, n + 1))

    def decode(self, toks):
        return ' '.join('s%d' % t for t in toks)


class FakeSpeculator:
    """Records every generate() call; yields 5 tokens then eos. Raises like the real one on a too-long prompt."""
    def __init__(self):
        self.calls = []; self.stats = {'steps': 0, 'drafted': 0, 'accepted': 0, 'accepted_by_position': [0]}

    def generate(self, ids, max_tokens, eos, prefill_step_size=4096):
        self.calls.append({'prompt_tokens': len(ids), 'max_tokens': max_tokens, 'prefill_step_size': prefill_step_size})
        if len(ids) > prefill_step_size:
            raise ValueError('PROMPT_TOO_LONG_FOR_ONE_CHUNK')
        for i in range(1, 6):
            yield 100 + i, 0
        yield 0, 0


@unittest.skipUnless(HAVE_STACK, 'fastapi/uvicorn/httpx not installed')
class SpeculativePreflightLive(unittest.TestCase):
    """Graph 34: the prompt length decides speculation before any response byte; the boundary (4096 / 4097) is exercised
    through the real HTTP path with a fake speculator that records what it was asked."""
    @classmethod
    def setUpClass(cls):
        cls.port = free_port(); cls.base = f'http://127.0.0.1:{cls.port}'; cls.spec = FakeSpeculator(); tok = FakeTokenizer()
        serve_resident.install(model='fake', processor=types.SimpleNamespace(tokenizer=tok), config={}, model_id='fake-spec', load_seconds=0.0, warmup=None, prefill_step_size=512,
                               default_max_tokens=64, speculator=cls.spec, draft_k=1, max_queue=2, speculative_max_prompt=4096,
                               render=lambda messages, **kw: json.dumps(messages), tokenize=tok.encode, generate=fake_generate)
        cls.server = uvicorn.Server(uvicorn.Config(serve_resident.app, host='127.0.0.1', port=cls.port, log_level='warning'))
        cls.thread = threading.Thread(target=cls.server.run, daemon=True); cls.thread.start()
        t0 = time.time()
        while not cls.server.started and time.time() - t0 < BOUND:
            time.sleep(0.02)
        assert cls.server.started

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True; cls.thread.join(BOUND)
        serve_resident.STATE['worker'].close()

    def post(self, n, stream=False, **extra):
        body = {'messages': [{'role': 'user', 'content': f'slow:{n}'}], 'stream': stream, 'max_tokens': 8, **extra}
        return httpx.post(self.base + '/v1/chat/completions', json=body, timeout=BOUND)

    def test_at_and_above_the_limit(self):
        before = len(self.spec.calls)
        r = self.post(4096); self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()['usage']['speculative']); self.assertEqual(r.json()['usage']['completion_tokens'], 6)
        self.assertEqual(self.spec.calls[-1], {'prompt_tokens': 4096, 'max_tokens': 8, 'prefill_step_size': 4096})
        self.assertEqual(r.json()['choices'][0]['message']['content'], '')          # the fake tokens never close </think>: all reasoning
        self.assertEqual(r.json()['choices'][0]['message']['reasoning_content'], 's101 s102 s103 s104 s105')
        r = self.post(4097); self.assertEqual(r.status_code, 200)
        self.assertFalse(r.json()['usage']['speculative']); self.assertIn('4097 tokens > speculative one-chunk limit 4096', r.json()['usage']['speculative_reason'])
        self.assertEqual(len(self.spec.calls), before + 1, 'the speculator was called for an ineligible prompt')
        self.assertEqual(r.json()['usage']['completion_tokens'], 8)                  # fake_generate's 'slow:4097' capped by max_tokens 8

    def test_non_greedy_takes_the_ordinary_path(self):
        before = len(self.spec.calls)
        r = self.post(10, temperature=0.7); self.assertFalse(r.json()['usage']['speculative']); self.assertIn('temperature', r.json()['usage']['speculative_reason'])
        r = self.post(10, top_p=0.9); self.assertFalse(r.json()['usage']['speculative'])
        self.assertEqual(len(self.spec.calls), before)

    def test_stream_above_the_limit_is_ordinary_and_complete(self):
        chunks = []
        with httpx.stream('POST', self.base + '/v1/chat/completions', json={'messages': [{'role': 'user', 'content': 'slow:5000'}], 'stream': True, 'max_tokens': 3}, timeout=BOUND) as r:
            self.assertEqual(r.status_code, 200)
            for line in r.iter_lines():
                if line.startswith('data: '):
                    chunks.append(line[6:])
        self.assertEqual(chunks[-1], '[DONE]'); last = json.loads(chunks[-2])
        self.assertFalse(last['usage']['speculative']); self.assertEqual(last['choices'][0]['finish_reason'], 'length'); self.assertNotIn('error', last)


if __name__ == '__main__':
    unittest.main()
