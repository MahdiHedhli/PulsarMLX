#!/usr/bin/env python3
"""OpenAI-style chat completions over the fully resident GLM-5.3-Flash build (dogfood serving, not the research harness).

Why not mlx_vlm.server: its loader resolves model types from the installed package and cannot pick up the pinned
pipenetwork runtime (custom `glm5_next`), so this serves the same load path as run_resident.py:
glm53_flash_mlx.load (sanitize -> nn.quantize per config map -> strict load_weights, weights materialized), Metal
buffers wired up to the max recommended working set (graph 23 finding: unwired, the OS evicts the experts decode
does not touch and prefill pages them back), one warm-up generate at startup so the first request does not pay the
per-process settle, and generation on ONE inference worker thread (serve_worker.InferenceWorker: the model is owned by
that thread alone; handlers enqueue a job and await its items on the event loop, so an active stream, a concurrent
non-streaming request and /health never wait on each other - graph 30: the first version consumed the generator on the
event loop under a threading lock held across the stream's yields and deadlocked under exactly that interleaving).
Speculation (--mtp) is decided per request BEFORE any response byte (graph 34): greedy sampling and a tokenized prompt no
longer than --speculative-max-prompt (the speculator's one-chunk prefill limit, default 4096); otherwise the ordinary
stream_generate path; usage.speculative / usage.speculative_reason say which ran.
Queue: at most --max-queue jobs pending (running + waiting), 503 + Retry-After beyond that; a client that disconnects
mid-stream cancels its job and the model is released within one token; a non-streaming request runs to completion
(max_tokens bounds it); an exception inside a generation answers that request with 500 and the worker continues.

Endpoints: GET /v1/models, POST /v1/chat/completions (stream: true|false; messages with system/user/assistant
roles through the model's chat template; max_tokens, temperature, top_p, repetition_penalty; usage in the
response; `reasoning_effort` low|medium|high maps onto the template's Reasoning Effort line, default Max), GET /health.
The chat template opens a <think> block, so the model's reasoning is returned as
`reasoning_content` (everything before `</think>`) and the answer as `content`, in both modes. No tool calling, no images, no prompt-cache reuse across requests (prefill is
70-190 tok/s on the Studio).

Pins: mlx-vlm 8d79dbcf…, glm5_next a61a7c7d… (PYTHONPATH -> the pinned pipenetwork checkout).
"""
import argparse
import asyncio
import json
import os
import sys
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
import uvicorn

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from serve_policy import speculative_eligible  # noqa: E402
from serve_worker import InferenceWorker, QueueFull, WorkerDead  # noqa: E402

app = FastAPI(title="PulsarMLX GLM-5.3-Flash resident server")
STATE = {}


def load(args):
    import mlx.core as mx
    from glm53_flash_mlx.load import load as load_pinned
    from mlx_vlm import generate, stream_generate
    from mlx_vlm.prompt_utils import apply_chat_template

    if not args.no_wire:
        mx.set_wired_limit(int(mx.device_info()["max_recommended_working_set_size"]))
    t0 = time.time()
    model, processor = load_pinned(args.model, lazy=False)
    config = json.load(open(os.path.join(args.model, "config.json")))
    load_s = time.time() - t0
    warm = None
    if args.warmup:
        tw = time.time()
        w = generate(model, processor, apply_chat_template(processor, config, "Hello.", num_images=0), max_tokens=args.warmup, verbose=False, temperature=0.0)
        warm = {"tokens": args.warmup, "seconds": round(time.time() - tw, 1), "generation_tps": getattr(w, "generation_tps", None)}
    spec = None
    if args.mtp:
        from mtp_speculator import MTPSpeculator
        spec = MTPSpeculator(model.language_model, args.mtp, draft_k=args.draft_k)
    install(model=model, processor=processor, config=config, model_id=args.model_id, load_seconds=round(load_s, 1), warmup=warm,
            prefill_step_size=args.prefill_step_size, default_max_tokens=args.max_tokens, speculator=spec, draft_k=args.draft_k, max_queue=args.max_queue,
            speculative_max_prompt=args.speculative_max_prompt,
            render=lambda messages, **kw: apply_chat_template(processor, config, messages, num_images=0, **kw),
            tokenize=lambda prompt: processor.tokenizer.encode(prompt),
            generate=lambda prompt, **kw: stream_generate(model, processor, prompt, **kw))
    print(f"loaded in {load_s:.1f}s; warm-up {warm}; serving {args.model_id}", flush=True)


