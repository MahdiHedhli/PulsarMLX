#!/usr/bin/env python3
"""GLM-5.3-Flash dogfood entrypoint: unpruned mixed-4/8 build, cold experts on NVMe, hot experts in memory.

NOT part of the successor research harness and NOT yet run on real weights.
It carries the qualified configuration from graphs 15/18/19:

  * repack() the converted build into an offload directory (once; ~1x the build size on disk);
  * load through mlx-vlm at the pinned commit (offload_index.json is auto-detected and patch_model applied);
  * FINDING (graph 19): OffloadedSwitchGLU host-evaluates routing indices, which mx.compile forbids; every
    patched decoder layer must run its FFN eagerly -> set layer.compile_ffn = False after loading;
  * generate with a bounded prefill chunk (prefill_step_size) so the lazy graph never pins every expert;
  * log tokens/s and the ExpertStore statistics (hits, misses, evictions, resident set) per run.

Pins (install from these exact revisions; both retained under evidence/model-metadata):
  mlx-vlm      Blaizzy/mlx-vlm@8d79dbcf82a7885ddfc56fb4a55440fa9c5dfb90
  glm5_next    PipeNetwork/glm53-flash-mlx@a61a7c7d2fbdf3d218a9909365a24bd794f3a247
Operator-side settings (not done by this script): on a 128 GB Mac, raising the GPU wired limit
(sysctl iogpu.wired_limit_mb) lets the auto budget grow; the script accepts an explicit --expert-cache-gb.
"""
import argparse
import json
import os
import sys
import time


def expert_budget_gb(total_ram_gb: float, resident_gb: float = 10.0, kv_reserve_gb: float = 8.0, recommended_fraction: float = 0.75) -> float:
    """The store's own rule (0.8 x recommended working set - resident - KV reserve), with macOS's default
    recommended working set taken as ~75% of unified memory. Returned in GB; clamp at 0."""
    return max(0.0, 0.8 * recommended_fraction * total_ram_gb - resident_gb - kv_reserve_gb)


def apply_eager_ffn_on_patched_layers(language_model) -> int:
    """Graph-19 remedy: OffloadedSwitchGLU cannot run inside the layer's compiled FFN block."""
    patched = 0
    for layer in language_model.model.layers:
        switch = getattr(getattr(layer, 'mlp', None), 'switch_mlp', None)
        if switch is not None and type(switch).__name__ == 'OffloadedSwitchGLU':
            layer.compile_ffn = False
            layer._ffn_c = None
            patched += 1
    return patched


def find_store(language_model):
    for layer in language_model.model.layers:
        switch = getattr(getattr(layer, 'mlp', None), 'switch_mlp', None)
        if switch is not None and hasattr(switch, 'store'):
            return switch.store
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--build', required=True, help='converted mixed-4/8 build directory (pipenetwork/GLM-5.3-Flash-MLX-mixed-4_8bit)')
    ap.add_argument('--offload', required=True, help='offload directory (created by repack on first use)')
    ap.add_argument('--expert-cache-gb', type=float, default=None, help='explicit hot-expert byte budget; default: the store auto budget')
    ap.add_argument('--prompt', default='Explain, in three sentences, why mixture-of-experts models can stream experts from disk.')
    ap.add_argument('--max-tokens', type=int, default=64)
    ap.add_argument('--prefill-step-size', type=int, default=256)
    ap.add_argument('--log', default='dogfood-run.json')
    args = ap.parse_args()

    from mlx_vlm import generate, load
    from mlx_vlm.moe_offload import repack
    from mlx_vlm.prompt_utils import apply_chat_template
    import mlx.core as mx

    t0 = time.time()
    if not os.path.exists(os.path.join(args.offload, 'offload_index.json')):
        print('repack: this reads the whole build once and writes the offload directory', flush=True)
        repack(args.build, args.offload)
    t_repack = time.time() - t0

    kwargs = {}
    if args.expert_cache_gb is not None:
        kwargs['expert_cache_gb'] = args.expert_cache_gb
    t1 = time.time()
    model, processor = load(args.offload, **kwargs)
    t_load = time.time() - t1
    lm = model.language_model if hasattr(model, 'language_model') else model
    eager = apply_eager_ffn_on_patched_layers(lm)
    store = find_store(lm)
    print(f'loaded in {t_load:.1f}s; patched layers set to eager FFN: {eager}; store: {store.stats() if store else None}', flush=True)

    config = json.load(open(os.path.join(args.offload, 'config.json')))
    prompt = apply_chat_template(processor, config, args.prompt, num_images=0)
    t2 = time.time()
    out = generate(model, processor, prompt, max_tokens=args.max_tokens, verbose=True, prefill_step_size=args.prefill_step_size)
    t_gen = time.time() - t2
    text = out.text if hasattr(out, 'text') else str(out)
    record = {'build': args.build, 'offload': args.offload, 'expert_cache_gb': args.expert_cache_gb, 'repack_seconds': round(t_repack, 1),
              'load_seconds': round(t_load, 1), 'generate_seconds': round(t_gen, 1), 'max_tokens': args.max_tokens, 'prefill_step_size': args.prefill_step_size,
              'patched_layers_eager_ffn': eager, 'store_stats': store.stats() if store else None, 'peak_memory_bytes': int(mx.get_peak_memory()),
              'device_info': {k: v for k, v in mx.device_info().items() if isinstance(v, (int, str))}, 'prompt': args.prompt, 'text': text,
              'pins': {'mlx-vlm': '8d79dbcf82a7885ddfc56fb4a55440fa9c5dfb90', 'glm5_next': 'a61a7c7d2fbdf3d218a9909365a24bd794f3a247'}}
    json.dump(record, open(args.log, 'w'), indent=2)
    print(json.dumps({k: v for k, v in record.items() if k not in ('text', 'prompt')}, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
