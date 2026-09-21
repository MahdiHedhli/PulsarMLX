#!/usr/bin/env python3
"""Synthetic HF-named checkpoint for the graph-11 stack fixture, frozen with the reference's expected parameters and a prospective matrix."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from scripts.research.glm53_flash.decoder_stack_sanitize import oracle  # noqa: E402

STACK_FIXTURE = ROOT / 'fixtures/research/glm53-flash-decoder-stack-v1/fixtures.json'


def swap12(v):  # (C, K, 1) -> (C, 1, K)
    return [[[v[c][k][a] for k in range(len(v[c]))] for a in range(len(v[c][0]))] for c in range(len(v))]


def checkpoint_from(case):
    cfg = case['config']; D = cfg['hidden_size']; ones = [1.0] * D
    ck = []
    add = lambda k, v, dt='float32': ck.append({'key': k, 'value': v, 'dtype': dt})
    add('model.embed_tokens.weight', case['embedding']); add('model.norm.weight', case['norm_weight']); add('lm_head.weight', case['lm_head'])
    for l, spec in ((0, case['layer0']), (1, case['layer1'])):
        p = f'model.layers.{l}'
        for hc, name in (('attn_hc', 'hc_attn'), ('ffn_hc', 'hc_ffn')):
            for q in ('fn', 'base', 'scale'):
                add(f'{p}.{name}_{q}', spec[hc][q])
        add(f'{p}.input_layernorm.weight', ones); add(f'{p}.post_attention_layernorm.weight', ones)
    # layer 0: linear attention + dense MLP
    lp = case['layer0']['linear_parameters']; p = 'model.layers.0'
    fused = lp['conv1d.weight']; Q = len(fused) // 3
    for i, c in enumerate('qkv'):
        add(f'{p}.self_attn.{c}_conv1d.weight', swap12(fused[i * Q:(i + 1) * Q]))
    for name in ('q_proj.weight', 'k_proj.weight', 'v_proj.weight', 'b_proj.weight', 'g_a_proj.weight', 'g_b_proj.weight', 'o_norm.weight', 'o_proj.weight'):
        add(f'{p}.self_attn.{name}', lp[name])
    add(f'{p}.self_attn.A_log', lp['forget_gate.A_log'], 'bfloat16'); add(f'{p}.self_attn.dt_bias', lp['forget_gate.dt_bias'], 'bfloat16')
    add(f'{p}.self_attn.f_a_proj.weight', lp['forget_gate.f_a_proj.weight']); add(f'{p}.self_attn.f_b_proj.weight', lp['forget_gate.f_b_proj.weight'])
    for q in ('gate', 'up', 'down'):
        add(f'{p}.mlp.{q}_proj.weight', case['layer0']['ffn'][q])
    # layer 1: sparse attention + MoE
    sw, ix, moe = case['layer1']['sparse']['weights'], case['layer1']['sparse']['indexer'], case['layer1']['moe']; p = 'model.layers.1'
    for name in ('q_a_proj', 'q_a_layernorm', 'q_b_proj', 'kv_a_proj_with_mqa', 'kv_a_layernorm', 'o_proj'):
        add(f'{p}.self_attn.{name}.weight', sw[name])
    # kv_b_proj rows per head: [dq rows of embed_q[h]^T ; dv rows of unembed_out[h]]
    kv_b = []
    for h in range(cfg['num_attention_heads']):
        eq = sw['embed_q'][h]  # [kvr][dq]
        kv_b.extend([[eq[r][d] for r in range(len(eq))] for d in range(len(eq[0]))]); kv_b.extend(sw['unembed_out'][h])
    add(f'{p}.self_attn.kv_b_proj.weight', kv_b)
    add(f'{p}.self_attn.indexer.wq_b.weight', ix['wq_b']); add(f'{p}.self_attn.indexer.wk.weight', ix['wk'])
    add(f'{p}.self_attn.indexer.k_norm.weight', ix['k_norm_weight']); add(f'{p}.self_attn.indexer.k_norm.bias', ix['k_norm_bias'])
    add(f'{p}.self_attn.indexer.weights_proj.weight', ix['weights_proj'])
    add(f'{p}.self_attn.indexer.index_kpool_compress_ape', ix['compress_ape']); add(f'{p}.self_attn.indexer.index_kpool_compress_gate', ix['compress_gate'])
    for e in range(cfg['n_routed_experts']):
        for q in ('gate', 'up', 'down'):
            add(f'{p}.mlp.experts.{e}.{q}_proj.weight', moe['experts'][q][e])
    add(f'{p}.mlp.gate.weight', moe['gate_weight']); add(f'{p}.mlp.gate.e_score_correction_bias', moe['gate_bias'])
    for q in ('gate', 'up', 'down'):
        add(f'{p}.mlp.shared_experts.{q}_proj.weight', moe['shared'][q])
    # MTP layer (index == num_hidden_layers) and an 'mtp.' key: both must be dropped
    add('model.layers.2.self_attn.q_proj.weight', lp['q_proj.weight']); add('model.layers.2.mlp.gate_proj.weight', case['layer0']['ffn']['gate'])
    add('model.mtp.embed_tokens.weight', case['embedding'])
    return ck


def main(out_path):
    stack = json.loads(STACK_FIXTURE.read_bytes()); base = stack['cases'][0]
    ck = checkpoint_from(base)
    expected = oracle.run(ck, base['config'])
    expected['logits'] = stack['expected'][base['fixture_id']]['logits']
    assert len(expected['parameters']) == 58, len(expected['parameters'])
    variants = {
        'mtp-filter-removed': ("    dropped = [k for k in w if 'mtp.' in k]\n    w = {k: v for k, v in w.items() if 'mtp.' not in k}", "    dropped = []"),
        'hc-rename-collision': ("nk = k.replace('.hc_attn_', '.attn_hc.').replace('.hc_ffn_', '.ffn_hc.')", "nk = k.replace('.hc_attn_', '.ffn_hc.').replace('.hc_ffn_', '.ffn_hc.')"),
        'conv-fusion-order-reversed': ("'value': parts['q']['value'] + parts['k']['value'] + parts['v']['value']", "'value': parts['v']['value'] + parts['k']['value'] + parts['q']['value']"),
        'conv-axis-move-omitted': ("            value = _moveaxis_2_to_1(value)", "            value = value"),
        'fp32-cast-omitted': ("        if k.endswith(FP32_SUFFIXES) and dtype != 'float32':\n            dtype = 'float32'", "        pass"),
        'forget-gate-move-omitted': ("                nk = nk[:-len(fp)] + 'forget_gate.' + fp; break", "                break"),
        'kv-b-split-not-transposed': ("wk = [[[heads[h][d][r] for d in range(dq)] for r in range(len(rows[0]))] for h in range(H)]", "wk = [[heads[h][d] for d in range(dq)] for h in range(H)]"),
        'experts-stack-order-reversed': ("joined = [w.pop(f'{prefix}.mlp.experts.{e}.{m}.{kind}') for e in range(cfg['n_routed_experts'])]", "joined = [w.pop(f'{prefix}.mlp.experts.{e}.{m}.{kind}') for e in reversed(range(cfg['n_routed_experts']))]"),
    }
    text = Path(oracle.__file__).read_text()
    predicted = {}
    def shape(v):
        return [len(v)] + shape(v[0]) if isinstance(v, list) else []
    def flat(v):
        return [x for y in v for x in flat(y)] if isinstance(v, list) else [v]
    for label, (before, after) in variants.items():
        assert text.count(before) == 1, label
        ns = {'__name__': 'variant_' + label}; exec(compile(text.replace(before, after), 'oracle-variant:' + label, 'exec'), ns)
        v = ns['run'](ck, base['config'])['parameters']
        if set(v) != set(expected['parameters']):
            predicted[label] = ('KILL', 'structural:keys:' + ','.join(sorted(set(v) ^ set(expected['parameters']))[:4]))
        elif any(shape(v[k]['value']) != shape(expected['parameters'][k]['value']) for k in v):
            predicted[label] = ('KILL', 'structural:shape:' + ','.join(k for k in v if shape(v[k]['value']) != shape(expected['parameters'][k]['value']))[:120])
        elif any(v[k]['dtype'] != expected['parameters'][k]['dtype'] for k in v):
            predicted[label] = ('KILL', 'structural:dtype:' + ','.join(k for k in v if v[k]['dtype'] != expected['parameters'][k]['dtype'])[:120])
        else:
            err = max(abs(a - b) for k in v for a, b in zip(flat(v[k]['value']), flat(expected['parameters'][k]['value'])))
            predicted[label] = ('KILL' if err >= 1e-3 else 'INACTIVE' if err <= 1e-4 else 'WEAK_STRUCTURAL', err)
    matrix = {'schema': 'flash-sanitize-expected-kill-matrix/1', 'frozen_before_tests': True, 'prospective_from_oracle_variants': True,
              'fixtures': ['stack-sanitize-hf-naming'], 'kill_margin_factor': 10,
              'cell_scope': 'a structural failure (key set, shape, dtype, strict-load rejection) or a parameter/logits value error',
              'matrix': {k: [v[0]] for k, v in predicted.items()}, 'predicted_oracle_variant_error': {k: [v[1]] for k, v in predicted.items()},
              'oracle_variants': {k: {'before': b, 'after': a} for k, (b, a) in variants.items()}, 'needle_counts': {k: 1 for k in variants}}
    doc = {'schema': 'flash-sanitize-fixtures/1', 'oracle': 'scripts/research/glm53_flash/decoder_stack_sanitize/oracle.py',
           'derived_from': {'fixture': 'fixtures/research/glm53-flash-decoder-stack-v1/fixtures.json', 'case': base['fixture_id']},
           'naming': 'pipenetwork glm5_next.py Model.sanitize output for the language model: model.language_model.X -> X; lm_head.X kept',
           'tolerances': {'logits': 1e-4, 'parameters': 0.0},
           'cases': [{'fixture_id': 'stack-sanitize-hf-naming', 'config': base['config'], 'ids': base['ids'], 'checkpoint': ck}],
           'expected': {'stack-sanitize-hf-naming': expected}, 'expected_kill_matrix': matrix}
    Path(out_path).write_text(json.dumps(doc, indent=1, sort_keys=True) + '\n')
    print('checkpoint keys', len(ck), 'parameters', len(expected['parameters']), 'dropped', expected['dropped_keys'])
    for k, v in predicted.items():
        print(f'  {k:32s} {v[0]:9s} {v[1] if isinstance(v[1], str) else round(v[1], 5)}')


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else ROOT / 'fixtures/research/glm53-flash-decoder-stack-sanitize-v1/fixtures.json')
