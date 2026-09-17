#!/usr/bin/env python3
"""GLM-5.3-Flash dogfood entrypoint, fully resident: a build that fits unified memory (e.g. pipenetwork's REAP50,
144 of 288 experts, 96.3 GB) loaded through the pinned pipenetwork loader with every weight materialized before the
first token, no expert offload, the decoder layers on their compiled FFN path.

NOT part of the successor research harness. Steps:
  1. glm53_flash_mlx.load.load(path, lazy=False): sanitize -> nn.quantize per the config's quantization map ->
     strict load_weights (the shape check for a pruned expert count: SwitchGLU, the router and
     e_score_correction_bias are sized from text_config.n_routed_experts) -> mx.eval(parameters);
  2. wire the process's Metal buffers up to the device's max recommended working set (mx.set_wired_limit), as
     mlx-lm does for large models. FINDING (graph 23, Studio, 96 GB resident + ~20 GB of other apps): unwired,
     the OS evicted the experts that decode does not touch and every prefill pass paged them back at ~30 GB/s
     (~70 ms per MoE layer, flat in T: 2.2 / 17 / 58 tok/s at 16 / 64 / 256 tokens); wired: 59 / 98 / 187 tok/s.
     --no-wire reproduces the unwired behaviour. Making the wired set resident is paid once per process (the OS
     pages other applications out: ~27 s on the Studio with ~20 GB of them), so the first prompt of a fresh process
     is slow; --warmup runs a short generate first and records it, and the measured run then reflects a long-lived
     server process;
  3. mlx_vlm.generate with a bounded prefill chunk; log load time, tokens/s, peak memory, device info, the
     checkpoint's revision (download-record.json) and its `reap` block when present.

Pins: mlx-vlm Blaizzy/mlx-vlm@8d79dbcf82a7885ddfc56fb4a55440fa9c5dfb90; glm5_next PipeNetwork/glm53-flash-mlx@a61a7c7d2fbdf3d218a9909365a24bd794f3a247
(run with PYTHONPATH pointing at the pinned pipenetwork checkout).
"""
import argparse
import json
import os
import sys
import time


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--model', required=True, help='converted build directory (config.json + *.safetensors)')
    ap.add_argument('--prompt', default='What is the capital of France? Answer in one short sentence.')
    ap.add_argument('--max-tokens', type=int, default=96)
    ap.add_argument('--prefill-step-size', type=int, default=256)
    ap.add_argument('--no-wire', action='store_true', help='do not wire the Metal buffers (default: wire up to max_recommended_working_set_size)')
    ap.add_argument('--warmup', type=int, default=0, help='tokens of a recorded warm-up generate before the measured run (0 = none)')
    ap.add_argument('--lazy', action='store_true', help='do not materialize the weights before the first token (default: materialize)')
    ap.add_argument('--log', default='dogfood-resident.json')
    args = ap.parse_args()

    import mlx.core as mx
    from glm53_flash_mlx.load import load
    from mlx_vlm import generate
    from mlx_vlm.prompt_utils import apply_chat_template

    wired_limit = None
    if not args.no_wire:
        wired_limit = int(mx.device_info()['max_recommended_working_set_size'])
        mx.set_wired_limit(wired_limit)
    config = json.load(open(os.path.join(args.model, 'config.json')))
    record_path = os.path.join(args.model, 'download-record.json')
    download = json.load(open(record_path)) if os.path.exists(record_path) else None
    t0 = time.time()
    model, processor = load(args.model, lazy=args.lazy)
    t_load = time.time() - t0
    n_params = sum(v.size for _, v in __import__('mlx.utils', fromlist=['tree_flatten']).tree_flatten(model.parameters()))
    print(f'loaded in {t_load:.1f}s; experts per MoE layer: {config["text_config"].get("n_routed_experts")}; active memory {mx.get_active_memory() / 1e9:.1f} GB', flush=True)

    prompt = apply_chat_template(processor, config, args.prompt, num_images=0)
    warm = None
    if args.warmup:
        tw = time.time()
        w = generate(model, processor, prompt, max_tokens=args.warmup, verbose=False, prefill_step_size=args.prefill_step_size, temperature=0.0)
        warm = {'tokens': args.warmup, 'seconds': round(time.time() - tw, 1), 'prompt_tps': getattr(w, 'prompt_tps', None), 'generation_tps': getattr(w, 'generation_tps', None)}
        print(f'warm-up: {warm}', flush=True)
    t1 = time.time()
    out = generate(model, processor, prompt, max_tokens=args.max_tokens, verbose=True, prefill_step_size=args.prefill_step_size, temperature=0.0)
    t_gen = time.time() - t1
    text = out.text if hasattr(out, 'text') else str(out)
    record = {'model': args.model, 'download': download, 'reap': config.get('reap'), 'n_routed_experts': config['text_config'].get('n_routed_experts'),
              'lazy': args.lazy, 'wired_limit_bytes': wired_limit, 'warmup': warm, 'load_seconds': round(t_load, 1), 'generate_seconds': round(t_gen, 1), 'max_tokens': args.max_tokens,
              'prefill_step_size': args.prefill_step_size, 'parameter_elements': int(n_params), 'peak_memory_bytes': int(mx.get_peak_memory()),
              'device_info': {k: v for k, v in mx.device_info().items() if isinstance(v, (int, str))}, 'prompt': args.prompt, 'text': text,
              'generation_stats': {k: getattr(out, k) for k in ('prompt_tokens', 'generation_tokens', 'prompt_tps', 'generation_tps', 'peak_memory') if hasattr(out, k)},
              'pins': {'mlx-vlm': '8d79dbcf82a7885ddfc56fb4a55440fa9c5dfb90', 'glm5_next': 'a61a7c7d2fbdf3d218a9909365a24bd794f3a247'}}
    json.dump(record, open(args.log, 'w'), indent=2)
    print(json.dumps({k: v for k, v in record.items() if k not in ('text', 'prompt')}, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