def install(**state):
    """Bind the model-side callables and start the worker (tests bind a fake model here and drive the real HTTP path)."""
    if STATE.get("worker") is not None:
        STATE["worker"].close()
    STATE.update(state, requests=0, worker=InferenceWorker(max_queue=int(state.get("max_queue") or 4)))


def _messages(body):
    msgs = body.get("messages") or []
    out = []
    for m in msgs:
        role = m.get("role", "user"); content = m.get("content", "")
        if isinstance(content, list):   # OpenAI content parts: keep the text parts
            content = "".join(p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text")
        msg = {"role": role, "content": content}
        if role == "assistant" and isinstance(m.get("reasoning_content"), str):
            msg["reasoning_content"] = m["reasoning_content"]   # the template re-inserts <think>…</think> on history turns
        out.append(msg)
    return out


def _reasoning_effort(body):
    """OpenAI's reasoning_effort -> the template's {low, high} (anything else is the template default, 'max')."""
    v = str(body.get("reasoning_effort") or "").lower()
    return {"low": "low", "medium": "high", "high": "high"}.get(v)


THINK_END = "</think>"


class _SpecResult:
    def __init__(self, text, prompt_tokens, generation_tokens, prompt_tps, generation_tps, finish_reason):
        self.text, self.prompt_tokens, self.generation_tokens = text, prompt_tokens, generation_tokens
        self.prompt_tps, self.generation_tps, self.finish_reason = prompt_tps, generation_tps, finish_reason


def _run_speculative(spec, processor, prompt, max_tokens, ids=None, max_prompt_tokens=4096):
    """Greedy MTP speculative generation yielding stream_generate-like results (text per token, stats on the last).
    `ids`: the prompt already tokenized by the preflight (must be <= max_prompt_tokens: the speculator prefills in one chunk)."""
    tok = processor.tokenizer
    _e = getattr(tok, "eos_token_ids", None)
    eos = set(_e if isinstance(_e, (list, set, tuple)) else [_e if _e is not None else tok.eos_token_id])
    ids = tok.encode(prompt) if ids is None else ids
    t0 = time.time(); t_first = None; toks = []; emitted = ""
    for tkn, _ in spec.generate(ids, max_tokens, eos, prefill_step_size=max_prompt_tokens):
        if t_first is None:
            t_first = time.time()
        toks.append(tkn)
        if tkn in eos:
            break
        full = tok.decode(toks)
        piece = full[len(emitted):] if full.startswith(emitted) else ""
        if piece and not piece.endswith("\ufffd"):
            emitted = full
        else:
            piece = ""
        n = len(toks); done = n >= max_tokens
        yield _SpecResult(piece, len(ids), n, round(len(ids) / max(1e-9, t_first - t0), 2), round((n - 1) / max(1e-9, time.time() - t_first), 2), "length" if done else None)
    n = len(toks)
    tail = tok.decode(toks if toks and toks[-1] not in eos else toks[:-1])
    yield _SpecResult(tail[len(emitted):] if tail.startswith(emitted) else "", len(ids), n, round(len(ids) / max(1e-9, (t_first or time.time()) - t0), 2),
                      round((n - 1) / max(1e-9, time.time() - (t_first or t0)), 2), "length" if n >= max_tokens else "stop")


def _split_think(text):
    """(reasoning_content, content): the template opened <think>, so the text up to </think> is reasoning."""
    i = text.find(THINK_END)
    if i < 0:
        return text.strip(), ""     # never closed: everything is reasoning (max_tokens hit while thinking)
    return text[:i].strip(), text[i + len(THINK_END):].lstrip("\n")


class _ThinkSplitter:
    """Streaming version: routes pieces to reasoning_content until </think> is seen, holding back a partial marker."""
    def __init__(self):
        self.in_think = True; self.buf = ""; self.first_content = True

    def feed(self, piece):
        if not self.in_think:
            if self.first_content:
                piece = piece.lstrip("\n")
                self.first_content = not piece
            return [("content", piece)] if piece else []
        self.buf += piece; out = []
        i = self.buf.find(THINK_END)
        if i >= 0:
            if self.buf[:i]:
                out.append(("reasoning_content", self.buf[:i]))
            rest = self.buf[i + len(THINK_END):].lstrip("\n"); self.buf = ""; self.in_think = False
            if rest:
                self.first_content = False
                out.append(("content", rest))
            return out
        # emit everything except a tail that could be the start of the marker
        keep = 0
        for k in range(min(len(THINK_END) - 1, len(self.buf)), 0, -1):
            if THINK_END.startswith(self.buf[-k:]):
                keep = k; break
        emit, self.buf = self.buf[:len(self.buf) - keep], self.buf[len(self.buf) - keep:]
        return [("reasoning_content", emit)] if emit else []

    def flush(self):
        if self.buf:
            piece, self.buf = self.buf, ""
            return [("reasoning_content" if self.in_think else "content", piece)]
        return []


@app.get("/health")
async def health():
    spec = STATE.get("speculator")
    worker = STATE.get("worker")
    return {"status": "ok" if "model" in STATE else "loading", "model": STATE.get("model_id"), "load_seconds": STATE.get("load_seconds"), "warmup": STATE.get("warmup"), "requests": STATE.get("requests"),
            "speculative": ({"draft_k": STATE.get("draft_k"), **spec.stats} if spec is not None else None), "worker": worker.stats() if worker is not None else None}


@app.get("/v1/models")
async def models():
    return {"object": "list", "data": [{"id": STATE.get("model_id"), "object": "model", "owned_by": "pulsarmlx"}]}


def _prepare(messages, effort):
    """(prompt text, token ids): the chat template and the tokenizer, run on a worker thread."""
    prompt = STATE["render"](messages, **({"reasoning_effort": effort} if effort else {}))
    return prompt, STATE["tokenize"](prompt)


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    if "model" not in STATE:
        return JSONResponse({"error": {"message": "model loading"}}, status_code=503)
    ready = STATE.get("ready")                  # paged engine (serve_offload): a poisoned store / fatal state rejects new work
    if ready is not None and not ready():
        return JSONResponse({"error": {"message": STATE.get("not_ready_reason", "engine not ready"), "type": "engine_fatal"}}, status_code=503)
    messages = _messages(body)
    if not messages:
        return JSONResponse({"error": {"message": "messages required"}}, status_code=400)
    processor = STATE["processor"]
    effort = _reasoning_effort(body)
    prompt, ids = await asyncio.to_thread(_prepare, messages, effort)   # template + tokenizer off the event loop (graph 34 review)
    limits = STATE.get("limits") or {}          # bounded requests (serve_offload): explicit 400 before any model work
    max_tokens = int(body.get("max_tokens") or STATE["default_max_tokens"])
    if limits.get("max_prompt_tokens") and len(ids) > limits["max_prompt_tokens"]:
        return JSONResponse({"error": {"message": f"prompt {len(ids)} tokens exceeds the admitted limit {limits['max_prompt_tokens']}", "type": "prompt_too_long"}}, status_code=400)
    if limits.get("max_output_tokens") and max_tokens > limits["max_output_tokens"]:
        return JSONResponse({"error": {"message": f"max_tokens {max_tokens} exceeds the admitted limit {limits['max_output_tokens']}", "type": "max_tokens_too_large"}}, status_code=400)
    kwargs = {"max_tokens": max_tokens, "temperature": float(body.get("temperature", 0.0)),
              "prefill_step_size": STATE["prefill_step_size"]}
    if body.get("top_p") is not None:
        kwargs["top_p"] = float(body["top_p"])
    if body.get("repetition_penalty") is not None:
        kwargs["repetition_penalty"] = float(body["repetition_penalty"])
    rid = "chatcmpl-" + uuid.uuid4().hex[:24]; created = int(time.time()); model_id = STATE["model_id"]
    stream = bool(body.get("stream", False))

    spec = STATE.get("speculator")              # preflight: the prompt length decides speculation before any response byte
    speculative, why = speculative_eligible(spec is not None, kwargs["temperature"], kwargs.get("top_p"), kwargs.get("repetition_penalty"), len(ids), STATE["speculative_max_prompt"])

    def make_generator():                       # runs on the worker thread only
        if speculative:
            return _run_speculative(spec, processor, prompt, kwargs["max_tokens"], ids=ids, max_prompt_tokens=STATE["speculative_max_prompt"])
        return STATE["generate"](prompt, **kwargs)

    loop = asyncio.get_running_loop(); items = asyncio.Queue()

    def deliver(item):                          # worker thread -> event loop; a closed loop (shutdown) just drops the item
        try:
            loop.call_soon_threadsafe(items.put_nowait, item)
        except RuntimeError:
            pass
    try:
        if STATE.get("worker") is None:
            return JSONResponse({"error": {"message": "engine stopped", "type": "engine_fatal"}}, status_code=503)
        job = STATE["worker"].submit(make_generator, deliver)
    except QueueFull as exc:
        return JSONResponse({"error": {"message": str(exc), "type": "overloaded"}}, status_code=503, headers={"Retry-After": "1"})
    except WorkerDead as exc:
        return JSONResponse({"error": {"message": str(exc), "type": "worker_dead"}}, status_code=503)
    STATE["requests"] += 1

    deadline = STATE.get("request_deadline_s")

    async def results():
        """Items until the terminal marker; raises the generation's exception; cancels the job if the consumer stops early
        or the request deadline passes (a generation deadline: the job is cancelled at its next token)."""
        t_submit = time.time()
        try:
            while True:
                if deadline:
                    remaining = deadline - (time.time() - t_submit)
                    if remaining <= 0:
                        raise TimeoutError(f"request deadline {deadline}s exceeded")
                    kind, payload = await asyncio.wait_for(items.get(), timeout=remaining)
                else:
                    kind, payload = await items.get()
                if kind == "item":
                    yield payload
                elif kind == "error":
                    raise payload
                else:
                    return
        finally:
            job.cancel()                        # no-op after completion; releases the model when the client went away
            hook = STATE.get("after_job")       # paged engine: refresh readiness (poison) after every job
            if hook is not None:
                hook(job)

    def usage_of(final):
        return {"prompt_tokens": final.prompt_tokens, "completion_tokens": final.generation_tokens, "total_tokens": final.prompt_tokens + final.generation_tokens,
                "prompt_tps": round(final.prompt_tps, 2), "generation_tps": round(final.generation_tps, 2), "speculative": speculative, "speculative_reason": why}

    if not stream:
        text, final = "", None
        try:
            async for r in results():
                text += r.text; final = r
        except asyncio.TimeoutError:
            return JSONResponse({"error": {"message": f"request deadline {deadline}s exceeded", "type": "deadline"}}, status_code=504)
        except Exception as exc:
            return JSONResponse({"error": {"message": f"generation failed: {type(exc).__name__}: {exc}", "type": "generation_error"}}, status_code=500)
        if final is None:
            return JSONResponse({"error": {"message": "generation produced no output", "type": "generation_error"}}, status_code=500)
        reasoning, answer = _split_think(text)
        msg = {"role": "assistant", "content": answer}
        if reasoning:
            msg["reasoning_content"] = reasoning
        return {"id": rid, "object": "chat.completion", "created": created, "model": model_id,
                "choices": [{"index": 0, "message": msg, "finish_reason": final.finish_reason or "stop"}], "usage": usage_of(final)}

    async def sse():
        head = {"id": rid, "object": "chat.completion.chunk", "created": created, "model": model_id}
        yield "data: " + json.dumps({**head, "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}]}) + "\n\n"
        final = None; splitter = _ThinkSplitter()
        try:
            async for r in results():
                final = r
                for field, piece in splitter.feed(r.text):
                    yield "data: " + json.dumps({**head, "choices": [{"index": 0, "delta": {field: piece}, "finish_reason": None}]}) + "\n\n"
        except Exception as exc:                # headers are out: report the failure in-band and end the stream
            yield "data: " + json.dumps({**head, "error": {"message": f"generation failed: {type(exc).__name__}: {exc}", "type": "generation_error"}}) + "\n\n"
            yield "data: [DONE]\n\n"
            return
        for field, piece in splitter.flush():
            yield "data: " + json.dumps({**head, "choices": [{"index": 0, "delta": {field: piece}, "finish_reason": None}]}) + "\n\n"
        usage = usage_of(final) if final else None
        yield "data: " + json.dumps({**head, "choices": [{"index": 0, "delta": {}, "finish_reason": (final.finish_reason if final else None) or "stop"}], "usage": usage}) + "\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(sse(), media_type="text/event-stream")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True); ap.add_argument("--model-id", default="glm-5.3-flash-reap50")
    ap.add_argument("--host", default="127.0.0.1"); ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--max-tokens", type=int, default=1024, help="default when the request omits max_tokens")
    ap.add_argument("--prefill-step-size", type=int, default=512); ap.add_argument("--warmup", type=int, default=8)
    ap.add_argument("--mtp", default=None, help="MTP layer directory (convert_mtp.py output): greedy requests (temperature 0, no top_p/penalty) use speculative decoding")
    ap.add_argument("--draft-k", type=int, default=1)
    ap.add_argument("--speculative-max-prompt", type=int, default=4096, help="longest prompt (tokens) the speculator prefills in one chunk; longer greedy prompts take the ordinary path")
    ap.add_argument("--no-wire", action="store_true", help="do not wire the Metal buffers (default wires; assumes a dedicated serving host)")
    ap.add_argument("--max-queue", type=int, default=4, help="requests pending on the inference worker (running + waiting) before 503")
    args = ap.parse_args()
    load(args)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
