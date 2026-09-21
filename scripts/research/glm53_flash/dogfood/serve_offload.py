#!/usr/bin/env python3
"""Minimal long-lived PAGED server for the unpruned GLM-5.3-Flash build (unpruned-persistent G55).

The resident server (serve_resident.py) loads a fully resident build; this entrypoint loads the paged one through the
accepted paged loader (run_offload.load_offloaded: repack + PulsarSlotStore) and serves the same OpenAI-style HTTP
surface with the same inference worker (one generation at a time, bounded queue, cancellation). What persists across
requests: the loaded weights, the expert slots, the store's policy state and its read resources. What is fresh for every
request: mlx_vlm.stream_generate builds a new prompt cache (KV / sparse-attention / recurrent / conv state) per call,
positions and generation state start at zero, the detokenizer is reset, and the stop matcher is the tokenizer's
StoppingCriteria consulted per generated token. Cross-request prefix caching is OFF. The saved warm state on disk is
ignored (never deleted): the first request starts from an empty logical store.

Everything the accepted configuration needs is EXPLICIT on the command line (no fall-through to lru / stack / gap-2
defaults) and verified before the model loads: the repack directory must exist with an expert-contiguous layout (no
auto-repack), the checkpoint must be unpruned (288 routed experts, no `reap` block) on this explicitly unpruned path,
the expert budget is given in bytes and capped by --max-expert-cache-bytes, wiring and the write mode are stated, and
the termination policy is the qualified glm5-eos-v1 unless --allow-legacy-stop says otherwise. The health endpoint
reports cached counters (store.stats() builds a dict; no MLX evaluation) and the engine readiness: a poisoned store or a
dead worker makes the engine not ready and every new request is rejected with 503 engine_fatal; there is no automatic
reload. Requests are bounded (prompt tokens, max_tokens, queue depth, a per-request deadline that cancels the job at
its next token). The listener defaults to loopback; --test-seam enables a loopback-only POST /test/reset-logical-store
that forgets the resident experts at idle (the same-process logical-cold control of G57) and is never a serving API.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import serve_resident as sr  # noqa: E402  (shared app, handlers, worker wiring)
from paged_identity import verify_artifact  # noqa: E402
from fastapi import Request  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
import uvicorn  # noqa: E402

app = sr.app
ENGINE = {"ready": True, "reason": None, "store": None, "loaded_utc": None, "config": None, "identity": None, "test_seam": False}


def load(args):
    import mlx.core as mx
    from mlx_vlm import stream_generate
    from mlx_vlm.prompt_utils import apply_chat_template
    from run_offload import load_offloaded
    import stop_policy

    identity = verify_artifact(args.offload, args.max_expert_cache_bytes, args.expert_cache_bytes)
    t0 = time.time()
    # lazy=False: the resident weights are materialized HERE, on the loading thread. MLX (0.32) binds a lazily mx.load()-ed
    # array to the loading thread's default stream and refuses to evaluate it on another thread ("There is no Stream(cpu, N)
    # in current thread"); the generation runs on the inference worker thread (pilot first contact: the first request aborted
    # the process). Materialized arrays are thread-agnostic; the store's slot tensors are allocated evaluated and its reads
    # convert on the calling (worker) thread.
    model, processor, config, store, eager = load_offloaded(args.offload, args.expert_cache_bytes / 1e9, lazy=False, store_policy="slot", warm_start=False, cache_clear_threshold_gb=args.cache_clear_threshold_gb,
                                                            read_workers=args.read_workers, coalesce_gap_experts=args.coalesce_gap, read_chunk_bytes=args.read_chunk_mib << 20, wire=args.wire, write_mode=args.write_mode)
    if store.stats()["budget_bytes"] != args.expert_cache_bytes or store.coalesce_gap_experts != args.coalesce_gap or store.write_mode != args.write_mode or store.read_chunk_bytes != args.read_chunk_mib << 20:
        raise SystemExit("STORE_CONFIG_MISMATCH the store did not take the requested settings")
    version = args.stop_policy if args.allow_legacy_stop else stop_policy.POLICY_VERSION
    policy = stop_policy.build(args.offload, processor.tokenizer, version=version); installed = stop_policy.apply(processor, policy)
    load_s = time.time() - t0
    ENGINE.update(store=store, loaded_utc=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), identity=identity,
                  config={"backend": "paged", "offload": os.path.abspath(args.offload), "expert_cache_bytes": args.expert_cache_bytes, "wired": bool(args.wire), "aligned_reads": True, "read_workers": args.read_workers, "read_chunk_mib": args.read_chunk_mib, "bulk_min": store.bulk_min, "prefill_step_size": args.prefill_step_size,
                          "coalesce_gap": args.coalesce_gap, "write_mode": args.write_mode, "warm_start": False, "prefix_reuse": False, "mtp": False, "sampling": "as requested (greedy by default)", "stop_policy": {"version": policy["version"], "terminal_ids": policy["terminal_ids"], "names": {str(k): v for k, v in policy["names"].items()}, **installed},
                          "limits": {"max_prompt_tokens": args.max_prompt_tokens, "max_output_tokens": args.max_output_tokens, "max_queue": args.max_queue, "request_deadline_s": args.request_deadline_s}, "eager_ffn_layers": eager, "load_seconds": round(load_s, 1), "capacity_per_layer": store.capacity, "expert_bytes": store.expert_bytes},
                  test_seam=bool(args.test_seam))
    model_id = args.model_id or "glm-5.3-flash-unpruned-mixed-4_8bit-paged"

    def ready():
        st = ENGINE["store"]
        if st is not None and st.poisoned is not None:
            ENGINE["ready"] = False; ENGINE["reason"] = f"store poisoned: {st.poisoned}"
        w = sr.STATE.get("worker")
        if w is not None and w.stats().get("dead"):
            ENGINE["ready"] = False; ENGINE["reason"] = f"worker dead: {w.stats()['dead']}"
        return ENGINE["ready"]

    def after_job(job):
        ready()

    sr.install(model=model, processor=processor, config=config, model_id=model_id, load_seconds=round(load_s, 1), warmup=None, prefill_step_size=args.prefill_step_size,
               default_max_tokens=args.default_max_tokens, speculator=None, draft_k=0, max_queue=args.max_queue, speculative_max_prompt=0,
               render=lambda messages, **kw: apply_chat_template(processor, config, messages, num_images=0, **kw), tokenize=lambda prompt: processor.tokenizer.encode(prompt),
               generate=lambda prompt, **kw: stream_generate(model, processor, prompt, **kw),
               ready=ready, not_ready_reason=None, limits={"max_prompt_tokens": args.max_prompt_tokens, "max_output_tokens": args.max_output_tokens}, request_deadline_s=args.request_deadline_s, after_job=after_job)
    sr.STATE["not_ready_reason"] = None
    sr.STATE["trace_snapshot"] = lambda: store.stats()      # opt-in per-request store deltas (pulsar_trace); cached counters, no MLX evaluation
    print(f"loaded in {load_s:.1f}s; {model_id}; experts {identity['n_routed_experts']} top-{identity['num_experts_per_tok']}; budget {args.expert_cache_bytes} B; gap {args.coalesce_gap}; write {args.write_mode}; wired {args.wire}; stop {policy['version']} {policy['names']}", flush=True)


@app.get("/v1/engine")
async def engine():
    st = ENGINE["store"]
    stats = st.stats() if st is not None else None
    ready = ENGINE["ready"] and (st is None or st.poisoned is None)
    return {"ready": ready, "reason": ENGINE["reason"], "model": sr.STATE.get("model_id"), "backend": "paged", "loaded_utc": ENGINE["loaded_utc"], "identity": ENGINE["identity"], "config": ENGINE["config"], "store": stats,
            "worker": sr.STATE["worker"].stats() if sr.STATE.get("worker") else None, "requests": sr.STATE.get("requests"), "test_seam": ENGINE["test_seam"]}


@app.get("/readyz")
async def readyz():
    st = ENGINE["store"]; ok = ENGINE["ready"] and (st is None or st.poisoned is None) and sr.STATE.get("worker") is not None and not sr.STATE["worker"].stats().get("dead")
    return JSONResponse({"ready": ok, "reason": None if ok else (ENGINE["reason"] or "not ready")}, status_code=200 if ok else 503)


@app.post("/test/reset-logical-store")
async def reset_logical_store(request: Request):
    """Test seam only: forget every resident expert at idle (slot buffers stay allocated). Loopback + --test-seam only."""
    if not ENGINE["test_seam"] or request.client is None or request.client.host not in ("127.0.0.1", "::1"):
        return JSONResponse({"error": {"message": "test seam disabled", "type": "forbidden"}}, status_code=403)
    w = sr.STATE.get("worker")
    if w is None or w.stats()["pending"] != 0 or w.stats()["busy"]:
        return JSONResponse({"error": {"message": "engine busy: reset only at idle", "type": "busy"}}, status_code=409)
    import asyncio
    result = await asyncio.get_running_loop().run_in_executor(None, ENGINE["store"].reset_logical_state)   # nothing else touches the store while the worker is idle
    return {"reset": result, "store": ENGINE["store"].stats()}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offload", required=True, help="the existing contiguous repack directory (never repacked here)")
    ap.add_argument("--expert-cache-bytes", type=int, required=True); ap.add_argument("--max-expert-cache-bytes", type=int, default=60_000_000_000, help="admitted ceiling; refuse above")
    ap.add_argument("--coalesce-gap", type=int, required=True); ap.add_argument("--write-mode", choices=("stack", "per-expert"), required=True)
    wire = ap.add_mutually_exclusive_group(required=True); wire.add_argument("--wire", dest="wire", action="store_true"); wire.add_argument("--no-wire", dest="wire", action="store_false")
    ap.add_argument("--read-workers", type=int, default=8); ap.add_argument("--read-chunk-mib", type=int, default=64); ap.add_argument("--prefill-step-size", type=int, default=256); ap.add_argument("--cache-clear-threshold-gb", type=float, default=2.0)
    ap.add_argument("--stop-policy", choices=("glm5-eos-v1", "legacy-tokenizer-eos"), default="glm5-eos-v1"); ap.add_argument("--allow-legacy-stop", action="store_true", help="required to run the legacy policy (diagnostics only)")
    ap.add_argument("--max-prompt-tokens", type=int, default=2048); ap.add_argument("--max-output-tokens", type=int, default=512); ap.add_argument("--default-max-tokens", type=int, default=256)
    ap.add_argument("--max-queue", type=int, default=4); ap.add_argument("--request-deadline-s", type=float, default=900.0)
    ap.add_argument("--host", default="127.0.0.1"); ap.add_argument("--port", type=int, required=True); ap.add_argument("--allow-remote", action="store_true")
    ap.add_argument("--model-id", default=None); ap.add_argument("--test-seam", action="store_true", help="enable the loopback-only logical-reset test seam")
    args = ap.parse_args(argv)
    if args.host not in ("127.0.0.1", "localhost", "::1") and not args.allow_remote:
        raise SystemExit("LOOPBACK_ONLY pass --allow-remote to bind elsewhere")
    if args.stop_policy != "glm5-eos-v1" and not args.allow_legacy_stop:
        raise SystemExit("LEGACY_STOP_REQUIRES_FLAG --allow-legacy-stop")
    load(args)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
