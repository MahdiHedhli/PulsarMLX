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
ap.add_argument('--texts', default=None, help='JSON file {"passages": {name: text}}: one teacher-forced forward per passage; aggregate with standard errors (graph 28)')
ap.add_argument('--lazy', action='store_true', help='resident: do not materialize the weights before the first forward (the forward wires them layer by layer)')
ap.add_argument('--offload', action='store_true', help='paged path (slot store) for builds that do not fit resident'); ap.add_argument('--expert-cache-gb', type=float, default=70.0)
ap.add_argument('--coalesce-gap', type=int, default=2, help='offload: merged-range gap (unpruned-fidelity G37)'); ap.add_argument('--store', default='slot', choices=('slot', 'lru'), help='offload: slot store or the upstream LRU expert path (correctness comparator)')
ap.add_argument('--write-mode', default='stack', choices=('stack', 'per-expert')); ap.add_argument('--logits-out', default=None, help='save the float32 logits of every position of TEXT (or of each --texts passage, suffixed) as .npy for bit-identity comparison')
args = ap.parse_args()
import mlx.core as mx, sys
if args.offload:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from run_offload import load_offloaded
    t0 = time.time(); model, processor, _cfg, _store, _eager = load_offloaded(args.model, args.expert_cache_gb, store_policy=args.store, warm_start=False, coalesce_gap_experts=args.coalesce_gap, wire=not args.no_wire, write_mode=args.write_mode); load_s = time.time() - t0
else:
    from glm53_flash_mlx.load import load
    if not args.no_wire:
        mx.set_wired_limit(int(mx.device_info()['max_recommended_working_set_size']))
    t0 = time.time(); model, processor = load(args.model, lazy=args.lazy); load_s = time.time() - t0
tok = processor.tokenizer
def teacher_forced(text, logits_path=None):
    ids = tok.encode(text); x = mx.array([ids]); cache = model.language_model.make_cache()
    t1 = time.time(); out = model.language_model(x, cache=cache); logits = getattr(out, 'logits', out).astype(mx.float32)
    if logits_path:
        import numpy as np
        mx.eval(logits); np.save(logits_path, np.asarray(logits[0]))
    logp = logits[0, :-1] - mx.logsumexp(logits[0, :-1], axis=-1, keepdims=True)
    tgt = mx.array(ids[1:]); nll = -mx.take_along_axis(logp, tgt[:, None], axis=-1)[:, 0]; mx.eval(nll); dt = time.time() - t1
    top1 = mx.argmax(logits[0, :-1], axis=-1) == tgt; mx.eval(top1)
    return {'n_tokens': len(ids) - 1, 'mean_nll': float(nll.mean()), 'ppl': float(mx.exp(nll.mean())), 'top1_acc': float(top1.astype(mx.float32).mean()), 'forward_seconds': round(dt, 2),
            'nll_sum': float(nll.sum()), 'nll_sq_sum': float((nll * nll).sum())}
base = {'model': os.path.basename(args.model.rstrip('/')), 'path': 'offload' if args.offload else ('resident-lazy' if args.lazy else 'resident'), 'load_seconds': round(load_s, 1), 'store': args.store if args.offload else None, 'coalesce_gap': args.coalesce_gap if args.offload else None,
        'store_stats': (_store.stats() if args.offload and hasattr(_store, 'stats') else None),
        'reap': json.load(open(os.path.join(args.model, 'config.json'))).get('reap')}
if args.texts:
    import hashlib, math
    raw = open(args.texts, 'rb').read(); passages = json.loads(raw)['passages']
    per = {}
    for name, text in passages.items():
        per[name] = teacher_forced(text, (args.logits_out.replace('.npy', '') + '-' + name + '.npy') if args.logits_out else None); print(name, json.dumps({k: per[name][k] for k in ('n_tokens', 'mean_nll', 'ppl', 'top1_acc', 'forward_seconds')}), flush=True)
    n = sum(r['n_tokens'] for r in per.values()); tot = sum(r['nll_sum'] for r in per.values()); means = [r['mean_nll'] for r in per.values()]
    m = len(means); mean_of_means = sum(means) / m; se_passages = (sum((v - mean_of_means) ** 2 for v in means) / (m - 1)) ** 0.5 / m ** 0.5
    token_var = sum(r['nll_sq_sum'] for r in per.values()) / n - (tot / n) ** 2
    rec = {**base, 'texts_sha256': hashlib.sha256(raw).hexdigest(), 'passages': per, 'aggregate': {'n_passages': m, 'n_tokens': n, 'token_weighted_mean_nll': tot / n, 'token_weighted_ppl': math.exp(tot / n),
           'mean_of_passage_means': mean_of_means, 'se_across_passages': se_passages, 'se_per_token_iid': (max(token_var, 0.0) / n) ** 0.5}, 'peak_memory_gb': round(mx.get_peak_memory() / 1e9, 1)}
else:
    rec = {**base, **teacher_forced(TEXT, args.logits_out), 'peak_memory_gb': round(mx.get_peak_memory() / 1e9, 1)}
if args.offload and hasattr(_store, 'stats'):
    rec['store_stats_final'] = _store.stats()
json.dump(rec, open(args.log, 'w'), indent=1); print(json.dumps({k: v for k, v in rec.items() if k not in ('passages', 'store_stats', 'store_stats_final')}))
