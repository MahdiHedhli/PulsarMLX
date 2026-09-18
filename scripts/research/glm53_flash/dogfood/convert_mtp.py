#!/usr/bin/env python3
"""Convert the original checkpoint's MTP layer (layer num_hidden_layers) for the pinned runtime (graph 25).

Reads only the tensors `model.language_model.layers.<N>.*` from the original FP8 shards, dequantizes the 128-block
FP8 pairs exactly as upstream's sanitize does (mx.from_fp8 * weight_scale_inv), stacks the routed experts into
switch_mlp tensors, splits kv_b_proj into embed_q / unembed_out as the runtime's sparse attention expects, quantizes
with the target build's scheme (experts 4-bit g64, everything else with a to_quantized 8-bit g64) and strict-loads
into Glm5NextMTP before saving <out>/model.safetensors + config.json + convert-record.json.
"""
import argparse
import glob
import json
import os
import sys
import time


def dequant(mx, weight, scale_inv):
    weight = mx.from_fp8(weight, dtype=mx.bfloat16)
    bs = 128
    m, n = weight.shape
    pad_bottom, pad_side = (-m) % bs, (-n) % bs
    weight = mx.pad(weight, ((0, pad_bottom), (0, pad_side)))
    weight = weight.reshape(((m + pad_bottom) // bs, bs, (n + pad_side) // bs, bs))
    weight = (weight * scale_inv[:, None, :, None]).reshape(m + pad_bottom, n + pad_side)
    return weight[:m, :n].astype(mx.bfloat16)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--original', required=True, help='directory with the original shards + index + config')
    ap.add_argument('--target', required=True, help='the converted build whose config/quantization scheme to mirror')
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    import mlx.core as mx
    import mlx.nn as nn
    from mlx.utils import tree_flatten
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from glm53_flash_mlx.load import make_config
    from mtp_module import Glm5NextMTP

    t0 = time.time()
    target_cfg = json.load(open(os.path.join(args.target, 'config.json')))
    tc = target_cfg['text_config']; N = int(tc['num_hidden_layers'])
    prefix = f'model.language_model.layers.{N}.'
    index = json.load(open(os.path.join(args.original, 'model.safetensors.index.json')))['weight_map']
    shards = sorted({v for k, v in index.items() if k.startswith(prefix)})
    raw = {}
    for s in shards:
        d = mx.load(os.path.join(args.original, s))
        raw.update({k[len(prefix):]: v for k, v in d.items() if k.startswith(prefix)})
    print(f'{len(raw)} tensors of layer {N} from {shards}', flush=True)
    # FP8 -> bf16
    w = {}
    for k, v in raw.items():
        if k.endswith('weight_scale_inv'):
            continue
        si = raw.get(k + '_scale_inv')
        w[k] = dequant(mx, v, si) if si is not None else v
    # experts -> switch_mlp
    E = int(tc['n_routed_experts'])   # the ORIGINAL expert count for the MTP layer (it was not pruned)
    E = max(int(k.split('.')[2]) for k in w if k.startswith('mlp.experts.')) + 1
    for proj in ('gate_proj', 'up_proj', 'down_proj'):
        w[f'mlp.switch_mlp.{proj}.weight'] = mx.stack([w.pop(f'mlp.experts.{e}.{proj}.weight') for e in range(E)])
    # kv_b_proj -> embed_q / unembed_out (upstream's unquantized branch)
    v = w.pop('self_attn.kv_b_proj.weight'); heads = int(tc['num_attention_heads']); nope = int(tc['qk_nope_head_dim']); vd = int(tc['v_head_dim'])
    v = v.reshape(heads, nope + vd, -1)
    w['self_attn.embed_q.weight'] = mx.contiguous(v[:, :nope, :].swapaxes(-1, -2))
    w['self_attn.unembed_out.weight'] = mx.contiguous(v[:, nope:, :])
    w['shared_head_norm.weight'] = w.pop('shared_head.norm.weight')
    mx.eval(list(w.values()))
    # module with the MTP layer's expert count, quantized like the target build
    mtp_tc = dict(tc); mtp_tc['n_routed_experts'] = E
    config = make_config({**target_cfg, 'text_config': mtp_tc})
    module = Glm5NextMTP(config.text_config)
    q = target_cfg['quantization']
    def predicate(path, m):
        if not hasattr(m, 'to_quantized'):
            return False
        return {'group_size': q['group_size'], 'bits': q['bits']} if 'switch_mlp' in path else {'group_size': 64, 'bits': 8}
    nn.quantize(module, group_size=q['group_size'], bits=q['bits'], class_predicate=predicate)
    # quantize the bf16 tensors to match: load through the module's quantized parameters by quantizing each Linear/SwitchLinear weight
    params = dict(tree_flatten(module.parameters()))
    weights = {}
    for name, arr in w.items():
        if name in params and name.endswith('.weight') and (name[:-7] + '.scales') in params:
            spec = predicate(name[:-7], None) or {}
            bits, gs = ({'group_size': q['group_size'], 'bits': q['bits']} if 'switch_mlp' in name else {'group_size': 64, 'bits': 8}).values()
            gs, bits = (q['group_size'], q['bits']) if 'switch_mlp' in name else (64, 8)
            qw, sc, bi = mx.quantize(arr, group_size=gs, bits=bits)
            weights[name] = qw; weights[name[:-7] + '.scales'] = sc; weights[name[:-7] + '.biases'] = bi
        else:
            weights[name] = arr
    missing = sorted(set(params) - set(weights)); extra = sorted(set(weights) - set(params))
    print('missing', missing[:10], 'extra', extra[:10], flush=True)
    module.load_weights(list(weights.items()), strict=True)
    mx.eval(module.parameters())
    os.makedirs(args.out, exist_ok=True)
    flat = dict(tree_flatten(module.parameters()))
    mx.save_safetensors(os.path.join(args.out, 'model.safetensors'), flat, metadata={'format': 'mlx'})
    json.dump({**target_cfg, 'text_config': mtp_tc, 'mtp': {'source_repo': 'zai-org/GLM-5.3-Flash', 'source_layer': N, 'num_experts': E}}, open(os.path.join(args.out, 'config.json'), 'w'), indent=1)
    rec = json.load(open(os.path.join(args.original, 'download-record.json'))) if os.path.exists(os.path.join(args.original, 'download-record.json')) else None
    total = sum(v.nbytes for v in flat.values())
    json.dump({'source': rec, 'layer': N, 'num_experts': E, 'tensors': len(flat), 'bytes': total, 'seconds': round(time.time() - t0, 1),
               'scheme': 'switch_mlp 4-bit g64; other to_quantized modules 8-bit g64'}, open(os.path.join(args.out, 'convert-record.json'), 'w'), indent=1)
    print(f'saved {len(flat)} tensors, {total / 1e9:.2f} GB, in {time.time() - t0:.0f}s', flush=True)


if __name__ == '__main__':
    main()
