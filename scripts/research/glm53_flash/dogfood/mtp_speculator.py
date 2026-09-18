"""Greedy MTP speculative decoding on the pinned runtime (graph 25).

  * target forward with the pre-final-norm hidden exposed: a mirror of Glm5NextModel.__call__ (embed, masks, the
    hc_mult broadcast, the layers, the stream mean) that also returns the mean before `norm`;
  * verification at T = k+1 tokens: the 11 DSA layers' KV caches and the MTP's own cache trim on rejection; the 34
    linear-attention layers only return their final recurrent state, so their forward is run through a verbatim
    copy of Glm5NextLinearAttention.__call__ that keeps the batched projections and, on a partial acceptance of n
    tokens, re-runs the delta rule over the accepted prefix from the pre-step state (one small kernel per layer) and
    restores the conv state from the retained conv input;
  * draft/verify loop ported from mlx-vlm's GlmMoeDsaMTPDraftModel (seed token, round accounting, trim) but greedy
    only; drafts come from the MTP layer fed with the target's hidden and the next token's embedding. The hidden
    handed to the MTP is the POST-final-norm hidden by default: measured first-draft acceptance on the Studio was
    0.767 / 0.691 / 0.916 (three prompts) against 0.747 / 0.674 / 0.871 with the pre-norm stream mean
    (`hidden_convention='pre-norm'` keeps the alternative).

Speculative output is equivalent to plain greedy decoding, not bit-identical: verification evaluates the target at a
different T, so logits differ at bf16-ulp level and near-ties can flip (the same caveat as the slot store).
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, List, Optional

import mlx.core as mx
import mlx.nn as nn

from glm53_flash_mlx.glm5_next.language import _l2norm, gated_delta_update
from mlx_vlm.models.base import create_attention_mask, create_ssm_mask
from mlx_vlm.models.cache import CacheList, KVCache


def linear_attention_forward(attn, inputs, mask, cache, capture: dict):
    """Verbatim Glm5NextLinearAttention.__call__ (pinned a61a7c7d) with the conv input and the delta-rule inputs
    captured so the state at any accepted position can be recomputed."""
    B, S, _ = inputs.shape
    if attn.fuse_in:
        q_o, k_o, v_o, fa_o, ga_o, b_o = attn._fused_in_proj(inputs)
        mixed = mx.concatenate([q_o, k_o, v_o], axis=-1)
    else:
        mixed = mx.concatenate([attn.q_proj(inputs), attn.k_proj(inputs), attn.v_proj(inputs)], axis=-1)
        fa_o = attn.forget_gate.f_a_proj(inputs)
        ga_o = attn.g_a_proj(inputs)
        b_o = attn.b_proj(inputs)
    if mask is not None and mask.dtype == mx.bool_:
        mixed = mx.where(mask[..., None], mixed, 0)
    if cache is not None and cache[0] is not None:
        conv_state = cache[0]
    else:
        conv_state = mx.zeros((B, attn.conv_kernel_size - 1, attn.conv_dim), dtype=inputs.dtype)
    conv_input = mx.concatenate([conv_state, mixed], axis=1)
    if cache is not None:
        cache[0] = mx.contiguous(conv_input[:, -(attn.conv_kernel_size - 1):, :])
    conv_out = nn.silu(attn.conv1d(conv_input))
    q, k, v = mx.split(conv_out, [attn.qkv_dim, 2 * attn.qkv_dim], axis=-1)
    q = q.reshape(B, S, attn.num_heads, attn.head_dim)
    k = k.reshape(B, S, attn.num_heads, attn.head_dim)
    v = v.reshape(B, S, attn.num_heads, attn.head_dim)
    fg = attn.forget_gate
    a = fg.f_b_proj(fa_o).reshape(B, S, attn.num_heads, attn.head_dim)
    in_dtype = q.dtype
    q = (_l2norm(q.astype(mx.float32)) * (attn.head_dim ** -0.5)).astype(in_dtype)
    k = _l2norm(k.astype(mx.float32)).astype(in_dtype)
    state = cache[1] if cache is not None else None
    capture.update(conv_input=conv_input, q=q, k=k, v=v, a=a, b=b_o, state_before=state)
    out, state = gated_delta_update(q, k, v, a, b_o, fg.A_log.reshape(attn.num_heads, 1), fg.dt_bias.reshape(attn.num_heads, attn.head_dim),
                                    state=state, lower_bound=fg.safe_gate_lower_bound)
    if cache is not None:
        cache[1] = state
        cache.advance(S)
    gate = attn.g_b_proj(ga_o).reshape(B, S, attn.num_heads, attn.head_dim)
    out = attn.o_norm(out, gate).reshape(B, S, -1)
    return attn.o_proj(out)


def rollback_linear(attn, cache, capture: dict, n: int) -> None:
    """Restore a linear layer's cache to the state after the first n of the S verified tokens."""
    K = attn.conv_kernel_size
    conv_input = capture['conv_input']
    cache[0] = mx.contiguous(conv_input[:, n:n + K - 1, :])          # rows [n, n+K-1) of [state(K-1) | mixed(S)]
    fg = attn.forget_gate
    if n == 0:
        cache[1] = capture['state_before']
        return
    sl = lambda x: x[:, :n]
    _, state = gated_delta_update(sl(capture['q']), sl(capture['k']), sl(capture['v']), sl(capture['a']), sl(capture['b']),
                                  fg.A_log.reshape(attn.num_heads, 1), fg.dt_bias.reshape(attn.num_heads, attn.head_dim),
                                  state=capture['state_before'], lower_bound=fg.safe_gate_lower_bound)
    cache[1] = state


