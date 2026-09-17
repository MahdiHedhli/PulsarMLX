#!/usr/bin/env python3
"""GLM-5.3-Flash dogfood entrypoint: unpruned mixed-4/8 build, cold experts on NVMe, hot experts in memory.

NOT part of the successor research harness. It replays the pinned pipenetwork load() (its custom model type is
not resolvable by mlx_vlm.load, so mlx-vlm's automatic offload patching does not apply) on the repack output:

  1. mlx_vlm.moe_offload.repack(build, offload) once: experts/layer_NNNN.safetensors + resident-*.safetensors + config;
  2. Model(config) from the pinned glm5_next; the resident shards are mmapped and passed through Model.sanitize;
  3. nn.quantize with the config's quantization map exactly as pipenetwork's load() does (per-path entries win; a module
     with to_quantized quantizes iff its scales are present in the resident weights -> routed experts stay unquantized
     modules and are then swapped);
  4. patch_model(model, offload, expert_cache_gb) swaps every switch layer for an OffloadedSwitchGLU over an ExpertStore;
  5. FINDING (graph 19): OffloadedSwitchGLU host-evaluates routing indices, which mx.compile forbids; the decoder layer
     compiles its FFN at B=1,S=1 -> patched layers run the eager FFN path (compile_ffn = False);
  6. strict load of the resident weights (the patched model's parameters are exactly the resident set);
  7. generate with a bounded prefill chunk; log tokens/s, peak memory and the ExpertStore statistics.

Pins: mlx-vlm Blaizzy/mlx-vlm@8d79dbcf82a7885ddfc56fb4a55440fa9c5dfb90; glm5_next PipeNetwork/glm53-flash-mlx@a61a7c7d2fbdf3d218a9909365a24bd794f3a247
(run with PYTHONPATH pointing at the pinned pipenetwork checkout).
"""
import argparse
import glob
import json
import os
import sys
import time


def expert_budget_gb(total_ram_gb: float, resident_gb: float = 10.0, kv_reserve_gb: float = 8.0, recommended_fraction: float = 0.75) -> float:
    """The store's rule (0.8 x recommended working set - resident - KV reserve), with macOS's default recommended
    working set taken as ~75% of unified memory. In GB, clamped at 0."""
    return max(0.0, 0.8 * recommended_fraction * total_ram_gb - resident_gb - kv_reserve_gb)


def apply_eager_ffn_on_patched_layers(language_model) -> int:
    """Graph-19 remedy: OffloadedSwitchGLU cannot run inside the layer's compiled FFN block."""
    patched = 0
    for layer in language_model.model.layers:
        switch = getattr(getattr(layer, 'mlp', None), 'switch_mlp', None)
        if switch is not None and type(switch).__name__ in ('OffloadedSwitchGLU', 'PulsarSwitchGLU'):
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


