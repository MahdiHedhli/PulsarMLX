#!/usr/bin/env python3
"""Teacher-forced mean NLL per token of a fixed text under a resident build (graph 27): a comparative quality indicator
between pruned builds (lower is closer to the text's distribution), not a benchmark. One model per process."""
import argparse, json, os, time
TEXT = ("Mixture-of-experts language models replace a single dense feed-forward block with many smaller expert networks and a "
        "router that sends each token to a few of them. Because only the selected experts run, the model can hold far more "
        "parameters than it uses per token, which is why a 320-billion-parameter model can decode with the compute of an "
        "18-billion-parameter one. The cost moves from arithmetic to memory: every selected expert's weights must be read "
        "for every token, so decoding speed is bounded by how fast those weights can be streamed. On a workstation with unified "
        "memory the resident weights stream at hundreds of gigabytes per second, but a model larger than memory must page "
        "experts from storage, and a solid-state drive delivers a small fraction of that bandwidth. Two strategies follow. "
        "The first keeps the most frequently routed experts resident and pages the rest, betting on routing skew; its speed "
        "depends on the hit rate and on how cheaply a miss can be read. The second prunes experts that a calibration set "
        "rarely uses, shrinking the model until it fits; its cost is a change in the model's behaviour, which must be measured "
        "rather than assumed. In practice both are used together: a pruned build for interactive use, and a paged unpruned "
        "build when fidelity matters more than latency. The engineering questions are then concrete: how many kernel launches "
        "a decode step needs, whether the operating system keeps the weights resident, how the page cache competes with the "
        "expert store, and how a speculative draft head changes the arithmetic of a step. Each of these has a number, and each "
        "number was measured on the same machine before any conclusion was written down.")
ap = argparse.ArgumentParser(); ap.add_argument('--model', required=True, help='resident build dir, or with --offload the repack dir'); ap.add_argument('--log', required=True); ap.add_argument('--no-wire', action='store_true')
ap.add_argument('--lazy', action='store_true', help='resident: do not materialize the weights before the first forward (the forward wires them layer by layer)')
ap.add_argument('--offload', action='store_true', help='paged path (slot store) for builds that do not fit resident'); ap.add_argument('--expert-cache-gb', type=float, default=70.0)
args = ap.parse_args()
import mlx.core as mx, sys
if args.offload:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from run_offload import load_offloaded
    t0 = time.time(); model, processor, _cfg, _store, _eager = load_offloaded(args.model, args.expert_cache_gb, store_policy='slot', warm_start=False); load_s = time.time() - t0
else:
    from glm53_flash_mlx.load import load
    if not args.no_wire:
        mx.set_wired_limit(int(mx.device_info()['max_recommended_working_set_size']))
    t0 = time.time(); model, processor = load(args.model, lazy=args.lazy); load_s = time.time() - t0
tok = processor.tokenizer; ids = tok.encode(TEXT)
x = mx.array([ids]); cache = model.language_model.make_cache()
t1 = time.time(); out = model.language_model(x, cache=cache); logits = getattr(out, 'logits', out).astype(mx.float32)
logp = logits[0, :-1] - mx.logsumexp(logits[0, :-1], axis=-1, keepdims=True)
tgt = mx.array(ids[1:]); nll = -mx.take_along_axis(logp, tgt[:, None], axis=-1)[:, 0]; mx.eval(nll); dt = time.time() - t1
top1 = mx.argmax(logits[0, :-1], axis=-1) == tgt; mx.eval(top1)
rec = {'model': os.path.basename(args.model.rstrip('/')), 'path': 'offload' if args.offload else ('resident-lazy' if args.lazy else 'resident'), 'n_tokens': len(ids) - 1, 'mean_nll': float(nll.mean()), 'ppl': float(mx.exp(nll.mean())), 'top1_acc': float(top1.astype(mx.float32).mean()),
       'load_seconds': round(load_s, 1), 'forward_seconds': round(dt, 2), 'peak_memory_gb': round(mx.get_peak_memory() / 1e9, 1), 'reap': json.load(open(os.path.join(args.model, 'config.json'))).get('reap')}
json.dump(rec, open(args.log, 'w'), indent=1); print(json.dumps(rec))