def accept_prefix(drafts: List[int], targets: List[int]) -> tuple:
    """Greedy verification: (n accepted drafts, bonus token). targets[i] is the target's argmax after consuming
    draft i-1 (targets[0] follows the last committed token); the bonus is targets[n] - the target's own next token
    at the first disagreement, or after the whole block when every draft matched."""
    k = len(drafts)
    if len(targets) != k + 1:
        raise ValueError('TARGETS_LENGTH')
    n = 0
    while n < k and drafts[n] == targets[n]:
        n += 1
    return n, targets[n]


class MTPSpeculator:
    def __init__(self, target, mtp_dir: str, draft_k: int = 1, hidden_convention: str = 'post-norm'):
        from glm53_flash_mlx.load import make_config
        from mtp_module import Glm5NextMTP
        self.target = target                     # LanguageModel
        self.model = target.model                # Glm5NextModel
        self.k = int(draft_k)
        if hidden_convention not in ('post-norm', 'pre-norm'):
            raise ValueError('HIDDEN_CONVENTION')
        self.hidden_convention = hidden_convention
        cfg = json.load(open(os.path.join(mtp_dir, 'config.json')))
        config = make_config(cfg)
        self.mtp = Glm5NextMTP(config.text_config)
        q = cfg['quantization']
        nn.quantize(self.mtp, group_size=q['group_size'], bits=q['bits'],
                    class_predicate=lambda p, m: (False if not hasattr(m, 'to_quantized') else ({'group_size': q['group_size'], 'bits': q['bits']} if 'switch_mlp' in p else {'group_size': 64, 'bits': 8})))
        self.mtp.load_weights(list(mx.load(os.path.join(mtp_dir, 'model.safetensors')).items()), strict=True)
        mx.eval(self.mtp.parameters()); self.mtp.eval()
        self.mtp_config = cfg.get('mtp')
        self._mtp_cache = None; self._seed_token = None; self._seed_hidden = None; self._round_appended = 0
        self.stats = {'steps': 0, 'drafted': 0, 'accepted': 0, 'accepted_by_position': [0] * self.k}

    # --- target -----------------------------------------------------------------------------------
    def target_forward(self, inputs, cache, verify: bool = False):
        """(logits, hidden_pre_norm, captures) mirroring Glm5NextModel.__call__ / LanguageModel.__call__."""
        m = self.model
        h = m.embed_tokens(inputs)
        fa_cache = cache[m.fa_idx]
        fa_mask = create_attention_mask(h, fa_cache[0] if fa_cache else None, return_array=True)
        ssm_mask = create_ssm_mask(h, cache[m.ssm_idx])
        h = mx.contiguous(mx.broadcast_to(h[:, :, None, :], (h.shape[0], h.shape[1], m.hc_mult, h.shape[2])))
        captures = {}
        for i, (layer, c) in enumerate(zip(m.layers, cache)):
            mask = ssm_mask if layer.is_linear else fa_mask
            if verify and layer.is_linear:
                cap = {}; captures[i] = cap
                orig = layer.self_attn
                layer.self_attn = lambda x, mk, cc, _a=orig, _cap=cap: linear_attention_forward(_a, x, mk, cc, _cap)
                try:
                    h = layer(h, mask=mask, cache=c)
                finally:
                    layer.self_attn = orig
            else:
                h = layer(h, mask=mask, cache=c)
        mean = h.mean(axis=2)
        out = m.norm(mean)
        logits = self.target.model.embed_tokens.as_linear(out) if self.target.args.tie_word_embeddings else self.target.lm_head(out)
        return logits, (out if self.hidden_convention == 'post-norm' else mean), captures

    def rollback(self, cache, captures, S: int, keep: int) -> None:
        """Keep the first `keep` of the S verified tokens in every cache."""
        drop = S - keep
        for i, (layer, c) in enumerate(zip(self.model.layers, cache)):
            if layer.is_linear:
                if drop:
                    rollback_linear(layer.self_attn, c, captures[i], keep)
            else:
                if drop:
                    for kv in c:
                        kv.trim(drop)

    # --- MTP ---------------------------------------------------------------------------------------
    def _mtp_forward(self, tokens, hidden):
        cache = self._mtp_cache[0]
        emb = self.model.embed_tokens(tokens)
        mask = None if emb.shape[1] == 1 else create_attention_mask(emb, cache[0], return_array=True)
        return self.mtp(hidden, emb, mask, cache)

    def _lm_head(self, h):
        return self.target.model.embed_tokens.as_linear(h) if self.target.args.tie_word_embeddings else self.target.lm_head(h)

    def _seed(self, hidden):
        self._seed_token = mx.argmax(self._lm_head(hidden), axis=-1)
        self._seed_hidden = hidden

    def prefill(self, input_ids, hidden, bonus: int) -> None:
        self._mtp_cache = [CacheList(KVCache(), KVCache())]
        shifted = mx.concatenate([input_ids[:, 1:], mx.array([[bonus]], dtype=input_ids.dtype)], axis=1)
        out = self._mtp_forward(shifted, hidden[:, :shifted.shape[1], :])
        self._seed(out[:, -1:, :])

    def draft(self, last_token: int, hidden_last) -> List[int]:
        """k draft tokens after last_token; hidden_last = the target's hidden at last_token's position."""
        token = mx.array([[last_token]], dtype=mx.int32); prev = hidden_last
        tokens = []; self._round_appended = 0
        if self._seed_token is not None:
            token = self._seed_token; prev = self._seed_hidden; tokens.append(token); self._seed_token = None; self._seed_hidden = None
        while len(tokens) < self.k:
            prev = self._mtp_forward(token, prev); self._round_appended += 1
            token = mx.argmax(self._lm_head(prev), axis=-1); tokens.append(token)
        t = mx.concatenate(tokens, axis=1); mx.eval(t)
        return [int(x) for x in t[0].tolist()]

    def accept(self, verify_hidden, drafts: List[int], accepted: int, bonus: int) -> None:
        keep_appended = min(accepted, self._round_appended)
        trim = self._round_appended - keep_appended
        if trim > 0:
            for c in self._mtp_cache:
                for kv in c:
                    kv.trim(trim)
        toks, hids = [], []
        for i in range(keep_appended, accepted):
            toks.append(drafts[i]); hids.append(verify_hidden[:, i:i + 1, :])
        toks.append(bonus); hids.append(verify_hidden[:, accepted:accepted + 1, :])
        out = self._mtp_forward(mx.array([toks], dtype=mx.int32), mx.concatenate(hids, axis=1))
        self._seed(out[:, -1:, :])
        self._round_appended = 0

    # --- loop --------------------------------------------------------------------------------------
    def generate(self, prompt_ids: List[int], max_tokens: int, eos: set, prefill_step_size: int = 4096):
        """Greedy speculative generation. Yields (token, accepted_in_step) per generated token; records stats."""
        cache = self.target.make_cache()
        ids = mx.array([prompt_ids], dtype=mx.int32)
        if ids.shape[1] > prefill_step_size:
            raise ValueError(f'PROMPT_TOO_LONG_FOR_ONE_CHUNK: {ids.shape[1]} > {prefill_step_size} (the MTP prefill needs the hidden of every prompt position)')
        logits, hidden, _ = self.target_forward(ids, cache)   # one chunk: the MTP prefill needs every position's hidden
        bonus = int(mx.argmax(logits[:, -1, :], axis=-1).item())
        self.prefill(ids, hidden, bonus)
        produced = [bonus]; last = bonus; hidden_last = hidden[:, -1:, :]
        yield bonus, 0
        if bonus in eos:
            return
        while len(produced) < max_tokens:
            drafts = self.draft(last, hidden_last)
            step_ids = mx.array([[last] + drafts], dtype=mx.int32)
            logits, hidden, caps = self.target_forward(step_ids, cache, verify=True)
            targets = mx.argmax(logits[0], axis=-1); mx.eval(targets); targets = [int(x) for x in targets.tolist()]
            n, new_bonus = accept_prefix(drafts, targets)
            self.rollback(cache, caps, self.k + 1, n + 1)
            self.stats['steps'] += 1; self.stats['drafted'] += self.k; self.stats['accepted'] += n
            for i in range(n):
                self.stats['accepted_by_position'][i] += 1
            self.accept(hidden, drafts, n, new_bonus)
            stop = False
            for t in drafts[:n] + [new_bonus]:
                produced.append(t); yield t, n
                if t in eos or len(produced) >= max_tokens:
                    stop = True; break
            if stop:
                return
            last = new_bonus; hidden_last = hidden[:, n:n + 1, :]

