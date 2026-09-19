#!/usr/bin/env python3
"""Fresh-process PAGED reference for one chat request (unpruned-persistent G56/G57): the accepted paged loader, the same
explicit settings and the same stop policy and generation call as serve_offload.py, but a new process and an empty
logical store per invocation. Takes the request as a messages JSON (so history requests are rendered exactly as the
server renders them), records the token ids, per-token times, finish reason and store counters. This is the
"reference arm" of the serving-parity and warm-store comparisons; run_offload.py remains the single-prompt runner.
"""
import argparse
import hashlib
import json
import os
import signal
import sys
import time


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--offload', required=True); ap.add_argument('--expert-cache-bytes', type=int, required=True); ap.add_argument('--coalesce-gap', type=int, required=True); ap.add_argument('--write-mode', choices=('stack', 'per-expert'), required=True)
    wire = ap.add_mutually_exclusive_group(required=True); wire.add_argument('--wire', dest='wire', action='store_true'); wire.add_argument('--no-wire', dest='wire', action='store_false')
    ap.add_argument('--read-workers', type=int, default=8); ap.add_argument('--read-chunk-mib', type=int, default=64); ap.add_argument('--prefill-step-size', type=int, default=256)
    ap.add_argument('--stop-policy', choices=('glm5-eos-v1', 'legacy-tokenizer-eos'), default='glm5-eos-v1')
    ap.add_argument('--messages', required=True, help='JSON file: {"messages": [...], "max_tokens": N, "reasoning_effort": "low", "temperature": 0.0}')
    ap.add_argument('--log', required=True)
    args = ap.parse_args()
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import mlx.core as mx
    from mlx_vlm import stream_generate
    from mlx_vlm.prompt_utils import apply_chat_template
    from run_offload import load_offloaded
    from paged_identity import verify_artifact
    import stop_policy
    stop = {'signal': None}
    signal.signal(signal.SIGTERM, lambda signum, frame: stop.update(signal=signum))
    identity = verify_artifact(args.offload, 60_000_000_000, args.expert_cache_bytes)
    req = json.load(open(args.messages))
    t0 = time.time()
    model, processor, config, store, eager = load_offloaded(args.offload, args.expert_cache_bytes / 1e9, store_policy='slot', warm_start=False, read_workers=args.read_workers, coalesce_gap_experts=args.coalesce_gap, read_chunk_bytes=args.read_chunk_mib << 20, wire=args.wire, write_mode=args.write_mode)
    policy = stop_policy.build(args.offload, processor.tokenizer, version=args.stop_policy); installed = stop_policy.apply(processor, policy)
    load_s = time.time() - t0
    effort = req.get('reasoning_effort', 'low'); max_tokens = int(req.get('max_tokens', 256)); temperature = float(req.get('temperature', 0.0))
    prompt = apply_chat_template(processor, config, req['messages'], num_images=0, **({'reasoning_effort': effort} if effort else {}))
    ids = processor.tokenizer.encode(prompt)
    before = store.stats(); t1 = time.time(); times = []; toks = []; text = ''; final = None; first_answer = None
    for r in stream_generate(model, processor, prompt, max_tokens=max_tokens, temperature=temperature, prefill_step_size=args.prefill_step_size):
        now = time.time() - t1; times.append(round(now, 4)); toks.append(r.token); text += r.text; final = r
        if first_answer is None and '</think>' in text and text.split('</think>', 1)[1].strip():
            first_answer = now
        if stop['signal'] is not None:
            break
    gen_s = time.time() - t1; after = store.stats()
    delta = {k: after[k] - before[k] for k in ('hits', 'misses', 'evictions', 'requested_read_bytes', 'overread_bytes', 'alignment_overread_bytes', 'hot_copy_bytes', 'logical_admitted_bytes', 'cold_reads', 'hot_reads')}
    n = len(times); half = n // 2
    rec = {'arm': 'paged-reference-fresh-process', 'request': req, 'prompt_tokens': len(ids), 'load_s': round(load_s, 2), 'generate_s': round(gen_s, 2), 'first_token_s': times[0] if times else None, 'first_answer_s': None if first_answer is None else round(first_answer, 3), 'tokens': toks, 'tokens_sha256_12': hashlib.sha256(json.dumps(toks).encode()).hexdigest()[:12],
           'generation_tokens': getattr(final, 'generation_tokens', 0), 'finish_reason': getattr(final, 'finish_reason', None), 'decode_tps_after_first': round((n - 1) / (times[-1] - times[0]), 3) if n > 1 and times[-1] > times[0] else None, 'decode_tps_last_half': round((n - 1 - half) / (times[-1] - times[half]), 3) if n >= 4 else None,
           'text': text, 'usable_answer': first_answer is not None, 'store_delta': delta, 'store_final': after, 'stop_policy': {'version': policy['version'], 'terminal_ids': policy['terminal_ids'], **installed}, 'config': {'expert_cache_bytes': args.expert_cache_bytes, 'coalesce_gap': args.coalesce_gap, 'write_mode': args.write_mode, 'wired': args.wire, 'prefill_step_size': args.prefill_step_size, 'read_workers': args.read_workers, 'read_chunk_mib': args.read_chunk_mib},
           'identity': identity, 'mx_memory': {'active': int(mx.get_active_memory()), 'cache': int(mx.get_cache_memory()), 'peak': int(mx.get_peak_memory())}, 'terminated_by_signal': stop['signal']}
    json.dump(rec, open(args.log, 'w'), indent=1)
    print(json.dumps({k: rec[k] for k in ('prompt_tokens', 'load_s', 'generate_s', 'first_token_s', 'first_answer_s', 'generation_tokens', 'finish_reason', 'decode_tps_after_first', 'tokens_sha256_12', 'usable_answer')}))


if __name__ == '__main__':
    main()