def load_offloaded(offload_dir: str, expert_cache_gb, lazy: bool = True, store_policy: str = 'lru', warm_start: bool = True, cache_clear_threshold_gb=2.0, read_workers: int = 8):
    """Pipenetwork's load_model() replayed on a repack output, with patch_model and the eager-FFN remedy."""
    import mlx.core as mx
    import mlx.nn as nn
    from glm53_flash_mlx.load import make_config
    from glm53_flash_mlx.glm5_next import Model
    from mlx_vlm.moe_offload import patch_model
    from mlx_vlm.utils import load_processor

    config = json.load(open(os.path.join(offload_dir, 'config.json')))
    model = Model(make_config(config))
    weights = {}
    for wf in sorted(glob.glob(os.path.join(offload_dir, 'resident-*.safetensors'))):
        weights.update(mx.load(wf))
    weights = model.sanitize(weights)
    quantization = config.get('quantization')
    if quantization is not None:
        def class_predicate(p, m):
            if p in quantization:
                return quantization[p]
            if not hasattr(m, 'to_quantized'):
                return False
            return f'{p}.scales' in weights
        nn.quantize(model, group_size=quantization['group_size'], bits=quantization['bits'], class_predicate=class_predicate)
    if store_policy == 'slot':
        # graph 24: stacked per-layer slots + gather_qmm over them (no per-expert loop, no bulk prefill bypass)
        from pulsar_slot_store import patch_model_slots
        store, patched = patch_model_slots(model, offload_dir, expert_cache_gb=expert_cache_gb, warm_start=warm_start, read_workers=read_workers)
    else:
        store = patch_model(model, offload_dir, expert_cache_gb=expert_cache_gb)
    if store_policy == 'pulsar':
        # PulsarMLX-native policy (graph 21): LFU with decay + persisted warm state, same interface and on-disk format
        from pulsar_expert_store import PulsarExpertStore
        threshold = None if cache_clear_threshold_gb is None else int(cache_clear_threshold_gb * (1 << 30))
        pstore = PulsarExpertStore(offload_dir, store._budget, 0, warm_start=warm_start, cache_clear_threshold_bytes=threshold)
        for layer in model.language_model.model.layers:
            switch = getattr(getattr(layer, 'mlp', None), 'switch_mlp', None)
            if switch is not None and hasattr(switch, 'store'):
                switch.store = pstore
        store = pstore
    eager = apply_eager_ffn_on_patched_layers(model.language_model)
    model.load_weights(list(weights.items()), strict=True)
    if not lazy:
        mx.eval(model.parameters())
    model.eval()
    from pathlib import Path
    processor = load_processor(Path(offload_dir), add_detokenizer=True)
    return model, processor, config, store, eager


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--build', required=True, help='converted mixed-4/8 build directory')
    ap.add_argument('--offload', required=True, help='offload directory (created by repack on first use)')
    ap.add_argument('--expert-cache-gb', type=float, default=None, help='hot-expert byte budget; default: the store auto budget')
    ap.add_argument('--prompt', default='Explain, in three sentences, why mixture-of-experts models can stream experts from disk.')
    ap.add_argument('--max-tokens', type=int, default=64)
    ap.add_argument('--prefill-step-size', type=int, default=256)
    ap.add_argument('--log', default='dogfood-run.json')
    ap.add_argument('--store', choices=('lru', 'pulsar', 'slot'), default='lru', help="'lru' = upstream ExpertStore; 'pulsar' = PulsarExpertStore (LFU with decay + warm state); 'slot' = PulsarSlotStore + PulsarSwitchGLU (graph 24: slots + gather_qmm)")
    ap.add_argument('--no-warm', action='store_true', help='pulsar: ignore a saved warm state (cold start)')
    ap.add_argument('--save-warm', action='store_true', help='pulsar: save the warm state after the run')
    ap.add_argument('--read-workers', type=int, default=8, help='slot: threads for cold expert reads')
    ap.add_argument('--cache-clear-threshold-gb', type=float, default=2.0, help='pulsar: clear the MLX allocator cache after an eviction batch only when it is at or above this (GiB); 0 = upstream behaviour (every batch); negative = never')
    args = ap.parse_args()

    import mlx.core as mx
    from mlx_vlm import generate
    from mlx_vlm.moe_offload import repack
    from mlx_vlm.prompt_utils import apply_chat_template

    t0 = time.time()
    if not os.path.exists(os.path.join(args.offload, 'offload_index.json')):
        print('repack: reads the whole build once and writes the offload directory', flush=True)
        repack(args.build, args.offload)
    t_repack = time.time() - t0

    t1 = time.time()
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    threshold_gb = None if args.cache_clear_threshold_gb < 0 else args.cache_clear_threshold_gb
    model, processor, config, store, eager = load_offloaded(args.offload, args.expert_cache_gb, store_policy=args.store, warm_start=not args.no_warm, cache_clear_threshold_gb=threshold_gb, read_workers=args.read_workers)
    t_load = time.time() - t1
    print(f'loaded in {t_load:.1f}s; patched layers on the eager FFN path: {eager}; store: {store.stats()}', flush=True)

    prompt = apply_chat_template(processor, config, args.prompt, num_images=0)
    t2 = time.time()
    out = generate(model, processor, prompt, max_tokens=args.max_tokens, verbose=True, prefill_step_size=args.prefill_step_size, temperature=0.0)
    t_gen = time.time() - t2
    text = out.text if hasattr(out, 'text') else str(out)
    warm_path = store.save_warm_state() if (args.store in ('pulsar', 'slot') and args.save_warm) else None
    record = {'build': args.build, 'offload': args.offload, 'store_policy': args.store, 'cache_clear_threshold_gb': threshold_gb, 'read_workers': args.read_workers, 'warm_state_saved': warm_path, 'expert_cache_gb': args.expert_cache_gb, 'repack_seconds': round(t_repack, 1),
              'load_seconds': round(t_load, 1), 'generate_seconds': round(t_gen, 1), 'max_tokens': args.max_tokens, 'prefill_step_size': args.prefill_step_size,
              'patched_layers_eager_ffn': eager, 'store_stats': store.stats(), 'peak_memory_bytes': int(mx.get_peak_memory()),
              'device_info': {k: v for k, v in mx.device_info().items() if isinstance(v, (int, str))}, 'prompt': args.prompt, 'text': text,
              'generation_stats': {k: getattr(out, k) for k in ('prompt_tokens', 'generation_tokens', 'prompt_tps', 'generation_tps', 'peak_memory') if hasattr(out, k)},
              'pins': {'mlx-vlm': '8d79dbcf82a7885ddfc56fb4a55440fa9c5dfb90', 'glm5_next': 'a61a7c7d2fbdf3d218a9909365a24bd794f3a247'}}
    json.dump(record, open(args.log, 'w'), indent=2)
    print(json.dumps({k: v for k, v in record.items() if k not in ('text', 'prompt')}, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
